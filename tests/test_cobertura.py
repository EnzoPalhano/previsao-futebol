"""Testes do relatório de cobertura: o buraco de odds precisa aparecer.

Um relatório de cobertura que erra para menos é pior do que não ter relatório:
ele dá confiança num backtest que na verdade rodou com metade dos jogos. Por
isso os testes aqui usam tabelas pequenas e conferidas na mão.
"""

from __future__ import annotations

import pandas as pd
import pytest

from futebol.dados import cobertura, limpeza


def tabela(linhas: list[dict]) -> pd.DataFrame:
    """Monta uma tabela de jogos com as colunas padrão, vazias por omissão."""
    base: dict = dict.fromkeys(limpeza.COLUNAS_TABELA)
    completas = []
    for linha in linhas:
        jogo = {**base, **linha}
        jogo.setdefault("grupo", "grupo1")
        completas.append(jogo)
    jogos = pd.DataFrame(completas, columns=list(limpeza.COLUNAS_TABELA))
    jogos["data"] = pd.to_datetime(jogos["data"])
    return jogos


#: Um jogo com todos os quatro mercados preenchidos.
COMPLETO: dict = {
    "data": "2024-08-16",
    "liga": "E0",
    "temporada": "2024/25",
    "mandante": "ENG:Arsenal",
    "visitante": "ENG:Chelsea",
    "gols_mandante": 2,
    "gols_visitante": 1,
    "resultado": "H",
    "odd_pre_H": 1.8,
    "odd_pre_D": 3.6,
    "odd_pre_A": 4.2,
    "odd_pre_over25": 1.9,
    "odd_pre_under25": 1.95,
    "odd_fech_H": 1.75,
    "odd_fech_D": 3.7,
    "odd_fech_A": 4.4,
    "odd_fech_over25": 1.88,
    "odd_fech_under25": 1.97,
    "grupo": "grupo1",
}

#: Um jogo do Grupo 2: só fechamento de 1X2, como manda a regra 12.
SO_FECHAMENTO: dict = {
    "data": "2024-05-19",
    "liga": "BRA",
    "temporada": "2024",
    "mandante": "BRA:Palmeiras",
    "visitante": "BRA:Santos",
    "gols_mandante": 1,
    "gols_visitante": 1,
    "resultado": "D",
    "odd_fech_H": 1.69,
    "odd_fech_D": 3.5,
    "odd_fech_A": 4.9,
    "grupo": "grupo2",
}


# ----------------------------------------------------------------------------
# Presença de mercado
# ----------------------------------------------------------------------------
def test_mercado_incompleto_nao_conta_como_presente() -> None:
    """Sem a odd de empate, o 1X2 não dá para apostar — logo, não existe."""
    jogos = tabela([COMPLETO, {**COMPLETO, "odd_pre_D": None}])
    assert list(cobertura.tem_mercado(jogos, "1x2_pre")) == [True, False]


def test_grupo2_nao_tem_nenhum_mercado_pre_jogo() -> None:
    jogos = tabela([SO_FECHAMENTO])
    assert not cobertura.tem_mercado(jogos, "1x2_pre").any()
    assert not cobertura.tem_mercado(jogos, "ou25_pre").any()
    assert cobertura.tem_mercado(jogos, "1x2_fech").all()


# ----------------------------------------------------------------------------
# Agregação
# ----------------------------------------------------------------------------
def test_falta_e_fracao_de_jogos_sem_o_mercado() -> None:
    jogos = tabela([COMPLETO, COMPLETO, {**COMPLETO, "odd_pre_over25": None}])
    resumo = cobertura.por(jogos, ["liga", "temporada"])

    assert len(resumo) == 1
    linha = resumo.iloc[0]
    assert linha["jogos"] == 3
    assert linha["falta_1x2_pre"] == 0.0
    assert linha["falta_ou25_pre"] == pytest.approx(1 / 3)


