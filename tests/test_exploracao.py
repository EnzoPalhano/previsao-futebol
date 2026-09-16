"""Testes da exploração: as contas que descrevem o futebol e o mercado.

Cada teste usa uma tabela pequena em que dá para conferir o número na mão —
é a única forma de saber se a média que sai de um `groupby` é a média certa.
"""

from __future__ import annotations

import pandas as pd
import pytest

from futebol.avaliacao import exploracao
from futebol.dados import limpeza


def tabela(linhas: list[dict]) -> pd.DataFrame:
    """Tabela de jogos com as colunas padrão, vazias por omissão."""
    base: dict = dict.fromkeys(limpeza.COLUNAS_TABELA)
    completas = [{**base, "grupo": "grupo1", "formato": "A", **linha} for linha in linhas]
    jogos = pd.DataFrame(completas, columns=list(limpeza.COLUNAS_TABELA))
    jogos["data"] = pd.to_datetime(jogos["data"])
    return jogos


def jogo(
    casa: int, fora: int, *, liga: str = "E0", temporada: str = "2024/25", **extra
) -> dict:
    """Um jogo com placar, resultado coerente e o que mais o teste pedir."""
    resultado = "H" if casa > fora else "A" if fora > casa else "D"
    return {
        "data": "2024-08-16",
        "liga": liga,
        "temporada": temporada,
        "mandante": "ENG:A",
        "visitante": "ENG:B",
        "gols_mandante": casa,
        "gols_visitante": fora,
        "resultado": resultado,
        **extra,
    }


#: Odds de 1X2 com margem conhecida: 1/1,6 + 1/3,2 + 1/3,2 = 1,25.
ODDS_25 = {"odd_pre_H": 1.6, "odd_pre_D": 3.2, "odd_pre_A": 3.2}
#: Mercado justo: as implícitas somam exatamente 1.
ODDS_0 = {"odd_pre_H": 2.0, "odd_pre_D": 4.0, "odd_pre_A": 4.0}


# ----------------------------------------------------------------------------
# Gols
# ----------------------------------------------------------------------------
def test_distribuicao_de_gols_bate_com_a_contagem() -> None:
    jogos = tabela([jogo(1, 1), jogo(2, 1), jogo(0, 0), jogo(1, 1)])
    distribuicao = exploracao.distribuicao_gols(jogos, maximo=3)

    assert list(distribuicao["jogos"]) == [1, 0, 2, 1]
    assert distribuicao["observado"].sum() == pytest.approx(1.0)


def test_poisson_usa_a_media_observada() -> None:
    """A comparação só faz sentido contra a Poisson de mesma média."""
    jogos = tabela([jogo(1, 1), jogo(2, 1)])  # média de 2,5 gols
    distribuicao = exploracao.distribuicao_gols(jogos, maximo=12)
    media_poisson = (distribuicao["gols"] * distribuicao["poisson"]).sum()
    assert media_poisson == pytest.approx(2.5, abs=0.01)


def test_frequencia_over25_conta_tres_gols_ou_mais() -> None:
    jogos = tabela([jogo(2, 0), jogo(2, 1), jogo(3, 1)])
    linha = exploracao.frequencia_over25(jogos).iloc[0]

    assert linha["jogos"] == 3
    assert linha["over25"] == pytest.approx(2 / 3)
    assert linha["gols_por_jogo"] == pytest.approx(3.0)


# ----------------------------------------------------------------------------
# Mando de campo
# ----------------------------------------------------------------------------
def test_vantagem_de_mando_nas_tres_medidas() -> None:
    jogos = tabela([jogo(2, 0), jogo(1, 1), jogo(0, 1), jogo(3, 1)])
    linha = exploracao.vantagem_mando(jogos).iloc[0]

    assert linha["vitorias_casa"] == pytest.approx(0.5)
    assert linha["empates"] == pytest.approx(0.25)
    assert linha["pontos_casa"] == pytest.approx((3 + 1 + 0 + 3) / 4)
    assert linha["saldo_gols"] == pytest.approx((2 + 0 - 1 + 2) / 4)


