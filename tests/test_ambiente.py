"""Testes da Fase 0: provam que o ambiente está montado corretamente.

Estes testes não testam regra de negócio nenhuma. Eles respondem três
perguntas que precisam estar resolvidas antes de qualquer código de verdade:

1. O ``pytest`` está funcionando?
2. O pacote ``futebol`` é importável? (é isso que prova que o
   ``pyproject.toml`` e o ``pip install -e .`` estão corretos — sem isso,
   com o layout ``src/``, nada mais funciona)
3. O ``config.yaml`` carrega e está coerente?
"""

from __future__ import annotations

import sys

import pytest


# ----------------------------------------------------------------------
# 1. O pytest funciona?
# ----------------------------------------------------------------------
def test_pytest_funciona() -> None:
    """O teste mais bobo possível: se este falhar, nada mais importa."""
    assert 2 + 2 == 4


def test_versao_minima_do_python() -> None:
    """O projeto exige Python 3.11 ou superior."""
    assert sys.version_info >= (3, 11), (
        f"Python 3.11+ é necessário, mas este ambiente tem {sys.version.split()[0]}."
    )


# ----------------------------------------------------------------------
# 2. O pacote é importável?
# ----------------------------------------------------------------------
def test_pacote_futebol_importavel() -> None:
    """Prova que o ``pip install -e .`` funcionou.

    Com o layout ``src/``, o Python só acha o pacote ``futebol`` se o projeto
    tiver sido instalado em modo editável. Se este teste falhar, rode::

        pip install -e ".[dev]"
    """
    import futebol

    assert futebol is not None


def test_subpacotes_existem() -> None:
    """Todos os subpacotes previstos na estrutura devem ser importáveis."""
    subpacotes = [
        "futebol.dados",
        "futebol.odds",
        "futebol.modelos",
        "futebol.features",
        "futebol.avaliacao",
        "futebol.backtest",
        "futebol.app",
    ]
    for nome in subpacotes:
        __import__(nome)


# ----------------------------------------------------------------------
# 3. A configuração carrega e é coerente?
# ----------------------------------------------------------------------
def test_config_carrega() -> None:
    """O ``config.yaml`` deve ser encontrado e lido sem erro."""
    from futebol.config import carregar_config

    cfg = carregar_config()
    assert cfg.seed == 42, "A semente deve ser 42 (regra 2.4: resultados reproduzíveis)."


def test_camada_ativa_existe() -> None:
    """A camada de ligas apontada em ``ligas.ativa`` deve existir de verdade."""
    from futebol.config import carregar_config

    cfg = carregar_config()
    ligas = cfg.ligas_ativas()
    assert "grupo1" in ligas and "grupo2" in ligas
    total = len(ligas["grupo1"]) + len(ligas["grupo2"])
    assert total > 0, "A camada ativa não tem nenhuma liga configurada."


def test_camada_inexistente_da_erro_claro() -> None:
    """Apontar para uma camada que não existe deve falhar com mensagem útil."""
    from futebol.config import Config, ErroDeConfiguracao

    cfg = Config(
        bruto={"ligas": {"ativa": "nao_existe", "camadas": {"real": {}}}},
        seed=42,
        raiz=".",  # type: ignore[arg-type]
    )
    with pytest.raises(ErroDeConfiguracao, match="não existe"):
        cfg.ligas_ativas()


def test_secao_obrigatoria_faltando_da_erro() -> None:
    """Um config.yaml incompleto deve ser recusado na hora de carregar."""
    from futebol.config import ErroDeConfiguracao, carregar_config

    with pytest.raises(ErroDeConfiguracao, match="não encontrado"):
        carregar_config("caminho/que/nao/existe.yaml")


# ----------------------------------------------------------------------
# 4. Regras do projeto que já dá para verificar automaticamente
# ----------------------------------------------------------------------
def test_grupo2_nunca_entra_em_backtest() -> None:
    """Guarda da regra 12 do projeto (secao 4.4 da especificacao).

    As ligas do Grupo 2 (BRA, ARG, USA, ...) só têm odds de fechamento.
    Elas nunca podem aparecer numa camada marcada como apostável.
    Este teste trava a lista para que ninguém a mova por engano.
    """
    from futebol.config import carregar_config

    cfg = carregar_config()
    camadas = cfg.bruto["ligas"]["camadas"]

    paises_grupo2 = {
        "ARG", "AUT", "BRA", "CHN", "DNK", "FIN", "IRL", "JPN",
        "MEX", "NOR", "POL", "ROU", "RUS", "SWE", "SWZ", "USA",
    }

    for nome, camada in camadas.items():
        grupo1 = set(camada.get("grupo1") or [])
        intrusos = grupo1 & paises_grupo2
        assert not intrusos, (
            f"A camada {nome!r} tem país do Grupo 2 dentro de grupo1: {intrusos}. "
            "Grupo 2 só tem odds de fechamento e não pode entrar em backtest nem CLV."
        )


def test_backtest_nao_usa_odd_maxima() -> None:
    """Guarda da regra 2.6a: apostar na odd média, nunca na máxima.

    Apostar na ``Max`` infla o ROI artificialmente e é o erro que invalida
    a maior parte dos backtests de aposta.
    """
    from futebol.config import carregar_config

    cfg = carregar_config()
    coluna = cfg.secao("backtest")["coluna_odd_aposta"]
    assert "max" not in str(coluna).lower(), (
        f"A coluna de aposta do backtest é {coluna!r}. "
        "A regra 2.6a proíbe usar a odd máxima como cenário principal."
    )


def test_selecao_de_modelo_e_por_log_loss() -> None:
    """Guarda da regra 2.6b: modelo se escolhe por log loss, nunca por ROI."""
    from futebol.config import carregar_config

    cfg = carregar_config()
    metrica = str(cfg.secao("avaliacao")["metrica_selecao_modelo"]).lower()
    assert metrica in {"log_loss", "brier"}, (
        f"Métrica de seleção de modelo é {metrica!r}. "
        "A regra 2.6b exige log loss (ou Brier), nunca ROI."
    )


def test_uma_selecao_por_jogo_nas_multiplas() -> None:
    """Guarda da Fase 7: mercados do mesmo jogo são correlacionados."""
    from futebol.config import carregar_config

    cfg = carregar_config()
    assert cfg.secao("multiplas")["uma_selecao_por_jogo"] is True, (
        "Múltiplas precisam de no máximo uma seleção por jogo: mercados do "
        "mesmo jogo são correlacionados e multiplicar probabilidades seria errado."
    )
