"""Liga de mentira com forças conhecidas, para os testes de modelo.

Este arquivo não tem teste nenhum: ele é a bancada dos testes de
:mod:`futebol.modelos`. A ideia é o único jeito honesto de testar um modelo de
estimação — **sortear placares a partir de forças escolhidas a dedo e exigir
que o ajuste reencontre essas forças**. Num dado real isso é impossível, porque
ninguém sabe a força verdadeira do Arsenal.

Fica separado dos arquivos de teste porque é usado por dois deles
(``test_poisson.py`` e ``test_dixon_coles.py``), e um teste importando o outro
é o tipo de amarração que quebra sozinha mais tarde.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Uma liga de seis times com forças conhecidas, do melhor para o pior.
TIMES: list[str] = [f"ENG:T{i}" for i in range(6)]

#: Força de ataque de cada time, em log (``+0,5`` = faz 1,65 vez a média).
ATAQUE: dict[str, float] = dict(
    zip(TIMES, [0.5, 0.3, 0.1, -0.1, -0.3, -0.5], strict=True)
)

#: Força de defesa de cada time, em log e com sinal invertido: positivo é
#: defesa boa (``+0,4`` = sofre 0,67 da média da liga).
DEFESA: dict[str, float] = dict(
    zip(TIMES, [0.4, 0.2, 0.0, 0.0, -0.2, -0.4], strict=True)
)


def rodizio(times: list[str], voltas: int = 1) -> list[tuple[str, str]]:
    """Todos contra todos, em casa e fora, repetido ``voltas`` vezes."""
    return [
        (casa, fora)
        for _ in range(voltas)
        for casa in times
        for fora in times
        if casa != fora
    ]


def tabela_de_jogos(
    confrontos: list[tuple[str, str]],
    gols_mandante,
    gols_visitante,
    liga: str = "E0",
    inicio: str = "2019-08-01",
) -> pd.DataFrame:
    """Monta a tabela no formato que os modelos esperam.

    Um jogo por dia, em sequência, o que deixa o efeito do decaimento temporal
    fácil de raciocinar: a posição na lista é a idade do jogo em dias.
    """
    return pd.DataFrame(
        {
            "data": pd.date_range(inicio, periods=len(confrontos), freq="D"),
            "liga": [liga] * len(confrontos),
            "mandante": [casa for casa, _ in confrontos],
            "visitante": [fora for _, fora in confrontos],
            "gols_mandante": gols_mandante,
            "gols_visitante": gols_visitante,
        }
    )


def simular_liga(
    times: list[str] = TIMES,
    ataque: dict[str, float] | None = None,
    defesa: dict[str, float] | None = None,
    intercepto: float = 0.1,
    fator_casa: float = 0.25,
    voltas: int = 6,
    liga: str = "E0",
    seed: int = 42,
) -> pd.DataFrame:
    """Sorteia placares de duas Poisson independentes, a partir das forças dadas.

    Os gols saem exatamente do modelo de :mod:`futebol.modelos.poisson`::

        λ = exp(intercepto + ataque do mandante − defesa do visitante + fator casa)
        μ = exp(intercepto + ataque do visitante − defesa do mandante)
    """
    ataque = ATAQUE if ataque is None else ataque
    defesa = DEFESA if defesa is None else defesa
    gerador = np.random.default_rng(seed)
    confrontos = rodizio(times, voltas)

    lam = np.array(
        [
            np.exp(intercepto + ataque[casa] - defesa[fora] + fator_casa)
            for casa, fora in confrontos
        ]
    )
    mu = np.array(
        [np.exp(intercepto + ataque[fora] - defesa[casa]) for casa, fora in confrontos]
    )
    return tabela_de_jogos(
        confrontos, gerador.poisson(lam), gerador.poisson(mu), liga=liga
    )
