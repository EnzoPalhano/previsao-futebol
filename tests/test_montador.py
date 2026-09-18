"""Testes do montador de bilhetes — a peça que vira tela na Fase 8.

O que um erro aqui produziria: um bilhete bonito, com uma chance de ganhar
escrita em negrito, e errada. Como o app vai mostrar esse número para alguém
decidir apostar dinheiro, os testes conferem as três coisas que a especificação
exige e que nenhuma delas dá erro quando quebra: probabilidades entre 0 e 1, uma
seleção por jogo, e o prêmio calculado direito.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from futebol.backtest import montador, multiplas
from futebol.config import Config

CONFIG = Config(
    bruto={
        "multiplas": {
            "min_selecoes": 1,
            "max_selecoes": 8,
            "odd_minima_selecao": 1.20,
            "odd_maxima_selecao": 5.00,
            "uma_selecao_por_jogo": True,
            "beam_width": 20,
        }
    },
    seed=42,
    raiz=Path("."),
)


def _rodada(n_jogos: int = 12) -> pd.DataFrame:
    linhas = []
    for i in range(n_jogos):
        for chave, prob, odd in (
            ("H", 0.75 - i * 0.03, 1.30 + i * 0.08),
            ("over25", 0.50 - i * 0.01, 1.90 + i * 0.05),
        ):
            linhas.append(
                {
                    "data": pd.Timestamp("2023-04-15"),
                    "liga": "E0",
                    "mandante": f"ENG:{i}",
                    "visitante": f"ENG:{i + 100}",
                    "selecao": chave,
                    "mercado": "1x2" if chave == "H" else "ou25",
                    "prob": prob,
                    "odd": odd,
                    "prob_justa": (1 / odd) / 1.05,
                    "ganhou": True,
                }
            )
    return pd.DataFrame(linhas)


# ----------------------------------------------------------------------------
# Montar por tamanho
# ----------------------------------------------------------------------------
def test_monta_o_tamanho_pedido() -> None:
    opcao = montador.por_tamanho(_rodada(), tamanho=4)
    assert opcao is not None
    assert opcao.tamanho == 4


def test_nunca_repete_jogo_no_mesmo_bilhete() -> None:
    """A restrição que torna o produto das probabilidades defensável."""
    opcao = montador.por_tamanho(_rodada(), tamanho=6)
    chaves = opcao.pernas[list(multiplas.CHAVE_DO_JOGO)]
    assert not chaves.duplicated().any()


def test_por_tamanho_devolve_o_bilhete_mais_provavel_que_existe() -> None:
    """A escolha gulosa é ótima aqui, e o teste confere contra a força bruta."""
    from itertools import combinations

    rodada = _rodada(n_jogos=6)
    por_jogo = multiplas.melhor_selecao_por_jogo(rodada)
    melhor_na_marra = max(
        float(np.prod(por_jogo.iloc[list(indices)]["prob"]))
        for indices in combinations(range(len(por_jogo)), 3)
    )
    opcao = montador.por_tamanho(rodada, tamanho=3)
    assert opcao.prob_modelo == pytest.approx(melhor_na_marra)


def test_rodada_curta_demais_nao_monta_nada() -> None:
    assert montador.por_tamanho(_rodada(n_jogos=2), tamanho=5) is None


# ----------------------------------------------------------------------------
# As contas do bilhete
# ----------------------------------------------------------------------------
def test_o_premio_e_o_valor_vezes_a_odd_total() -> None:
    opcao = montador.por_tamanho(_rodada(), tamanho=3, valor=25.0)
    assert opcao.premio == pytest.approx(25.0 * opcao.odd_total)


def test_a_chance_fica_entre_zero_e_um() -> None:
    for tamanho in range(1, 9):
        opcao = montador.por_tamanho(_rodada(), tamanho=tamanho)
        assert 0.0 < opcao.prob_modelo <= 1.0
        assert 0.0 < opcao.prob_implicita <= 1.0


def test_a_chance_cai_a_cada_jogo_acrescentado() -> None:
    rodada = _rodada()
    chances = [montador.por_tamanho(rodada, k).prob_modelo for k in range(1, 9)]
    assert chances == sorted(chances, reverse=True)


def test_a_comissao_sobe_a_cada_jogo_acrescentado() -> None:
    rodada = _rodada()
    margens = [
        montador.por_tamanho(rodada, k).margem_acumulada for k in range(1, 9)
    ]
    assert margens == sorted(margens)


def test_o_ev_e_calculado_em_reais() -> None:
    """EV = valor × (chance × odd − 1). Negativo é o caso comum, e tem aviso."""
    opcao = montador.por_tamanho(_rodada(), tamanho=3, valor=10.0)
    esperado = 10.0 * (opcao.prob_modelo * opcao.odd_total - 1.0)
    assert opcao.ev == pytest.approx(esperado)
    assert opcao.ev_negativo == (opcao.ev < 0)


def test_a_chance_tambem_sai_como_um_em_x() -> None:
    opcao = montador.por_tamanho(_rodada(), tamanho=5)
    assert opcao.uma_em == pytest.approx(1.0 / opcao.prob_modelo)


# ----------------------------------------------------------------------------
# Prêmio alvo
# ----------------------------------------------------------------------------
def test_o_premio_alvo_e_alcancado() -> None:
    opcao = montador.montar(_rodada(), CONFIG, premio_alvo=100.0, valor=10.0)
    assert opcao is not None
    assert opcao.premio >= 100.0


def test_o_bilhete_do_premio_alvo_nao_repete_jogo() -> None:
    opcao = montador.montar(_rodada(), CONFIG, premio_alvo=200.0, valor=10.0)
    chaves = opcao.pernas[list(multiplas.CHAVE_DO_JOGO)]
    assert not chaves.duplicated().any()


def test_premio_inalcancavel_devolve_nada_em_vez_de_inventar() -> None:
    """Melhor não responder do que responder um bilhete que não existe."""
    assert montador.montar(_rodada(n_jogos=3), CONFIG, premio_alvo=1e9, valor=1.0) is None


def test_a_busca_nao_cresce_o_bilhete_depois_de_alcancar_o_alvo() -> None:
    """Acrescentar seleção a um bilhete que já serve só diminui a chance."""
    facil = montador.montar(_rodada(), CONFIG, premio_alvo=15.0, valor=10.0)
    dificil = montador.montar(_rodada(), CONFIG, premio_alvo=150.0, valor=10.0)
    assert facil.tamanho < dificil.tamanho


def test_a_busca_em_feixe_e_reproduzivel() -> None:
    """Mesma entrada, mesmo bilhete — o app não pode mudar de ideia sozinho."""
    primeira = montador.montar(_rodada(), CONFIG, premio_alvo=200.0, valor=10.0)
    segunda = montador.montar(_rodada(), CONFIG, premio_alvo=200.0, valor=10.0)
    assert primeira.pernas.equals(segunda.pernas)


def test_a_busca_ganha_do_guloso_quando_o_guloso_nao_serve() -> None:
    """Por que a busca existe, em forma de teste.

    O guloso pega as seleções mais prováveis — que são as de **odd mais baixa**.
    Com um prêmio alvo, ele frequentemente monta um bilhete que não paga o
    suficiente, e aí ele não é uma resposta: é um bilhete inválido. A busca
    troca probabilidade por odd só o quanto for preciso para alcançar o alvo.
    """
    rodada = multiplas.elegiveis(_rodada(), CONFIG)
    achado = montador.montar(_rodada(), CONFIG, premio_alvo=100.0, valor=10.0)
    guloso = montador.por_tamanho(rodada, achado.tamanho, 10.0)

    assert achado.premio >= 100.0
    assert guloso.premio < 100.0  # o guloso do mesmo tamanho não serviria
    # E o preço da troca: menos chance, em troca de alcançar o alvo.
    assert achado.prob_modelo < guloso.prob_modelo


def test_a_busca_nao_perde_para_nenhum_bilhete_valido_pequeno() -> None:
    """Contra a força bruta, num caso pequeno o bastante para enumerar tudo."""
    from itertools import combinations

    rodada = _rodada(n_jogos=7)
    por_jogo = multiplas.melhor_selecao_por_jogo(multiplas.elegiveis(rodada, CONFIG))
    alvo = 6.0

    melhor_na_marra = 0.0
    for tamanho in range(1, len(por_jogo) + 1):
        for indices in combinations(range(len(por_jogo)), tamanho):
            escolhidas = por_jogo.iloc[list(indices)]
            if float(np.prod(escolhidas["odd"])) >= alvo:
                melhor_na_marra = max(
                    melhor_na_marra, float(np.prod(escolhidas["prob"]))
                )

    achado = montador.montar(rodada, CONFIG, premio_alvo=alvo * 10.0, valor=10.0)
    assert achado.prob_modelo == pytest.approx(melhor_na_marra)


# ----------------------------------------------------------------------------
# A porta de entrada
# ----------------------------------------------------------------------------
def test_pedir_tamanho_e_premio_ao_mesmo_tempo_e_erro() -> None:
    """São perguntas diferentes; escolher uma por conta própria seria pior."""
    with pytest.raises(ValueError, match="OU o prêmio alvo"):
        montador.montar(_rodada(), CONFIG, tamanho=3, premio_alvo=100.0)


def test_nao_pedir_nada_e_erro() -> None:
    with pytest.raises(ValueError, match="OU o prêmio alvo"):
        montador.montar(_rodada(), CONFIG)


def test_valor_apostado_tem_de_ser_positivo() -> None:
    with pytest.raises(ValueError, match="positivo"):
        montador.montar(_rodada(), CONFIG, premio_alvo=100.0, valor=0.0)


def test_a_faixa_de_odd_do_config_e_respeitada() -> None:
    rodada = _rodada()
    rodada.loc[0, "odd"] = 1.01
    opcao = montador.montar(rodada, CONFIG, tamanho=8)
    assert (opcao.pernas["odd"] >= 1.20).all()


# ----------------------------------------------------------------------------
# A tabela comparativa
# ----------------------------------------------------------------------------
def test_o_comparativo_mostra_a_chance_caindo_e_a_comissao_subindo() -> None:
    tabela = montador.comparar_tamanhos(_rodada(), CONFIG, faixa=(1, 6))
    assert list(tabela["tamanho"]) == [1, 2, 3, 4, 5, 6]
    assert tabela["prob_modelo"].is_monotonic_decreasing
    assert tabela["margem_acumulada"].is_monotonic_increasing
    assert tabela["premio"].is_monotonic_increasing


def test_o_aviso_de_independencia_existe_e_fala_de_bilhete_grande() -> None:
    """A especificação exige este aviso no relatório **e** na tela do app."""
    assert "independentes" in montador.AVISO_DE_INDEPENDENCIA
    assert "menor" in montador.AVISO_DE_INDEPENDENCIA
