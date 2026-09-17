"""Testes da trava do teste final (regra 7).

A armadilha que estes testes existem para pegar está registrada no CLAUDE.md:
competição de ano civil chama a temporada de ``2024``, não de ``2024/25``. Um
filtro que só conheça a forma europeia deixaria o Brasileirão, a MLS e o
Japonês **inteiros** vazarem para dentro do treino — em silêncio, sem erro
nenhum, e com um resultado final que pareceria ótimo.
"""

from __future__ import annotations

import pandas as pd
import pytest

from futebol.avaliacao import divisao
from futebol.config import Config, ErroDeConfiguracao, carregar_config


def _config(codigos: list[int]) -> Config:
    """Uma configuração mínima, com a lista de teste final que o teste quiser."""
    return Config(
        bruto={"avaliacao": {"temporadas_teste_final": codigos}},
        seed=42,
        raiz=carregar_config().raiz,
    )


def _jogos() -> pd.DataFrame:
    """Jogos das duas formas de temporada: europeia e de ano civil."""
    return pd.DataFrame(
        {
            "data": pd.to_datetime(
                [
                    "2022-09-01",
                    "2023-09-01",
                    "2024-09-01",
                    "2025-09-01",
                    "2022-05-01",
                    "2024-05-01",
                    "2025-05-01",
                ]
            ),
            "liga": ["E0", "E0", "E0", "E0", "BRA", "BRA", "BRA"],
            "temporada": [
                "2022/23",
                "2023/24",
                "2024/25",
                "2025/26",
                "2022",
                "2024",
                "2025",
            ],
            "mandante": ["A"] * 7,
            "visitante": ["B"] * 7,
            "gols_mandante": [1] * 7,
            "gols_visitante": [0] * 7,
        }
    )


def test_o_ano_de_corte_sai_do_codigo_do_site() -> None:
    assert divisao.ano_de_corte(_config([2425, 2526])) == 2024


def test_lista_vazia_de_teste_final_e_erro() -> None:
    """Projeto sem teste final reservado não deveria conseguir rodar."""
    with pytest.raises(ValueError, match="teste final"):
        divisao.ano_de_corte(_config([]))


def test_reconhece_as_duas_formas_de_temporada() -> None:
    """O ponto do arquivo: ``2024`` está trancada tanto quanto ``2024/25``."""
    assert divisao.e_teste_final("2024/25", 2024)
    assert divisao.e_teste_final("2024", 2024)
    assert not divisao.e_teste_final("2023/24", 2024)
    assert not divisao.e_teste_final("2023", 2024)


def test_a_temporada_em_andamento_tambem_fica_trancada() -> None:
    """O corte é por ano, e de propósito mais largo que a lista do config."""
    assert divisao.e_teste_final("2026/27", 2024)


def test_separar_deixa_de_fora_as_duas_formas() -> None:
    resultado = divisao.separar(_jogos(), _config([2425, 2526]))

    assert len(resultado.jogos) == 3, "sobram 2022/23, 2023/24 e 2022"
    assert resultado.trancados == 4
    assert resultado.temporadas_trancadas == ("2024", "2024/25", "2025", "2025/26")
    assert set(resultado.jogos["temporada"]) == {"2022/23", "2023/24", "2022"}


def test_resumo_diz_o_que_ficou_de_fora() -> None:
    resumo = divisao.separar(_jogos(), _config([2425, 2526])).resumo()
    assert "3 jogos liberados" in resumo
    assert "2024/25" in resumo


def test_usa_teste_final_avisa_sem_proibir() -> None:
    cfg = _config([2425, 2526])
    assert divisao.usa_teste_final(_jogos(), cfg)
    assert not divisao.usa_teste_final(divisao.separar(_jogos(), cfg).jogos, cfg)


def test_o_config_do_projeto_tem_teste_final_reservado() -> None:
    """Conferência no arquivo de verdade, não numa configuração de mentira."""
    cfg = carregar_config()
    assert divisao.ano_de_corte(cfg) == 2024
    assert ErroDeConfiguracao is not None  # o módulo de config está importável
