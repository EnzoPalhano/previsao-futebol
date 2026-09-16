"""Testes da detecção de formato e do inventário de colunas.

Este arquivo é a forma automatizada da seção 4.4 da especificação. A fonte
atualiza os arquivos sem avisar; se uma coluna que o projeto usa for renomeada
ou sumir, é aqui que aparece — com o nome exato do que faltou, não com um
``KeyError`` no meio do pipeline três módulos adiante.

Os testes de estrutura rodam sem internet, sobre cabeçalhos sintéticos. No fim
há testes marcados ``rede`` que conferem os arquivos de verdade.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from futebol.config import carregar_config
from futebol.dados import download, formatos


# ----------------------------------------------------------------------------
# Cabeçalhos mínimos de cada formato, montados a partir dos próprios mapas
# ----------------------------------------------------------------------------
def cabecalho_minimo(formato: str) -> list[str]:
    """As colunas essenciais do formato, que é o mínimo para ele ser válido."""
    return sorted(formatos.COLUNAS_ESSENCIAIS[formato])


# ----------------------------------------------------------------------------
# Detecção de formato
# ----------------------------------------------------------------------------
@pytest.mark.parametrize("formato", ["A", "B", "C"])
def test_detecta_cada_formato(formato: str) -> None:
    assert formatos.detectar_formato(cabecalho_minimo(formato)) == formato


def test_a_e_b_se_distinguem_pela_media() -> None:
    """A quebra entre os formatos é exatamente esta: ``AvgH`` contra ``BbAvH``."""
    base = ["HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "Date"]
    assert formatos.detectar_formato([*base, "AvgH"]) == "A"
    assert formatos.detectar_formato([*base, "BbAvH"]) == "B"


def test_c_se_distingue_pelos_nomes_curtos() -> None:
    """Formato C usa ``Home``/``HG``; A e B usam ``HomeTeam``/``FTHG``."""
    assert formatos.detectar_formato(cabecalho_minimo("C")) == "C"
    assert "HomeTeam" not in formatos.COLUNAS_ESSENCIAIS["C"]


def test_formato_desconhecido_diz_o_que_faltou() -> None:
    with pytest.raises(formatos.ErroDeFormato) as erro:
        formatos.detectar_formato(["Data", "Casa", "Fora"])

    mensagem = str(erro.value)
    assert "AvgH" in mensagem and "BbAvH" in mensagem and "Home" in mensagem


# ----------------------------------------------------------------------------
# Os mapeamentos
# ----------------------------------------------------------------------------
@pytest.mark.parametrize("formato", ["A", "B", "C"])
def test_mapa_so_produz_colunas_padrao(formato: str) -> None:
    """Nenhum mapa pode inventar uma coluna de saída fora do padrão."""
    desconhecidas = set(formatos.MAPAS[formato]) - set(formatos.COLUNAS_PADRAO)
    assert desconhecidas == set(), f"colunas fora do padrão no formato {formato}"


def test_odd_de_aposta_e_sempre_a_media_pre_jogo() -> None:
    """Regra 8: aposta-se na odd MÉDIA pré-jogo, nunca na máxima."""
    assert formatos.MAPA_A["odd_pre_H"] == "AvgH"
    assert formatos.MAPA_B["odd_pre_H"] == "BbAvH"
    for mapa in (formatos.MAPA_A, formatos.MAPA_B):
        for padrao, origem in mapa.items():
            if padrao.startswith("odd_pre"):
                assert "Max" not in origem, f"{padrao} aponta para odd máxima"


def test_grupo2_nao_tem_odd_pre_jogo_nem_over_under() -> None:
    """Base da regra 12: por isso o Grupo 2 não entra em backtest nem em CLV."""
    saidas = set(formatos.MAPA_C)
    assert not any(c.startswith("odd_pre") for c in saidas)
    assert not any("over25" in c or "under25" in c for c in saidas)


def test_formato_b_nao_tem_fechamento_de_over_under() -> None:
    """Antes de 2019/20 esse mercado de fechamento simplesmente não existe."""
    assert "odd_fech_over25" not in formatos.MAPA_B
    assert "odd_fech_under25" not in formatos.MAPA_B


def test_formato_b_fecha_com_pinnacle_e_isso_esta_documentado() -> None:
    """Armadilha: o fechamento do B é Pinnacle, não média. Comparar com o
    pré-jogo médio mistura timing com diferença entre casas."""
    assert formatos.MAPA_B["odd_fech_H"] == "PSCH"
    assert formatos.MAPA_A["odd_fech_H"] == "AvgCH"
    assert "Pinnacle" in formatos.AVISO_CLV_FORMATO_B


# ----------------------------------------------------------------------------
# Leitura de cabeçalho
# ----------------------------------------------------------------------------
def test_remove_o_bom_do_grupo2(tmp_path: Path) -> None:
    """Sem isso a primeira coluna vira '\\ufeffCountry' e some o 'Country'."""
    arquivo = tmp_path / "BRA.csv"
    arquivo.write_bytes("﻿Country,League,Season\n".encode())

    colunas = formatos.ler_cabecalho(arquivo)
    assert colunas[0] == "Country"


def test_aceita_arquivo_que_nao_e_utf8(tmp_path: Path) -> None:
    """Arquivos antigos trazem acentos em codificação legada."""
    arquivo = tmp_path / "x.csv"
    arquivo.write_bytes(b"Date,HomeTeam,Malm\xf6\n")
    assert formatos.ler_cabecalho(arquivo)[0] == "Date"


def test_ignora_retorno_de_carro_do_windows(tmp_path: Path) -> None:
    arquivo = tmp_path / "x.csv"
    arquivo.write_bytes(b"Date,HomeTeam,AvgH\r\n")
    assert formatos.ler_cabecalho(arquivo)[-1] == "AvgH"


# ----------------------------------------------------------------------------
# Inventário
# ----------------------------------------------------------------------------
def test_inventario_aponta_coluna_essencial_que_sumiu(tmp_path: Path) -> None:
    """O cenário que motiva este arquivo existir: a fonte renomeia uma coluna."""
    colunas = [c for c in cabecalho_minimo("A") if c != "AvgCH"]
    arquivo = tmp_path / "E0.csv"
    arquivo.write_text(",".join(colunas) + "\n", encoding="utf-8")

    inventario = formatos.inventariar(arquivo)
    assert inventario.formato == "A"
    assert inventario.utilizavel is False
    assert inventario.essenciais_faltando == ("AvgCH",)


def test_inventario_aceita_arquivo_sem_colunas_opcionais(tmp_path: Path) -> None:
    """RUS não tem B365 nem Betfair, e mesmo assim é utilizável."""
    colunas = cabecalho_minimo("C")
    arquivo = tmp_path / "RUS.csv"
    arquivo.write_text(",".join(colunas) + "\n", encoding="utf-8")

    inventario = formatos.inventariar(arquivo)
    assert inventario.utilizavel is True
    assert "B365CH" in inventario.opcionais_faltando


# ----------------------------------------------------------------------------
# Conferência contra os arquivos de verdade (não roda no CI)
# ----------------------------------------------------------------------------
@pytest.mark.rede
@pytest.mark.parametrize(
    ("formato_esperado", "grupo", "codigo", "temporada"),
    [
        ("A", "grupo1", "E0", 2425),
        ("A", "grupo1", "D1", 1920),
        ("B", "grupo1", "E0", 1718),
        ("C", "grupo2", "BRA", None),
        ("C", "grupo2", "RUS", None),
    ],
)
def test_inventario_da_fonte_continua_valendo(
    formato_esperado: str, grupo: str, codigo: str, temporada: int | None
) -> None:
    """Baixa o arquivo real e confere o inventário da seção 4.4.

    Se este teste falhar, a fonte mudou o formato: leia a mensagem, atualize
    o mapa em ``formatos.py`` e regenere ``docs/dicionario_dados.md``.
    """
    cfg = carregar_config()
    fontes = cfg.secao("fontes")
    alvo = (
        download.alvo_grupo1(cfg, codigo, temporada)
        if grupo == "grupo1"
        else download.alvo_grupo2(cfg, codigo)
    )
    download.baixar_alvo(
        alvo,
        user_agent=str(fontes["user_agent"]),
        timeout=int(fontes["timeout_segundos"]),
    )

    inventario = formatos.inventariar(alvo.destino)
    assert inventario.formato == formato_esperado
    assert inventario.essenciais_faltando == (), (
        f"A fonte mudou {codigo} ({formato_esperado}): sumiram as colunas "
        f"{', '.join(inventario.essenciais_faltando)}."
    )
