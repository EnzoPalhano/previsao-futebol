"""O Elo: conservação, ordem e — acima de tudo — nada de futuro no rating.

O teste que importa mais neste arquivo é
``test_jogos_do_mesmo_dia_nao_se_influenciam``. O Elo é um cálculo sequencial, e
sequencial é onde vazamento de dados entra sem fazer barulho: basta atualizar o
rating jogo a jogo, na ordem da tabela, para que o resultado do jogo das 16h de
sábado ajude a prever o das 18h — informação que não existia na hora de apostar.
O modelo fica melhor, o relatório fica bonito, e a aposta real perde dinheiro.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futebol.modelos import elo as modulo_elo
from futebol.modelos.elo import Elo, ErroDeElo


def _jogos(linhas: list[tuple[str, str, str, int, int]]) -> pd.DataFrame:
    """Tabela mínima a partir de ``(data, mandante, visitante, gols, gols)``."""
    return pd.DataFrame(
        {
            "data": pd.to_datetime([linha[0] for linha in linhas]),
            "liga": ["E0"] * len(linhas),
            "temporada": ["2023/24"] * len(linhas),
            "mandante": [linha[1] for linha in linhas],
            "visitante": [linha[2] for linha in linhas],
            "gols_mandante": [linha[3] for linha in linhas],
            "gols_visitante": [linha[4] for linha in linhas],
        }
    )


# ----------------------------------------------------------------------------
# A trava contra vazamento
# ----------------------------------------------------------------------------
def test_jogos_do_mesmo_dia_nao_se_influenciam() -> None:
    """Regra 6 num cálculo sequencial: o dia inteiro usa o rating de ontem.

    O ENG:A joga duas vezes no mesmo sábado. Se o Elo atualizasse jogo a jogo, o
    segundo jogo já veria o resultado do primeiro — e é isso que não pode.
    """
    jogos = _jogos(
        [
            ("2023-08-05", "ENG:A", "ENG:B", 5, 0),
            ("2023-08-05", "ENG:A", "ENG:C", 0, 0),
        ]
    )
    antes = Elo().ratings_antes(jogos)

    assert antes["elo_mandante"].iloc[0] == antes["elo_mandante"].iloc[1] == 1500.0


def test_o_dia_seguinte_ja_enxerga_o_dia_anterior() -> None:
    """O contrário do teste acima: o corte é por dia, não um congelamento."""
    jogos = _jogos(
        [
            ("2023-08-05", "ENG:A", "ENG:B", 3, 0),
            ("2023-08-06", "ENG:A", "ENG:C", 0, 0),
        ]
    )
    antes = Elo().ratings_antes(jogos)

    assert antes["elo_mandante"].iloc[0] == 1500.0
    assert antes["elo_mandante"].iloc[1] > 1500.0


def test_dois_jogos_do_mesmo_time_no_mesmo_dia_somam_as_duas_correcoes() -> None:
    """Calendário remarcado não pode fazer uma das correções sumir."""
    elo = Elo()
    elo.ratings_antes(
        _jogos(
            [
                ("2023-08-05", "ENG:A", "ENG:B", 3, 0),
                ("2023-08-05", "ENG:A", "ENG:C", 3, 0),
            ]
        )
    )
    uma_vitoria = Elo()
    uma_vitoria.ratings_antes(_jogos([("2023-08-05", "ENG:A", "ENG:B", 3, 0)]))

    ganho_duplo = elo.rating("ENG:A") - 1500.0
    ganho_simples = uma_vitoria.rating("ENG:A") - 1500.0
    assert ganho_duplo == pytest.approx(2 * ganho_simples)


# ----------------------------------------------------------------------------
# A conta
# ----------------------------------------------------------------------------
def test_time_novo_comeca_no_rating_inicial() -> None:
    assert Elo().rating("ENG:NuncaJogou") == 1500.0
    assert Elo(rating_inicial=1000.0).rating("ENG:NuncaJogou") == 1000.0


def test_a_soma_dos_ratings_nunca_muda() -> None:
    """O Elo redistribui pontos, não cria. Se a soma andar, há erro de sinal."""
    gerador = np.random.default_rng(7)
    times = [f"ENG:T{i}" for i in range(6)]
    linhas = []
    for dia in range(60):
        casa, fora = gerador.choice(times, size=2, replace=False)
        linhas.append(
            (
                f"2023-08-{dia % 28 + 1:02d}",
                str(casa),
                str(fora),
                int(gerador.integers(0, 4)),
                int(gerador.integers(0, 4)),
            )
        )
    elo = Elo()
    elo.ratings_antes(_jogos(linhas))

    esperado = 1500.0 * len(elo.ratings)
    assert sum(elo.ratings.values()) == pytest.approx(esperado)


def test_vitoria_do_azarao_move_mais_que_a_do_favorito() -> None:
    """É a ideia inteira do Elo: o passo é do tamanho da surpresa."""
    favorito = Elo()
    favorito.ratings = {"ENG:Forte": 1800.0, "ENG:Fraco": 1200.0}
    favorito.ratings_antes(_jogos([("2023-08-05", "ENG:Forte", "ENG:Fraco", 2, 0)]))
    ganho_esperado = favorito.rating("ENG:Forte") - 1800.0

    azarao = Elo()
    azarao.ratings = {"ENG:Forte": 1800.0, "ENG:Fraco": 1200.0}
    azarao.ratings_antes(_jogos([("2023-08-05", "ENG:Fraco", "ENG:Forte", 2, 0)]))
    ganho_surpresa = azarao.rating("ENG:Fraco") - 1200.0

    assert ganho_surpresa > ganho_esperado
    assert ganho_esperado > 0


def test_empate_entre_iguais_tira_pontos_do_mandante() -> None:
    """Por causa da vantagem de casa, empatar em casa é abaixo do esperado."""
    elo = Elo(vantagem_casa=50.0)
    elo.ratings_antes(_jogos([("2023-08-05", "ENG:A", "ENG:B", 1, 1)]))

    assert elo.rating("ENG:A") < 1500.0
    assert elo.rating("ENG:B") > 1500.0


def test_sem_vantagem_de_casa_o_empate_entre_iguais_nao_move_ninguem() -> None:
    elo = Elo(vantagem_casa=0.0)
    elo.ratings_antes(_jogos([("2023-08-05", "ENG:A", "ENG:B", 1, 1)]))

    assert elo.rating("ENG:A") == pytest.approx(1500.0)
    assert elo.rating("ENG:B") == pytest.approx(1500.0)


def test_a_vantagem_de_casa_entra_na_expectativa_nao_no_rating() -> None:
    elo = Elo(vantagem_casa=50.0)
    entre_iguais = elo.esperado(1500.0, 1500.0)

    assert entre_iguais > 0.5
    assert elo.esperado(1500.0, 1550.0) == pytest.approx(0.5)


def test_quatrocentos_pontos_valem_dez_vezes_mais_chance() -> None:
    """A escala do Elo, conferida na definição dela."""
    elo = Elo(vantagem_casa=0.0)
    esperado = elo.esperado(1900.0, 1500.0)

    assert esperado / (1.0 - esperado) == pytest.approx(10.0)


def test_k_maior_move_mais() -> None:
    def ganho(k: float) -> float:
        elo = Elo(k=k)
        elo.ratings_antes(_jogos([("2023-08-05", "ENG:A", "ENG:B", 2, 0)]))
        return elo.rating("ENG:A") - 1500.0

    assert ganho(40.0) == pytest.approx(2 * ganho(20.0))


def test_jogo_sem_placar_nao_atualiza() -> None:
    """Partida futura ou linha quebrada não ensina nada — e não pode zerar nada."""
    jogos = _jogos([("2023-08-05", "ENG:A", "ENG:B", 2, 0)])
    jogos.loc[0, "gols_mandante"] = np.nan
    elo = Elo()
    elo.ratings_antes(jogos)

    assert elo.ratings == {}


def test_o_resultado_sai_do_placar_e_nao_da_coluna_resultado() -> None:
    """Divergência da fonte não pode entrar no rating em silêncio."""
    jogos = _jogos([("2023-08-05", "ENG:A", "ENG:B", 0, 2)])
    jogos["resultado"] = "H"  # a fonte diz vitória do mandante; o placar diz o contrário
    elo = Elo()
    elo.ratings_antes(jogos)

    assert elo.rating("ENG:A") < 1500.0


# ----------------------------------------------------------------------------
# Alinhamento com a tabela
# ----------------------------------------------------------------------------
def test_o_indice_devolvido_e_o_da_entrada() -> None:
    """As colunas são coladas ao lado dos jogos: desalinhar seria catastrófico."""
    jogos = _jogos(
        [
            ("2023-08-12", "ENG:A", "ENG:B", 1, 0),
            ("2023-08-05", "ENG:C", "ENG:D", 2, 2),
        ]
    )
    jogos.index = [77, 42]
    antes = Elo().ratings_antes(jogos)

    assert list(antes.index) == [77, 42]
    assert list(antes.columns) == list(modulo_elo.COLUNAS_ELO)


def test_a_ordem_das_linhas_da_tabela_nao_muda_o_resultado() -> None:
    """A cronologia mora na coluna ``data``, não na ordem em que as linhas vieram."""
    linhas = [
        ("2023-08-05", "ENG:A", "ENG:B", 3, 0),
        ("2023-08-12", "ENG:A", "ENG:C", 1, 1),
        ("2023-08-19", "ENG:B", "ENG:C", 0, 2),
    ]
    em_ordem = Elo().ratings_antes(_jogos(linhas))
    embaralhados = _jogos(linhas).sample(frac=1.0, random_state=3)
    fora_de_ordem = Elo().ratings_antes(embaralhados)

    pd.testing.assert_frame_equal(em_ordem, fora_de_ordem.reindex(em_ordem.index))


def test_a_diferenca_e_mandante_menos_visitante() -> None:
    antes = Elo().ratings_antes(
        _jogos(
            [
                ("2023-08-05", "ENG:A", "ENG:B", 3, 0),
                ("2023-08-12", "ENG:B", "ENG:A", 0, 1),
            ]
        )
    )
    esperado = antes["elo_mandante"] - antes["elo_visitante"]
    pd.testing.assert_series_equal(
        antes["elo_diferenca"], esperado, check_names=False
    )


# ----------------------------------------------------------------------------
# A chave do clube
# ----------------------------------------------------------------------------
def test_promovido_leva_o_rating_para_a_outra_divisao() -> None:
    """``ENG:Luton`` é a mesma chave na E1 e na E0 — é esse o ponto da regra 14.

    Se a chave fosse por competição, todo promovido renasceria com 1500 e o Elo
    seria ruído exatamente nos times sobre os quais há mais o que dizer.
    """
    jogos = _jogos(
        [
            ("2023-08-05", "ENG:Luton", "ENG:B", 4, 0),
            ("2024-08-05", "ENG:Luton", "ENG:C", 0, 0),
        ]
    )
    jogos.loc[0, ["liga", "temporada"]] = ["E1", "2023/24"]
    jogos.loc[1, ["liga", "temporada"]] = ["E0", "2024/25"]
    antes = Elo().ratings_antes(jogos)

    assert antes["elo_mandante"].iloc[1] > 1500.0


def test_times_de_paises_diferentes_nao_se_misturam() -> None:
    """Sem confronto entre eles, cada país é um universo de Elo isolado.

    A conferência é feita do jeito mais direto possível: processar a Inglaterra
    sozinha tem de dar exatamente o mesmo rating que processá-la junto com o
    Brasil. Comparar o rating de um inglês com o de um brasileiro, isso sim, não
    significaria nada — eles medem distância até médias diferentes.
    """
    ingleses = [("2023-08-05", "ENG:A", "ENG:B", 3, 0)]
    brasileiros = [("2023-08-05", "BRA:A", "BRA:B", 0, 3)]

    sozinha = Elo()
    sozinha.ratings_antes(_jogos(ingleses))
    juntas = Elo()
    juntas.ratings_antes(_jogos(ingleses + brasileiros))

    assert juntas.rating("ENG:A") == pytest.approx(sozinha.rating("ENG:A"))
    assert juntas.rating("ENG:B") == pytest.approx(sozinha.rating("ENG:B"))
    assert juntas.rating("BRA:A") < 1500.0 < juntas.rating("BRA:B")


def test_clube_em_duas_divisoes_na_mesma_temporada_e_encontrado() -> None:
    """Isso não é promoção: é homônimo, e fundiria dois times num rating só."""
    jogos = _jogos(
        [
            ("2023-08-05", "ENG:Igual", "ENG:B", 1, 0),
            ("2023-08-12", "ENG:Igual", "ENG:C", 1, 0),
        ]
    )
    jogos.loc[1, "liga"] = "E2"
    problemas = modulo_elo.clubes_em_duas_divisoes_na_mesma_temporada(jogos)

    assert list(problemas["time"]) == ["ENG:Igual"]


def test_subir_de_divisao_entre_temporadas_nao_e_problema() -> None:
    jogos = _jogos(
        [
            ("2023-08-05", "ENG:Luton", "ENG:B", 1, 0),
            ("2024-08-05", "ENG:Luton", "ENG:C", 1, 0),
        ]
    )
    jogos.loc[0, ["liga", "temporada"]] = ["E1", "2023/24"]
    jogos.loc[1, ["liga", "temporada"]] = ["E0", "2024/25"]

    assert modulo_elo.clubes_em_duas_divisoes_na_mesma_temporada(jogos).empty


# ----------------------------------------------------------------------------
# Erros
# ----------------------------------------------------------------------------
def test_tabela_sem_as_colunas_diz_o_que_falta() -> None:
    with pytest.raises(ErroDeElo, match="gols_mandante"):
        Elo().ratings_antes(
            pd.DataFrame(
                {
                    "data": pd.to_datetime(["2023-08-05"]),
                    "mandante": ["ENG:A"],
                    "visitante": ["ENG:B"],
                    "gols_visitante": [0],
                }
            )
        )


def test_k_nao_positivo_e_erro() -> None:
    with pytest.raises(ErroDeElo, match="positivo"):
        Elo(k=0.0)
