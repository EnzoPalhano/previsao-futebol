"""Testes do teste final — a fase que roda uma vez.

⚠️ **Nenhum teste aqui abre o cofre de verdade.** Eles conferem a trava, o
pré-registro e o recorte da janela, tudo em tabelas montadas à mão. O teste
final propriamente dito é um comando que o Enzo roda, uma vez, e cujo resultado
vira relatório.

O teste mais importante do arquivo é
:func:`test_o_config_ainda_bate_com_o_pre_registro`: ele é a razão de a
configuração estar congelada em código. O ``CLAUDE.md`` não é versionado (regra
15b), então o pré-registro que mora lá não tem testemunha no histórico do Git e
pode ser editado depois sem rastro. A cópia em código tem data de commit, e este
teste garante que ela e o ``config.yaml`` não se separem em silêncio.
"""

from __future__ import annotations

import pandas as pd
import pytest

from futebol.avaliacao import divisao, teste_final
from futebol.config import carregar_config


@pytest.fixture(scope="module")
def cfg():
    return carregar_config()


def _tabela(temporadas_e_datas) -> pd.DataFrame:
    """Uma tabela mínima com o que o recorte da janela precisa."""
    linhas = [
        {
            "data": pd.Timestamp(data),
            "temporada": temporada,
            "liga": "E0",
            "mandante": "ENG:A",
            "visitante": "ENG:B",
        }
        for temporada, data in temporadas_e_datas
    ]
    return pd.DataFrame(linhas)


# ----------------------------------------------------------------------------
# O pré-registro
# ----------------------------------------------------------------------------
def test_o_config_ainda_bate_com_o_pre_registro(cfg) -> None:
    """Se o config.yaml mudar depois de 21/09/2026, o pytest fica vermelho.

    A alternativa seria o teste final rodar com uma configuração diferente da
    registrada — e produzir um número que não responde à pergunta que o
    pré-registro fez.
    """
    teste_final.conferir_config(cfg)


def test_config_alterado_derruba_o_teste_final(cfg) -> None:
    """A trava precisa realmente travar, e não só existir."""

    class ConfigMexido:
        def __init__(self, original):
            self.bruto = {
                **original.bruto,
                "backtest": {**original.bruto["backtest"], "ev_minimo": 0.10},
            }

        def secao(self, nome):
            return self.bruto[nome]

    with pytest.raises(teste_final.PreRegistroViolado, match="ev_minimo"):
        teste_final.conferir_config(ConfigMexido(cfg))


def test_o_pre_registro_manda_apostar_na_odd_media(cfg) -> None:
    """Regra 8: a odd da aposta é a média pré-jogo, nunca a máxima."""
    assert teste_final.CONFIGURACAO["odd_da_aposta"] == "odd_pre"
    assert "max" not in str(teste_final.CONFIGURACAO["odd_da_aposta"]).lower()


def test_a_contagem_de_configuracoes_nunca_encolhe() -> None:
    """Regra 11: o número soma, nunca é reescrito para baixo.

    108 = 29 de modelo (Fases 3 a 5) + 16 (Fase 6) + 63 (Fase 7) + 0 (Fase 8).
    """
    assert teste_final.CONFIGURACOES_TESTADAS == 108


# ----------------------------------------------------------------------------
# A janela
# ----------------------------------------------------------------------------
def test_a_janela_pega_as_duas_formas_de_temporada() -> None:
    """``2024/25`` e ``2024`` são o mesmo período.

    É a armadilha registrada no CLAUDE.md: um filtro que só conhece a forma
    europeia descarta Brasil, EUA, Noruega e Japão **em silêncio**.
    """
    assert teste_final.do_teste_final("2024/25")
    assert teste_final.do_teste_final("2024")
    assert teste_final.do_teste_final("2025/26")
    assert teste_final.do_teste_final("2025")


def test_a_janela_deixa_de_fora_a_temporada_em_andamento() -> None:
    """Temporada incompleta não é amostra de temporada."""
    assert not teste_final.do_teste_final("2026")
    assert not teste_final.do_teste_final("2026/27")


def test_a_janela_deixa_de_fora_o_que_veio_antes() -> None:
    """Treino e validação não podem entrar no teste final."""
    for temporada in ("2019/20", "2021/22", "2023/24", "2023"):
        assert not teste_final.do_teste_final(temporada)


def test_o_recorte_guarda_o_historico_e_corta_o_futuro(cfg) -> None:
    """A tabela do walk-forward mantém o passado e solta o que segue trancado.

    Prever a rodada de agosto de 2024 **precisa** do histórico até julho de
    2024, e isso é legítimo — a regra 6 proíbe usar o futuro, não o passado. O
    que não pode entrar é a temporada que ainda está rolando.
    """
    tabela = _tabela(
        [
            ("2022/23", "2023-01-10"),
            ("2023/24", "2024-01-10"),
            ("2024/25", "2024-09-10"),
            ("2025", "2025-05-10"),
            ("2026/27", "2026-09-10"),
        ]
    )
    janela = teste_final.abrir_cofre(tabela, cfg)

    temporadas = set(janela.jogos["temporada"])
    assert "2022/23" in temporadas, "o histórico sumiu"
    assert "2023/24" in temporadas
    assert "2026/27" not in temporadas, "temporada em andamento entrou"
    assert janela.avaliados == 2
    assert janela.ainda_trancados == 1
    assert janela.temporadas == ("2024/25", "2025")


def test_o_recorte_recusa_tabela_sem_teste_final(cfg) -> None:
    """Um teste final sobre nada é pior que nenhum teste final."""
    tabela = _tabela([("2022/23", "2023-01-10"), ("2023/24", "2024-01-10")])
    with pytest.raises(ValueError, match="Nenhum jogo das temporadas"):
        teste_final.abrir_cofre(tabela, cfg)


def test_a_janela_comeca_onde_o_cofre_comeca(cfg) -> None:
    """O que a Fase 8 usou termina exatamente onde o teste final começa.

    Sem isso haveria um buraco (jogos que ninguém avaliou) ou uma sobreposição
    (jogos avaliados duas vezes, uma delas indevidamente).
    """
    assert divisao.ano_de_corte(cfg) == min(teste_final.ANOS_DO_TESTE_FINAL)
