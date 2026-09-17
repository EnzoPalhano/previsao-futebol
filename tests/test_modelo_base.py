"""Testes do contrato dos modelos: a matriz de placares e a trava de data.

Os dois testes que mais importam aqui:

1. **a matriz vira mercados coerentes** — se esta conta estiver errada, todo
   modelo do projeto estará errado do mesmo jeito, e nenhuma comparação entre
   eles apanharia o erro (todos erram junto);
2. **o corte de data é estrito** — é a trava contra data leakage (regra 6),
   e ela mora na classe base justamente para nenhum modelo poder esquecê-la.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futebol.modelos import base

#: Uma matriz 3x3 escrita na mão, com todas as casas diferentes, para as contas
#: de mercado poderem ser conferidas somando à mão:
#:
#:            v0    v1    v2
#:     m0   0,10  0,08  0,04     -> empate, visitante, visitante
#:     m1   0,14  0,18  0,09     -> mandante, empate, visitante
#:     m2   0,11  0,13  0,13     -> mandante, mandante, empate
MATRIZ = np.array(
    [
        [0.10, 0.08, 0.04],
        [0.14, 0.18, 0.09],
        [0.11, 0.13, 0.13],
    ]
)


def _tabela() -> pd.DataFrame:
    """Uma tabela mínima de treino, com três datas distintas."""
    return pd.DataFrame(
        {
            "data": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"]),
            "liga": ["E0", "E0", "E0"],
            "mandante": ["ENG:A", "ENG:B", "ENG:A"],
            "visitante": ["ENG:B", "ENG:A", "ENG:B"],
            "gols_mandante": [1, 2, 0],
            "gols_visitante": [0, 2, 1],
        }
    )


class ModeloDeMentira(base.Modelo):
    """Modelo que devolve sempre a mesma matriz — serve para testar a base."""

    nome = "mentira"

    def __init__(self) -> None:
        super().__init__()
        self.jogos_vistos: int | None = None

    def _ajustar(self, jogos: pd.DataFrame) -> None:
        self.jogos_vistos = len(jogos)

    def matriz_de_placares(self, jogo: base.Jogo) -> np.ndarray:
        return base.normalizar_matriz(MATRIZ)


# ----------------------------------------------------------------------------
# A matriz de placares vira mercados
# ----------------------------------------------------------------------------
def test_mercados_conferidos_na_mao() -> None:
    """Cada mercado é uma região da matriz; aqui as regiões são somadas à mão."""
    mercados = base.mercados_da_matriz(MATRIZ)

    # Triângulo de baixo: 0,14 + 0,11 + 0,13
    assert mercados["H"] == pytest.approx(0.38)
    # Diagonal: 0,10 + 0,18 + 0,13
    assert mercados["D"] == pytest.approx(0.41)
    # Triângulo de cima: 0,08 + 0,04 + 0,09
    assert mercados["A"] == pytest.approx(0.21)
    # Soma dos gols >= 3: (1,2) 0,09 + (2,1) 0,13 + (2,2) 0,13
    assert mercados["over25"] == pytest.approx(0.35)
    # Tudo fora da primeira linha e da primeira coluna: 0,18+0,09+0,13+0,13
    assert mercados["ambos_marcam"] == pytest.approx(0.53)


def test_probabilidades_somam_um_em_cada_grupo() -> None:
    """1X2, Over/Under e ambos-marcam são partições da mesma matriz."""
    mercados = base.mercados_da_matriz(MATRIZ)
    for grupo in base.GRUPOS_COMPLEMENTARES:
        assert sum(mercados[chave] for chave in grupo) == pytest.approx(1.0)


def test_nenhuma_probabilidade_e_negativa() -> None:
    mercados = base.mercados_da_matriz(MATRIZ)
    assert all(valor >= 0.0 for valor in mercados.values())


def test_previsao_tem_exatamente_as_chaves_do_contrato() -> None:
    mercados = base.mercados_da_matriz(MATRIZ)
    assert tuple(mercados) == base.CHAVES_PREVISAO


def test_matriz_que_nao_soma_um_e_recusada() -> None:
    """Uma matriz não normalizada é erro de programação, não de dado."""
    with pytest.raises(base.ErroDeModelo, match="soma"):
        base.mercados_da_matriz(MATRIZ * 2)


def test_normalizar_corta_negativo_e_redistribui() -> None:
    """A correção do Dixon-Coles pode empurrar uma casa para baixo de zero."""
    bruta = np.array([[0.5, -0.1], [0.2, 0.2]])
    normalizada = base.normalizar_matriz(bruta)
    assert (normalizada >= 0).all()
    assert normalizada.sum() == pytest.approx(1.0)
    # O negativo virou zero e os 0,9 restantes foram reescalados.
    assert normalizada[0, 0] == pytest.approx(0.5 / 0.9)


def test_placar_mais_provavel_e_o_argmax() -> None:
    linha, coluna, probabilidade = base.placar_mais_provavel(MATRIZ)
    assert (linha, coluna) == (1, 1)
    assert probabilidade == pytest.approx(0.18)


# ----------------------------------------------------------------------------
# A trava contra data leakage
# ----------------------------------------------------------------------------
def test_corte_de_data_e_estrito() -> None:
    """Jogo do próprio dia da previsão não pode entrar no treino."""
    jogos = _tabela()
    antes = base.jogos_ate(jogos, "2024-01-08")
    assert len(antes) == 1, "só o jogo de 01/01 é anterior a 08/01"
    assert antes["data"].max() < pd.Timestamp("2024-01-08")


def test_treinar_respeita_o_corte() -> None:
    modelo = ModeloDeMentira().treinar(_tabela(), ate_data="2024-01-15")
    assert modelo.jogos_vistos == 2
    assert modelo.ultima_data_de_treino == pd.Timestamp("2024-01-08")


def test_treinar_sem_data_usa_tudo() -> None:
    modelo = ModeloDeMentira().treinar(_tabela())
    assert modelo.jogos_vistos == 3


def test_corte_que_nao_deixa_jogo_nenhum_falha_alto() -> None:
    """Melhor um erro claro que um modelo treinado no vazio."""
    with pytest.raises(base.ErroDeModelo, match="Nenhum jogo"):
        ModeloDeMentira().treinar(_tabela(), ate_data="2023-01-01")


def test_jogo_sem_placar_nao_entra_no_treino() -> None:
    """Partida futura já na tabela não pode contar como aprendizado."""
    jogos = _tabela()
    jogos.loc[2, ["gols_mandante", "gols_visitante"]] = None
    modelo = ModeloDeMentira().treinar(jogos)
    assert modelo.jogos_vistos == 2


def test_tabela_sem_as_colunas_certas_e_recusada() -> None:
    with pytest.raises(base.ErroDeModelo, match="gols_mandante"):
        ModeloDeMentira().treinar(_tabela().drop(columns=["gols_mandante"]))


# ----------------------------------------------------------------------------
# O contrato de uso
# ----------------------------------------------------------------------------
def test_prever_sem_treinar_falha() -> None:
    with pytest.raises(base.ErroDeModelo, match="não foi treinado"):
        ModeloDeMentira().prever(base.Jogo("E0", "ENG:A", "ENG:B"))


def test_prever_aceita_dicionario_e_jogo() -> None:
    modelo = ModeloDeMentira().treinar(_tabela())
    de_objeto = modelo.prever(base.Jogo("E0", "ENG:A", "ENG:B"))
    de_dicionario = modelo.prever(
        {"liga": "E0", "mandante": "ENG:A", "visitante": "ENG:B"}
    )
    assert de_objeto == de_dicionario


def test_jogo_de_mapa_sem_time_falha() -> None:
    with pytest.raises(base.ErroDeModelo, match="visitante"):
        base.Jogo.de_mapa({"liga": "E0", "mandante": "ENG:A"})


def test_prever_muitos_mantem_o_indice() -> None:
    """Desalinhar previsão e resultado é o jeito silencioso de mentir."""
    jogos = _tabela().set_index(pd.Index([10, 20, 30], name="id"))
    previsoes = ModeloDeMentira().treinar(jogos).prever_muitos(jogos)
    assert list(previsoes.index) == [10, 20, 30]
    assert list(previsoes.columns) == list(base.CHAVES_PREVISAO)
