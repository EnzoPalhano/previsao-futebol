"""O relatório da Fase 5: o que ele promete estar escrito tem de estar escrito.

O teste mais útil aqui é ``test_toda_feature_tem_explicacao``. A especificação
pede que a importância venha acompanhada do significado de cada coluna, e uma
feature nova entra no gráfico automaticamente — mas não entra no dicionário de
explicações automaticamente. Sem este teste, a primeira feature acrescentada na
Fase 7 apareceria no relatório como um travessão.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from futebol.avaliacao import relatorio_fase5, selecao
from futebol.features import construtor
from futebol.modelos import gbm


def test_toda_feature_tem_explicacao_em_portugues() -> None:
    sem_explicacao = [
        nome
        for nome in construtor.nomes_das_features()
        if nome not in relatorio_fase5.O_QUE_CADA_FEATURE_SIGNIFICA
    ]

    assert not sem_explicacao, (
        f"features sem explicacao no relatorio: {sem_explicacao}. A especificacao "
        "pede a importancia COM o que cada coluna significa."
    )


def test_toda_feature_cai_numa_familia_conhecida() -> None:
    """Uma feature sem família viraria a fatia "outras" do gráfico, sem sentido."""
    orfas = [
        nome
        for nome in construtor.nomes_das_features()
        if gbm.familia_da_feature(nome) == "outras"
    ]

    assert not orfas, f"features sem familia: {orfas}"


def test_o_dicionario_de_explicacoes_nao_tem_sobra() -> None:
    """Explicação de coluna que não existe mais é documentação mentindo."""
    conhecidas = set(construtor.nomes_das_features())
    sobrando = set(relatorio_fase5.O_QUE_CADA_FEATURE_SIGNIFICA) - conhecidas

    assert not sobrando, f"explicacoes de features inexistentes: {sorted(sobrando)}"


def test_os_nomes_da_fase_5_batem_com_os_candidatos(bancada_fase5) -> None:
    """Se um candidato for renomeado, o relatório o classificaria como Fase 4."""
    cfg, jogos, features = bancada_fase5
    lista = selecao.candidatos_fase5(cfg, features, jogos=jogos)

    assert {c.nome for c in lista} == set(relatorio_fase5.DA_FASE_5)


def test_a_importancia_soma_cem_por_cento() -> None:
    importancia = pd.DataFrame(
        {
            "feature": ["dc_H", "elo_diferenca", "descanso_mandante"],
            "pct": [60.0, 30.0, 10.0],
            "familia": ["Dixon-Coles", "Elo", "calendário"],
        }
    )
    texto = relatorio_fase5._importancia(importancia, Path("x.png"))

    assert "60,0%" in texto
    assert "Dixon-Coles" in texto
    assert "Importância não é utilidade" in texto


def test_o_pre_registro_soma_as_fases_anteriores() -> None:
    texto = relatorio_fase5._pre_registro({"a": None, "b": None}, "2026-09-17")
    total = 13 + selecao.N_CONFIGURACOES_FASE_4 + len(relatorio_fase5.DA_FASE_5)

    assert f"**{total}**" in texto
    assert "nunca** é reescrito para baixo" in texto


@pytest.fixture(scope="module")
def bancada_fase5():
    import numpy as np

    from futebol.config import carregar_config

    gerador = np.random.default_rng(4)
    times = [f"ENG:T{i}" for i in range(6)]
    linhas = []
    for dia in range(200):
        casa, fora = gerador.choice(times, size=2, replace=False)
        linhas.append(
            (
                pd.Timestamp("2022-01-01") + pd.Timedelta(days=dia),
                str(casa),
                str(fora),
                float(gerador.integers(0, 4)),
                float(gerador.integers(0, 4)),
            )
        )
    jogos = pd.DataFrame(
        linhas,
        columns=["data", "mandante", "visitante", "gols_mandante", "gols_visitante"],
    )
    jogos["liga"] = "E0"
    jogos["temporada"] = "2023/24"
    cfg = carregar_config()
    features = construtor.construir(jogos, cfg=cfg)
    for coluna in construtor.COLUNAS_DC:
        features[coluna] = float("nan")
    return cfg, jogos, features[construtor.nomes_das_features()]
