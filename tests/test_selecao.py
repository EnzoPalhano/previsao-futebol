"""Testes da escolha oficial do modelo (regras 9 e 11).

Duas coisas precisam ser verdade aqui, e nenhuma delas é sobre estatística:

1. **a escolha é por log loss**, e não pela ordem em que os candidatos foram
   escritos, nem pelo Brier, nem pela acurácia;
2. **a lista de candidatos é contável e estável.** A regra 11 manda registrar
   quantas configurações foram testadas; se a lista mudar de tamanho sem
   ninguém notar, o pré-registro vira ficção.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from futebol.avaliacao import selecao, validacao
from futebol.config import carregar_config
from futebol.modelos.baseline import Baseline
from simulacao import simular_liga


@pytest.fixture
def cfg_em_pasta_temporaria(tmp_path):
    """A configuração do projeto, com a raiz apontando para uma pasta de teste.

    Assim o cache de previsões é escrito e lido numa pasta descartável, sem
    encostar em ``data/processed`` do projeto.
    """
    return dataclasses.replace(carregar_config(), raiz=tmp_path)


def _tabela(voltas: int = 8) -> pd.DataFrame:
    jogos = simular_liga(voltas=voltas)
    diferenca = jogos["gols_mandante"] - jogos["gols_visitante"]
    return jogos.assign(
        grupo="grupo1",
        temporada="2019/20",
        resultado=np.where(diferenca > 0, "H", np.where(diferenca == 0, "D", "A")),
    )


# ----------------------------------------------------------------------------
# A lista de candidatos (regra 11)
# ----------------------------------------------------------------------------
def test_sao_treze_configuracoes_distintas() -> None:
    """O número que vai para o pré-registro sai daqui, não da memória."""
    cfg = carregar_config()
    lista = selecao.candidatos(cfg, _tabela(), inicio="2019-09-01")

    assert len(lista) == 13
    assert len({c.nome for c in lista}) == 13, "nome repetido faria o cache colidir"


def test_o_padrao_da_grade_nao_e_contado_duas_vezes() -> None:
    """O ``xi`` e o ``m`` do ponto de partida já estão no candidato 'dixon-coles'."""
    cfg = carregar_config()
    nomes = {c.nome for c in selecao.candidatos(cfg, _tabela(), inicio="2019-09-01")}

    assert f"dc-xi-{selecao.XI_DA_GRADE}" not in nomes
    assert f"dc-m-{selecao.M_DA_GRADE:.0f}" not in nomes


def test_a_grade_nao_muda_quando_o_config_muda() -> None:
    """A grade dos 13 candidatos é um fato histórico: não segue o ``config.yaml``.

    Regressão da Fase 4 (regra 11). A fase termina gravando a escolha no config.
    Enquanto a grade era montada a partir de lá, rodar a validação de novo depois
    disso montava uma grade **diferente** — o encolhimento varrido em torno do
    ``xi`` novo, e o nome ``dixon-coles`` apontando para outra configuração.
    Seriam configurações novas disputando, com a contagem da regra 11 subindo sem
    ninguém ver.
    """
    cfg = carregar_config()
    jogos = _tabela()
    antes = selecao.candidatos(cfg, jogos, inicio="2019-09-01")

    modelos = cfg.secao("modelos")
    modelos["dixon_coles"]["xi"] = 0.03
    modelos["shrinkage"]["jogos_equivalentes"] = 99
    depois = selecao.candidatos(cfg, jogos, inicio="2019-09-01")

    assert [c.nome for c in antes] == [c.nome for c in depois]
    assert [c.parametros for c in antes] == [c.parametros for c in depois]


def test_todo_candidato_diz_quais_sao_os_parametros_dele() -> None:
    """"dixon-coles" não identifica uma configuração; xi e m identificam."""
    lista = selecao.candidatos(carregar_config(), _tabela(), inicio="2019-09-01")
    for candidato in lista:
        assert candidato.parametros, f"{candidato.nome} sem parâmetros registrados"
        assert candidato.descricao


def test_o_fator_casa_unico_sai_so_do_passado() -> None:
    """Regra 6: o número congelado não pode ter visto a janela de avaliação."""
    jogos = _tabela()
    corte = jogos["data"].iloc[len(jogos) // 2]
    lista = selecao.candidatos(carregar_config(), jogos, inicio=corte)

    candidato = next(c for c in lista if c.nome == "dc-casa-unica")
    from futebol.modelos.base import jogos_ate
    from futebol.modelos.poisson import fator_casa_global

    esperado = fator_casa_global(jogos_ate(jogos, corte))
    assert candidato.parametros["valor_fator_casa"] == pytest.approx(
        esperado, abs=1e-6
    )


# ----------------------------------------------------------------------------
# O cache
# ----------------------------------------------------------------------------
def _candidato_fake(nome: str, **parametros: object) -> selecao.Candidato:
    return selecao.Candidato(
        nome=nome,
        descricao="para o teste",
        construir=lambda: Baseline(max_gols=6),
        parametros=parametros,
    )


def test_o_cache_separa_janelas_diferentes(cfg_em_pasta_temporaria) -> None:
    """Previsões de janelas diferentes não podem cair no mesmo arquivo."""
    cfg = cfg_em_pasta_temporaria
    candidato = _candidato_fake("dixon-coles", modelo="dixon-coles", xi=0.003)
    um = selecao.caminho_do_cache(cfg, candidato, "2021-07-01", "2024-06-03")
    outro = selecao.caminho_do_cache(cfg, candidato, "2022-07-01", "2024-06-03")
    assert um != outro
    assert um.parent == selecao.pasta_do_cache(cfg)


def test_o_cache_separa_parametros_diferentes_com_o_mesmo_nome(
    cfg_em_pasta_temporaria,
) -> None:
    """O nome ``dixon-coles`` muda de significado quando o ``config.yaml`` muda.

    Regressão da Fase 4: o candidato chamado ``dixon-coles`` é *o que tiver o
    ``xi`` do config*. Com o cache guardado só pelo nome, gravar a escolha da
    fase (``xi`` 0,0018 → 0,003) faria a execução seguinte ler as previsões
    antigas achando que eram do valor novo — sem erro nenhum na tela.
    """
    cfg = cfg_em_pasta_temporaria
    antes = _candidato_fake("dixon-coles", modelo="dixon-coles", xi=0.0018, m=6.0)
    depois = _candidato_fake("dixon-coles", modelo="dixon-coles", xi=0.003, m=6.0)
    janela = ("2021-07-01", "2024-06-03")

    assert selecao.caminho_do_cache(cfg, antes, *janela) != selecao.caminho_do_cache(
        cfg, depois, *janela
    )


def test_mesmos_parametros_com_nomes_diferentes_reaproveitam_o_cache(
    cfg_em_pasta_temporaria,
) -> None:
    """``dc-xi-0.003`` e ``dixon-coles`` com xi=0,003 são a mesma medição.

    O contrário do teste acima: se a assinatura fosse o nome, trocar o config
    obrigaria a remedir horas de walk-forward que já estavam medidas.
    """
    cfg = cfg_em_pasta_temporaria
    parametros = {"modelo": "dixon-coles", "xi": 0.003, "m": 6.0}
    janela = ("2021-07-01", "2024-06-03")
    um = selecao.caminho_do_cache(cfg, _candidato_fake("dixon-coles", **parametros), *janela)
    outro = selecao.caminho_do_cache(cfg, _candidato_fake("dc-xi-0.003", **parametros), *janela)

    assert selecao.marca_dos_parametros(parametros) in um.name
    assert um.name.split("__")[-1] == outro.name.split("__")[-1]


def test_segunda_rodada_le_do_cache(cfg_em_pasta_temporaria) -> None:
    cfg = cfg_em_pasta_temporaria
    jogos = _tabela()
    candidato = selecao.Candidato(
        nome="baseline-teste",
        descricao="para o teste",
        construir=lambda: Baseline(max_gols=6),
    )
    inicio = jogos["data"].iloc[len(jogos) // 2]

    avisos: list[str] = []
    primeira = selecao.rodar_candidato(
        jogos, candidato, cfg, inicio=inicio, aviso=avisos.append
    )
    segunda = selecao.rodar_candidato(
        jogos, candidato, cfg, inicio=inicio, aviso=avisos.append
    )

    assert len(primeira) == len(segunda) > 0
    assert any("cache" in aviso for aviso in avisos)
    pd.testing.assert_frame_equal(
        primeira[list(validacao.CHAVES_1X2)], segunda[list(validacao.CHAVES_1X2)]
    )


def test_forcar_ignora_o_cache(cfg_em_pasta_temporaria) -> None:
    cfg = cfg_em_pasta_temporaria
    jogos = _tabela()
    candidato = selecao.Candidato(
        nome="baseline-teste",
        descricao="para o teste",
        construir=lambda: Baseline(max_gols=6),
    )
    inicio = jogos["data"].iloc[len(jogos) // 2]

    selecao.rodar_candidato(jogos, candidato, cfg, inicio=inicio)
    avisos: list[str] = []
    selecao.rodar_candidato(
        jogos, candidato, cfg, inicio=inicio, forcar=True, aviso=avisos.append
    )
    assert any("medindo" in aviso for aviso in avisos)


def test_gravacao_interrompida_nao_deixa_cache_pela_metade(tmp_path) -> None:
    """Fechar o computador no meio da gravação não pode corromper o cache.

    Um parquet truncado com o nome do arquivo bom seria lido, na próxima
    execução, como "já medido" — e a fase inteira sairia de previsões pela
    metade, sem nenhuma mensagem de erro.
    """
    destino = tmp_path / "previsoes.parquet"
    previsoes = _previsoes(0.5)

    class QuebraNoMeio(pd.DataFrame):
        """Um DataFrame que falha na hora de gravar, como um desligamento."""

        def to_parquet(self, *args, **kwargs):  # noqa: D102
            raise KeyboardInterrupt("simulando o terminal sendo fechado")

    with pytest.raises(KeyboardInterrupt):
        selecao._gravar_no_cache(QuebraNoMeio(previsoes), destino)

    assert not destino.exists(), "o cache bom não pode ter sido criado"
    assert not list(tmp_path.glob("*.parcial")), "o arquivo temporário ficou para trás"


def test_gravacao_completa_deixa_so_o_arquivo_bom(tmp_path) -> None:
    destino = tmp_path / "previsoes.parquet"
    selecao._gravar_no_cache(_previsoes(0.5), destino)

    assert destino.is_file()
    assert not list(tmp_path.glob("*.parcial"))
    assert len(pd.read_parquet(destino)) == 200


# ----------------------------------------------------------------------------
# A escolha (regra 9)
# ----------------------------------------------------------------------------
def _previsoes(probabilidade_certa: float, n: int = 200) -> pd.DataFrame:
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


def _candidato(nome: str) -> selecao.Candidato:
    return selecao.Candidato(
        nome=nome,
        descricao=nome,
        construir=lambda: Baseline(max_gols=6),
        parametros={"marca": nome},
    )


def test_vence_quem_tem_a_menor_log_loss() -> None:
    previsoes = {
        "ruim": _previsoes(0.20),
        "bom": _previsoes(0.70),
        "meio": _previsoes(0.45),
    }
    lista = [_candidato(nome) for nome in previsoes]

    escolha = selecao.escolher(previsoes, lista)

    assert escolha.vencedor.nome == "bom"
    assert [m.nome for m in escolha.medidas] == ["bom", "meio", "ruim"]
    assert escolha.parametros == {"marca": "bom"}
    assert escolha.n_configuracoes == 3


def test_a_margem_sobre_o_segundo_e_reportada() -> None:
    """Escolha apertada e escolha folgada precisam ser distinguíveis."""
    previsoes = {"bom": _previsoes(0.70), "quase": _previsoes(0.69)}
    escolha = selecao.escolher(previsoes, [_candidato(n) for n in previsoes])

    assert escolha.vencedor.nome == "bom"
    assert escolha.margem == pytest.approx(np.log(0.70) - np.log(0.69), abs=1e-9)
    assert escolha.margem < 0.02, "esta é uma escolha apertada"


def test_a_escolha_mede_todos_nos_mesmos_jogos() -> None:
    """Um candidato que pulou rodadas não pode parecer melhor por isso."""
    completo = _previsoes(0.50, n=200)
    parcial = _previsoes(0.80, n=200).iloc[:120]

    escolha = selecao.escolher(
        {"completo": completo, "parcial": parcial},
        [_candidato("completo"), _candidato("parcial")],
    )
    assert {m.n for m in escolha.medidas} == {120}