def test_agregacao_separa_por_temporada() -> None:
    jogos = tabela(
        [
            COMPLETO,
            {**COMPLETO, "temporada": "2023/24", "data": "2023-08-11", "odd_pre_H": None},
        ]
    )
    resumo = cobertura.por(jogos, ["liga", "temporada"]).set_index("temporada")

    assert resumo.loc["2024/25", "falta_1x2_pre"] == 0.0
    assert resumo.loc["2023/24", "falta_1x2_pre"] == 1.0


def test_agregacao_traz_o_periodo_coberto() -> None:
    jogos = tabela([COMPLETO, {**COMPLETO, "data": "2025-05-25"}])
    linha = cobertura.por(jogos, ["liga"]).iloc[0]
    assert linha["primeiro"] == pd.Timestamp("2024-08-16")
    assert linha["ultimo"] == pd.Timestamp("2025-05-25")


# ----------------------------------------------------------------------------
# Viés de seleção
# ----------------------------------------------------------------------------
def test_vies_conta_so_as_ligas_que_deveriam_ter_a_odd() -> None:
    """O Grupo 2 nunca tem odd pré-jogo: incluí-lo diria sempre "faltam 100%"."""
    jogos = tabela([COMPLETO, SO_FECHAMENTO])
    vies = cobertura.vies_de_selecao(jogos)

    assert vies.jogos_sem_odd == 0
    assert vies.fracao == 0.0


def test_vies_aponta_onde_a_falta_se_concentra() -> None:
    sem_odd = {
        **COMPLETO,
        "liga": "E3",
        "mandante": "ENG:Accrington",
        "odd_pre_H": None,
        "odd_pre_D": None,
        "odd_pre_A": None,
    }
    jogos = tabela([COMPLETO, sem_odd, sem_odd])
    vies = cobertura.vies_de_selecao(jogos)

    assert vies.jogos_sem_odd == 2
    assert vies.fracao == pytest.approx(2 / 3)
    assert vies.por_liga.iloc[0]["liga"] == "E3"
    assert vies.times_mais_afetados["ENG:Accrington"] == 2


def test_vies_compara_gols_dos_dois_conjuntos() -> None:
    """Jogo sem odd não é sorteado: se ele é de outro tipo, isso tem que aparecer."""
    sem_odd = {
        **COMPLETO,
        "gols_mandante": 4,
        "gols_visitante": 3,
        "odd_pre_H": None,
        "odd_pre_D": None,
        "odd_pre_A": None,
    }
    vies = cobertura.vies_de_selecao(tabela([COMPLETO, sem_odd]))

    assert vies.media_gols_com == pytest.approx(3.0)
    assert vies.media_gols_sem == pytest.approx(7.0)
    assert vies.parece_aleatorio is False


# ----------------------------------------------------------------------------
# Relatório
# ----------------------------------------------------------------------------
def test_relatorio_diz_quais_ligas_entraram() -> None:
    """Regra 13: sem isso, um número do relatório não quer dizer nada."""
    jogos = tabela([COMPLETO, SO_FECHAMENTO])
    texto = cobertura.relatorio_markdown(
        jogos, camada="camada_principal", gerado_em="2026-09-16"
    )

    assert "camada_principal" in texto
    assert "Grupo 1 (backtest + CLV): **E0**" in texto
    assert "Grupo 2 (treino e calibração apenas): **BRA**" in texto
    assert "regra 12" in texto.lower()


def test_relatorio_tem_uma_linha_por_liga_e_temporada() -> None:
    jogos = tabela(
        [COMPLETO, {**COMPLETO, "temporada": "2023/24", "data": "2023-08-11"}]
    )
    texto = cobertura.relatorio_markdown(jogos, camada="teste", gerado_em="2026-09-16")

    assert "| E0 | 2024/25 | 1 |" in texto
    assert "| E0 | 2023/24 | 1 |" in texto


def test_relatorio_avisa_quando_faltam_odds() -> None:
    sem_odd = {
        **COMPLETO,
        "odd_pre_H": None,
        "odd_pre_D": None,
        "odd_pre_A": None,
        "gols_mandante": 5,
    }
    texto = cobertura.relatorio_markdown(
        tabela([COMPLETO, sem_odd]), camada="teste", gerado_em="2026-09-16"
    )

    assert "50,0%" in texto
    assert "Fase 6" in texto
