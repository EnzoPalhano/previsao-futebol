"""Testes das múltiplas: a conta que tem de estar certa antes de medir qualquer coisa.

Três erros moram aqui, e nenhum deles dá exceção:

1. **duas seleções do mesmo jogo** no mesmo bilhete. O produto das
   probabilidades sairia errado para mais, e a chance de ganhar mostrada seria
   otimista sem que nada acusasse;
2. **bilhetes que compartilham partidas** dentro de uma rodada. O acerto de um
   ficaria amarrado ao do outro, e o intervalo de confiança sairia mais estreito
   do que a realidade;
3. **a margem calculada contra a odd em vez de contra a probabilidade justa**.
   Daria um número plausível e sem significado.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from futebol.backtest import multiplas
from futebol.config import Config

CONFIG = Config(
    bruto={
        "multiplas": {
            "min_selecoes": 1,
            "max_selecoes": 4,
            "odd_minima_selecao": 1.20,
            "odd_maxima_selecao": 5.00,
            "uma_selecao_por_jogo": True,
            "beam_width": 10,
        }
    },
    seed=42,
    raiz=Path("."),
)


def _candidatos(n_jogos: int = 8, data: str = "2022-01-01") -> pd.DataFrame:
    """Duas seleções por jogo, com probabilidades e odds conhecidas."""
    linhas = []
    for i in range(n_jogos):
        # A seleção "A" é sempre a mais provável do jogo; a "B" é a alternativa.
        for chave, prob, odd, ganhou in (
            ("H", 0.70 - i * 0.02, 1.40 + i * 0.05, i % 2 == 0),
            ("over25", 0.55 - i * 0.02, 1.80 + i * 0.05, i % 3 == 0),
        ):
            linhas.append(
                {
                    "data": pd.Timestamp(data),
                    "liga": "E0",
                    "mandante": f"ENG:{i}",
                    "visitante": f"ENG:{i + 100}",
                    "selecao": chave,
                    "mercado": "1x2" if chave == "H" else "ou25",
                    "prob": prob,
                    "odd": odd,
                    # A justa é um pouco menor que 1/odd: é assim que a comissão
                    # da casa entra na conta.
                    "prob_justa": (1 / odd) / 1.05,
                    "ganhou": ganhou,
                }
            )
    return pd.DataFrame(linhas)


# ----------------------------------------------------------------------------
# Uma seleção por jogo
# ----------------------------------------------------------------------------
def test_so_uma_selecao_por_jogo() -> None:
    """A restrição que torna o produto das probabilidades defensável."""
    por_jogo = multiplas.melhor_selecao_por_jogo(_candidatos())
    assert len(por_jogo) == 8
    assert not por_jogo.duplicated(subset=list(multiplas.CHAVE_DO_JOGO)).any()


def test_a_selecao_escolhida_e_a_mais_provavel_do_jogo() -> None:
    por_jogo = multiplas.melhor_selecao_por_jogo(_candidatos())
    assert set(por_jogo["selecao"]) == {"H"}


def test_a_chave_do_jogo_inclui_a_liga() -> None:
    """Regra 14: há clubes homônimos em países diferentes.

    Sem a liga na chave, um ``Everton`` inglês e um chileno seriam a mesma
    partida, e o bilhete perderia uma seleção em silêncio.
    """
    assert "liga" in multiplas.CHAVE_DO_JOGO


# ----------------------------------------------------------------------------
# Os blocos
# ----------------------------------------------------------------------------
def test_os_blocos_nao_compartilham_partidas() -> None:
    """Bilhetes com jogos em comum estreitariam o IC de mentira."""
    por_jogo = multiplas.melhor_selecao_por_jogo(_candidatos(n_jogos=9))
    blocos = multiplas.montar_da_rodada(por_jogo, tamanho=4)

    assert len(blocos) == 2  # 9 // 4, e a sobra é descartada
    primeiro = set(blocos[0]["mandante"])
    segundo = set(blocos[1]["mandante"])
    assert not (primeiro & segundo)


def test_o_primeiro_bloco_leva_os_maiores_favoritos() -> None:
    por_jogo = multiplas.melhor_selecao_por_jogo(_candidatos())
    blocos = multiplas.montar_da_rodada(por_jogo, tamanho=3)
    assert blocos[0]["prob"].min() >= blocos[1]["prob"].max()


def test_rodada_curta_demais_nao_monta_bilhete() -> None:
    por_jogo = multiplas.melhor_selecao_por_jogo(_candidatos(n_jogos=2))
    assert multiplas.montar_da_rodada(por_jogo, tamanho=5) == []


# ----------------------------------------------------------------------------
# As contas de um bilhete
# ----------------------------------------------------------------------------
def test_a_odd_total_e_o_produto_das_odds() -> None:
    pernas = multiplas.melhor_selecao_por_jogo(_candidatos()).head(3)
    resumo = multiplas.resumir(pernas, 3, 0)
    assert resumo["odd_total"] == pytest.approx(float(np.prod(pernas["odd"])))


def test_a_chance_e_o_produto_das_chances() -> None:
    pernas = multiplas.melhor_selecao_por_jogo(_candidatos()).head(3)
    resumo = multiplas.resumir(pernas, 3, 0)
    assert resumo["prob_modelo"] == pytest.approx(float(np.prod(pernas["prob"])))


def test_a_chance_de_uma_multipla_fica_entre_0_e_1() -> None:
    por_jogo = multiplas.melhor_selecao_por_jogo(_candidatos())
    for tamanho in (2, 3, 4):
        resumo = multiplas.resumir(por_jogo.head(tamanho), tamanho, 0)
        assert 0.0 < resumo["prob_modelo"] < 1.0
        assert 0.0 < resumo["prob_implicita"] < 1.0


def test_acrescentar_selecao_so_diminui_a_chance() -> None:
    """A verdade central da fase, em forma de teste."""
    por_jogo = multiplas.melhor_selecao_por_jogo(_candidatos())
    chances = [
        multiplas.resumir(por_jogo.head(k), k, 0)["prob_modelo"] for k in range(1, 6)
    ]
    assert chances == sorted(chances, reverse=True)


def test_a_margem_acumulada_cresce_com_o_tamanho() -> None:
    """A comissão de cada perna se multiplica — e é o achado principal."""
    por_jogo = multiplas.melhor_selecao_por_jogo(_candidatos())
    margens = [
        multiplas.resumir(por_jogo.head(k), k, 0)["margem_acumulada"]
        for k in range(1, 6)
    ]
    assert margens == sorted(margens)


def test_a_margem_acumulada_bate_com_a_formula() -> None:
    """Com 5% por seleção, três seleções custam ``1,05³ − 1 = 15,76%``."""
    por_jogo = multiplas.melhor_selecao_por_jogo(_candidatos())
    resumo = multiplas.resumir(por_jogo.head(3), 3, 0)
    assert resumo["margem_acumulada"] == pytest.approx(
        multiplas.margem_teorica(0.05, 3), rel=1e-6
    )


def test_a_formula_da_margem_teorica() -> None:
    assert multiplas.margem_teorica(0.06, 1) == pytest.approx(0.06)
    assert multiplas.margem_teorica(0.06, 3) == pytest.approx(1.06**3 - 1)


def test_o_bilhete_so_ganha_se_todas_as_selecoes_ganharem() -> None:
    pernas = multiplas.melhor_selecao_por_jogo(_candidatos()).head(4)
    resumo = multiplas.resumir(pernas, 4, 0)
    assert resumo["acertos"] == int(pernas["ganhou"].sum())
    assert bool(resumo["ganhou"]) == (resumo["acertos"] == 4)


def test_o_retorno_de_um_bilhete_vencedor_e_a_odd_menos_um() -> None:
    """Um bilhete em que todas as pernas ganharam."""
    pernas = _candidatos(n_jogos=4).query("selecao == 'H' and mandante in ['ENG:0']")
    resumo = multiplas.resumir(pernas, len(pernas), 0)
    assert bool(resumo["ganhou"])
    assert resumo["retorno_unitario"] == pytest.approx(resumo["odd_total"] - 1.0)


# ----------------------------------------------------------------------------
# A faixa de odd
# ----------------------------------------------------------------------------
def test_a_faixa_de_odd_descarta_os_extremos() -> None:
    candidatos = _candidatos()
    candidatos.loc[0, "odd"] = 1.05  # abaixo do mínimo
    candidatos.loc[1, "odd"] = 9.90  # acima do máximo
    dentro = multiplas.elegiveis(candidatos, CONFIG)
    assert len(dentro) == len(candidatos) - 2
    assert dentro["odd"].between(1.20, 5.00).all()


# ----------------------------------------------------------------------------
# O histórico
# ----------------------------------------------------------------------------
def _historico() -> multiplas.Historico:
    rodadas = pd.concat(
        [_candidatos(data=f"2022-01-0{dia}") for dia in range(1, 6)], ignore_index=True
    )
    return multiplas.montar_historico(rodadas, CONFIG)


def test_o_historico_traz_bilhetes_e_pernas_casados() -> None:
    historico = _historico()
    assert set(historico.pernas["id"]) == set(historico.multiplas["id"])
    contagem = historico.pernas.groupby("id").size()
    esperado = historico.multiplas.set_index("id")["tamanho"]
    pd.testing.assert_series_equal(
        contagem.sort_index(), esperado.sort_index(), check_names=False
    )


def test_o_historico_monta_os_tamanhos_pedidos() -> None:
    historico = multiplas.montar_historico(_candidatos(), CONFIG, tamanhos=(2, 3))
    assert set(historico.multiplas["tamanho"]) == {2, 3}


def test_historico_sem_jogo_e_erro_em_vez_de_tabela_vazia() -> None:
    """Falhar alto: uma medição de zero bilhetes não pode passar despercebida."""
    with pytest.raises(ValueError, match="Nenhuma múltipla montada"):
        multiplas.montar_historico(_candidatos(n_jogos=1), CONFIG)


# ----------------------------------------------------------------------------
# A medição
# ----------------------------------------------------------------------------
def test_a_medicao_cobre_todos_os_bilhetes() -> None:
    historico = _historico()
    tabela = multiplas.medir_por_tamanho(
        historico.multiplas, amostras_bootstrap=200
    )
    assert int(tabela["multiplas"].sum()) == len(historico.multiplas)


def test_a_taxa_real_e_a_fracao_que_ganhou() -> None:
    historico = _historico()
    tabela = multiplas.medir_por_tamanho(historico.multiplas, amostras_bootstrap=200)
    for _, linha in tabela.iterrows():
        do_tamanho = historico.multiplas.query("tamanho == @linha.tamanho")
        assert linha["real"] == pytest.approx(do_tamanho["ganhou"].mean())


def test_a_razao_por_selecao_e_constante_quando_o_erro_e_por_perna() -> None:
    """O diagnóstico central da fase, num caso construído.

    Se o modelo exagera a chance de **cada** seleção por um fator fixo, a razão
    entre a previsão do mercado e a do modelo, tirada a raiz do tamanho do
    bilhete, tem de sair igual em todos os tamanhos. É essa constância que
    separa "o modelo erra por perna" de "há correlação entre jogos".
    """
    candidatos = pd.concat(
        [_candidatos(data=f"2022-02-0{dia}") for dia in range(1, 6)], ignore_index=True
    )
    # O mercado acha tudo 10% menos provável que o modelo, em toda seleção.
    candidatos["prob_justa"] = candidatos["prob"] * 0.90
    historico = multiplas.montar_historico(candidatos, CONFIG)
    tabela = multiplas.medir_por_tamanho(historico.multiplas, amostras_bootstrap=100)

    assert tabela["razao_por_selecao"].to_numpy() == pytest.approx(0.90, abs=1e-9)


def test_o_desvio_relativo_e_o_desvio_dividido_pela_previsao() -> None:
    historico = _historico()
    tabela = multiplas.medir_por_tamanho(historico.multiplas, amostras_bootstrap=200)
    esperado = tabela["desvio"] / tabela["prevista_modelo"]
    assert tabela["desvio_relativo"].to_numpy() == pytest.approx(esperado.to_numpy())


def test_o_menor_efeito_detectavel_cresce_quando_a_chance_cai() -> None:
    """Regra 10: em bilhete grande, "não detectei" quer dizer muito menos."""
    historico = _historico()
    tabela = multiplas.medir_por_tamanho(historico.multiplas, amostras_bootstrap=200)
    assert (
        tabela.sort_values("tamanho")["detectavel_relativo"].is_monotonic_increasing
    )
