"""Testes da leitura do mercado: medir a margem e tirá-la sem inventar nada.

Os números conferidos aqui na mão importam porque tudo que vem depois — o
baseline que os modelos precisam bater, o EV do backtest, o CLV — é calculado
em cima destas probabilidades. Um erro aqui não apareceria como erro:
apareceria como um modelo que parece bom.
"""

from __future__ import annotations

import numpy as np
import pytest

from futebol.odds import mercado

#: Um 1X2 com margem folgada, fácil de conferir na mão:
#: 1/1,6 + 1/3,2 + 1/3,2 = 0,625 + 0,3125 + 0,3125 = 1,25.
JOGO_SIMPLES = [1.6, 3.2, 3.2]

#: O mesmo jogo sem nenhuma margem: as implícitas já somam 1,00.
JOGO_JUSTO = [2.0, 4.0, 4.0]

#: Um jogo real da Premier League (Liverpool x Norwich, 2019/20), com um
#: favorito pesadíssimo. É onde os métodos mais discordam.
JOGO_DESEQUILIBRADO = [1.14, 8.75, 19.83]


# ----------------------------------------------------------------------------
# Probabilidade implícita e margem
# ----------------------------------------------------------------------------
def test_probabilidade_implicita_e_um_sobre_a_odd() -> None:
    assert mercado.probabilidade_implicita([2.0, 4.0]) == pytest.approx([0.5, 0.25])


def test_probabilidades_implicitas_nao_somam_um() -> None:
    """O que sobra de 100% é exatamente a margem da casa."""
    probabilidades = mercado.probabilidade_implicita(JOGO_SIMPLES)
    assert probabilidades.sum() == pytest.approx(1.25)


def test_overround_e_o_numero_da_secao_4_3() -> None:
    """Premier League 2024/25, 1X2 de fechamento: 4,19% na especificação."""
    assert mercado.overround(JOGO_SIMPLES) == pytest.approx(0.25)
    assert mercado.overround([1.8, 3.6, 4.2]) == pytest.approx(0.0714286, abs=1e-6)


def test_mercado_justo_tem_overround_zero() -> None:
    assert mercado.overround(JOGO_JUSTO) == pytest.approx(0.0)
    assert mercado.overround([2.0, 2.0]) == pytest.approx(0.0)


def test_fatia_da_casa_e_menor_que_o_overround() -> None:
    """São o mesmo fato visto dos dois lados; confundi-los infla o número."""
    over = mercado.overround(JOGO_SIMPLES)
    fatia = mercado.fatia_da_casa(JOGO_SIMPLES)
    assert fatia == pytest.approx(over / (1 + over))
    assert fatia < over


def test_odd_impossivel_e_recusada() -> None:
    """Odd 1,00 pagaria de volta o que foi apostado: não é odd."""
    with pytest.raises(mercado.ErroDeMercado, match="menor ou igual"):
        mercado.probabilidade_implicita([1.0, 5.0])


# ----------------------------------------------------------------------------
# Remoção de margem: o que os três métodos têm em comum
# ----------------------------------------------------------------------------
@pytest.mark.parametrize("metodo", mercado.METODOS)
def test_probabilidades_sem_margem_somam_um(metodo: str) -> None:
    for jogo in (JOGO_SIMPLES, JOGO_DESEQUILIBRADO, [1.9, 1.9]):
        assert mercado.remover_margem(jogo, metodo).sum() == pytest.approx(1.0)


@pytest.mark.parametrize("metodo", mercado.METODOS)
def test_a_ordem_das_opcoes_nunca_muda(metodo: str) -> None:
    """Tirar margem redistribui, mas o favorito continua favorito."""
    probabilidades = mercado.remover_margem([1.5, 4.0, 7.0], metodo)
    assert probabilidades[0] > probabilidades[1] > probabilidades[2]


