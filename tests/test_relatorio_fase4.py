"""Testes das tabelas de grade do relatório da Fase 4.

O relatório é quase todo texto montado a partir de números já medidos e
testados em ``test_validacao.py`` e ``test_selecao.py``. O que sobra de lógica
própria — e portanto de risco — são as duas tabelas de varredura: elas traduzem
um valor da grade (``xi = 0,0018``) no nome do candidato que o mediu
(``dixon-coles``, porque esse valor é o padrão do ``config.yaml``).

É uma tradução chata e fácil de errar, e o erro seria mudo: a tabela mostraria o
número de outra configuração, com o rótulo certo.
"""

from __future__ import annotations

import numpy as np
import pytest

from futebol.avaliacao import relatorio_fase4, selecao, validacao
from futebol.config import carregar_config
from simulacao import simular_liga


def _medida(nome: str, log_loss: float) -> validacao.Medida:
    return validacao.Medida(
        nome=nome,
        n=1000,
        log_loss=log_loss,
        brier=0.6,
        acuracia=0.5,
        ece=0.01,
        log_loss_ou=0.68,
    )


def _por_nome(cfg) -> dict[str, validacao.Medida]:
    """Uma medida para cada candidato da lista oficial."""
    xi_padrao = float(cfg.secao("modelos")["dixon_coles"]["xi"])
    m_padrao = float(cfg.secao("modelos")["shrinkage"]["jogos_equivalentes"])
    nomes = ["baseline", "poisson", "dixon-coles", "dc-casa-unica"]
    nomes += [f"dc-xi-{xi}" for xi in selecao.GRADE_XI if xi != xi_padrao]
    nomes += [f"dc-m-{m}" for m in selecao.GRADE_ENCOLHIMENTO if m != m_padrao]
    return {nome: _medida(nome, 1.0 + 0.001 * posicao) for posicao, nome in enumerate(nomes)}


def test_a_grade_de_xi_cobre_todos_os_valores() -> None:
    cfg = carregar_config()
    tabela = relatorio_fase4._varredura_xi(cfg, _por_nome(cfg), {})

    assert list(tabela["xi"]) == list(selecao.GRADE_XI)
    assert tabela["log_loss"].notna().all()


def test_o_valor_padrao_da_grade_usa_a_medida_do_dixon_coles() -> None:
    """``xi = 0,0018`` não tem candidato próprio: ele **é** o 'dixon-coles'."""
    cfg = carregar_config()
    medidas = _por_nome(cfg)
    tabela = relatorio_fase4._varredura_xi(cfg, medidas, {})

    xi_padrao = float(cfg.secao("modelos")["dixon_coles"]["xi"])
    linha = tabela.loc[tabela["xi"] == xi_padrao].iloc[0]
    assert linha["log_loss"] == pytest.approx(medidas["dixon-coles"].log_loss)


def test_a_meia_vida_e_legivel_e_o_zero_e_tratado() -> None:
    cfg = carregar_config()
    tabela = relatorio_fase4._varredura_xi(cfg, _por_nome(cfg), {})

    sem_decaimento = tabela.loc[tabela["xi"] == 0.0].iloc[0]
    assert sem_decaimento["meia_vida_texto"] == "sem decaimento"

    com_decaimento = tabela.loc[tabela["xi"] == 0.0018].iloc[0]
    assert com_decaimento["meia_vida_texto"] == f"{np.log(2) / 0.0018:.0f} dias"


def test_a_grade_de_encolhimento_cobre_todos_os_valores() -> None:
    cfg = carregar_config()
    tabela = relatorio_fase4._varredura_encolhimento(cfg, _por_nome(cfg))

    assert list(tabela["jogos_equivalentes"]) == list(selecao.GRADE_ENCOLHIMENTO)
    # Peso próprio com 10 jogos: n/(n+m) = 10/(10+m).
    linha = tabela.loc[tabela["jogos_equivalentes"] == 6].iloc[0]
    assert linha["peso_com_10_jogos"] == pytest.approx(10 / 16)


def test_o_mercado_nao_disputa_a_escolha() -> None:
    """Regra 9: o mercado é régua, não candidato.

    Se ele entrasse na seleção venceria sempre — e o projeto estaria
    "escolhendo" algo que não é um modelo dele.
    """
    jogos = simular_liga(voltas=2)
    nomes = {
        candidato.nome
        for candidato in selecao.candidatos(
            carregar_config(), jogos, inicio=jogos["data"].max()
        )
    }
    assert relatorio_fase4.NOME_MERCADO not in nomes
    assert "dixon-coles" in nomes
