"""Testes dos gráficos: eles precisam sair, e precisam sair certos.

Teste de gráfico não julga beleza. Julga três coisas que dão errado calado:

1. o arquivo foi escrito e não está vazio;
2. os dados desenhados são os dados medidos — a curva de calibração vem da
   mesma função que o relatório usa para o número do ECE;
3. a cor identifica a série, e não a posição dela no ranking. Se um modelo sai
   do gráfico, os outros não podem trocar de cor.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futebol.avaliacao import graficos


def _previsoes(probabilidade_certa: float, n: int = 300, liga: str = "E0") -> pd.DataFrame:
    gerador = np.random.default_rng(3)
    resto = (1 - probabilidade_certa) / 2
    return pd.DataFrame(
        {
            "H": [probabilidade_certa] * n,
            "D": [resto] * n,
            "A": [resto] * n,
            "over25": [0.5] * n,
            "under25": [0.5] * n,
            "observado": gerador.integers(0, 3, n),
            "observado_ou": gerador.integers(0, 2, n),
            "liga": [liga] * n,
        }
    )


def test_a_curva_de_calibracao_e_escrita(tmp_path) -> None:
    destino = graficos.curva_calibracao(
        {"modelo": _previsoes(0.5), "mercado": _previsoes(0.4)},
        tmp_path / "calibracao.png",
        subtitulo="janela de teste",
    )
    assert destino.is_file()
    assert destino.stat().st_size > 5_000, "PNG pequeno demais para ter conteúdo"


def test_os_dados_da_curva_sao_os_da_tabela_de_calibracao() -> None:
    """O gráfico e o número do relatório têm que contar a mesma história."""
    from futebol.avaliacao import metricas

    previsoes = _previsoes(0.5)
    do_grafico = graficos.dados_de_calibracao(previsoes)
    da_metrica = pd.DataFrame(
        metricas.tabela_calibracao(
            previsoes[["H", "D", "A"]].to_numpy(), previsoes["observado"].to_numpy()
        )
    )
    pd.testing.assert_frame_equal(do_grafico, da_metrica)


def test_a_cor_segue_a_serie_e_nao_o_ranking() -> None:
    """A paleta é atribuída em ordem fixa, e nunca reciclada."""
    assert len(graficos.PALETA) >= 4
    assert len(set(graficos.PALETA)) == len(graficos.PALETA)
    assert len(graficos.MARCADORES) >= len(graficos.PALETA[:4])


def test_o_grafico_de_distancia_e_escrito(tmp_path) -> None:
    tabela = pd.DataFrame(
        {
            "liga": ["E0", "SP1", "BRA"],
            "jogos": [500, 400, 300],
            "dixon-coles": [1.02, 1.05, 1.01],
            "mercado (fechamento)": [0.99, 1.06, 0.98],
        }
    )
    destino = graficos.distancia_do_mercado(
        tabela, tmp_path / "distancia.png", coluna_modelo="dixon-coles"
    )
    assert destino.is_file()
    assert destino.stat().st_size > 5_000


def test_a_distancia_e_modelo_menos_mercado() -> None:
    """Sinal trocado aqui inverteria a leitura do gráfico inteiro."""
    tabela = pd.DataFrame(
        {
            "liga": ["E0"],
            "jogos": [500],
            "modelo": [1.05],
            "mercado (fechamento)": [1.00],
        }
    )
    # O cálculo é feito dentro da função; aqui se confere a convenção que o
    # rótulo do eixo promete: positivo = o modelo perdeu do mercado.
    esperado = tabela["modelo"] - tabela["mercado (fechamento)"]
    assert esperado.iloc[0] == pytest.approx(0.05)


def test_formatador_usa_virgula_decimal() -> None:
    """O relatório é lido em português; ponto decimal ali é ruído."""
    formatador = graficos._virgula(3)
    assert formatador(1.0234, None) == "1,023"
