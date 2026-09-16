"""Testes do filtro de qualidade: quem entra no backtest e por quê.

Este filtro é a resposta do projeto para "quero as ligas com apostas boas".
Se ele aprovar uma liga que não deveria, o erro só apareceria na Fase 6, em
forma de ROI bonito e sem sentido. Cada critério tem seu teste.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futebol.avaliacao import filtro
from futebol.config import Config
from futebol.dados import limpeza


def config_de_teste(**cortes) -> Config:
    """Config só com a seção que o filtro lê."""
    padrao = {
        "margem_maxima": 0.08,
        "cobertura_minima_odds": 0.90,
        "jogos_minimos": 100,
        "fator_ece_maximo": 2.0,
    }
    return Config(
        bruto={"filtro_qualidade_mercado": {**padrao, **cortes}},
        seed=42,
        raiz=__import__("pathlib").Path("."),
    )


def liga_sintetica(
    codigo: str,
    *,
    n: int = 400,
    margem: float = 0.05,
    grupo: str = "grupo1",
    sem_odd: float = 0.0,
    seed: int = 3,
) -> pd.DataFrame:
    """Uma liga inventada com margem controlada e mercado bem calibrado.

    As odds saem de probabilidades verdadeiras, e os resultados são sorteados
    **dessas mesmas** probabilidades: o mercado desta liga é honesto por
    construção, e o que varia entre os testes é só o que cada um quer testar.
    """
    gerador = np.random.default_rng(seed)
    probabilidades = gerador.dirichlet([6.0, 4.0, 5.0], size=n)
    sorteio = gerador.random((n, 1))
    observado = np.minimum((sorteio > probabilidades.cumsum(axis=1)).sum(axis=1), 2)

    odds = 1.0 / (probabilidades * (1.0 + margem))
    base: dict = dict.fromkeys(limpeza.COLUNAS_TABELA)
    linhas = []
    for i in range(n):
        gols_casa, gols_fora = (2, 0) if observado[i] == 0 else (1, 1) if observado[i] == 1 else (0, 2)
        linhas.append(
            {
                **base,
                "data": pd.Timestamp("2024-08-16"),
                "liga": codigo,
                "temporada": "2024/25",
                "mandante": f"{codigo}:A",
                "visitante": f"{codigo}:B",
                "gols_mandante": gols_casa,
                "gols_visitante": gols_fora,
                "resultado": "HDA"[observado[i]],
                "odd_pre_H": odds[i, 0],
                "odd_pre_D": odds[i, 1],
                "odd_pre_A": odds[i, 2],
                "odd_fech_H": odds[i, 0],
                "odd_fech_D": odds[i, 1],
                "odd_fech_A": odds[i, 2],
                "grupo": grupo,
                "formato": "A" if grupo == "grupo1" else "C",
            }
        )

    jogos = pd.DataFrame(linhas, columns=list(limpeza.COLUNAS_TABELA))
    if sem_odd:
        quantos = int(n * sem_odd)
        jogos.loc[: quantos - 1, ["odd_pre_H", "odd_pre_D", "odd_pre_A"]] = np.nan
    if grupo == "grupo2":
        # Regra 12: o Grupo 2 não tem odd pré-jogo nenhuma.
        jogos[["odd_pre_H", "odd_pre_D", "odd_pre_A"]] = np.nan
    return jogos


def avaliar(jogos: pd.DataFrame, cfg: Config) -> pd.Series:
    return filtro.avaliar(jogos, cfg, repeticoes=15).iloc[0]


# ----------------------------------------------------------------------------
# Cada critério
# ----------------------------------------------------------------------------
def test_liga_boa_passa() -> None:
    linha = avaliar(liga_sintetica("E0", margem=0.04), config_de_teste())
    assert linha["aprovada"]
    assert linha["motivos"] == ""
    assert linha["margem_pre"] == pytest.approx(0.04, abs=0.005)


def test_margem_alta_reprova_e_diz_o_numero() -> None:
    linha = avaliar(liga_sintetica("SC3", margem=0.12), config_de_teste())
    assert not linha["aprovada"]
    assert "margem alta" in linha["motivos"]
    assert "12" in linha["motivos"]


def test_historico_curto_reprova() -> None:
    linha = avaliar(liga_sintetica("XX", n=120), config_de_teste(jogos_minimos=1000))
    assert not linha["aprovada"]
    assert "histórico curto" in linha["motivos"]


def test_cobertura_baixa_reprova() -> None:
    linha = avaliar(liga_sintetica("YY", sem_odd=0.4), config_de_teste())
    assert not linha["aprovada"]
    assert "cobertura" in linha["motivos"]


def test_calibracao_ruim_reprova() -> None:
    """Um mercado cujas odds não correspondem ao que acontece é reprovado."""
    jogos = liga_sintetica("ZZ", n=2000, margem=0.04)
    # Inverte as odds de mandante e visitante: as probabilidades passam a
    # apontar para o lado errado, sem mexer no que aconteceu em campo.
    jogos[["odd_pre_H", "odd_pre_A"]] = jogos[["odd_pre_A", "odd_pre_H"]].to_numpy()

    linha = avaliar(jogos, config_de_teste())
    assert not linha["aprovada"]
    assert "calibração" in linha["motivos"]


def test_grupo2_nunca_e_aprovado() -> None:
    """Regra 12: sem odd pré-jogo não existe aposta para simular."""
    linha = avaliar(liga_sintetica("BRA", grupo="grupo2"), config_de_teste())

    assert not linha["aprovada"]
    assert "regra 12" in linha["motivos"]
    assert np.isnan(linha["margem_pre"])


def test_grupo2_nao_e_reprovado_por_outros_motivos() -> None:
    """O motivo do Grupo 2 é estrutural: não faz sentido listar margem junto."""
    linha = avaliar(liga_sintetica("BRA", grupo="grupo2", n=120), config_de_teste())
    assert linha["motivos"].count(";") == 0


# ----------------------------------------------------------------------------
# A tabela e a lista final
# ----------------------------------------------------------------------------
def test_avaliacao_traz_uma_linha_por_liga_com_aprovadas_primeiro() -> None:
    jogos = pd.concat(
        [
            liga_sintetica("E0", margem=0.04),
            liga_sintetica("SC3", margem=0.12),
            liga_sintetica("BRA", grupo="grupo2"),
        ],
        ignore_index=True,
    )
    tabela = filtro.avaliar(jogos, config_de_teste(), repeticoes=15)

    assert len(tabela) == 3
    assert tabela.iloc[0]["liga"] == "E0"
    assert list(tabela["aprovada"]) == [True, False, False]


def test_lista_de_aprovadas_sai_ordenada() -> None:
    jogos = pd.concat(
        [
            liga_sintetica("SP1", margem=0.05),
            liga_sintetica("E0", margem=0.04),
            liga_sintetica("SC3", margem=0.12),
        ],
        ignore_index=True,
    )
    tabela = filtro.avaliar(jogos, config_de_teste(), repeticoes=15)
    assert filtro.ligas_aprovadas(tabela) == ["E0", "SP1"]


def test_criterios_saem_do_config() -> None:
    criterios = filtro.Criterios.do_config(config_de_teste(margem_maxima=0.05))
    assert criterios.margem_maxima == 0.05
    assert criterios.fator_ece_maximo == 2.0


def test_margem_medida_e_a_pre_jogo_nao_a_de_fechamento() -> None:
    """Regra 8: aposta-se na odd pré-jogo, então é a margem dela que importa."""
    jogos = liga_sintetica("E0", margem=0.04)
    # Fechamento com margem absurda (as implícitas somam 2,5), que o filtro
    # precisa reportar sem deixar isso reprovar a liga.
    jogos[["odd_fech_H", "odd_fech_D", "odd_fech_A"]] = 1.2

    linha = avaliar(jogos, config_de_teste())
    assert linha["margem_pre"] == pytest.approx(0.04, abs=0.005)
    assert linha["margem_fech"] > 1.0
    assert linha["aprovada"]
