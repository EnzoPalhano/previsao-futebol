"""Faz o terminal do Windows aguentar nome de time estrangeiro.

O console do Windows não usa UTF-8 por padrão: ele usa uma tabela antiga
(cp1252) que não tem letras como ``ž``, ``ș`` ou ``ø``. Imprimir um nome de
clube romeno, tcheco ou norueguês **derruba o script** com
``UnicodeEncodeError`` — e derruba depois de já ter feito o trabalho todo,
o que é a pior hora possível.

Quem lida com dados de 38 países acaba nesse erro mais cedo ou mais tarde.
A solução é uma linha, e ela fica aqui para os scripts não a repetirem.
"""

from __future__ import annotations

import sys


def preparar_saida() -> None:
    """Põe a saída do terminal em UTF-8, trocando o que não couber por ``?``.

    O ``errors="replace"`` é a parte importante: mesmo num terminal que não
    aceite UTF-8, um caractere estranho vira ``?`` em vez de interromper o
    programa. Nome feio na tela é um aborrecimento; script que morre no fim de
    uma rodada de dez minutos é outra coisa.
    """
    for fluxo in (sys.stdout, sys.stderr):
        # `reconfigure` não existe quando a saída foi redirecionada para algo
        # que não é um arquivo de texto (um pipe em teste, por exemplo).
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")
