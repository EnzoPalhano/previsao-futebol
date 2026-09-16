"""Testes da padronização de nomes de times.

Os dois erros que este módulo existe para impedir:

1. **Partir um time em dois** — o mesmo clube com duas chaves diferentes. O Elo
   e as médias móveis ficam errados e nada acusa.
2. **Juntar dois times diferentes** — homônimos em países diferentes virando um
   só. Pior que o primeiro, e igualmente silencioso.

Por isso o teste mais importante daqui não é sobre formatação de texto: é o que
confirma que subida e descida de divisão mantêm a mesma chave.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from futebol.dados import nomes_times


# ----------------------------------------------------------------------------
# Normalização
# ----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Arsenal", "arsenal"),
        ("Atlético Madrid", "atletico madrid"),
        ("Nott'm Forest", "nottm forest"),
        ("FC Bayern", "bayern"),
        ("Bayern Munich FC", "bayern munich"),
        ("  Real   Madrid  ", "real madrid"),
        ("Malmö FF", "malmo"),
        ("PSV Eindhoven", "psv eindhoven"),
    ],
)
def test_normalizar(entrada: str, esperado: str) -> None:
    assert nomes_times.normalizar(entrada) == esperado


def test_normalizar_nao_apaga_o_nome_inteiro() -> None:
    """Um clube chamado só 'AC' não pode virar string vazia."""
    assert nomes_times.normalizar("AC") == "ac"
    assert nomes_times.normalizar("FC") == "fc"


# ----------------------------------------------------------------------------
# País da competição — o ponto central do desenho
# ----------------------------------------------------------------------------
def test_divisoes_do_mesmo_pais_dao_o_mesmo_pais() -> None:
    assert nomes_times.pais_do_codigo("E0") == "ENG"
    assert nomes_times.pais_do_codigo("E1") == "ENG"
    assert nomes_times.pais_do_codigo("EC") == "ENG"


def test_codigo_do_grupo2_ja_e_o_pais() -> None:
    assert nomes_times.pais_do_codigo("BRA") == "BRA"


def test_codigo_desconhecido_estoura() -> None:
    """Melhor falhar que gerar chave com prefixo inventado."""
    with pytest.raises(nomes_times.ErroDeNomes, match="desconhecido"):
        nomes_times.pais_do_codigo("XX9")


def test_toda_liga_do_config_tem_pais(tmp_path: Path) -> None:
    """Se alguém acrescentar uma liga no config.yaml sem mapear o país,
    é aqui que aparece — não no meio do pipeline."""
    from futebol.config import carregar_config

    cfg = carregar_config()
    camadas = cfg.bruto["ligas"]["camadas"]
    for nome, camada in camadas.items():
        for codigo in (camada.get("grupo1") or []) + (camada.get("grupo2") or []):
            # Não deve levantar.
            nomes_times.pais_do_codigo(codigo), f"{nome}/{codigo}"


# ----------------------------------------------------------------------------
# Os dois erros silenciosos
# ----------------------------------------------------------------------------
def test_time_rebaixado_mantem_a_mesma_chave() -> None:
    """Burnley cai da E0 para a E1 e volta. Se a chave mudasse, o histórico
    dele se partiria em dois exatamente onde ele mais muda de nível."""
    mapa = nomes_times.MapaTimes(
        [{"pais": "ENG", "nome_fonte": "Burnley", "nome_padrao": "Burnley"}]
    )
    resolvidos = nomes_times.padronizar(
        [("E0", "Burnley"), ("E1", "Burnley")], mapa
    )
    assert resolvidos[("E0", "Burnley")] == resolvidos[("E1", "Burnley")] == "ENG:Burnley"


def test_homonimos_de_paises_diferentes_nao_se_misturam() -> None:
    """'Everton' existe na Inglaterra e no Chile. 'Nacional' em vários países."""
    mapa = nomes_times.MapaTimes(
        [
            {"pais": "ENG", "nome_fonte": "Everton", "nome_padrao": "Everton"},
            {"pais": "ARG", "nome_fonte": "River Plate", "nome_padrao": "River Plate"},
            {"pais": "URU", "nome_fonte": "River Plate", "nome_padrao": "River Plate"},
        ]
    )
    assert mapa.resolver("ENG", "Everton") == "Everton"
    assert nomes_times.chave("ENG", "Everton") != nomes_times.chave("CHI", "Everton")
    assert nomes_times.chave("ARG", "River Plate") != nomes_times.chave(
        "URU", "River Plate"
    )


# ----------------------------------------------------------------------------
# Resolução pelo mapa
# ----------------------------------------------------------------------------
def test_resolve_por_nome_exato_e_por_normalizado() -> None:
    mapa = nomes_times.MapaTimes(
        [{"pais": "GER", "nome_fonte": "Bayern Munich", "nome_padrao": "Bayern"}]
    )
    assert mapa.resolver("GER", "Bayern Munich") == "Bayern"
    # Mesmo nome com sigla e caixa diferentes cai no normalizado.
    assert mapa.resolver("GER", "FC Bayern Munich") == "Bayern"
    assert mapa.resolver("GER", "  bayern   munich ") == "Bayern"


def test_nao_resolve_atravessando_pais() -> None:
    mapa = nomes_times.MapaTimes(
        [{"pais": "ENG", "nome_fonte": "Everton", "nome_padrao": "Everton"}]
    )
    assert mapa.resolver("CHI", "Everton") is None


def test_sugestao_ajuda_mas_nao_decide() -> None:
    mapa = nomes_times.MapaTimes(
        [{"pais": "ENG", "nome_fonte": "Man United", "nome_padrao": "Man United"}]
    )
    assert mapa.sugerir("ENG", "Man Utd") == "Man United"
    # Sugerir não é resolver: o nome continua fora do mapa.
    assert mapa.resolver("ENG", "Man Utd") is None


# ----------------------------------------------------------------------------
# Nome desconhecido precisa PARAR o pipeline
# ----------------------------------------------------------------------------
def test_nome_fora_do_mapa_levanta_erro() -> None:
    mapa = nomes_times.MapaTimes(
        [{"pais": "ENG", "nome_fonte": "Arsenal", "nome_padrao": "Arsenal"}]
    )
    with pytest.raises(nomes_times.NomeDesconhecido) as erro:
        nomes_times.padronizar([("E0", "Arsenal"), ("E0", "Time Novo FC")], mapa)

    assert "Time Novo FC" in str(erro.value)
    assert [p.nome_fonte for p in erro.value.pendentes] == ["Time Novo FC"]


def test_pendencias_sao_gravadas_para_revisao(tmp_path: Path) -> None:
    mapa = nomes_times.MapaTimes(
        [{"pais": "ENG", "nome_fonte": "Man United", "nome_padrao": "Man United"}]
    )
    destino = tmp_path / "nomes_pendentes.csv"

    with pytest.raises(nomes_times.NomeDesconhecido):
        nomes_times.padronizar(
            [("E0", "Man Utd")], mapa, caminho_pendencias=destino
        )

    with destino.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))

    assert len(linhas) == 1
    assert linhas[0]["nome_fonte"] == "Man Utd"
    assert linhas[0]["sugestao"] == "Man United"


def test_mesmo_nome_desconhecido_aparece_uma_vez_so() -> None:
    """O time joga 38 vezes; a pendência é uma."""
    mapa = nomes_times.MapaTimes([])
    with pytest.raises(nomes_times.NomeDesconhecido) as erro:
        nomes_times.padronizar([("E0", "Novo")] * 38, mapa)
    assert len(erro.value.pendentes) == 1


# ----------------------------------------------------------------------------
# O mapa versionado de verdade
# ----------------------------------------------------------------------------
def test_mapa_versionado_carrega_e_tem_conteudo() -> None:
    mapa = nomes_times.carregar_mapa()
    assert len(mapa) > 0, "src/futebol/dados/mapa_times.csv está vazio"
    assert "ENG" in mapa.paises


def test_mapa_versionado_nao_tem_linha_repetida() -> None:
    """Duas linhas com o mesmo (pais, nome_fonte) e padrões diferentes seriam
    uma ambiguidade silenciosa: a última venceria."""
    caminho = nomes_times.CAMINHO_MAPA_PADRAO
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))

    chaves = [(li["pais"], li["nome_fonte"]) for li in linhas]
    repetidas = {c for c in chaves if chaves.count(c) > 1}
    assert repetidas == set(), f"linhas repetidas no mapa: {repetidas}"


def test_mapa_versionado_esta_ordenado() -> None:
    """Ordenação mantém o diff do Git legível quando as 38 ligas entrarem."""
    caminho = nomes_times.CAMINHO_MAPA_PADRAO
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))

    atual = [(li["pais"], li["nome_padrao"], li["nome_fonte"]) for li in linhas]
    assert atual == sorted(atual)


def test_mapa_versionado_cobre_as_ligas_ativas() -> None:
    """Critério de 'pronto' da Fase 1: o mapa cobre as ligas ativas sem pendência."""
    from futebol.config import carregar_config

    cfg = carregar_config()
    mapa = nomes_times.carregar_mapa()
    paises_ativos = {
        nomes_times.pais_do_codigo(c)
        for grupo in cfg.ligas_ativas().values()
        for c in grupo
    }
    assert paises_ativos <= mapa.paises, (
        f"países sem nenhum time no mapa: {sorted(paises_ativos - mapa.paises)}"
    )
