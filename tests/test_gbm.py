"""O LightGBM: contrato, marcos de retreino e um cache que não pode confundir.

Dois testes aqui valem mais que os outros:

- ``test_o_walk_forward_nao_acusa_vazamento`` põe o GBM na mesma máquina de
  avaliação da Fase 4 e deixa a trava oficial julgá-lo. É o que garante que o
  retreino a cada 30 dias não abriu uma porta;
- ``test_fabricas_diferentes_nao_compartilham_cache`` é a regressão direta do
  defeito que a Fase 4 destravou: um ajuste guardado sob uma chave que muda de
  significado quando a configuração muda. Aqui o cache é de instância
  justamente para esse dia não existir, e o teste prova que não existe.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futebol.avaliacao import validacao
from futebol.config import carregar_config
from futebol.features import construtor
from futebol.modelos import base
from futebol.modelos.gbm import ErroDeGBM, FabricaGBM


def _liga(dias: int = 1200, seed: int = 2) -> pd.DataFrame:
    """Uma liga de 12 times, um jogo por dia, com forças de verdade."""
    gerador = np.random.default_rng(seed)
    times = [f"ENG:T{i}" for i in range(12)]
    forca = dict(zip(times, np.linspace(0.45, -0.45, len(times)), strict=True))
    linhas = []
    for dia in range(dias):
        casa, fora = gerador.choice(times, size=2, replace=False)
        lam = np.exp(0.2 + forca[str(casa)] - forca[str(fora)] + 0.25)
        mu = np.exp(0.2 + forca[str(fora)] - forca[str(casa)])
        linhas.append(
            (
                pd.Timestamp("2018-01-01") + pd.Timedelta(days=dia),
                str(casa),
                str(fora),
                float(gerador.poisson(lam)),
                float(gerador.poisson(mu)),
            )
        )
    jogos = pd.DataFrame(
        linhas, columns=["data", "mandante", "visitante", "gols_mandante", "gols_visitante"]
    )
    jogos["liga"] = "E0"
    jogos["temporada"] = "2023/24"
    jogos["resultado"] = np.where(
        jogos["gols_mandante"] > jogos["gols_visitante"],
        "H",
        np.where(jogos["gols_mandante"] == jogos["gols_visitante"], "D", "A"),
    )
    return jogos


@pytest.fixture(scope="module")
def bancada():
    """Jogos, features e uma fábrica — caro de montar, reaproveitado no arquivo."""
    cfg = carregar_config()
    jogos = _liga()
    features = construtor.construir(jogos, cfg=cfg)
    return cfg, jogos, features


#: Um corte de treino dentro da simulação, com jogos depois dele para prever.
#: A simulação começa em 2018-01-01 e dura 1.200 dias, ou seja, vai até
#: 2021-04-14 — pedir uma previsão depois disso não mediria nada.
CORTE = pd.Timestamp("2021-01-15")


def _fabrica(bancada, **extras) -> FabricaGBM:
    cfg, jogos, features = bancada
    parametros = {"minimo_de_treino": 200, "n_estimators": 40, "chaves": jogos}
    parametros.update(extras)
    return FabricaGBM(features, cfg=cfg, **parametros)


# ----------------------------------------------------------------------------
# Vazamento
# ----------------------------------------------------------------------------
def test_o_treino_para_antes_do_marco_e_o_marco_antes_da_previsao(bancada) -> None:
    _, jogos, _ = bancada
    fabrica = _fabrica(bancada)
    corte = CORTE

    modelo = fabrica.novo().treinar(jogos, ate_data=corte)
    marco = fabrica.marco_de(corte)

    assert marco <= corte
    assert modelo.ultima_data_de_treino < marco


def test_a_trilha_de_auditoria_diz_o_treino_real_e_nao_o_corte_pedido(bancada) -> None:
    """Declarar o corte pedido seria declarar um treino que não houve."""
    _, jogos, _ = bancada
    fabrica = _fabrica(bancada)
    # Um corte bem no fim do intervalo de um marco: o ajuste vem de semanas atrás.
    corte = fabrica.marco_de(CORTE) + pd.Timedelta(days=fabrica.passo_dias - 1)

    modelo = fabrica.novo().treinar(jogos, ate_data=corte)

    assert modelo.ultima_data_de_treino < fabrica.marco_de(corte)
    assert modelo.ultima_data_de_treino < corte - pd.Timedelta(days=10)


def test_o_walk_forward_nao_acusa_vazamento(bancada) -> None:
    """A trava oficial da Fase 4 julgando o modelo novo, sem nenhuma exceção."""
    _, jogos, _ = bancada
    fabrica = _fabrica(bancada)

    resultado = validacao.walk_forward(
        jogos,
        fabrica.novo,
        inicio="2020-06-01",
        fim="2020-12-01",
        minimo_de_treino=200,
        escopo="tudo",
    )
    validacao.conferir_sem_vazamento(resultado.previsoes)

    assert len(resultado.previsoes) > 0
    assert (resultado.previsoes["treino_ate"] < resultado.previsoes["data"]).all()


# ----------------------------------------------------------------------------
# Os marcos e o cache
# ----------------------------------------------------------------------------
def test_datas_dentro_do_mesmo_marco_reaproveitam_o_ajuste(bancada) -> None:
    _, jogos, _ = bancada
    fabrica = _fabrica(bancada)

    marco = fabrica.marco_de(CORTE)
    um = fabrica.novo().treinar(jogos, ate_data=marco)
    outro = fabrica.novo().treinar(
        jogos, ate_data=marco + pd.Timedelta(days=fabrica.passo_dias - 1)
    )

    assert um._ajuste is outro._ajuste
    assert len(fabrica._ajustes) == 1


def test_marcos_diferentes_treinam_de_novo(bancada) -> None:
    _, jogos, _ = bancada
    fabrica = _fabrica(bancada)

    marco = fabrica.marco_de(CORTE)
    um = fabrica.novo().treinar(jogos, ate_data=marco)
    outro = fabrica.novo().treinar(
        jogos, ate_data=marco + pd.Timedelta(days=fabrica.passo_dias)
    )

    assert um._ajuste is not outro._ajuste
    assert len(fabrica._ajustes) == 2


def test_a_ancora_dos_marcos_nao_depende_da_tabela(bancada) -> None:
    """Dois recortes diferentes têm de cair nos mesmos marcos.

    Se os marcos fossem contados a partir do primeiro jogo da tabela, mudar a
    janela mudaria silenciosamente em que dias o modelo é retreinado — e duas
    medições que se comparam teriam regimes de retreino diferentes.
    """
    cfg, jogos, features = bancada
    inteira = FabricaGBM(features, cfg=cfg, minimo_de_treino=200)
    recorte = jogos.loc[jogos["data"] >= "2019-01-01"]
    parcial = FabricaGBM(
        features.reindex(recorte.index), cfg=cfg, minimo_de_treino=200
    )
    assert inteira.marco_de(CORTE) == parcial.marco_de(CORTE)


def test_fabricas_diferentes_nao_compartilham_cache(bancada) -> None:
    """Regressão do defeito da Fase 4: cache que muda de significado em silêncio.

    Duas configurações diferentes são duas fábricas, cada uma com o próprio
    cache. Não existe chave global que possa passar a apontar para outra coisa
    quando um parâmetro muda.
    """
    _, jogos, _ = bancada
    rasa = _fabrica(bancada, num_leaves=4)
    funda = _fabrica(bancada, num_leaves=31)

    de_uma = rasa.novo().treinar(jogos, ate_data=CORTE)
    de_outra = funda.novo().treinar(jogos, ate_data=CORTE)

    assert de_uma._ajuste is not de_outra._ajuste
    assert rasa.parametros != funda.parametros
    entradas = rasa.features.loc[jogos.index[-5:], rasa.colunas]
    assert not np.allclose(de_uma.medias(entradas)[0], de_outra.medias(entradas)[0])


def test_os_parametros_identificam_a_configuracao(bancada) -> None:
    """"gbm" não identifica nada; os hiperparâmetros identificam (regra 11)."""
    fabrica = _fabrica(bancada)
    parametros = fabrica.parametros

    assert parametros["modelo"] == "gbm"
    assert parametros["passo_retreino"] == 30
    assert parametros["n_estimators"] == 40
    assert "verbose" not in parametros


# ----------------------------------------------------------------------------
# O contrato de modelo
# ----------------------------------------------------------------------------
def test_as_previsoes_obedecem_ao_contrato(bancada) -> None:
    _, jogos, _ = bancada
    fabrica = _fabrica(bancada)
    modelo = fabrica.novo().treinar(jogos, ate_data=CORTE)
    alvo = jogos.loc[jogos["data"] >= CORTE].head(20)

    previsoes = modelo.prever_muitos(alvo)

    assert list(previsoes.columns) == list(base.CHAVES_PREVISAO)
    assert list(previsoes.index) == list(alvo.index)
    for grupo in base.GRUPOS_COMPLEMENTARES:
        assert np.allclose(previsoes[list(grupo)].sum(axis=1), 1.0)
    assert (previsoes.to_numpy() >= 0).all()


def test_prever_um_jogo_concorda_com_prever_muitos(bancada) -> None:
    """Os dois caminhos saem da mesma matriz; divergir seria incoerência."""
    _, jogos, _ = bancada
    fabrica = _fabrica(bancada)
    modelo = fabrica.novo().treinar(jogos, ate_data=CORTE)
    alvo = jogos.loc[jogos["data"] >= CORTE].head(1)

    em_lote = modelo.prever_muitos(alvo).iloc[0]
    avulso = modelo.prever(base.Jogo.de_mapa(alvo.iloc[0]))

    for chave in base.CHAVES_PREVISAO:
        assert avulso[chave] == pytest.approx(em_lote[chave])


def test_o_modelo_aprende_quem_e_mais_forte(bancada) -> None:
    """Sanidade: quanto maior a vantagem de Elo do mandante, mais favorito ele é.

    A pergunta e o teste sao o mesmo: o GBM extraiu sinal das features, ou esta
    devolvendo a media da liga para todo mundo? A correlacao entre a diferenca
    de Elo e a probabilidade prevista de vitoria do mandante responde isso sem
    depender de um confronto especifico ter sido sorteado pela simulacao.
    """
    _, jogos, features = bancada
    fabrica = _fabrica(bancada)
    modelo = fabrica.novo().treinar(jogos, ate_data=CORTE)
    adiante = jogos.loc[jogos["data"] >= CORTE]
    assert len(adiante) > 50, "a simulacao nao deixou jogos para prever"

    previstas = modelo.prever_muitos(adiante)["H"]
    elo = features.loc[adiante.index, "elo_diferenca"]

    assert previstas.corr(elo) > 0.5
    assert previstas.std() > 0.02, "previsoes quase constantes: o GBM nao aprendeu"


# ----------------------------------------------------------------------------
# Erros
# ----------------------------------------------------------------------------
def test_jogo_sem_features_e_erro_claro(bancada) -> None:
    _, jogos, features = bancada
    cfg = carregar_config()
    fabrica = FabricaGBM(
        features.iloc[:-5], cfg=cfg, minimo_de_treino=200, n_estimators=20
    )
    modelo = fabrica.novo().treinar(jogos, ate_data=CORTE)

    with pytest.raises(ErroDeGBM, match="não têm features"):
        modelo.prever_muitos(jogos.tail(5))


def test_treino_insuficiente_e_erro_claro(bancada) -> None:
    _, jogos, _ = bancada
    fabrica = _fabrica(bancada, minimo_de_treino=10_000)

    with pytest.raises(ErroDeGBM, match="mínimo"):
        fabrica.novo().treinar(jogos, ate_data=CORTE)


def test_features_vazias_e_erro_claro() -> None:
    with pytest.raises(ErroDeGBM, match="vazia"):
        FabricaGBM(pd.DataFrame())


def test_prever_sem_treinar_e_erro_claro(bancada) -> None:
    _, jogos, _ = bancada
    fabrica = _fabrica(bancada)

    with pytest.raises(base.ErroDeModelo, match="não foi treinado"):
        fabrica.novo().prever_muitos(jogos.head(3))


def test_sem_tabela_de_chaves_o_jogo_avulso_explica_o_que_falta(bancada) -> None:
    cfg, jogos, features = bancada
    fabrica = FabricaGBM(features, cfg=cfg, minimo_de_treino=200, n_estimators=20)
    modelo = fabrica.novo().treinar(jogos, ate_data=CORTE)

    with pytest.raises(ErroDeGBM, match="prever em lote"):
        modelo.prever(base.Jogo.de_mapa(jogos.iloc[-1]))
