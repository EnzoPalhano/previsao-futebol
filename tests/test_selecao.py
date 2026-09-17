"""Testes da escolha oficial do modelo (regras 9 e 11).

Duas coisas precisam ser verdade aqui, e nenhuma delas é sobre estatística:

1. **a escolha é por log loss**, e não pela ordem em que os candidatos foram
   escritos, nem pelo Brier, nem pela acurácia;
2. **a lista de candidatos é contável e estável.** A regra 11 manda registrar
   quantas configurações foram testadas; se a lista mudar de tamanho sem
   ninguém notar, o pré-registro vira ficção.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from futebol.avaliacao import selecao, validacao
from futebol.config import carregar_config
from futebol.modelos.baseline import Baseline
from simulacao import simular_liga


@pytest.fixture
def cfg_em_pasta_temporaria(tmp_path):
    """A configuração do projeto, com a raiz apontando para uma pasta de teste.

    Assim o cache de previsões é escrito e lido numa pasta descartável, sem
    encostar em ``data/processed`` do projeto.
    """
    return dataclasses.replace(carregar_config(), raiz=tmp_path)


def _tabela(voltas: int = 8) -> pd.DataFrame:
    jogos = simular_liga(voltas=voltas)
    diferenca = jogos["gols_mandante"] - jogos["gols_visitante"]
    return jogos.assign(
        grupo="grupo1",
        temporada="2019/20",
        resultado=np.where(diferenca > 0, "H", np.where(diferenca == 0, "D", "A")),
    )


# ----------------------------------------------------------------------------
# A lista de candidatos (regra 11)
# ----------------------------------------------------------------------------
def test_sao_treze_configuracoes_distintas() -> None:
    """O número que vai para o pré-registro sai daqui, não da memória."""
    cfg = carregar_config()
    lista = selecao.candidatos(cfg, _tabela(), inicio="2019-09-01")

    assert len(lista) == 13
    assert len({c.nome for c in lista}) == 13, "nome repetido faria o cache colidir"


def test_o_padrao_do_config_nao_e_contado_duas_vezes() -> None:
    """O ``xi`` e o ``m`` do config.yaml já estão no candidato 'dixon-coles'."""
    cfg = carregar_config()
    modelos = cfg.secao("modelos")
    nomes = {c.nome for c in selecao.candidatos(cfg, _tabela(), inicio="2019-09-01")}

    assert f"dc-xi-{modelos['dixon_coles']['xi']}" not in nomes
    assert f"dc-m-{modelos['shrinkage']['jogos_equivalentes']}" not in nomes


def test_todo_candidato_diz_quais_sao_os_parametros_dele() -> None:
    """"dixon-coles" não identifica uma configuração; xi e m identificam."""
    lista = selecao.candidatos(carregar_config(), _tabela(), inicio="2019-09-01")
    for candidato in lista:
        assert candidato.parametros, f"{candidato.nome} sem parâmetros registrados"
        assert candidato.descricao


def test_o_fator_casa_unico_sai_so_do_passado() -> None:
    """Regra 6: o número congelado não pode ter visto a janela de avaliação."""
    jogos = _tabela()
    corte = jogos["data"].iloc[len(jogos) // 2]
    lista = selecao.candidatos(carregar_config(), jogos, inicio=corte)

    candidato = next(c for c in lista if c.nome == "dc-casa-unica")
    from futebol.modelos.base import jogos_ate
    from futebol.modelos.poisson import fator_casa_global

    esperado = fator_casa_global(jogos_ate(jogos, corte))
    assert candidato.parametros["valor_fator_casa"] == pytest.approx(
        esperado, abs=1e-6
    )


# ----------------------------------------------------------------------------
# O cache
# ----------------------------------------------------------------------------
def test_o_cache_separa_janelas_diferentes(cfg_em_pasta_temporaria) -> None:
    """Previsões de janelas diferentes não podem cair no mesmo arquivo."""
    cfg = cfg_em_pasta_temporaria
    um = selecao.caminho_do_cache(cfg, "dixon-coles", "2021-07-01", "2024-06-03")
    outro = selecao.caminho_do_cache(cfg, "dixon-coles", "2022-07-01", "2024-06-03")
    assert um != outro
    assert um.parent == selecao.pasta_do_cache(cfg)


def test_segunda_rodada_le_do_cache(cfg_em_pasta_temporaria) -> None:
    cfg = cfg_em_pasta_temporaria
    jogos = _tabela()
    candidato = selecao.Candidato(
        nome="baseline-teste",
        descricao="para o teste",
        construir=lambda: Baseline(max_gols=6),
    )
    inicio = jogos["data"].iloc[len(jogos) // 2]

    avisos: list[str] = []
    primeira = selecao.rodar_candidato(
        jogos, candidato, cfg, inicio=inicio, aviso=avisos.append
    )
    segunda = selecao.rodar_candidato(
        jogos, candidato, cfg, inicio=inicio, aviso=avisos.append
    )

    assert len(primeira) == len(segunda) > 0
    assert any("cache" in aviso for aviso in avisos)
    pd.testing.assert_frame_equal(
        primeira[list(validacao.CHAVES_1X2)], segunda[list(validacao.CHAVES_1X2)]
    )


def test_forcar_ignora_o_cache(cfg_em_pasta_temporaria) -> None:
    cfg = cfg_em_pasta_temporaria
    jogos = _tabela()
    candidato = selecao.Candidato(
        nome="baseline-teste",
        descricao="para o teste",
        construir=lambda: Baseline(max_gols=6),
    )
    inicio = jogos["data"].iloc[len(jogos) // 2]

    selecao.rodar_candidato(jogos, candidato, cfg, inicio=inicio)
    avisos: list[str] = []
    selecao.rodar_candidato(
        jogos, candidato, cfg, inicio=inicio, forcar=True, aviso=avisos.append
    )
    assert any("medindo" in aviso for aviso in avisos)


# ----------------------------------------------------------------------------
# A escolha (regra 9)
# ----------------------------------------------------------------------------
def _previsoes(probabilidade_certa: float, n: int = 200) -> pd.DataFrame:
    resto = (1 - probabilidade_certa) / 2
    return pd.DataFrame(
        {
            "H": [probabilidade_certa] * n,
            "D": [resto] * n,
            "A": [resto] * n,
            "over25": [0.5] * n,
            "under25": [0.5] * n,
            "observado": [0] * n,
            "observado_ou": [0] * n,
            "liga": ["E0"] * n,
        }
    )


def _candidato(nome: str) -> selecao.Candidato:
    return selecao.Candidato(
        nome=nome,
        descricao=nome,
        construir=lambda: Baseline(max_gols=6),
        parametros={"marca": nome},
    )


def test_vence_quem_tem_a_menor_log_loss() -> None:
    previsoes = {
        "ruim": _previsoes(0.20),
        "bom": _previsoes(0.70),
        "meio": _previsoes(0.45),
    }
    lista = [_candidato(nome) for nome in previsoes]

    escolha = selecao.escolher(previsoes, lista)

    assert escolha.vencedor.nome == "bom"
    assert [m.nome for m in escolha.medidas] == ["bom", "meio", "ruim"]
    assert escolha.parametros == {"marca": "bom"}
    assert escolha.n_configuracoes == 3


def test_a_margem_sobre_o_segundo_e_reportada() -> None:
    """Escolha apertada e escolha folgada precisam ser distinguíveis."""
    previsoes = {"bom": _previsoes(0.70), "quase": _previsoes(0.69)}
    escolha = selecao.escolher(previsoes, [_candidato(n) for n in previsoes])

    assert escolha.vencedor.nome == "bom"
    assert escolha.margem == pytest.approx(np.log(0.70) - np.log(0.69), abs=1e-9)
    assert escolha.margem < 0.02, "esta é uma escolha apertada"


def test_a_escolha_mede_todos_nos_mesmos_jogos() -> None:
    """Um candidato que pulou rodadas não pode parecer melhor por isso."""
    completo = _previsoes(0.50, n=200)
    parcial = _previsoes(0.80, n=200).iloc[:120]

    escolha = selecao.escolher(
        {"completo": completo, "parcial": parcial},
        [_candidato("completo"), _candidato("parcial")],
    )
    assert {m.n for m in escolha.medidas} == {120}
