"""Testes do backtest: o lugar do projeto onde um bug vira lucro.

Todo erro possível aqui tem a mesma assinatura — o número sai plausível e
errado. Apostar na odd de fechamento em vez da pré-jogo, contar como ganha uma
aposta perdida, deixar uma liga do Grupo 2 entrar: nenhum desses aparece como
exceção. Aparece como um ROI melhor.

Daí a forma dos testes abaixo: em vez de conferir que "roda", eles montam uma
tabela pequena com o resultado já conhecido e exigem o número exato.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from futebol.backtest import simulador
from futebol.config import Config

#: Um config mínimo, só com o que o backtest lê. Montado à mão para o teste não
#: depender do config.yaml de verdade — que muda quando o projeto muda de fase.
CONFIG = Config(
    bruto={
        "ligas_aprovadas_backtest": ["E0"],
        "backtest": {
            "ev_minimo": 0.05,
            "banca_inicial": 1000.0,
            "stake_fixa_pct": 0.01,
            "kelly_fracao": 0.25,
            "kelly_teto_pct": 0.05,
            "bootstrap_amostras": 500,
        },
    },
    seed=42,
    raiz=Path("."),
)


def _jogos() -> pd.DataFrame:
    """Quatro jogos: dois na liga aprovada, um do Grupo 2, um sem odd pré-jogo."""
    return pd.DataFrame(
        {
            "data": pd.to_datetime(
                ["2022-01-01", "2022-01-01", "2022-01-02", "2022-01-03"]
            ),
            "liga": ["E0", "E0", "BRA", "E0"],
            "grupo": ["grupo1", "grupo1", "grupo2", "grupo1"],
            "temporada": ["2021/22"] * 4,
            "mandante": ["ENG:A", "ENG:C", "BRA:X", "ENG:E"],
            "visitante": ["ENG:B", "ENG:D", "BRA:Y", "ENG:F"],
            "gols_mandante": [2, 0, 1, 3],
            "gols_visitante": [0, 0, 1, 3],
            "resultado": ["H", "D", "D", "D"],
            "odd_pre_H": [2.0, 3.0, 2.5, np.nan],
            "odd_pre_D": [4.0, 3.0, 3.0, np.nan],
            "odd_pre_A": [4.0, 3.0, 2.5, np.nan],
            "odd_pre_over25": [2.0, 2.0, 2.0, np.nan],
            "odd_pre_under25": [2.0, 2.0, 2.0, np.nan],
            "odd_fech_H": [1.8, 3.2, 2.5, 2.0],
            "odd_fech_D": [4.2, 3.0, 3.0, 4.0],
            "odd_fech_A": [4.4, 2.9, 2.5, 4.0],
            "odd_fech_over25": [2.0, 2.0, 2.0, 2.0],
            "odd_fech_under25": [2.0, 2.0, 2.0, 2.0],
        }
    )


def _previsoes(jogos: pd.DataFrame) -> pd.DataFrame:
    """O modelo acha o mandante bem mais provável do que o mercado acha."""
    return pd.DataFrame(
        {
            "H": [0.60, 0.40, 0.40, 0.50],
            "D": [0.20, 0.30, 0.30, 0.25],
            "A": [0.20, 0.30, 0.30, 0.25],
            "over25": [0.60, 0.60, 0.60, 0.60],
            "under25": [0.40, 0.40, 0.40, 0.40],
            "ambos_marcam": [0.5] * 4,
            "ambos_nao_marcam": [0.5] * 4,
        },
        index=jogos.index,
    )


@pytest.fixture
def amostra() -> simulador.Amostra:
    jogos = _jogos()
    return simulador.preparar(jogos, _previsoes(jogos), CONFIG)


# ----------------------------------------------------------------------------
# Quem entra e quem fica de fora
# ----------------------------------------------------------------------------
def test_liga_do_grupo_2_nunca_entra(amostra) -> None:
    """Regra 12: sem odd pré-jogo não há aposta, e o Brasileirão não tem."""
    assert "BRA" not in set(amostra.candidatos["liga"])
    assert amostra.fora_por_grupo2 == 1


def test_jogo_sem_odd_pre_e_pulado_e_contado(amostra) -> None:
    """A exigência da Fase 1d: jogo sem odd não é uma amostra aleatória."""
    assert amostra.jogos_sem_odd == 1
    assert amostra.jogos_com_odd == 2
    assert "ENG:E" not in set(amostra.candidatos["mandante"])


def test_cada_jogo_vira_cinco_candidatas(amostra) -> None:
    assert len(amostra.candidatos) == 2 * len(simulador.SELECOES)
    assert set(amostra.candidatos["selecao"]) == {s.chave for s in simulador.SELECOES}


def test_liga_aprovada_vazia_e_erro_em_vez_de_tabela_vazia() -> None:
    """Falhar alto: um backtest de zero apostas não pode passar despercebido."""
    jogos = _jogos()
    cfg = Config(bruto={**CONFIG.bruto, "ligas_aprovadas_backtest": []}, seed=42, raiz=Path("."))
    with pytest.raises(ValueError, match="Nenhum jogo elegível"):
        simulador.preparar(jogos, _previsoes(jogos), cfg)


# ----------------------------------------------------------------------------
# As contas de cada aposta
# ----------------------------------------------------------------------------
def test_aposta_se_na_odd_pre_jogo_e_nunca_na_de_fechamento(amostra) -> None:
    """Regra 8. Se este teste cair, o ROI do projeto inteiro vira ficção."""
    do_mandante = amostra.candidatos.query("selecao == 'H' and mandante == 'ENG:A'")
    assert float(do_mandante["odd"].iloc[0]) == pytest.approx(2.0)
    assert float(do_mandante["odd_fech"].iloc[0]) == pytest.approx(1.8)


def test_ev_e_probabilidade_vezes_odd_menos_um(amostra) -> None:
    """0,60 × 2,00 − 1 = 0,20."""
    linha = amostra.candidatos.query("selecao == 'H' and mandante == 'ENG:A'").iloc[0]
    assert linha["ev"] == pytest.approx(0.20)


def test_o_retorno_de_quem_ganhou_e_odd_menos_um(amostra) -> None:
    ganhou = amostra.candidatos.query("selecao == 'H' and mandante == 'ENG:A'").iloc[0]
    assert bool(ganhou["ganhou"])
    assert ganhou["retorno_unitario"] == pytest.approx(1.0)


def test_o_retorno_de_quem_perdeu_e_menos_um(amostra) -> None:
    perdeu = amostra.candidatos.query("selecao == 'A' and mandante == 'ENG:A'").iloc[0]
    assert not bool(perdeu["ganhou"])
    assert perdeu["retorno_unitario"] == pytest.approx(-1.0)


def test_over_under_nao_tem_empate_tecnico(amostra) -> None:
    """2,5 não é placar possível: um dos dois lados sempre ganha, nunca os dois."""
    gols = amostra.candidatos.loc[
        amostra.candidatos["selecao"].isin(["over25", "under25"])
    ]
    for _, do_jogo in gols.groupby("mandante"):
        assert int(do_jogo["ganhou"].sum()) == 1


def test_o_empate_do_zero_a_zero_paga(amostra) -> None:
    """ENG:C 0x0 — empate ganha, e menos de 2,5 gols também."""
    do_jogo = amostra.candidatos.query("mandante == 'ENG:C'")
    ganhas = set(do_jogo.loc[do_jogo["ganhou"], "selecao"])
    assert ganhas == {"D", "under25"}


# ----------------------------------------------------------------------------
# CLV
# ----------------------------------------------------------------------------
def test_clv_bruto_compara_os_dois_precos_de_balcao(amostra) -> None:
    """Peguei 2,00 e o mercado fechou em 1,80: 2,00/1,80 − 1 = +11,1%."""
    linha = amostra.candidatos.query("selecao == 'H' and mandante == 'ENG:A'").iloc[0]
    assert linha["clv_bruto"] == pytest.approx(2.0 / 1.8 - 1.0)


def test_clv_usa_a_probabilidade_justa_do_fechamento(amostra) -> None:
    """A margem é tirada do grupo inteiro, e por isso as três justas somam 1."""
    do_jogo = amostra.candidatos.query("mandante == 'ENG:A' and mercado == '1x2'")
    assert float(do_jogo["prob_fech"].sum()) == pytest.approx(1.0)
    linha = do_jogo.query("selecao == 'H'").iloc[0]
    assert linha["clv"] == pytest.approx(linha["odd"] * linha["prob_fech"] - 1.0)


def test_clv_nao_depende_do_resultado_do_jogo(amostra) -> None:
    """A razão de o CLV ser o critério primário (seção 8.3): ele é só preço.

    Trocando todos os placares, o CLV de cada candidata tem de ficar idêntico.
    """
    jogos = _jogos()
    outros_placares = jogos.assign(
        gols_mandante=[0, 4, 1, 3], gols_visitante=[3, 1, 1, 3],
        resultado=["A", "H", "D", "D"],
    )
    outra = simulador.preparar(outros_placares, _previsoes(jogos), CONFIG)
    assert outra.candidatos["clv"].to_numpy() == pytest.approx(
        amostra.candidatos["clv"].to_numpy()
    )


# ----------------------------------------------------------------------------
# Escolher as apostas
# ----------------------------------------------------------------------------
def test_so_aposta_acima_do_limite_de_ev(amostra) -> None:
    apostas = simulador.selecionar(amostra.candidatos, 0.05)
    assert (apostas["ev"] > 0.05).all()
    assert len(apostas) < len(amostra.candidatos)


def test_apertar_o_limite_nunca_acrescenta_aposta(amostra) -> None:
    folgado = simulador.selecionar(amostra.candidatos, 0.0)
    apertado = simulador.selecionar(amostra.candidatos, 0.10)
    assert len(apertado) <= len(folgado)


def test_a_aleatoria_e_reproduzivel(amostra) -> None:
    """Semente fixa: dois relatórios do mesmo dado dão a mesma comparação."""
    primeira = simulador.aleatorias(amostra.candidatos, 4, seed=7)
    segunda = simulador.aleatorias(amostra.candidatos, 4, seed=7)
    assert primeira.equals(segunda)


def test_a_aleatoria_nunca_pede_mais_do_que_existe(amostra) -> None:
    sorteadas = simulador.aleatorias(amostra.candidatos, 10_000, seed=7)
    assert len(sorteadas) == len(amostra.candidatos)


# ----------------------------------------------------------------------------
# Medir
# ----------------------------------------------------------------------------
def test_roi_de_stake_constante_e_a_media_dos_retornos(amostra) -> None:
    apostas = simulador.selecionar(amostra.candidatos, 0.0)
    medida = simulador.medir(apostas, "teste", amostras_bootstrap=200)
    assert medida.roi == pytest.approx(apostas["retorno_unitario"].mean())
    assert medida.n == len(apostas)


def test_a_medida_de_zero_apostas_nao_estoura(amostra) -> None:
    """Um limite de EV altíssimo não seleciona nada — e isso não é erro."""
    vazio = simulador.selecionar(amostra.candidatos, 100.0)
    medida = simulador.medir(vazio, "vazio")
    assert medida.n == 0
    assert np.isnan(medida.roi)


def test_o_intervalo_de_confianca_encolhe_com_a_amostra() -> None:
    """Sanidade do bootstrap: mais apostas, menos incerteza."""
    def largura(n: int) -> float:
        gerador = np.random.default_rng(0)
        apostas = pd.DataFrame(
            {
                "retorno_unitario": np.where(gerador.random(n) < 0.5, 1.0, -1.0),
                "clv": np.full(n, 0.01),
                "clv_bruto": np.full(n, 0.01),
                "ganhou": np.full(n, True),
                "odd": np.full(n, 2.0),
            }
        )
        baixo, alto = simulador.medir(apostas, "x", amostras_bootstrap=400).roi_ic
        return alto - baixo

    assert largura(4000) < largura(250)


def test_a_grade_de_configuracoes_e_contavel() -> None:
    """Regra 11: o número tem de ser explícito, não 'algumas variações'."""
    grade = simulador.grade()
    assert len(grade) == simulador.N_CONFIGURACOES_FASE_6 == 16
    assert len({c.rotulo for c in grade}) == 16


def test_rodar_calcula_as_quatro_combinacoes_de_dinheiro() -> None:
    """As DUAS variantes de banca, sempre — nunca só a mais bonita."""
    jogos = _jogos()
    resultado = simulador.rodar(jogos, _previsoes(jogos), CONFIG, ev_minimo=0.0)
    assert set(resultado.evolucoes) == {
        ("stake_fixa", "fixa"),
        ("stake_fixa", "composta"),
        ("kelly_fracionado", "fixa"),
        ("kelly_fracionado", "composta"),
    }
    assert resultado.aleatorio.n == resultado.resultado.n
