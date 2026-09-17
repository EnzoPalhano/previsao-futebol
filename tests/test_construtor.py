"""As features: conferidas na mão, e provadas causais.

O teste que vale mais aqui é ``test_apagar_o_futuro_nao_muda_o_passado``. Ele é a
definição operacional da regra 6: se as features de um jogo de março mudam
quando eu acrescento os jogos de abril, então alguma coluna está olhando o
futuro. É um teste que não depende de eu ter lembrado de pôr ``shift(1)`` em
cada lugar — ele pega o esquecimento onde quer que ele esteja.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futebol.config import carregar_config
from futebol.features import construtor
from futebol.features.construtor import ErroDeFeatures


def _jogos(linhas: list[tuple[str, str, str, float, float]]) -> pd.DataFrame:
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


def _liga_de_mentira(dias: int = 120, seed: int = 11) -> pd.DataFrame:
    """Uma liga de 8 times, um jogo por dia, placares sorteados."""
    gerador = np.random.default_rng(seed)
    times = [f"ENG:T{i}" for i in range(8)]
    linhas = []
    for dia in range(dias):
        casa, fora = gerador.choice(times, size=2, replace=False)
        linhas.append(
            (
                str(pd.Timestamp("2023-01-01") + pd.Timedelta(days=dia)),
                str(casa),
                str(fora),
                float(gerador.integers(0, 4)),
                float(gerador.integers(0, 4)),
            )
        )
    return _jogos(linhas)


# ----------------------------------------------------------------------------
# Causalidade — o que este arquivo existe para provar
# ----------------------------------------------------------------------------
def test_apagar_o_futuro_nao_muda_o_passado() -> None:
    """Features de um jogo não podem depender de nada posterior a ele.

    Se acrescentar os jogos de abril mudar qualquer feature de um jogo de março,
    há uma coluna olhando o futuro — não importa qual, nem onde.
    """
    jogos = _liga_de_mentira()
    corte = jogos["data"].iloc[len(jogos) // 2]

    com_futuro = construtor.construir(jogos)
    so_passado = construtor.construir(jogos.loc[jogos["data"] < corte])

    pd.testing.assert_frame_equal(
        com_futuro.loc[so_passado.index], so_passado, check_like=True
    )


def test_o_proprio_jogo_nao_entra_nas_features_dele() -> None:
    """Mudar o placar de um jogo não pode mexer nas features desse mesmo jogo."""
    jogos = _liga_de_mentira()
    alvo = jogos.index[-1]

    antes = construtor.construir(jogos).loc[alvo]
    alterados = jogos.copy()
    alterados.loc[alvo, ["gols_mandante", "gols_visitante"]] = [9.0, 0.0]
    depois = construtor.construir(alterados).loc[alvo]

    pd.testing.assert_series_equal(antes, depois)


def test_jogo_do_mesmo_dia_nao_entra_e_o_caso_e_barrado() -> None:
    """Dois jogos do mesmo time no mesmo dia quebram o pressuposto do shift(1)."""
    jogos = _jogos(
        [
            ("2023-08-05", "ENG:A", "ENG:B", 3.0, 0.0),
            ("2023-08-05", "ENG:C", "ENG:A", 0.0, 1.0),
        ]
    )
    with pytest.raises(ErroDeFeatures, match="um jogo por time por dia"):
        construtor.construir(jogos)


def test_clube_em_duas_divisoes_na_mesma_temporada_e_barrado() -> None:
    jogos = _jogos(
        [
            ("2023-08-05", "ENG:Igual", "ENG:B", 1.0, 0.0),
            ("2023-08-12", "ENG:Igual", "ENG:C", 1.0, 0.0),
        ]
    )
    jogos.loc[1, "liga"] = "E2"
    with pytest.raises(ErroDeFeatures, match="homônimos"):
        construtor.construir(jogos)


# ----------------------------------------------------------------------------
# As contas, conferidas na mão
# ----------------------------------------------------------------------------
def test_media_de_gols_usa_so_os_jogos_anteriores() -> None:
    """ENG:A faz 1, 2, 3 e 4 gols em casa; a média móvel anda um jogo atrás."""
    jogos = _jogos(
        [
            (f"2023-08-{dia:02d}", "ENG:A", f"ENG:B{dia}", float(dia), 0.0)
            for dia in range(1, 5)
        ]
    )
    features = construtor.construir(jogos)

    esperado = [np.nan, 1.0, 1.5, 2.0]
    assert features["gols_feitos5_mandante"].tolist()[1:] == esperado[1:]
    assert np.isnan(features["gols_feitos5_mandante"].iloc[0])


def test_a_janela_de_cinco_esquece_o_sexto_jogo_atras() -> None:
    jogos = _jogos(
        [
            (f"2023-08-{dia:02d}", "ENG:A", f"ENG:B{dia}", float(dia), 0.0)
            for dia in range(1, 8)
        ]
    )
    features = construtor.construir(jogos)

    # No 7º jogo, a janela de 5 cobre os gols 2,3,4,5,6 — o primeiro já saiu.
    assert features["gols_feitos5_mandante"].iloc[6] == pytest.approx(4.0)
    assert features["gols_feitos10_mandante"].iloc[6] == pytest.approx(3.5)


def test_casa_e_fora_sao_medias_separadas() -> None:
    """O mandante traz a forma dele em casa; o visitante, a dele fora."""
    jogos = _jogos(
        [
            ("2023-08-01", "ENG:A", "ENG:X", 5.0, 0.0),  # A em casa: 5 gols
            ("2023-08-08", "ENG:Y", "ENG:A", 0.0, 1.0),  # A fora: 1 gol
            ("2023-08-15", "ENG:A", "ENG:Z", 0.0, 0.0),  # A em casa de novo
            ("2023-08-22", "ENG:W", "ENG:A", 0.0, 0.0),  # A fora de novo
        ]
    )
    features = construtor.construir(jogos)

    # 3º jogo: A é mandante, então vale só o jogo dele em casa (5 gols).
    assert features["gols_feitos5_mandante"].iloc[2] == pytest.approx(5.0)
    # 4º jogo: A é visitante, então vale só o jogo dele fora (1 gol).
    assert features["gols_feitos5_visitante"].iloc[3] == pytest.approx(1.0)


def test_pontos_contam_tres_um_e_zero_em_qualquer_mando() -> None:
    jogos = _jogos(
        [
            ("2023-08-01", "ENG:A", "ENG:X", 2.0, 0.0),  # vitória: 3
            ("2023-08-08", "ENG:Y", "ENG:A", 1.0, 1.0),  # empate fora: 1
            ("2023-08-15", "ENG:A", "ENG:Z", 0.0, 1.0),  # derrota: 0
            ("2023-08-22", "ENG:A", "ENG:W", 0.0, 0.0),
        ]
    )
    features = construtor.construir(jogos)

    assert features["pontos5_mandante"].iloc[3] == pytest.approx(4.0)
    assert features["historico_mandante"].iloc[3] == pytest.approx(3.0)


def test_descanso_e_em_dias_desde_o_jogo_anterior() -> None:
    jogos = _jogos(
        [
            ("2023-08-01", "ENG:A", "ENG:B", 1.0, 0.0),
            ("2023-08-04", "ENG:A", "ENG:C", 1.0, 0.0),
            ("2023-08-14", "ENG:C", "ENG:A", 1.0, 0.0),
        ]
    )
    features = construtor.construir(jogos)

    assert np.isnan(features["descanso_mandante"].iloc[0])
    assert features["descanso_mandante"].iloc[1] == pytest.approx(3.0)
    # 3º jogo: o mandante (C) jogou dia 4, o visitante (A) também.
    assert features["descanso_mandante"].iloc[2] == pytest.approx(10.0)
    assert features["descanso_diferenca"].iloc[2] == pytest.approx(0.0)


def test_jogo_sem_placar_nao_entra_nas_medias() -> None:
    """Partida futura não pode ser lida como um 0x0."""
    jogos = _jogos(
        [
            ("2023-08-01", "ENG:A", "ENG:B", np.nan, np.nan),
            ("2023-08-08", "ENG:A", "ENG:C", 4.0, 0.0),
            ("2023-08-15", "ENG:A", "ENG:D", 0.0, 0.0),
        ]
    )
    features = construtor.construir(jogos)

    assert features["gols_feitos5_mandante"].iloc[2] == pytest.approx(4.0)
    assert features["historico_mandante"].iloc[2] == pytest.approx(1.0)


def test_estadio_vazio_marca_o_periodo_de_portoes_fechados() -> None:
    jogos = _jogos(
        [
            ("2019-08-01", "ENG:A", "ENG:B", 1.0, 0.0),
            ("2020-10-01", "ENG:C", "ENG:D", 1.0, 0.0),
            ("2022-08-01", "ENG:E", "ENG:F", 1.0, 0.0),
        ]
    )
    features = construtor.construir(jogos)

    assert features["estadio_vazio"].tolist() == [0.0, 1.0, 0.0]


def test_o_elo_entra_nas_features() -> None:
    jogos = _liga_de_mentira(dias=30)
    features = construtor.construir(jogos)

    assert features["elo_mandante"].iloc[0] == 1500.0
    esperado = features["elo_mandante"] - features["elo_visitante"]
    pd.testing.assert_series_equal(
        features["elo_diferenca"], esperado, check_names=False
    )


# ----------------------------------------------------------------------------
# Forma da saída
# ----------------------------------------------------------------------------
def test_o_indice_e_o_da_entrada_e_a_ordem_nao_importa() -> None:
    jogos = _liga_de_mentira(dias=40)
    jogos.index = range(100, 140)

    em_ordem = construtor.construir(jogos)
    embaralhada = construtor.construir(jogos.sample(frac=1.0, random_state=5))

    assert list(em_ordem.index) == list(jogos.index)
    pd.testing.assert_frame_equal(em_ordem, embaralhada.reindex(em_ordem.index))


def test_nomes_das_features_descreve_o_que_construir_devolve() -> None:
    """A lista de nomes é usada pelo LightGBM: se ela mentir, o modelo quebra."""
    features = construtor.construir(_liga_de_mentira(dias=30))

    assert sorted(features.columns) == sorted(
        construtor.nomes_das_features(com_dixon_coles=False)
    )


def test_toda_feature_e_numerica() -> None:
    features = construtor.construir(_liga_de_mentira(dias=30))

    assert all(
        pd.api.types.is_numeric_dtype(features[coluna]) for coluna in features.columns
    )


def test_tabela_sem_colunas_diz_o_que_falta() -> None:
    with pytest.raises(ErroDeFeatures, match="temporada"):
        construtor.construir(
            pd.DataFrame(
                {
                    "data": pd.to_datetime(["2023-08-01"]),
                    "liga": ["E0"],
                    "mandante": ["ENG:A"],
                    "visitante": ["ENG:B"],
                    "gols_mandante": [1.0],
                    "gols_visitante": [0.0],
                }
            )
        )


# ----------------------------------------------------------------------------
# A feature do Dixon-Coles
# ----------------------------------------------------------------------------
def test_os_marcos_de_reajuste_cobrem_a_tabela() -> None:
    jogos = _liga_de_mentira(dias=100)
    marcos = construtor.marcos_de_reajuste(jogos, passo_dias=30)

    assert marcos[0] == jogos["data"].min()
    assert marcos[-1] > jogos["data"].max()
    assert (marcos.to_series().diff().dropna() == pd.Timedelta(days=30)).all()


def test_a_feature_do_dixon_coles_nao_olha_o_futuro() -> None:
    """Mesma prova do teste-ouro, agora na coluna que custa caro.

    O ajuste de um marco só vê jogos anteriores ao marco, e o marco é anterior
    ou igual à data prevista — então nenhuma previsão viu o próprio jogo.
    """
    cfg = carregar_config()
    jogos = _liga_de_mentira(dias=300, seed=3)
    corte = jogos["data"].iloc[200]

    inteira = construtor.probabilidades_do_dixon_coles(jogos, cfg, passo_dias=30)
    truncada = construtor.probabilidades_do_dixon_coles(
        jogos.loc[jogos["data"] < corte], cfg, passo_dias=30
    )
    comuns = truncada.dropna().index

    assert len(comuns) > 0, "o teste não mediu nada; aumente a simulação"
    pd.testing.assert_frame_equal(inteira.loc[comuns], truncada.loc[comuns])


def test_liga_sem_historico_suficiente_sai_ausente() -> None:
    """Inventar probabilidade onde não há treino seria pior que admitir que não sabe."""
    cfg = carregar_config()
    jogos = _liga_de_mentira(dias=40)
    probabilidades = construtor.probabilidades_do_dixon_coles(
        jogos, cfg, passo_dias=30, minimo_de_treino=100
    )

    assert probabilidades.isna().all().all()


def test_as_colunas_do_dixon_coles_entram_quando_fornecidas() -> None:
    cfg = carregar_config()
    jogos = _liga_de_mentira(dias=200, seed=4)
    probabilidades = construtor.probabilidades_do_dixon_coles(jogos, cfg)
    features = construtor.construir(jogos, cfg=cfg, probabilidades_dc=probabilidades)

    assert sorted(features.columns) == sorted(construtor.nomes_das_features())
    validas = features[list(construtor.COLUNAS_DC)].dropna()
    soma = validas[["dc_H", "dc_D", "dc_A"]].sum(axis=1)
    assert np.allclose(soma, 1.0)
