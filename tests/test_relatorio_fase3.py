"""Testes da medição fora da amostra que alimenta o relatório da Fase 3.

O teste que dá valor ao arquivo é
:func:`test_nenhuma_previsao_viu_o_proprio_jogo`. A medição por recortes é
exatamente o lugar onde data leakage entra sem ninguém notar: basta um ``>=``
onde deveria haver ``>``, ou um corte deslocado por um dia, e o modelo passa a
prever jogos que já viu. O resultado fica ótimo, e errado.

Os outros testes cobrem a aritmética: log loss, comparação emparelhada e o
cálculo do menor efeito detectável (regra 10).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futebol.avaliacao import relatorio_fase3 as R
from futebol.config import carregar_config
from futebol.modelos.baseline import Baseline
from futebol.modelos.dixon_coles import DixonColes
from simulacao import rodizio, simular_liga


def _jogos_longos() -> pd.DataFrame:
    """Dois anos de uma liga simulada, com as colunas que a medição usa."""
    jogos = simular_liga(voltas=20)
    gols = jogos["gols_mandante"] - jogos["gols_visitante"]
    return jogos.assign(
        grupo="grupo1",
        temporada="2019/20",
        resultado=np.where(gols > 0, "H", np.where(gols == 0, "D", "A")),
    )


# ----------------------------------------------------------------------------
# Os recortes
# ----------------------------------------------------------------------------
def test_cortes_cobrem_a_janela_inteira() -> None:
    cortes = R.cortes_da_janela("2023-07-15", "2023-10-01", passo="MS")
    assert cortes[0] == pd.Timestamp("2023-07-15"), "o primeiro corte é o início"
    assert cortes[-1] == pd.Timestamp("2023-10-01"), "o último é o fim da janela"
    assert cortes == sorted(cortes)


def test_janela_invertida_e_erro() -> None:
    with pytest.raises(ValueError, match="Janela vazia"):
        R.cortes_da_janela("2024-01-01", "2023-01-01")


def test_nenhuma_previsao_viu_o_proprio_jogo() -> None:
    """A trava contra data leakage, conferida jogo a jogo (regra 6).

    Para cada previsão, o jogo mais recente que entrou no treino precisa ser
    **anterior** ao jogo previsto. Se um dia sequer vazar, este teste falha.
    """
    jogos = _jogos_longos()
    inicio = jogos["data"].min() + pd.Timedelta(days=200)
    previsoes = R.previsoes_em_recortes(
        jogos, lambda: DixonColes(max_gols=8), inicio=inicio
    )

    assert len(previsoes) > 0
    assert (previsoes["treino_ate"] < previsoes["data"]).all(), (
        "houve previsão cujo treino incluiu um jogo da mesma data ou posterior"
    )
    assert (previsoes["data"] >= previsoes["corte"]).all()
    assert (previsoes["treino_ate"] < previsoes["corte"]).all()


def test_todo_jogo_da_janela_e_previsto_uma_vez() -> None:
    """Recorte que perde jogo, ou que prevê o mesmo jogo duas vezes, enviesa."""
    jogos = _jogos_longos()
    inicio = jogos["data"].min() + pd.Timedelta(days=200)
    previsoes = R.previsoes_em_recortes(
        jogos, lambda: Baseline(max_gols=8), inicio=inicio
    )

    da_janela = jogos.loc[jogos["data"] >= inicio]
    assert len(previsoes) == len(da_janela)
    assert set(previsoes.index) == set(da_janela.index)


def test_janela_sem_jogo_nenhum_e_erro() -> None:
    jogos = _jogos_longos()
    with pytest.raises(ValueError, match="Nenhum jogo"):
        R.previsoes_em_recortes(
            jogos,
            lambda: Baseline(max_gols=8),
            inicio=jogos["data"].max() + pd.Timedelta(days=10),
            fim=jogos["data"].max() + pd.Timedelta(days=40),
        )


def test_cada_recorte_treina_um_modelo_novo() -> None:
    """Reaproveitar o modelo treinado deixaria o ajuste anterior vazando."""
    jogos = _jogos_longos()
    criados: list[int] = []

    def construir():
        criados.append(1)
        return Baseline(max_gols=8)

    previsoes = R.previsoes_em_recortes(
        jogos, construir, inicio=jogos["data"].min() + pd.Timedelta(days=200)
    )
    assert len(criados) == previsoes["corte"].nunique() > 1


# ----------------------------------------------------------------------------
# As notas
# ----------------------------------------------------------------------------
def _previsoes_de_mentira(probabilidade_certa: float, n: int = 100) -> pd.DataFrame:
    """``n`` jogos em que o mandante ganhou e o modelo deu ``p`` para isso."""
    resto = (1 - probabilidade_certa) / 2
    return pd.DataFrame(
        {
            "H": [probabilidade_certa] * n,
            "D": [resto] * n,
            "A": [resto] * n,
            "over25": [0.5] * n,
            "under25": [0.5] * n,
            "ambos_marcam": [0.5] * n,
            "ambos_nao_marcam": [0.5] * n,
            "observado": [0] * n,
            "observado_ou": [0] * n,
        }
    )


def test_log_loss_conferida_na_mao() -> None:
    medida = R.medir(_previsoes_de_mentira(0.5), "teste")
    assert medida.log_loss == pytest.approx(-np.log(0.5))
    assert medida.n == 100
    # Over/Under: o modelo disse 50% e o over aconteceu sempre.
    assert medida.log_loss_ou == pytest.approx(-np.log(0.5))


def test_perdas_por_jogo_e_a_log_loss_antes_da_media() -> None:
    previsoes = _previsoes_de_mentira(0.4)
    assert R.perdas_por_jogo(previsoes).mean() == pytest.approx(
        R.medir(previsoes, "x").log_loss
    )


def test_comparacao_emparelhada_acha_a_diferenca() -> None:
    pior = _previsoes_de_mentira(0.30)
    melhor = _previsoes_de_mentira(0.60)
    diferenca = R.comparar(pior, melhor)

    assert diferenca.media == pytest.approx(-np.log(0.30) + np.log(0.60))
    assert diferenca.n == 100
    # Todas as diferenças são idênticas, então o erro-padrão é zero.
    assert diferenca.erro_padrao == pytest.approx(0.0)
    assert diferenca.significativa


def test_comparacao_com_conjuntos_diferentes_e_erro() -> None:
    with pytest.raises(ValueError, match="mesmos jogos"):
        R.comparar(_previsoes_de_mentira(0.3, n=10), _previsoes_de_mentira(0.6, n=20))


def test_efeito_minimo_detectavel_e_o_criterio_da_regra_10() -> None:
    diferenca = R.Diferenca(media=0.0005, erro_padrao=0.0004, n=11000)
    assert diferenca.efeito_minimo_detectavel == pytest.approx(0.00112)
    assert not diferenca.significativa, "o IC 95% cruza o zero"
    texto = diferenca.como_texto()
    assert "menor efeito detectável" in texto
    assert "indistinguível de zero" in texto


def test_diferenca_ruidosa_nao_e_declarada_real() -> None:
    """Em 11 mil jogos, 0,001 de log loss aparece por acaso com facilidade."""
    gerador = np.random.default_rng(3)
    iguais = _previsoes_de_mentira(0.5, n=2000)
    embaralhada = iguais.assign(observado=gerador.integers(0, 3, 2000))
    diferenca = R.comparar(embaralhada, embaralhada)
    assert diferenca.media == pytest.approx(0.0)
    assert not diferenca.significativa


# ----------------------------------------------------------------------------
# O mercado
# ----------------------------------------------------------------------------
def test_o_mercado_e_medido_so_no_grupo_1_com_odd() -> None:
    """Regras 12 e 13: sem odd de fechamento não há mercado a medir."""
    jogos = pd.DataFrame(
        {
            "grupo": ["grupo1", "grupo1", "grupo2"],
            "resultado": ["H", "D", "A"],
            "odd_fech_H": [2.0, 3.0, 1.5],
            "odd_fech_D": [3.4, 3.2, 4.0],
            "odd_fech_A": [3.6, np.nan, 5.0],
        }
    )
    medida, usados = R.medir_o_mercado(jogos)

    assert medida.n == 1, "um jogo sem odd completa e um do Grupo 2 ficam fora"
    assert list(usados.index) == [0]


def test_as_grades_de_varredura_estao_registradas() -> None:
    """Regra 11: a contagem de configurações precisa sair do código, não de memória."""
    assert 0.0 in R.valores_de_xi()
    assert carregar_config().secao("modelos")["dixon_coles"]["xi"] in R.valores_de_xi()
    assert (
        carregar_config().secao("modelos")["shrinkage"]["jogos_equivalentes"]
        in R.valores_de_encolhimento()
    )


def test_a_ordem_do_observado_do_over_under_nao_esta_invertida() -> None:
    """Um índice trocado aqui daria uma nota plausível e errada."""
    jogos = _jogos_longos()
    previsoes = R.previsoes_em_recortes(
        jogos,
        lambda: Baseline(max_gols=8),
        inicio=jogos["data"].min() + pd.Timedelta(days=200),
    )
    da_janela = jogos.loc[previsoes.index]
    muitos_gols = (da_janela["gols_mandante"] + da_janela["gols_visitante"]) >= 3
    # 0 é a coluna "over25", 1 é a "under25".
    assert (previsoes.loc[muitos_gols, "observado_ou"] == 0).all()
    assert (previsoes.loc[~muitos_gols, "observado_ou"] == 1).all()


def test_rodizio_da_bancada_gera_jogos_suficientes() -> None:
    """Conferência da bancada: sem jogos, os testes acima não provariam nada."""
    assert len(rodizio(["A", "B", "C"], voltas=2)) == 12
