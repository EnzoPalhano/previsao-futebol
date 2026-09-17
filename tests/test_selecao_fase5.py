"""Os candidatos que a Fase 5 acrescenta, e o cache das features.

A regra 11 é o assunto deste arquivo. Cada configuração medida na validação é
uma chance a mais de a melhor estar na frente por acaso, então o que importa
aqui é: são poucas, são **distintas** entre si, e cada uma se identifica pelos
parâmetros — nunca pelo nome, que é a lição que a Fase 4 deixou.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from futebol.avaliacao import selecao
from futebol.config import carregar_config
from futebol.features import construtor


@pytest.fixture(scope="module")
def bancada():
    gerador = np.random.default_rng(9)
    times = [f"ENG:T{i}" for i in range(8)]
    linhas = []
    for dia in range(400):
        casa, fora = gerador.choice(times, size=2, replace=False)
        linhas.append(
            (
                pd.Timestamp("2021-01-01") + pd.Timedelta(days=dia),
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
    # As colunas do Dixon-Coles entram como ausentes: aqui o que se testa é a
    # montagem dos candidatos, não a qualidade da feature.
    for coluna in construtor.COLUNAS_DC:
        features[coluna] = np.nan
    return cfg, jogos, features[construtor.nomes_das_features()]


# ----------------------------------------------------------------------------
# Os candidatos
# ----------------------------------------------------------------------------
def test_sao_tres_configuracoes_distintas(bancada) -> None:
    cfg, jogos, features = bancada
    lista = selecao.candidatos_fase5(cfg, features, jogos=jogos)

    assert len(lista) == 3
    assert len({c.nome for c in lista}) == 3
    assinaturas = {selecao.marca_dos_parametros(c.parametros) for c in lista}
    assert len(assinaturas) == 3, "duas configuracoes disputariam o mesmo cache"


def test_a_variante_sem_dixon_coles_nao_recebe_as_colunas_dele(bancada) -> None:
    """É a pergunta mais informativa da fase; se ela vazar, não pergunta nada."""
    cfg, jogos, features = bancada
    por_nome = {c.nome: c for c in selecao.candidatos_fase5(cfg, features, jogos=jogos)}

    sem_dc = por_nome["gbm-sem-dc"]
    assert sem_dc.parametros["com_dixon_coles"] is False
    assert por_nome["gbm"].parametros["com_dixon_coles"] is True

    colunas = sem_dc.construir().fabrica.colunas
    assert not any(coluna.startswith("dc_") for coluna in colunas)


def test_o_gbm_e_medido_com_todas_as_ligas_juntas(bancada) -> None:
    """Escopo "liga" daria ao modelo global um trinta e oito avos dos dados."""
    cfg, jogos, features = bancada
    lista = selecao.candidatos_fase5(cfg, features, jogos=jogos)

    assert all(c.escopo == "tudo" for c in lista)


def test_a_contagem_da_fase_4_nao_e_substituida(bancada) -> None:
    """Regra 11: o número de configurações testadas soma, nunca troca."""
    cfg, jogos, features = bancada
    da_fase4 = selecao.candidatos(cfg, jogos, inicio="2021-01-01")
    da_fase5 = selecao.candidatos_fase5(cfg, features, jogos=jogos)

    assert len(da_fase4) == selecao.N_CONFIGURACOES_FASE_4
    assert not {c.nome for c in da_fase4} & {c.nome for c in da_fase5}


# ----------------------------------------------------------------------------
# O cache das features
# ----------------------------------------------------------------------------
def test_o_cache_das_features_descreve_a_tabela(bancada) -> None:
    """Tabelas diferentes não podem cair no mesmo arquivo de features."""
    cfg, jogos, _ = bancada
    inteira = construtor.caminho_do_cache(cfg, jogos)
    recorte = construtor.caminho_do_cache(cfg, jogos.iloc[:-10])

    assert inteira != recorte
    assert str(len(jogos)) in inteira.name


def test_o_cache_grava_e_rele_as_mesmas_features(bancada, tmp_path) -> None:
    cfg, jogos, _ = bancada
    em_pasta_temporaria = dataclasses.replace(cfg, raiz=tmp_path)

    primeira = construtor.carregar_ou_construir(em_pasta_temporaria, jogos)
    avisos: list[str] = []
    segunda = construtor.carregar_ou_construir(
        em_pasta_temporaria, jogos, aviso=avisos.append
    )

    assert any("cache" in aviso for aviso in avisos)
    pd.testing.assert_frame_equal(primeira, segunda)
    assert list(primeira.columns) == construtor.nomes_das_features()


def test_forcar_recalcula_as_features(bancada, tmp_path) -> None:
    cfg, jogos, _ = bancada
    em_pasta_temporaria = dataclasses.replace(cfg, raiz=tmp_path)

    construtor.carregar_ou_construir(em_pasta_temporaria, jogos)
    avisos: list[str] = []
    construtor.carregar_ou_construir(
        em_pasta_temporaria, jogos, forcar=True, aviso=avisos.append
    )

    assert any("calculando" in aviso for aviso in avisos)
