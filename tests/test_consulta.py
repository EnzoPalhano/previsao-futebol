"""Testes da tradução "Arsenal x Chelsea" -> jogo do modelo.

O teste que justifica o módulo é o do **homônimo**: pedir "Everton" numa tabela
que tem o inglês e o chileno tem que dar erro com as duas opções, e nunca
escolher uma delas. Um chute aqui produziria uma previsão perfeitamente
formatada sobre o time errado — o pior tipo de erro que este projeto pode ter
(regra 14).
"""

from __future__ import annotations

import pandas as pd
import pytest

from futebol import consulta


def _jogos() -> pd.DataFrame:
    """Uma tabela pequena com os casos difíceis de propósito.

    Contém: dois Evertons (Inglaterra e Chile), um time com apóstrofo e acento,
    e um time inglês que aparece em duas divisões (subiu de divisão).
    """
    linhas = [
        # E0: Everton inglês, Liverpool, Nott'm Forest
        ("2024-08-10", "E0", "2024/25", "ENG:Everton", "ENG:Liverpool", 1, 3),
        ("2024-08-17", "E0", "2024/25", "ENG:Liverpool", "ENG:Nott'm Forest", 2, 0),
        ("2024-09-01", "E0", "2024/25", "ENG:Nott'm Forest", "ENG:Everton", 1, 1),
        # E1: Nott'm Forest numa temporada anterior, quando estava na segunda divisão
        ("2022-08-10", "E1", "2022/23", "ENG:Nott'm Forest", "ENG:Sunderland", 2, 1),
        ("2022-09-10", "E1", "2022/23", "ENG:Sunderland", "ENG:Nott'm Forest", 0, 0),
        # CHI: o outro Everton
        ("2024-03-10", "CHI", "2024", "CHI:Everton", "CHI:Colo Colo", 0, 2),
        ("2024-04-10", "CHI", "2024", "CHI:Colo Colo", "CHI:Everton", 1, 1),
    ]
    return pd.DataFrame(
        linhas,
        columns=[
            "data",
            "liga",
            "temporada",
            "mandante",
            "visitante",
            "gols_mandante",
            "gols_visitante",
        ],
    ).assign(data=lambda t: pd.to_datetime(t["data"]))


# ----------------------------------------------------------------------------
# Achar o time
# ----------------------------------------------------------------------------
def test_chave_inteira_e_aceita() -> None:
    assert consulta.resolver_time(_jogos(), "ENG:Liverpool") == "ENG:Liverpool"


def test_nome_solto_acha_o_time() -> None:
    assert consulta.resolver_time(_jogos(), "Liverpool") == "ENG:Liverpool"


def test_a_busca_ignora_maiuscula_e_pontuacao() -> None:
    """``nottm forest`` e ``Nott'm Forest`` são o mesmo time."""
    assert consulta.resolver_time(_jogos(), "nottm forest") == "ENG:Nott'm Forest"


def test_pedaco_do_nome_serve() -> None:
    assert consulta.resolver_time(_jogos(), "sunder") == "ENG:Sunderland"


def test_homonimo_e_erro_com_as_opcoes_na_mensagem() -> None:
    """O teste mais importante do arquivo (regra 14)."""
    with pytest.raises(consulta.ErroDeConsulta) as erro:
        consulta.resolver_time(_jogos(), "Everton")

    mensagem = str(erro.value)
    assert "ENG:Everton" in mensagem
    assert "CHI:Everton" in mensagem


def test_homonimo_resolvido_pela_liga() -> None:
    """Dizer a liga desfaz a ambiguidade sem precisar da chave inteira."""
    assert consulta.resolver_time(_jogos(), "Everton", liga="CHI") == "CHI:Everton"
    assert consulta.resolver_time(_jogos(), "Everton", liga="E0") == "ENG:Everton"


def test_time_que_nao_existe_diz_o_que_fazer() -> None:
    with pytest.raises(consulta.ErroDeConsulta, match="Não achei"):
        consulta.resolver_time(_jogos(), "Grêmio")


def test_nome_vazio_e_erro() -> None:
    with pytest.raises(consulta.ErroDeConsulta, match="vazio"):
        consulta.resolver_time(_jogos(), "   ")


# ----------------------------------------------------------------------------
# Achar a competição
# ----------------------------------------------------------------------------
def test_ligas_do_time_vem_da_mais_recente_para_a_mais_antiga() -> None:
    """Um time que subiu de divisão aparece nas duas."""
    ligas = consulta.ligas_do_time(_jogos(), "ENG:Nott'm Forest")
    assert list(ligas["liga"]) == ["E0", "E1"]
    assert list(ligas["jogos"]) == [2, 2]


def test_a_liga_escolhida_e_a_do_encontro_mais_recente() -> None:
    liga, explicacao = consulta.escolher_liga(
        _jogos(), "ENG:Nott'm Forest", "ENG:Liverpool"
    )
    assert liga == "E0"
    assert "os dois jogaram" in explicacao


def test_quando_os_dois_nunca_se_cruzaram_vale_a_liga_do_mandante() -> None:
    """E o aviso tem que aparecer: o visitante entra sem histórico nenhum."""
    liga, explicacao = consulta.escolher_liga(_jogos(), "ENG:Sunderland", "CHI:Colo Colo")
    assert liga == "E1"
    assert "ATENÇÃO" in explicacao


def test_time_sem_jogo_nenhum_e_erro() -> None:
    with pytest.raises(consulta.ErroDeConsulta, match="não tem jogo nenhum"):
        consulta.escolher_liga(_jogos(), "ENG:Inventado", "ENG:Liverpool")


# ----------------------------------------------------------------------------
# A resolução completa
# ----------------------------------------------------------------------------
def test_montar_devolve_o_jogo_e_a_contagem_de_historico() -> None:
    resolucao = consulta.montar(
        _jogos(), "nottm forest", "Liverpool", data="2024-10-01"
    )
    assert resolucao.jogo.liga == "E0"
    assert resolucao.jogo.mandante == "ENG:Nott'm Forest"
    assert resolucao.jogo.visitante == "ENG:Liverpool"
    assert resolucao.jogo.data == pd.Timestamp("2024-10-01")
    # Na E0 da tabela, cada um dos dois aparece em dois jogos.
    assert resolucao.jogos_do_mandante == 2
    assert resolucao.jogos_do_visitante == 2


def test_liga_pedida_a_mao_e_respeitada() -> None:
    resolucao = consulta.montar(_jogos(), "nottm", "Sunderland", liga="E1")
    assert resolucao.jogo.liga == "E1"
    assert "por você" in resolucao.explicacao_liga


def test_liga_que_nao_existe_lista_as_que_existem() -> None:
    with pytest.raises(consulta.ErroDeConsulta, match="E0"):
        consulta.montar(_jogos(), "nottm", "Liverpool", liga="XX")


def test_o_mesmo_time_nos_dois_lados_e_erro() -> None:
    with pytest.raises(consulta.ErroDeConsulta, match="mesmo time"):
        consulta.montar(_jogos(), "Liverpool", "ENG:Liverpool")
