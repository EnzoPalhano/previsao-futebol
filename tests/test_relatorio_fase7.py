"""O relatório da Fase 7: o que ele promete estar escrito tem de estar escrito.

A Fase 7 tem uma obrigação de texto que nenhuma outra tem: a especificação
manda o aviso de independência acompanhar **toda** chance de ganhar mostrada, no
relatório e na tela do app. Um aviso some numa reescrita sem dar erro nenhum, e
é por isso que ele tem teste.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from futebol.avaliacao import relatorio_fase7
from futebol.backtest import cash_out, montador, multiplas
from futebol.config import Config

CONFIG = Config(
    bruto={
        "multiplas": {
            "min_selecoes": 1,
            "max_selecoes": 4,
            "odd_minima_selecao": 1.10,
            "odd_maxima_selecao": 6.00,
            "uma_selecao_por_jogo": True,
            "beam_width": 10,
            "cash_out_margem_casa": 0.08,
        }
    },
    seed=42,
    raiz=Path("."),
)


def _candidatos(n_rodadas: int = 30) -> pd.DataFrame:
    gerador = np.random.default_rng(5)
    linhas = []
    for dia in range(n_rodadas):
        for jogo in range(6):
            justa = 0.50 + 0.06 * ((dia + jogo) % 4)
            linhas.append(
                {
                    "data": pd.Timestamp("2022-01-01") + pd.Timedelta(days=dia),
                    "liga": "E0" if jogo % 2 else "SP1",
                    "mandante": f"ENG:{jogo}",
                    "visitante": f"ENG:{jogo + 100}",
                    "selecao": "H",
                    "mercado": "1x2",
                    # O modelo exagera 4% em cada perna, de propósito: é o
                    # padrão que o relatório tem de conseguir diagnosticar.
                    "prob": justa * 1.04,
                    "odd": 1.0 / (justa * 1.05),
                    "prob_justa": justa,
                    "ganhou": bool(gerador.random() < justa),
                }
            )
    return pd.DataFrame(linhas)


@pytest.fixture
def relatorio_pronto(tmp_path) -> str:
    candidatos = _candidatos()
    historico = multiplas.montar_historico(candidatos, CONFIG, tamanhos=(2, 3, 4))
    por_tamanho = multiplas.medir_por_tamanho(
        historico.multiplas, amostras_bootstrap=200
    )
    tabelas = {
        tamanho: cash_out.como_tabela(
            cash_out.simular(historico, CONFIG, tamanho, amostras_bootstrap=200)
        )
        for tamanho in (2, 4)
    }
    pernas = historico.pernas.loc[historico.pernas["id"] == 0]
    rodada = candidatos.loc[candidatos["data"] == candidatos["data"].iloc[0]]
    return relatorio_fase7.montar(
        cfg=CONFIG,
        historico=historico,
        por_tamanho=por_tamanho,
        tabelas_de_cash_out=tabelas,
        distribuicao=(
            4,
            cash_out.distribuicao_de_acertos(
                pernas["prob_justa"].to_numpy(), repeticoes=2000
            ),
        ),
        exemplo=montador.montar(rodada, CONFIG, tamanho=3, valor=10.0),
        comparativo=montador.comparar_tamanhos(rodada, CONFIG, faixa=(1, 4)),
        caminho_margem=tmp_path / "fase7_margem.png",
        caminho_previsto=tmp_path / "fase7_previsto_real.png",
        janela=(pd.Timestamp("2021-07-01"), pd.Timestamp("2024-06-03")),
        gerado_em="2026-09-17",
    )


# ----------------------------------------------------------------------------
# As obrigações de texto
# ----------------------------------------------------------------------------
def test_o_aviso_de_independencia_aparece_junto_da_chance(relatorio_pronto) -> None:
    """A exigência mais explícita da seção 7.1 da especificação."""
    assert montador.AVISO_DE_INDEPENDENCIA in relatorio_pronto


def test_o_relatorio_documenta_a_limitacao_de_independencia(relatorio_pronto) -> None:
    assert "independência" in relatorio_pronto
    assert "uma seleção por jogo" in relatorio_pronto


def test_o_relatorio_diz_que_monte_carlo_nao_conserta_a_correlacao(
    relatorio_pronto,
) -> None:
    """Sem este parágrafo, alguém vai tentar 'consertar' com simulação."""
    assert "Monte Carlo" in relatorio_pronto
    assert "não" in relatorio_pronto


def test_o_relatorio_mostra_a_margem_crescendo_com_o_tamanho(relatorio_pronto) -> None:
    assert "comissão acumulada" in relatorio_pronto.lower()
    assert "(1 + m)ⁿ − 1" in relatorio_pronto or "ⁿ − 1" in relatorio_pronto


def test_o_relatorio_compara_previsto_com_real(relatorio_pronto) -> None:
    """O item (b) do "pronto quando" da fase."""
    assert "Aconteceu" in relatorio_pronto
    assert "O modelo prometeu" in relatorio_pronto
    assert "O mercado prometeria" in relatorio_pronto


def test_o_relatorio_traz_o_menor_erro_detectavel(relatorio_pronto) -> None:
    """Regra 10: "não detectei" sem o limiar de detecção não quer dizer nada."""
    assert "Menor erro detectável" in relatorio_pronto


def test_o_relatorio_tem_a_secao_de_cash_out(relatorio_pronto) -> None:
    assert "cash out" in relatorio_pronto.lower()
    assert "nunca sacar" in relatorio_pronto
    assert "Valor esperado" in relatorio_pronto


def test_o_relatorio_conta_as_configuracoes(relatorio_pronto) -> None:
    """Regra 11 — e nesta fase o número é grande."""
    assert f"**{relatorio_fase7.N_CONFIGURACOES_FASE_7}**" in relatorio_pronto
    assert "Total acumulado" in relatorio_pronto


def test_o_relatorio_traz_o_aviso_de_jogo_responsavel(relatorio_pronto) -> None:
    assert "188" in relatorio_pronto


def test_o_relatorio_lembra_que_a_fase_nao_escolhe_modelo(relatorio_pronto) -> None:
    assert "Regra 9" in relatorio_pronto


# ----------------------------------------------------------------------------
# Coerência interna
# ----------------------------------------------------------------------------
def test_o_diagnostico_de_erro_por_perna_e_reencontrado() -> None:
    """O relatório afirma medir o exagero por seleção — ele tem de reencontrá-lo.

    Os dados de teste são construídos com o modelo exagerando exatamente 4% em
    cada perna. A razão por seleção tem de voltar 1/1,04.
    """
    historico = multiplas.montar_historico(_candidatos(), CONFIG, tamanhos=(2, 3, 4))
    tabela = multiplas.medir_por_tamanho(historico.multiplas, amostras_bootstrap=100)
    assert tabela["razao_por_selecao"].to_numpy() == pytest.approx(
        1 / 1.04, abs=1e-6
    )


def test_a_contagem_da_fase_soma_as_anteriores() -> None:
    """Regra 11: o total soma e nunca é reescrito para baixo."""
    assert relatorio_fase7.N_CONFIGURACOES_FASE_7 > 0
    assert 29 + 16 + relatorio_fase7.N_CONFIGURACOES_FASE_7 == 108


def test_o_roi_da_fase_6_citado_bate_com_o_relatorio_dela() -> None:
    """Número de outra fase copiado à mão é número que envelhece calado."""
    fase6 = Path("docs/relatorios/fase6.md")
    if not fase6.is_file():
        pytest.skip("relatorio da Fase 6 ainda nao foi gerado")
    texto = fase6.read_text(encoding="utf-8")
    citado = f"{abs(relatorio_fase7.ROI_DA_FASE_6) * 100:.2f}".replace(".", ",")
    assert citado in texto