def test_mando_separado_por_temporada() -> None:
    jogos = tabela(
        [
            jogo(3, 0, temporada="2018/19"),
            jogo(0, 1, temporada="2020/21"),
            jogo(0, 2, temporada="2020/21"),
        ]
    )
    por_temporada = exploracao.vantagem_mando(jogos, ["liga", "temporada"]).set_index(
        "temporada"
    )
    assert por_temporada.loc["2018/19", "pontos_casa"] == pytest.approx(3.0)
    assert por_temporada.loc["2020/21", "pontos_casa"] == pytest.approx(0.0)


def test_queda_do_mando_na_pandemia_mede_a_diferenca() -> None:
    """O efeito dos estádios vazios tem que sair como número, não como gráfico."""
    jogos = tabela(
        [
            jogo(3, 0, temporada="2018/19"),
            jogo(2, 0, temporada="2018/19"),
            jogo(0, 1, temporada="2020/21"),
            jogo(1, 1, temporada="2020/21"),
        ]
    )
    linha = exploracao.queda_do_mando_na_pandemia(jogos).iloc[0]

    assert linha["pontos_casa_publico"] == pytest.approx(3.0)
    assert linha["pontos_casa_vazio"] == pytest.approx(0.5)
    assert linha["queda_pontos_casa"] == pytest.approx(2.5)


# ----------------------------------------------------------------------------
# Margem
# ----------------------------------------------------------------------------
def test_margem_media_e_o_overround() -> None:
    jogos = tabela([jogo(1, 0, **ODDS_25), jogo(1, 0, **ODDS_0)])
    linha = exploracao.margem(jogos, "1x2", "pre").iloc[0]

    assert linha["margem_media"] == pytest.approx(0.125)  # média de 25% e 0%
    assert linha["cobertura"] == pytest.approx(1.0)


def test_jogo_sem_odd_nao_entra_na_margem_mas_derruba_a_cobertura() -> None:
    jogos = tabela([jogo(1, 0, **ODDS_25), jogo(1, 0)])
    linha = exploracao.margem(jogos, "1x2", "pre").iloc[0]

    assert linha["jogos"] == 1
    assert linha["cobertura"] == pytest.approx(0.5)
    assert linha["margem_media"] == pytest.approx(0.25)


def test_ranking_de_margem_vem_da_mais_barata_para_a_mais_cara() -> None:
    jogos = tabela(
        [
            jogo(1, 0, liga="E0", odd_fech_H=2.0, odd_fech_D=4.0, odd_fech_A=4.0),
            jogo(1, 0, liga="SC3", odd_fech_H=1.6, odd_fech_D=3.2, odd_fech_A=3.2),
        ]
    )
    ranking = exploracao.ranking_de_margem(jogos)
    assert list(ranking["liga"]) == ["E0", "SC3"]


def test_evolucao_da_margem_mostra_a_variacao() -> None:
    jogos = tabela(
        [
            jogo(1, 0, temporada="2019/20", odd_fech_H=1.6, odd_fech_D=3.2, odd_fech_A=3.2),
            jogo(1, 0, temporada="2024/25", odd_fech_H=2.0, odd_fech_D=4.0, odd_fech_A=4.0),
        ]
    )
    por_temporada, resumo = exploracao.evolucao_margem(jogos)

    assert len(por_temporada) == 2
    linha = resumo.iloc[0]
    assert linha["primeira"] == pytest.approx(0.25)
    assert linha["ultima"] == pytest.approx(0.0)
    assert linha["variacao"] == pytest.approx(-0.25)


def test_pre_contra_fechamento_mede_o_aperto() -> None:
    """O mercado costuma apertar a margem até o apito inicial."""
    jogos = tabela(
        [
            jogo(
                1,
                0,
                odd_pre_H=1.6,
                odd_pre_D=3.2,
                odd_pre_A=3.2,
                odd_fech_H=2.0,
                odd_fech_D=4.0,
                odd_fech_A=4.0,
            )
        ]
    )
    linha = exploracao.pre_contra_fechamento(jogos).iloc[0]

    assert linha["margem_pre"] == pytest.approx(0.25)
    assert linha["margem_fech"] == pytest.approx(0.0)
    assert linha["aperto"] == pytest.approx(0.25)
