"""Testes do cash out.

O achado da fase é uma **identidade**, não uma medição: o valor esperado de
sacar é o de não sacar multiplicado por ``(1 − taxa)``, qualquer que seja o
momento do saque. Uma identidade se testa exigindo que ela valha exatamente, e é
o que os testes abaixo fazem — num caso construído à mão, onde a resposta certa
é calculável no papel.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from futebol.backtest import cash_out, multiplas
from futebol.config import Config

MARGEM = 0.08

CONFIG = Config(
    bruto={
        "multiplas": {
            "min_selecoes": 1,
            "max_selecoes": 4,
            "odd_minima_selecao": 1.0,
            "odd_maxima_selecao": 100.0,
            "uma_selecao_por_jogo": True,
            "beam_width": 10,
            "cash_out_margem_casa": MARGEM,
        }
    },
    seed=42,
    raiz=Path("."),
)


# ----------------------------------------------------------------------------
# As contas soltas
# ----------------------------------------------------------------------------
def test_o_valor_justo_e_a_chance_vezes_o_premio() -> None:
    assert cash_out.valor_justo(0.25, 200.0) == pytest.approx(50.0)


def test_a_oferta_e_o_justo_menos_a_taxa() -> None:
    assert cash_out.oferta(0.25, 200.0, 0.08) == pytest.approx(46.0)


def test_taxa_zero_devolve_o_valor_justo() -> None:
    assert cash_out.oferta(0.4, 100.0, 0.0) == pytest.approx(
        cash_out.valor_justo(0.4, 100.0)
    )


def test_a_margem_sai_do_config() -> None:
    assert cash_out.margem_da_casa(CONFIG) == pytest.approx(MARGEM)


# ----------------------------------------------------------------------------
# Monte Carlo — o uso legítimo dele nesta fase
# ----------------------------------------------------------------------------
def test_a_distribuicao_de_acertos_soma_um() -> None:
    d = cash_out.distribuicao_de_acertos([0.6] * 5, repeticoes=5000)
    assert len(d) == 6
    assert d.sum() == pytest.approx(1.0)


def test_a_chance_de_acertar_tudo_bate_com_o_produto() -> None:
    """O sorteio independente reproduz o produto — é exatamente o aviso de 7.1."""
    probabilidades = [0.7, 0.6, 0.5]
    d = cash_out.distribuicao_de_acertos(probabilidades, repeticoes=200_000, seed=1)
    assert d[-1] == pytest.approx(float(np.prod(probabilidades)), abs=0.005)


def test_a_distribuicao_e_reproduzivel() -> None:
    primeira = cash_out.distribuicao_de_acertos([0.5] * 4, repeticoes=2000, seed=7)
    segunda = cash_out.distribuicao_de_acertos([0.5] * 4, repeticoes=2000, seed=7)
    assert primeira == pytest.approx(segunda)


def test_certeza_absoluta_concentra_tudo_no_topo() -> None:
    d = cash_out.distribuicao_de_acertos([1.0, 1.0, 1.0], repeticoes=500)
    assert d[3] == pytest.approx(1.0)


# ----------------------------------------------------------------------------
# As estratégias
# ----------------------------------------------------------------------------
def _historico(n_rodadas: int = 40) -> multiplas.Historico:
    """Bilhetes em que a odd é exatamente a justa mais 5% de comissão."""
    gerador = np.random.default_rng(3)
    linhas = []
    for dia in range(n_rodadas):
        for jogo in range(4):
            justa = 0.55 + 0.05 * ((dia + jogo) % 3)
            linhas.append(
                {
                    "data": pd.Timestamp("2022-01-01") + pd.Timedelta(days=dia),
                    "liga": "E0",
                    "mandante": f"ENG:{jogo}",
                    "visitante": f"ENG:{jogo + 100}",
                    "selecao": "H",
                    "mercado": "1x2",
                    "prob": justa,
                    "odd": 1.0 / (justa * 1.05),
                    "prob_justa": justa,
                    "ganhou": bool(gerador.random() < justa),
                }
            )
    return multiplas.montar_historico(pd.DataFrame(linhas), CONFIG, tamanhos=(2, 4))


def test_sacar_custa_exatamente_a_taxa_qualquer_que_seja_o_momento() -> None:
    """A identidade que é o achado da seção de cash out.

    ``EV(sacar) = EV(não sacar) × (1 − taxa)`` — e o lado direito não depende do
    ponto de saque. Se este teste cair, ou a conta do valor esperado está errada,
    ou alguém introduziu dependência do resultado onde não podia haver.
    """
    estrategias = cash_out.simular(_historico(), CONFIG, tamanho=4, amostras_bootstrap=100)
    nunca = estrategias[0]
    saques = [e for e in estrategias if e.nome.startswith("sacar após")]

    assert len(saques) == 3  # os três pontos de decisão de um bilhete de quatro
    esperado = (1.0 + nunca.ev_mercado) * (1.0 - MARGEM) - 1.0
    for estrategia in saques:
        assert estrategia.ev_mercado == pytest.approx(esperado)


def test_sacar_sempre_e_pior_que_nunca_sacar() -> None:
    """Consequência direta da identidade: a taxa é dinheiro que some."""
    estrategias = cash_out.simular(_historico(), CONFIG, tamanho=4, amostras_bootstrap=100)
    nunca = estrategias[0]
    for estrategia in estrategias[1:-1]:
        assert estrategia.ev_mercado < nunca.ev_mercado


def test_taxa_zero_torna_o_cash_out_indiferente() -> None:
    """Sem taxa, sacar e não sacar valem o mesmo — o que confirma a conta."""
    sem_taxa = Config(
        bruto={"multiplas": {**CONFIG.bruto["multiplas"], "cash_out_margem_casa": 0.0}},
        seed=42,
        raiz=Path("."),
    )
    estrategias = cash_out.simular(
        _historico(), sem_taxa, tamanho=4, amostras_bootstrap=100
    )
    nunca = estrategias[0]
    for estrategia in estrategias[1:]:
        assert estrategia.ev_mercado == pytest.approx(nunca.ev_mercado)


def test_a_regra_que_usa_informacao_fica_entre_as_duas() -> None:
    """Ela só paga a taxa em parte dos bilhetes, então fica no meio."""
    estrategias = cash_out.simular(_historico(), CONFIG, tamanho=4, amostras_bootstrap=100)
    nunca, sacar_sempre, quando = estrategias[0], estrategias[1], estrategias[-1]
    assert sacar_sempre.ev_mercado <= quando.ev_mercado <= nunca.ev_mercado


def test_a_fracao_que_saca_cai_conforme_o_ponto_avanca() -> None:
    """Sacar depois de três acertos exige sobreviver a três — acontece menos."""
    estrategias = cash_out.simular(_historico(), CONFIG, tamanho=4, amostras_bootstrap=100)
    saques = [e.sacou for e in estrategias if e.nome.startswith("sacar após")]
    assert saques == sorted(saques, reverse=True)


def test_quem_perde_antes_do_ponto_de_saque_perde_a_aposta() -> None:
    """Não existe sacar depois de já ter perdido: o retorno é −1."""
    estrategias = cash_out.simular(_historico(), CONFIG, tamanho=2, amostras_bootstrap=100)
    sacar = [e for e in estrategias if e.nome.startswith("sacar após")][0]
    # Quem não sacou perdeu tudo; quem sacou recebeu a oferta.
    assert -1.0 <= sacar.roi <= 1.0
    assert 0.0 < sacar.sacou < 1.0


def test_tamanho_inexistente_devolve_lista_vazia() -> None:
    assert cash_out.simular(_historico(), CONFIG, tamanho=7) == []


def test_a_tabela_traz_as_duas_medidas_de_retorno() -> None:
    """A realizada (ruidosa) e a esperada (limpa) — a segunda é a que decide."""
    tabela = cash_out.como_tabela(
        cash_out.simular(_historico(), CONFIG, tamanho=4, amostras_bootstrap=100)
    )
    assert {"roi", "ev_mercado", "roi_baixo", "roi_alto"} <= set(tabela.columns)
    assert len(tabela) == 5  # nunca + 3 pontos de saque + a regra informada
