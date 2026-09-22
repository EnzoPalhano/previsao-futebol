"""Carrega o ``.env`` para dentro do ambiente.

⚠️ **Sem este módulo, o `.env` é um arquivo decorativo.** A especificação manda
guardar as chaves nele; `fontes.ApiFutebol` e `extracao.Extrator` as procuram em
``os.environ``. Faltava a ponte: ninguém lia o arquivo. As chaves podiam estar
preenchidas e o projeto continuaria dizendo "falta a chave" — um erro que
culparia o usuário por algo que era do código.

**Por que um leitor próprio e não o ``python-dotenv``.** São vinte linhas contra
uma dependência nova, e o projeto já tem doze. O formato usado aqui é o
mínimo — ``CHAVE=valor``, uma por linha, ``#`` comenta — que é exatamente o que
o ``.env.exemplo`` gera. Quem precisar de mais que isso troca por ``dotenv`` sem
mexer em quem chama.

⚠️ **O ambiente sempre vence o arquivo.** Uma variável já definida no shell
**não** é sobrescrita: quem exporta `API_FUTEBOL_CHAVE` na linha de comando
quer aquela chave, não a do arquivo. Fazer o contrário criaria o pior tipo de
confusão — dois valores para a mesma chave, e o vencedor dependendo da ordem em
que o código roda.
"""

from __future__ import annotations

import os
from pathlib import Path

#: O nome do arquivo, do lado do ``config.yaml``.
NOME = ".env"


def caminho(raiz: Path | None = None) -> Path:
    """Onde o ``.env`` deve estar."""
    if raiz is not None:
        return raiz / NOME
    # Sem raiz explícita, sobe de src/futebol/ até a raiz do projeto.
    return Path(__file__).resolve().parents[2] / NOME


def analisar(texto: str) -> dict[str, str]:
    """``CHAVE=valor`` por linha, virando dicionário.

    Tolera o que uma pessoa realmente escreve num ``.env``: linhas em branco,
    comentários, espaço em volta do ``=``, e valor entre aspas (que são
    retiradas — quem copia uma chave do painel da API às vezes leva as aspas
    junto, e uma chave com aspas dentro é uma chave inválida que produziria um
    401 sem explicação).
    """
    valores: dict[str, str] = {}
    for linha in texto.splitlines():
        limpa = linha.strip()
        if not limpa or limpa.startswith("#") or "=" not in limpa:
            continue
        chave, _, valor = limpa.partition("=")
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        if chave:
            valores[chave] = valor
    return valores


def carregar(raiz: Path | None = None) -> list[str]:
    """Põe o conteúdo do ``.env`` em ``os.environ``.

    Retorna:
        Os nomes das chaves que foram carregadas — **nunca os valores**. Um log
        que imprime o valor de uma chave de API é um log que vaza a chave, e
        logs vão para arquivos, para prints e para capturas de tela.

    Chave com valor vazio é ignorada: o ``.env.exemplo`` vem com todas as linhas
    vazias, e carregá-las faria ``os.environ`` ter a variável definida como
    string vazia — o que passaria por "existe" em qualquer teste ingênuo e
    falharia só na chamada à API.
    """
    arquivo = caminho(raiz)
    if not arquivo.is_file():
        return []

    carregadas = []
    for chave, valor in analisar(
        arquivo.read_text(encoding="utf-8", errors="replace")
    ).items():
        if not valor:
            continue
        # O ambiente vence o arquivo. Ver a nota no topo do módulo.
        if os.environ.get(chave):
            continue
        os.environ[chave] = valor
        carregadas.append(chave)
    return carregadas
