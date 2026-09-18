"""Testes das regras de stake e da conta da banca.

Um erro aqui não apareceria como erro: apareceria como um lucro. É o tipo de
bug que um backtest carrega até o fim sem dar nenhum sinal, porque o número que
sai continua sendo um número plausível.

Os valores conferidos são todos calculáveis na mão, de propósito.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futebol.backtest import estrategias


def _apostas(retornos, odds=None, probs=None, datas=None) -> pd.DataFrame:
    """Uma tabela de apostas mínima, com o retorno de cada uma já decidido."""
    n = len(retornos)
    return pd.DataFrame(
        {
            "data": pd.to_datetime(
                datas if datas is not None else pd.date_range("2022-01-01", periods=n)
            ),
            "prob": probs if probs is not None else np.full(n, 0.5),
            "odd": odds if odds is not None else np.full(n, 2.0),
            "retorno_unitario": np.asarray(retornos, dtype=float),
        }
    )


# ----------------------------------------------------------------------------
# Stake fixa
# ----------------------------------------------------------------------------
def test_stake_fixa_ignora_probabilidade_e_odd() -> None:
    """O ponto da estratégia: a mesma fração, sempre."""
    fixa = estrategias.StakeFixa(0.01)
    fracoes = fixa.fracao(np.array([0.10, 0.90]), np.array([15.0, 1.05]))
    assert fracoes == pytest.approx([0.01, 0.01])


def test_stake_fixa_recusa_fracao_impossivel() -> None:
    with pytest.raises(ValueError, match="entre 0 e 1"):
        estrategias.StakeFixa(1.5)


# ----------------------------------------------------------------------------
# Kelly
# ----------------------------------------------------------------------------
def test_kelly_reproduz_a_formula_na_mao() -> None:
    """p = 0,6 em odd 2,0: f* = (0,6·2 − 1)/(2 − 1) = 0,2; um quarto disso."""
    kelly = estrategias.KellyFracionado(fracao=0.25, teto=1.0)
    assert kelly.fracao(np.array([0.6]), np.array([2.0])) == pytest.approx([0.05])


def test_kelly_nao_aposta_contra_si_mesmo() -> None:
    """Vantagem negativa dá fração zero, nunca negativa."""
    kelly = estrategias.KellyFracionado()
    assert kelly.fracao(np.array([0.30]), np.array([2.0])) == pytest.approx([0.0])


def test_o_teto_segura_a_vantagem_absurda() -> None:
    """Vantagem enorme num azarão quase sempre é erro de modelo, não sorte."""
    kelly = estrategias.KellyFracionado(fracao=0.25, teto=0.05)
    sem_teto = (0.5 * 15.0 - 1.0) / 14.0 * 0.25
    assert sem_teto > 0.05
    assert kelly.fracao(np.array([0.5]), np.array([15.0])) == pytest.approx([0.05])


def test_criar_le_os_parametros_do_config() -> None:
    estrategia = estrategias.criar(
        "kelly_fracionado", {"kelly_fracao": 0.5, "kelly_teto_pct": 0.1}
    )
    assert isinstance(estrategia, estrategias.KellyFracionado)
    assert estrategia.fracao_kelly == 0.5
    assert estrategia.teto == 0.1


def test_criar_recusa_estrategia_desconhecida() -> None:
    with pytest.raises(ValueError, match="stake_fixa, kelly_fracionado"):
        estrategias.criar("martingale", {})


# ----------------------------------------------------------------------------
# A banca
# ----------------------------------------------------------------------------
def test_banca_fixa_soma_resultados_sem_compor() -> None:
    """Três apostas de 10 reais: ganha, ganha, perde. 1.000 + 10 + 10 − 10."""
    apostas = _apostas([1.0, 1.0, -1.0])
    evolucao = estrategias.simular_banca(
        apostas, estrategias.StakeFixa(0.01), 1000.0, "fixa"
    )
    assert evolucao.banca_final == pytest.approx(1010.0)
    assert evolucao.total_apostado == pytest.approx(30.0)
    assert evolucao.roi == pytest.approx(10.0 / 30.0)


def test_banca_composta_aposta_sobre_a_banca_atual() -> None:
    """Ganhando, a stake seguinte é maior — e é isso que compor significa."""
    apostas = _apostas([1.0, 1.0])
    evolucao = estrategias.simular_banca(
        apostas, estrategias.StakeFixa(0.10), 1000.0, "composta"
    )
    # 1.000 → aposta 100, ganha 100 → 1.100 → aposta 110, ganha 110 → 1.210.
    assert evolucao.banca_final == pytest.approx(1210.0)
    assert evolucao.total_apostado == pytest.approx(210.0)


def test_a_composta_so_difere_da_fixa_quando_a_banca_se_mexe() -> None:
    """Sanidade: com uma aposta só, as duas variantes são idênticas."""
    apostas = _apostas([1.0])
    fixa = estrategias.simular_banca(apostas, estrategias.StakeFixa(0.01), 1000.0, "fixa")
    composta = estrategias.simular_banca(
        apostas, estrategias.StakeFixa(0.01), 1000.0, "composta"
    )
    assert fixa.banca_final == pytest.approx(composta.banca_final)


def test_a_ordem_dentro_do_dia_nao_muda_nada() -> None:
    """O motivo de a banca ser resolvida por bloco de data, e não aposta a aposta.

    Se a stake do jogo das 18h dependesse do resultado do jogo das 16h, o
    backtest usaria informação que o apostador não tinha — e o resultado passaria
    a depender da ordem das linhas na tabela, que é arbitrária.
    """
    mesmo_dia = ["2022-01-01"] * 4
    apostas = _apostas([1.0, -1.0, 2.0, -1.0], datas=mesmo_dia)
    embaralhada = apostas.iloc[[3, 1, 0, 2]].reset_index(drop=True)

    estrategia = estrategias.StakeFixa(0.05)
    primeira = estrategias.simular_banca(apostas, estrategia, 1000.0, "composta")
    segunda = estrategias.simular_banca(embaralhada, estrategia, 1000.0, "composta")
    assert primeira.banca_final == pytest.approx(segunda.banca_final)


def test_nunca_se_aposta_dinheiro_que_nao_existe() -> None:
    """Trinta apostas de 5% num dia só pediriam 150% da banca."""
    apostas = _apostas([-1.0] * 30, datas=["2022-01-01"] * 30)
    evolucao = estrategias.simular_banca(
        apostas, estrategias.StakeFixa(0.05), 1000.0, "fixa"
    )
    assert evolucao.total_apostado == pytest.approx(1000.0)
    assert evolucao.datas_racionadas == 1
    assert evolucao.quebrou


def test_a_banca_para_quando_acaba() -> None:
    """Depois de zerar, não há aposta seguinte — nem lucro seguinte."""
    apostas = _apostas([-1.0] * 5, datas=["2022-01-01"] * 4 + ["2022-02-01"])
    evolucao = estrategias.simular_banca(
        apostas, estrategias.StakeFixa(0.30), 1000.0, "fixa"
    )
    assert evolucao.quebrou
    assert evolucao.banca_final == 0.0
    assert len(evolucao.curva) == 1


def test_a_banca_final_nao_e_recalculada_pelo_lucro() -> None:
    """Uma banca de centavos não pode virar zero por cancelamento de float.

    Perder 999,999999999 de uma banca de 1.000 dá lucro ``-1000.0`` arredondado;
    refazer ``inicial + lucro`` devolveria zero e apagaria a diferença entre
    "sobrou quase nada" e "acabou". São situações diferentes: a segunda para de
    apostar, a primeira não.
    """
    apostas = _apostas([-1.0] * 300, datas=pd.date_range("2022-01-01", periods=300))
    evolucao = estrategias.simular_banca(
        apostas, estrategias.StakeFixa(0.10), 1000.0, "composta"
    )
    assert 0 < evolucao.banca_final < 1e-6
    assert not evolucao.quebrou


def test_tipo_de_banca_desconhecido_e_erro() -> None:
    with pytest.raises(ValueError, match="'fixa' ou 'composta'"):
        estrategias.simular_banca(
            _apostas([1.0]), estrategias.StakeFixa(), 1000.0, "martingale"
        )


def test_tabela_sem_as_colunas_certas_e_erro() -> None:
    incompleta = pd.DataFrame({"data": pd.to_datetime(["2022-01-01"])})
    with pytest.raises(ValueError, match="não tem as colunas"):
        estrategias.simular_banca(incompleta, estrategias.StakeFixa(), 1000.0)


# ----------------------------------------------------------------------------
# Drawdown
# ----------------------------------------------------------------------------
def test_drawdown_mede_do_topo_ate_o_fundo_seguinte() -> None:
    """Sobe para 2.000, cai para 500: o pior momento é 75% abaixo do topo."""
    banca = pd.Series([1500.0, 2000.0, 500.0, 900.0])
    assert estrategias.drawdown_maximo(banca, 1000.0) == pytest.approx(0.75)


def test_drawdown_conta_a_queda_logo_na_primeira_aposta() -> None:
    """O topo começa na banca inicial: perder de cara também é drawdown."""
    banca = pd.Series([800.0, 900.0])
    assert estrategias.drawdown_maximo(banca, 1000.0) == pytest.approx(0.20)


def test_drawdown_de_serie_so_de_alta_e_zero() -> None:
    banca = pd.Series([1100.0, 1200.0, 1300.0])
    assert estrategias.drawdown_maximo(banca, 1000.0) == pytest.approx(0.0)
