"""Testes do walk-forward — incluindo o teste automatizado contra data leakage.

A Fase 4 da especificação pede, com essas palavras, um "teste automatizado
contra data leakage". Ele está aqui em duas formas, e as duas importam:

1. :func:`test_nenhuma_previsao_viu_o_proprio_jogo` — o caminho honesto: cada
   previsão é conferida contra a data até onde o treino foi;
2. :func:`test_modelo_trapaceiro_e_pego` — a **sabotagem**: um modelo que
   ignora o corte de data de propósito tem que ser pego. Um teste que só
   verifica o código certo não prova que a trava funciona; ele prova que o
   código certo passa. Só a sabotagem prova que o errado é reprovado.

O resto do arquivo cobre a aritmética das comparações, que é onde se inventa
resultado sem perceber: medir dois modelos em conjuntos diferentes de jogos e
pôr os dois na mesma tabela.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futebol.avaliacao import validacao as V
from futebol.modelos import base
from futebol.modelos.baseline import Baseline
from futebol.modelos.dixon_coles import DixonColes
from futebol.modelos.poisson import Poisson
from simulacao import simular_liga


def _tabela(voltas: int = 8, liga: str = "E0", seed: int = 42) -> pd.DataFrame:
    """Uma liga simulada com todas as colunas que a validação usa."""
    jogos = simular_liga(voltas=voltas, liga=liga, seed=seed)
    diferenca = jogos["gols_mandante"] - jogos["gols_visitante"]
    return jogos.assign(
        grupo="grupo1",
        temporada="2019/20",
        resultado=np.where(diferenca > 0, "H", np.where(diferenca == 0, "D", "A")),
    )


def _com_odds(jogos: pd.DataFrame, grupo: str = "grupo1") -> pd.DataFrame:
    """Acrescenta odds de fechamento plausíveis, com margem de 5%."""
    n = len(jogos)
    return jogos.assign(
        grupo=grupo,
        odd_fech_H=np.full(n, 2.00),
        odd_fech_D=np.full(n, 3.50),
        odd_fech_A=np.full(n, 4.00),
        odd_fech_over25=np.full(n, 1.90),
        odd_fech_under25=np.full(n, 1.95),
        odd_pre_H=np.where(np.arange(n) % 2 == 0, 2.05, np.nan),
        odd_pre_D=np.where(np.arange(n) % 2 == 0, 3.40, np.nan),
        odd_pre_A=np.where(np.arange(n) % 2 == 0, 4.10, np.nan),
        odd_pre_over25=np.full(n, 1.88),
        odd_pre_under25=np.full(n, 1.97),
    )


#: Metade da janela de cada tabela de teste, usada como início da avaliação.
def _meio(jogos: pd.DataFrame) -> pd.Timestamp:
    return jogos["data"].iloc[len(jogos) // 2]


# ----------------------------------------------------------------------------
# As rodadas
# ----------------------------------------------------------------------------
def test_rodadas_entrega_a_liga_inteira_e_so_as_datas_da_janela() -> None:
    """O histórico vem completo; a janela limita apenas o que é avaliado."""
    jogos = _tabela()
    inicio = _meio(jogos)
    (liga, do_liga, datas), = list(V.rodadas(jogos, inicio=inicio))

    assert liga == "E0"
    assert len(do_liga) == len(jogos), "o treino precisa do histórico inteiro"
    assert min(datas) >= inicio
    assert max(datas) == jogos["data"].max()


def test_rodadas_respeita_o_fim_exclusivo() -> None:
    jogos = _tabela()
    fim = jogos["data"].iloc[10]
    (_, _, datas), = list(V.rodadas(jogos, fim=fim))
    assert max(datas) < fim


def test_liga_sem_data_na_janela_nao_aparece() -> None:
    jogos = pd.concat([_tabela(liga="E0"), _tabela(liga="SP1", seed=7)])
    # A SP1 recebe datas deslocadas para fora da janela.
    jogos.loc[jogos["liga"] == "SP1", "data"] -= pd.Timedelta(days=5000)
    ligas = [liga for liga, _, _ in V.rodadas(jogos, inicio="2019-08-01")]
    assert ligas == ["E0"]


# ----------------------------------------------------------------------------
# O teste automatizado contra data leakage (regra 6)
# ----------------------------------------------------------------------------
def test_nenhuma_previsao_viu_o_proprio_jogo() -> None:
    """Para cada jogo previsto, o treino terminou antes dele."""
    jogos = _tabela()
    resultado = V.walk_forward(
        jogos,
        lambda: DixonColes(max_gols=8),
        inicio=_meio(jogos),
        minimo_de_treino=20,
    )
    previsoes = resultado.previsoes

    assert len(previsoes) > 0
    assert (previsoes["treino_ate"] < previsoes["data"]).all()
    V.conferir_sem_vazamento(previsoes)


class ModeloTrapaceiro(base.Modelo):
    """Um modelo que ignora o corte de data — de propósito.

    Ele existe só para provar que a trava pega quem trapaceia. Se este teste
    passar a falhar, a trava parou de funcionar.
    """

    nome = "trapaceiro"

    def treinar(self, jogos: pd.DataFrame, ate_data=None) -> base.Modelo:
        # A trapaça: ignora o `ate_data` e treina com a tabela inteira.
        self._treinado = True
        self.ultima_data_de_treino = pd.Timestamp(jogos["data"].max())
        return self

    def _ajustar(self, jogos: pd.DataFrame) -> None:  # pragma: no cover
        pass

    def matriz_de_placares(self, jogo: base.Jogo) -> np.ndarray:
        return base.normalizar_matriz(np.ones((4, 4)))


def test_modelo_trapaceiro_e_pego() -> None:
    """A sabotagem: treinar com a tabela inteira tem que ser detectado."""
    jogos = _tabela()
    resultado = V.walk_forward(
        jogos, ModeloTrapaceiro, inicio=_meio(jogos), minimo_de_treino=20
    )

    with pytest.raises(AssertionError, match="Vazamento de futuro"):
        V.conferir_sem_vazamento(resultado.previsoes)


def test_conferencia_aceita_previsao_honesta_e_recusa_a_de_hoje() -> None:
    """O corte é estrito: treino até a própria data do jogo já é vazamento."""
    honesta = pd.DataFrame(
        {
            "treino_ate": pd.to_datetime(["2024-01-01"]),
            "data": pd.to_datetime(["2024-01-02"]),
            "liga": ["E0"],
        }
    )
    V.conferir_sem_vazamento(honesta)

    do_mesmo_dia = honesta.assign(treino_ate=pd.to_datetime(["2024-01-02"]))
    with pytest.raises(AssertionError):
        V.conferir_sem_vazamento(do_mesmo_dia)


# ----------------------------------------------------------------------------
# O walk-forward
# ----------------------------------------------------------------------------
def test_todo_jogo_da_janela_e_previsto_uma_vez() -> None:
    jogos = _tabela()
    inicio = _meio(jogos)
    resultado = V.walk_forward(
        jogos, lambda: Baseline(max_gols=8), inicio=inicio, minimo_de_treino=20
    )

    da_janela = jogos.loc[jogos["data"] >= inicio]
    assert len(resultado.previsoes) == len(da_janela)
    assert set(resultado.previsoes.index) == set(da_janela.index)


def test_cada_rodada_treina_um_modelo_novo() -> None:
    """Reaproveitar o objeto treinado deixaria a rodada anterior influenciando."""
    jogos = _tabela()
    criados: list[int] = []

    def construir():
        criados.append(1)
        return Baseline(max_gols=8)

    resultado = V.walk_forward(
        jogos, construir, inicio=_meio(jogos), minimo_de_treino=20
    )
    assert len(criados) == resultado.ajustes > 1


def test_rodada_com_historico_curto_e_pulada_e_contada() -> None:
    """Pular em silêncio seria pior: a contagem entra no relatório."""
    jogos = _tabela()
    resultado = V.walk_forward(
        jogos, lambda: Baseline(max_gols=8), minimo_de_treino=100
    )

    assert resultado.rodadas_puladas > 0
    assert resultado.jogos_pulados > 0
    assert len(resultado.previsoes) + resultado.jogos_pulados == len(jogos)
    assert "histórico curto" in resultado.resumo()


def test_escopo_liga_e_escopo_tudo_dao_o_mesmo_resultado() -> None:
    """Invariante que sustenta a escolha de desempenho do módulo.

    Os modelos do projeto ajustam cada competição separadamente, então treinar
    com a tabela inteira ou só com a liga da vez tem de dar exatamente a mesma
    previsão. É essa igualdade que autoriza o caminho rápido.
    """
    jogos = pd.concat([_tabela(liga="E0"), _tabela(liga="SP1", seed=7)])
    inicio = jogos["data"].iloc[len(jogos) // 2]

    por_liga = V.walk_forward(
        jogos, lambda: Poisson(max_gols=8), inicio=inicio, minimo_de_treino=20
    )
    com_tudo = V.walk_forward(
        jogos,
        lambda: Poisson(max_gols=8),
        inicio=inicio,
        minimo_de_treino=20,
        escopo="tudo",
    )

    assert np.allclose(
        por_liga.previsoes[list(V.CHAVES_1X2)].to_numpy(),
        com_tudo.previsoes[list(V.CHAVES_1X2)].to_numpy(),
        atol=1e-9,
    )


def test_escopo_invalido_e_recusado() -> None:
    with pytest.raises(ValueError, match="escopo"):
        V.walk_forward(_tabela(), lambda: Baseline(max_gols=8), escopo="metade")


def test_janela_sem_rodada_alguma_e_erro() -> None:
    jogos = _tabela()
    with pytest.raises(ValueError, match="Nenhuma rodada"):
        V.walk_forward(
            jogos,
            lambda: Baseline(max_gols=8),
            inicio=jogos["data"].max() + pd.Timedelta(days=10),
            fim=jogos["data"].max() + pd.Timedelta(days=40),
        )


def test_as_ligas_sao_contadas() -> None:
    jogos = pd.concat([_tabela(liga="E0"), _tabela(liga="SP1", seed=7)])
    resultado = V.walk_forward(
        jogos,
        lambda: Baseline(max_gols=8),
        inicio=jogos["data"].iloc[len(jogos) // 2],
        minimo_de_treino=20,
    )
    assert resultado.ligas == 2


# ----------------------------------------------------------------------------
# O mercado na mesma forma
# ----------------------------------------------------------------------------
def test_mercado_vira_previsao_com_as_mesmas_colunas() -> None:
    jogos = _com_odds(_tabela(voltas=2))
    previsoes = V.previsoes_do_mercado(jogos)

    assert len(previsoes) == len(jogos)
    for chave in V.CHAVES_1X2:
        assert chave in previsoes.columns
    # Sem margem, as três somam 1 — é o que permite comparar com o modelo.
    assert np.allclose(previsoes[list(V.CHAVES_1X2)].sum(axis=1), 1.0)
    assert previsoes["over25"].notna().all()


def test_mercado_nao_tem_ambos_marcam() -> None:
    """A fonte não traz esse mercado; inventá-lo seria pior que deixá-lo vazio."""
    previsoes = V.previsoes_do_mercado(_com_odds(_tabela(voltas=2)))
    assert previsoes["ambos_marcam"].isna().all()


def test_jogo_sem_odd_completa_fica_fora_do_mercado() -> None:
    jogos = _com_odds(_tabela(voltas=2))
    jogos.loc[jogos.index[:5], "odd_fech_A"] = np.nan
    previsoes = V.previsoes_do_mercado(jogos)
    assert len(previsoes) == len(jogos) - 5


def test_grupo_2_nao_tem_mercado_pre_jogo() -> None:
    """Regra 12: sem odd pré-jogo não existe aposta a simular."""
    jogos = _com_odds(_tabela(voltas=2), grupo="grupo2")
    for coluna in ("odd_pre_H", "odd_pre_D", "odd_pre_A"):
        jogos[coluna] = np.nan

    previsoes = V.previsoes_do_mercado(jogos, momento="pre")
    assert len(previsoes) == 0


def test_tabela_sem_coluna_de_odd_e_recusada() -> None:
    with pytest.raises(ValueError, match="odd"):
        V.previsoes_do_mercado(_tabela(voltas=1))


# ----------------------------------------------------------------------------
# Medir e comparar
# ----------------------------------------------------------------------------
def _previsoes_de_mentira(probabilidade_certa: float, n: int = 100) -> pd.DataFrame:
    """``n`` jogos em que o mandante ganhou e o modelo deu ``p`` para isso."""
    resto = (1 - probabilidade_certa) / 2
    return pd.DataFrame(
        {
            "H": [probabilidade_certa] * n,
            "D": [resto] * n,
            "A": [resto] * n,
            "over25": [0.5] * n,
            "under25": [0.5] * n,
            "observado": [0] * n,
            "observado_ou": [0] * n,
            "liga": ["E0"] * n,
        }
    )


def test_medir_confere_na_mao() -> None:
    medida = V.medir(_previsoes_de_mentira(0.5), "teste")
    assert medida.log_loss == pytest.approx(-np.log(0.5))
    assert medida.acuracia == pytest.approx(1.0), "o mandante ganhou sempre"
    assert medida.n == 100


def test_acuracia_nao_premia_confianca_certa() -> None:
    """Duas previsões com acurácia igual e log loss muito diferente."""
    confiante = V.medir(_previsoes_de_mentira(0.90), "confiante")
    timida = V.medir(_previsoes_de_mentira(0.40), "timida")

    assert confiante.acuracia == timida.acuracia == pytest.approx(1.0)
    assert confiante.log_loss < timida.log_loss
    # É exatamente por isso que a escolha de modelo é por log loss (regra 9).


def test_comparacao_emparelhada_e_a_diferenca_das_perdas() -> None:
    pior = _previsoes_de_mentira(0.30)
    melhor = _previsoes_de_mentira(0.60)
    diferenca = V.comparar(pior, melhor)

    assert diferenca.media == pytest.approx(-np.log(0.30) + np.log(0.60))
    assert diferenca.erro_padrao == pytest.approx(0.0)
    assert diferenca.significativa


def test_comparacao_com_conjuntos_diferentes_e_erro() -> None:
    with pytest.raises(ValueError, match="mesmos jogos"):
        V.comparar(_previsoes_de_mentira(0.3, n=10), _previsoes_de_mentira(0.6, n=20))


def test_efeito_minimo_detectavel_e_o_criterio_da_regra_10() -> None:
    diferenca = V.Diferenca(media=0.0005, erro_padrao=0.0004, n=11000)
    assert diferenca.efeito_minimo_detectavel == pytest.approx(0.00112)
    assert not diferenca.significativa
    texto = diferenca.como_texto()
    assert "menor efeito detectável" in texto
    assert "indistinguível de zero" in texto


def test_mesmos_jogos_e_a_intersecao() -> None:
    um = _previsoes_de_mentira(0.5, n=10)
    outro = _previsoes_de_mentira(0.5, n=10).iloc[3:8]
    recortados = V.mesmos_jogos(um, outro)
    assert all(len(r) == 5 for r in recortados)


def test_medir_nos_mesmos_jogos_alinha_antes_de_medir() -> None:
    """O erro clássico: medir o modelo em 11 mil jogos e o mercado em 8 mil."""
    modelo = _previsoes_de_mentira(0.50, n=10)
    do_mercado = _previsoes_de_mentira(0.60, n=10).iloc[2:]

    medidas, alinhados = V.medir_nos_mesmos_jogos(
        {"modelo": modelo, "mercado": do_mercado}
    )
    assert [m.n for m in medidas] == [8, 8]
    assert all(len(p) == 8 for p in alinhados.values())


def test_por_liga_tem_uma_linha_por_competicao() -> None:
    um = _previsoes_de_mentira(0.5, n=120)
    um.loc[um.index[:60], "liga"] = "SP1"
    outro = um.assign(H=0.6, D=0.2, A=0.2)

    tabela = V.por_liga({"modelo": um, "mercado": outro}, minimo_de_jogos=50)
    assert sorted(tabela["liga"]) == ["E0", "SP1"]
    assert (tabela["mercado"] < tabela["modelo"]).all()


def test_por_liga_corta_liga_pequena() -> None:
    um = _previsoes_de_mentira(0.5, n=120)
    um.loc[um.index[:10], "liga"] = "SC3"
    tabela = V.por_liga({"modelo": um}, minimo_de_jogos=50)
    assert list(tabela["liga"]) == ["E0"]
