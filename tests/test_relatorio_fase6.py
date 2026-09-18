"""O relatório da Fase 6: o que ele promete estar escrito tem de estar escrito.

A Fase 6 é a que o projeto teria mais a ganhar escondendo coisa, e quase tudo o
que ela precisa dizer é uma **exigência de texto**, não de conta: dizer quais
ligas entraram (regra 13), quantos jogos foram pulados (Fase 1d), as **duas**
variantes de banca, o poder estatístico (regra 10) e quantas configurações
foram testadas (regra 11).

Exigência de texto se perde numa reescrita e não dá erro nenhum. Daí estes
testes: eles montam um backtest de mentira, geram o relatório e conferem que
cada obrigação continua lá.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from futebol.avaliacao import relatorio_fase6
from futebol.backtest import estrategias, simulador
from futebol.config import Config

CONFIG = Config(
    bruto={
        "ligas_aprovadas_backtest": ["E0", "SP1"],
        "backtest": {
            "ev_minimo": 0.05,
            "banca_inicial": 1000.0,
            "stake_fixa_pct": 0.01,
            "kelly_fracao": 0.25,
            "kelly_teto_pct": 0.05,
            "bootstrap_amostras": 200,
        },
    },
    seed=42,
    raiz=Path("."),
)


def _candidatos(n: int = 1200) -> pd.DataFrame:
    """Apostas de mentira, perdedoras de propósito e com CLV negativo."""
    gerador = np.random.default_rng(11)
    odd = gerador.uniform(1.2, 8.0, n)
    ganhou = gerador.random(n) < 0.9 / odd
    return pd.DataFrame(
        {
            "data": pd.date_range("2022-01-01", periods=n, freq="6h").floor("D"),
            "liga": np.where(np.arange(n) % 2 == 0, "E0", "SP1"),
            "temporada": np.where(np.arange(n) < n // 2, "2021/22", "2022/23"),
            "mandante": [f"ENG:{i % 20}" for i in range(n)],
            "visitante": [f"ENG:{(i + 1) % 20}" for i in range(n)],
            "mercado": np.where(np.arange(n) % 5 < 3, "1x2", "ou25"),
            "selecao": np.tile(["H", "D", "A", "over25", "under25"], n // 5),
            "prob": np.clip(1.08 / odd, 0.01, 0.99),
            "odd": odd,
            "ev": 1.08 / odd * odd - 1.0,
            "ganhou": ganhou,
            "retorno_unitario": np.where(ganhou, odd - 1.0, -1.0),
            "odd_fech": odd * 0.99,
            "prob_fech": np.clip(1.0 / (odd * 0.96), 0.01, 0.99),
            "clv": odd * np.clip(1.0 / (odd * 0.96), 0.01, 0.99) - 1.0,
            "clv_bruto": np.full(n, 1 / 0.99 - 1.0),
        }
    )


@pytest.fixture
def relatorio_pronto(tmp_path) -> str:
    candidatos = _candidatos()
    amostra = simulador.Amostra(
        candidatos=candidatos,
        ligas=["E0", "SP1"],
        jogos_na_janela=250,
        jogos_com_odd=240,
        jogos_sem_odd=10,
        jogos_sem_ou=3,
        jogos_sem_fechamento=1,
        fora_por_grupo2=500,
        fora_por_liga_reprovada=100,
    )
    apostas = simulador.selecionar(candidatos, 0.05)
    evolucoes = {}
    for nome in ("stake_fixa", "kelly_fracionado"):
        estrategia = estrategias.criar(nome, CONFIG.secao("backtest"))
        for tipo in estrategias.TIPOS_DE_BANCA:
            evolucoes[(nome, tipo)] = estrategias.simular_banca(
                apostas, estrategia, 1000.0, tipo
            )

    principal = simulador.Backtest(
        amostra=amostra,
        ev_minimo=0.05,
        apostas=apostas,
        resultado=simulador.medir(apostas, "modelo", amostras_bootstrap=200),
        aleatorio=simulador.medir(
            simulador.aleatorias(candidatos, len(apostas), seed=1),
            "aleatória",
            amostras_bootstrap=200,
        ),
        evolucoes=evolucoes,
    )
    grade = {
        limite: simulador.medir(
            simulador.selecionar(candidatos, limite), f"EV>{limite:.0%}",
            amostras_bootstrap=200,
        )
        for limite in simulador.GRADE_EV
    }
    return relatorio_fase6.montar(
        cfg=CONFIG,
        principal=principal,
        grade=grade,
        referencia=simulador.medir(candidatos, "todas", amostras_bootstrap=200),
        caminho_banca=tmp_path / "fase6_banca.png",
        caminho_lucro=tmp_path / "fase6_lucro_acumulado.png",
        janela=(pd.Timestamp("2021-07-01"), pd.Timestamp("2024-06-03")),
        modelo="dc-xi-0.003",
        gerado_em="2026-09-17",
    )


# ----------------------------------------------------------------------------
# As obrigações de texto
# ----------------------------------------------------------------------------
def test_o_relatorio_diz_quais_ligas_entraram(relatorio_pronto) -> None:
    """Regra 13: toda tabela de resultado diz de quais ligas ela fala."""
    assert "Regra 13" in relatorio_pronto
    assert "E0, SP1" in relatorio_pronto


def test_o_relatorio_declara_o_que_fez_com_os_jogos_sem_odd(relatorio_pronto) -> None:
    """Exigência da Fase 1d: jogo sem odd não some em silêncio."""
    assert "não ter odd média pré-jogo" in relatorio_pronto
    assert "10" in relatorio_pronto


def test_o_relatorio_diz_que_aposta_na_odd_media_e_nunca_na_max(
    relatorio_pronto,
) -> None:
    """Regra 8 — a trava que separa este backtest dos que dão lucro na internet."""
    assert "odd média pré-jogo" in relatorio_pronto
    assert "`Max`" in relatorio_pronto


def test_o_relatorio_mostra_as_duas_variantes_de_banca(relatorio_pronto) -> None:
    """Omitir qual banca foi usada é a forma mais comum de relatório enganoso."""
    assert "banca fixa" in relatorio_pronto
    assert "banca composta" in relatorio_pronto
    assert relatorio_pronto.count("banca composta") >= 2


def test_o_relatorio_traz_o_poder_estatistico(relatorio_pronto) -> None:
    """Regra 10: ROI sem 'o menor efeito detectável' não quer dizer nada."""
    assert "poder estatístico" in relatorio_pronto.lower()
    assert "menor efeito detectável" in relatorio_pronto
    assert "Apostas necessárias" in relatorio_pronto


def test_o_relatorio_conta_as_configuracoes_testadas(relatorio_pronto) -> None:
    """Regra 11: o número é explícito, contável e some às fases anteriores."""
    assert "Bonferroni" in relatorio_pronto
    assert f"**{simulador.N_CONFIGURACOES_FASE_6}**" in relatorio_pronto
    assert "**45**" in relatorio_pronto  # 29 de modelo + 16 de aposta


def test_o_relatorio_compara_com_a_estrategia_aleatoria(relatorio_pronto) -> None:
    """Comparação obrigatória da regra 2.6d."""
    assert "aleatória" in relatorio_pronto


def test_o_relatorio_traz_a_tabela_por_liga_e_por_temporada(relatorio_pronto) -> None:
    """Seção 4.3: média geral esconde que o lucro veio de uma liga só."""
    assert "## Por liga" in relatorio_pronto
    assert "### E por temporada" in relatorio_pronto


def test_o_relatorio_reporta_roi_e_clv_com_intervalo(relatorio_pronto) -> None:
    """Regra 2.6c: nunca um número seco."""
    assert "IC 95% do ROI" in relatorio_pronto
    assert "IC 95% do CLV" in relatorio_pronto


def test_o_relatorio_lembra_que_o_roi_nao_escolhe_modelo(relatorio_pronto) -> None:
    """Regra 9 — a regra que esta fase inteira poderia tentar contornar."""
    assert "Regra 9" in relatorio_pronto
    assert "nunca" in relatorio_pronto


def test_o_relatorio_traz_o_aviso_de_jogo_responsavel(relatorio_pronto) -> None:
    assert "188" in relatorio_pronto


def test_o_relatorio_cita_a_regra_12_do_grupo_2(relatorio_pronto) -> None:
    """Grupo 2 não pode entrar em backtest nem em CLV, e isso tem de estar dito."""
    assert "regra 12" in relatorio_pronto.lower()
    assert "Grupo 2" in relatorio_pronto


# ----------------------------------------------------------------------------
# Coerência interna
# ----------------------------------------------------------------------------
def test_a_tabela_por_temporada_cobre_todas_as_apostas() -> None:
    """Uma temporada esquecida sumiria da tabela sem dar erro."""
    candidatos = _candidatos()
    apostas = simulador.selecionar(candidatos, 0.05)
    tabela = relatorio_fase6._temporadas(apostas)
    assert int(tabela["apostas"].sum()) == len(apostas)


def test_as_faixas_de_odd_cobrem_qualquer_odd_possivel() -> None:
    """Uma odd fora das faixas sumiria da tabela do viés azarão–favorito."""
    odds = pd.Series([1.01, 1.5, 2.0, 7.3, 51.0, 999.0])
    faixas = pd.cut(odds, relatorio_fase6.FAIXAS_DE_ODD)
    assert faixas.notna().all()
