"""Apoio dos testes que tocam a internet de verdade.

Os testes marcados com ``@pytest.mark.rede`` existem para responder uma pergunta
só: **a fonte continua entregando o que o projeto espera?** Se o
football-data.co.uk mudar o nome de uma coluna ou o formato de um arquivo, é
esse punhado de testes que avisa.

⚠️ O problema é que eles falham por dois motivos completamente diferentes, e
tratar os dois igual atrapalha:

1. **a fonte mudou** — isso é um achado, e o teste tem que falhar alto;
2. **não deu para chegar na fonte** — sem internet, atrás de proxy, numa rede
   com filtro, no avião. Isso não diz nada sobre o projeto.

Como a regra 3 manda não commitar com teste falhando, o caso 2 bloquearia o
trabalho inteiro por um motivo que não é do projeto. Por isso o auxiliar aqui
transforma falha de **conexão** em ``skip``, e deixa qualquer outra falha
passar direto para o pytest.
"""

from __future__ import annotations

import pytest
import requests

from futebol.dados import download

#: Erros que significam "não cheguei no servidor", e não "o servidor respondeu
#: algo errado". ``ConnectTimeout`` herda das duas classes; ``ReadTimeout`` só de
#: ``Timeout``, por isso as duas aparecem.
SEM_ACESSO: tuple[type[Exception], ...] = (requests.ConnectionError, requests.Timeout)


def baixar_ou_pular(
    alvo: download.Alvo, *, user_agent: str, timeout: int, forcar: bool = False
) -> download.ResultadoDownload:
    """Baixa um alvo de verdade; **pula** o teste se a rede não colaborar.

    Args:
        alvo: o que baixar.
        user_agent: identificação enviada ao servidor.
        timeout: segundos de espera.
        forcar: rebaixar mesmo com o arquivo em disco.

    Retorna:
        O resultado do download.

    O que **não** é pulado: erro de HTTP (404, 500), corpo vazio, arquivo com
    coluna faltando. Tudo isso é notícia sobre a fonte, e continua falhando.
    """
    try:
        return download.baixar_alvo(
            alvo, user_agent=user_agent, timeout=timeout, forcar=forcar
        )
    except download.ErroDeDownload as erro:
        causa = erro.__cause__
        if isinstance(causa, SEM_ACESSO):
            pytest.skip(
                f"sem acesso a {alvo.url} ({type(causa).__name__}). "
                "Este teste só vale com internet aberta: numa rede com proxy ou "
                "filtro de domínio ele é pulado, porque a falha não diz nada "
                "sobre o projeto."
            )
        raise
