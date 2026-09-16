"""Ferramentas para escrever relatório em Markdown a partir de tabelas.

Todo relatório do projeto é um arquivo ``.md`` versionado no Git, e não um
gráfico solto ou um número no terminal. O motivo é a regra 13: um resultado
precisa dizer de quais ligas ele fala, e precisa continuar dizendo isso daqui
a seis meses.

Este módulo é só a parte chata — alinhar coluna, formatar porcentagem, montar
o cabeçalho — para os módulos de análise cuidarem da análise.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import pandas as pd


def pct(valor: float, casas: int = 1) -> str:
    """Fração vira porcentagem; vazio vira ``-``, nunca ``nan``.

    A vírgula decimal é proposital: o relatório é lido em português, e ler
    "4.27%" como quatro inteiros e vinte e sete centésimos exige um pulo mental
    que ninguém deveria ter que dar no meio de uma tabela.
    """
    if valor is None or pd.isna(valor):
        return "-"
    return f"{valor * 100:.{casas}f}%".replace(".", ",")


def num(valor: float, casas: int = 4) -> str:
    """Número com casas fixas e vírgula decimal; vazio vira ``-``."""
    if valor is None or pd.isna(valor):
        return "-"
    return f"{valor:.{casas}f}".replace(".", ",")


def inteiro(valor: float) -> str:
    """Inteiro com ponto de milhar no padrão brasileiro (2.660)."""
    if valor is None or pd.isna(valor):
        return "-"
    return f"{int(valor):,}".replace(",", ".")


def tabela_markdown(linhas: Iterable[Sequence[str]], cabecalho: Sequence[str]) -> str:
    """Monta uma tabela Markdown a partir de linhas já formatadas como texto."""
    partes = ["| " + " | ".join(cabecalho) + " |"]
    partes.append("|" + "|".join(["---"] * len(cabecalho)) + "|")
    partes += ["| " + " | ".join(linha) + " |" for linha in linhas]
    return "\n".join(partes)


def de_dataframe(
    tabela: pd.DataFrame,
    colunas: dict[str, str],
    formatos: dict[str, str] | None = None,
) -> str:
    """Converte um ``DataFrame`` em tabela Markdown.

    Args:
        tabela: os dados.
        colunas: ``{nome_da_coluna: título que aparece no relatório}``. Só as
            listadas entram, na ordem em que aparecem aqui.
        formatos: ``{nome_da_coluna: "pct" | "num" | "inteiro" | "num2"}``.
            O que não estiver aqui vira texto direto.
    """
    formatos = formatos or {}
    formatadores = {
        "pct": pct,
        "pct2": lambda v: pct(v, 2),
        "num": num,
        "num2": lambda v: num(v, 2),
        "num3": lambda v: num(v, 3),
        "inteiro": inteiro,
    }

    linhas = []
    for _, linha in tabela.iterrows():
        celulas = []
        for coluna in colunas:
            valor = linha[coluna]
            formatador = formatadores.get(formatos.get(coluna, ""))
            celulas.append(formatador(valor) if formatador else str(valor))
        linhas.append(celulas)

    return tabela_markdown(linhas, list(colunas.values()))