@pytest.mark.parametrize("metodo", mercado.METODOS)
def test_mercado_sem_margem_passa_intacto(metodo: str) -> None:
    """Se não há comissão para tirar, os três métodos concordam: não mexem."""
    assert mercado.overround(JOGO_JUSTO) == pytest.approx(0.0)
    assert mercado.remover_margem(JOGO_JUSTO, metodo) == pytest.approx(
        [0.5, 0.25, 0.25], abs=1e-9
    )


@pytest.mark.parametrize("metodo", mercado.METODOS)
def test_mercado_de_duas_opcoes_funciona(metodo: str) -> None:
    """Over/Under 2,5 tem duas pontas, não três."""
    probabilidades = mercado.remover_margem([1.9, 1.95], metodo)
    assert probabilidades.sum() == pytest.approx(1.0)
    assert probabilidades[0] > probabilidades[1]


# ----------------------------------------------------------------------------
# Remoção de margem: onde os métodos discordam — e por quê
# ----------------------------------------------------------------------------
def test_proporcional_da_mais_chance_ao_azarao_que_shin_e_power() -> None:
    """O ponto da Fase 2: o método escolhido muda a conta do azarão.

    Shin e power assumem que a casa cobrou comissão maior no azarão (viés
    favorito-azarão). Ao desfazer isso, sobra menos probabilidade para ele —
    e mais para o favorito.
    """
    proporcional = mercado.remover_margem(JOGO_DESEQUILIBRADO, "proporcional")
    shin = mercado.remover_margem(JOGO_DESEQUILIBRADO, "shin")
    power = mercado.remover_margem(JOGO_DESEQUILIBRADO, "power")

    azarao = -1
    favorito = 0
    assert proporcional[azarao] > shin[azarao] > power[azarao]
    assert proporcional[favorito] < shin[favorito] < power[favorito]


def test_a_discordancia_e_pequena_em_jogo_equilibrado() -> None:
    """Num jogo parelho os três métodos quase coincidem: o viés vive nas pontas."""
    equilibrado = [2.9, 3.1, 2.9]
    proporcional = mercado.remover_margem(equilibrado, "proporcional")
    shin = mercado.remover_margem(equilibrado, "shin")
    assert np.max(np.abs(proporcional - shin)) < 0.005


def test_z_de_shin_fica_entre_zero_e_um_e_cresce_com_a_margem() -> None:
    """z é a fração de dinheiro informado que a casa supõe estar enfrentando."""
    pouca = mercado.probabilidade_implicita(np.array([[2.02, 2.02]]))
    muita = mercado.probabilidade_implicita(np.array([[1.7, 1.7]]))

    z_pouca = mercado.z_de_shin(pouca)[0]
    z_muita = mercado.z_de_shin(muita)[0]
    assert 0.0 <= z_pouca < z_muita < 1.0


# ----------------------------------------------------------------------------
# Formato de entrada e de saída
# ----------------------------------------------------------------------------
def test_tabela_inteira_de_uma_vez() -> None:
    odds = np.array([[2.0, 4.0, 4.0], [1.5, 4.0, 7.0]])
    probabilidades = mercado.remover_margem(odds, "shin")

    assert probabilidades.shape == (2, 3)
    assert probabilidades.sum(axis=1) == pytest.approx([1.0, 1.0])


@pytest.mark.parametrize("metodo", mercado.METODOS)
def test_jogo_sem_odd_completa_vira_vazio(metodo: str) -> None:
    """Regra do projeto: odd que não existe vira vazio, nunca valor chutado."""
    odds = np.array([[2.0, 4.0, 4.0], [np.nan, 3.0, 3.0]])
    probabilidades = mercado.remover_margem(odds, metodo)

    assert probabilidades[0].sum() == pytest.approx(1.0)
    assert np.isnan(probabilidades[1]).all()


def test_um_jogo_volta_como_um_jogo() -> None:
    assert mercado.remover_margem(JOGO_SIMPLES, "power").shape == (3,)


def test_metodo_desconhecido_lista_os_que_existem() -> None:
    with pytest.raises(mercado.ErroDeMercado, match="proporcional"):
        mercado.remover_margem(JOGO_SIMPLES, "magica")
