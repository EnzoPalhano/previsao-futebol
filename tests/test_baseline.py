"""Testes do modelo burro: ele tem que devolver o histórico da liga, e só.

Um baseline errado é pior que nenhum: ele vira a régua da Fase 4, e uma régua
torta faria um modelo ruim parecer bom. Por isso os números aqui são conferidos
à mão, em tabelas pequenas escritas no próprio teste.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futebol.modelos import base
from futebol.modelos.baseline import MINIMO_DE_JOGOS, Baseline, contar_placares


def _jogos(placares: list[tuple[int, int]], liga: str = "E0") -> pd.DataFrame:
    """Uma tabela de jogos a partir de uma lista de placares."""
    return pd.DataFrame(
        {
            "data": pd.date_range("2024-01-01", periods=len(placares), freq="7D"),
            "liga": [liga] * len(placares),
            "temporada": ["2023/24"] * len(placares),
            "mandante": [f"{liga}:M{i}" for i in range(len(placares))],
            "visitante": [f"{liga}:V{i}" for i in range(len(placares))],
            "gols_mandante": [p[0] for p in placares],
            "gols_visitante": [p[1] for p in placares],
        }
    )


#: Quatro placares, repetidos até passar do mínimo de jogos da liga:
#: 1x0 (mandante), 1x1 (empate, ambos marcam), 0x2 (visitante), 2x1 (mandante,
#: ambos marcam, over 2,5).
PLACARES = [(1, 0), (1, 1), (0, 2), (2, 1)] * 10


# ----------------------------------------------------------------------------
# A contagem de placares
# ----------------------------------------------------------------------------
def test_frequencia_de_cada_placar() -> None:
    matriz = contar_placares(_jogos(PLACARES), max_gols=5)
    assert matriz.sum() == pytest.approx(1.0)
    for placar in [(1, 0), (1, 1), (0, 2), (2, 1)]:
        assert matriz[placar] == pytest.approx(0.25)
    assert matriz[3, 3] == 0.0


def test_goleada_acima_do_limite_vai_para_a_borda() -> None:
    """Descartar o jogo inflaria a frequência de todos os outros placares."""
    matriz = contar_placares(_jogos([(9, 0), (1, 0)]), max_gols=3)
    assert matriz.shape == (4, 4)
    assert matriz[3, 0] == pytest.approx(0.5), "o 9x0 foi contado no 3x0"
    assert matriz.sum() == pytest.approx(1.0)


# ----------------------------------------------------------------------------
# O modelo
# ----------------------------------------------------------------------------
def test_mercados_conferidos_na_mao() -> None:
    modelo = Baseline(max_gols=5).treinar(_jogos(PLACARES))
    previsao = modelo.prever(base.Jogo("E0", "E0:M0", "E0:V0"))

    assert previsao["H"] == pytest.approx(0.5), "1x0 e 2x1"
    assert previsao["D"] == pytest.approx(0.25), "1x1"
    assert previsao["A"] == pytest.approx(0.25), "0x2"
    assert previsao["over25"] == pytest.approx(0.25), "só o 2x1 soma 3 gols"
    assert previsao["ambos_marcam"] == pytest.approx(0.5), "1x1 e 2x1"


def test_probabilidades_somam_um_e_nao_sao_negativas() -> None:
    modelo = Baseline(max_gols=5).treinar(_jogos(PLACARES))
    previsao = modelo.prever(base.Jogo("E0", "E0:M0", "E0:V0"))
    for grupo in base.GRUPOS_COMPLEMENTARES:
        assert sum(previsao[chave] for chave in grupo) == pytest.approx(1.0)
    assert all(valor >= 0 for valor in previsao.values())


def test_o_modelo_ignora_quem_joga() -> None:
    """É isso que o torna o modelo burro — e a régua."""
    modelo = Baseline(max_gols=5).treinar(_jogos(PLACARES))
    um = modelo.prever(base.Jogo("E0", "E0:M0", "E0:V1"))
    outro = modelo.prever(base.Jogo("E0", "E0:M3", "E0:V2"))
    assert um == outro


def test_cada_liga_tem_a_sua_estatistica() -> None:
    """Liga com mais gol tem que prever mais gol."""
    muitos_gols = _jogos([(3, 2)] * 40, liga="N1")
    poucos_gols = _jogos([(0, 0)] * 40, liga="I1")
    modelo = Baseline(max_gols=5).treinar(pd.concat([muitos_gols, poucos_gols]))

    assert modelo.prever(base.Jogo("N1", "N1:M0", "N1:V0"))["over25"] == pytest.approx(1.0)
    assert modelo.prever(base.Jogo("I1", "I1:M0", "I1:V0"))["over25"] == pytest.approx(0.0)


def test_liga_desconhecida_cai_na_media_geral() -> None:
    """O app pode pedir uma liga que não estava no treino; quebrar seria pior."""
    modelo = Baseline(max_gols=5).treinar(_jogos(PLACARES))
    da_liga_nova = modelo.prever(base.Jogo("XX", "XX:M0", "XX:V0"))
    assert da_liga_nova == pytest.approx(modelo.geral.mercados())


def test_liga_pequena_demais_nao_ganha_estatistica_propria() -> None:
    grande = _jogos([(1, 0)] * MINIMO_DE_JOGOS, liga="E0")
    pequena = _jogos([(0, 3)] * (MINIMO_DE_JOGOS - 1), liga="SC3")
    modelo = Baseline(max_gols=5).treinar(pd.concat([grande, pequena]))

    assert "E0" in modelo.ligas
    assert "SC3" not in modelo.ligas, "poucos jogos: frequência é mais ruído que sinal"


def test_placar_mais_provavel() -> None:
    modelo = Baseline(max_gols=5).treinar(_jogos([(1, 1)] * 30 + [(2, 0)] * 10))
    assert modelo.placar_mais_provavel(base.Jogo("E0", "E0:M0", "E0:V0")) == (
        1,
        1,
        pytest.approx(0.75),
    )


def test_respeita_o_corte_de_data() -> None:
    """A trava da classe base tem que valer aqui também (regra 6)."""
    jogos = _jogos([(1, 0)] * 30 + [(0, 5)] * 30)
    corte = jogos.loc[30, "data"]
    modelo = Baseline(max_gols=5).treinar(jogos, ate_data=corte)

    previsao = modelo.prever(base.Jogo("E0", "E0:M0", "E0:V0"))
    assert previsao["H"] == pytest.approx(1.0), "só os 1x0 anteriores ao corte entraram"
    assert modelo.ultima_data_de_treino < corte


def test_resumo_tem_uma_linha_por_liga() -> None:
    modelo = Baseline(max_gols=5).treinar(
        pd.concat([_jogos(PLACARES, liga="E0"), _jogos(PLACARES, liga="SP1")])
    )
    resumo = modelo.resumo()
    assert sorted(resumo["liga"]) == ["E0", "SP1"]
    assert (resumo["jogos"] == 40).all()
    assert np.allclose(resumo[["H", "D", "A"]].sum(axis=1), 1.0)
