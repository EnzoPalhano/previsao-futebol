"""A odd vira probabilidade — e a margem da casa sai do meio do caminho.

Uma odd de 2,00 parece dizer "50% de chance". Não diz. Ela diz "50% **mais a
minha comissão**". Some as três probabilidades de um jogo e o total não dá
100%: dá 104%, 107%. Esses pontos a mais são a margem da casa, e comparar a
previsão de um modelo com um número que embute comissão é comparar coisas
diferentes — o modelo pareceria pior do que é.

Este módulo faz duas coisas:

1. **Mede** a margem (:func:`overround`), que é quanto o mercado cobra;
2. **Tira** a margem (:func:`remover_margem`), devolvendo probabilidades que
   somam 1 e podem ser comparadas com as do modelo.

⚠️ **Tirar a margem não tem resposta única.** É uma hipótese sobre *como* a casa
distribuiu a comissão entre as opções, e os três métodos aqui discordam de
propósito:

- **proporcional**: assume que a casa cobrou a mesma fatia de todo mundo. É o
  mais simples e o mais usado — e o que mais erra no azarão.
- **power** e **shin**: assumem que o azarão paga mais comissão que o favorito.
  Isso não é teoria: é o *viés favorito-azarão*, um dos efeitos mais
  replicados em mercados de aposta. Quem aposta em azarão aceita odd pior do
  que deveria, e as casas cobram por isso.

Por isso o projeto calcula os três e **compara**, em vez de escolher um no
escuro. A escolha entra no relatório da Fase 2, com número.

Uma nota de vocabulário, porque a literatura mistura os dois:

- **overround** = soma das probabilidades implícitas − 1. É o número da seção
  4.3 da especificação (E0 = 4,19% no 1X2 de fechamento);
- **fatia da casa** = overround / (1 + overround). É quanto, de cada real
  apostado, não volta para o conjunto dos apostadores.

São a mesma coisa vista de dois ângulos, e o projeto reporta o primeiro para
poder comparar com a tabela da especificação.
"""

from __future__ import annotations

import numpy as np

#: Quantas vezes a bisseção parte o intervalo ao meio. Com 60 passos o
#: intervalo inicial encolhe por um fator de 2^60 — precisão muito além do que
#: qualquer odd de casa de aposta carrega.
_PASSOS_BISSECAO = 60

#: Os métodos de remoção de margem que o projeto conhece.
METODOS: tuple[str, ...] = ("proporcional", "power", "shin")


class ErroDeMercado(Exception):
    """Odd impossível, ou método de remoção de margem que não existe."""


def _como_matriz(odds) -> tuple[np.ndarray, bool]:
    """Aceita um jogo só ou uma tabela inteira, e devolve sempre uma matriz.

    Retorna a matriz ``(n_jogos, n_opcoes)`` e se a entrada era de um jogo só,
    para o resultado voltar no mesmo formato que chegou.
    """
    matriz = np.asarray(odds, dtype=float)
    unidimensional = matriz.ndim == 1
    if unidimensional:
        matriz = matriz.reshape(1, -1)
    if matriz.ndim != 2:
        raise ErroDeMercado(
            f"Esperava um jogo (1 dimensão) ou uma tabela (2 dimensões), "
            f"veio algo com {matriz.ndim}."
        )
    return matriz, unidimensional


def probabilidade_implicita(odds):
    """A conta mais simples do mercado: ``1 / odd``.

    Odd 2,00 vira 0,50; odd 4,00 vira 0,25. Note que essas probabilidades
    **não somam 1** — a diferença é a margem.
    """
    matriz, era_um_jogo = _como_matriz(odds)
    if np.any(matriz[np.isfinite(matriz)] <= 1.0):
        raise ErroDeMercado(
            "Odd menor ou igual a 1,00 não existe: ela pagaria menos do que o "
            "apostador arriscou."
        )
    probabilidades = 1.0 / matriz
    return probabilidades[0] if era_um_jogo else probabilidades


def overround(odds):
    """Quanto o mercado cobra: soma das probabilidades implícitas − 1.

    É o número da seção 4.3: 0,0419 = 4,19%, a margem da Premier League no
    1X2 de fechamento. Quanto **menor**, melhor para quem aposta.
    """
    probabilidades = np.atleast_2d(probabilidade_implicita(odds))
    soma = probabilidades.sum(axis=1) - 1.0
    return soma[0] if np.ndim(odds) == 1 else soma


def fatia_da_casa(odds):
    """Quanto de cada real apostado **não** volta para os apostadores.

    É o overround visto pelo outro lado: ``over / (1 + over)``. Sempre um
    pouco menor que o overround, e é o número que responde "qual o meu
    prejuízo esperado se eu apostar no acaso?".
    """
    over = overround(odds)
    return over / (1.0 + over)


# ----------------------------------------------------------------------------
# Remoção de margem
# ----------------------------------------------------------------------------
def _bissecao(funcao, baixo: np.ndarray, alto: np.ndarray) -> np.ndarray:
    """Acha, para cada linha, o valor em que ``funcao`` cruza o zero.

    Bisseção vetorizada: em vez de resolver 117.000 equações uma a uma num
    laço Python, parte os 117.000 intervalos ao meio de uma vez, 60 vezes.
    Exige que ``funcao(baixo)`` e ``funcao(alto)`` tenham sinais opostos, o
    que é garantido pela matemática de cada método (ver os comentários).
    """
    baixo = np.array(baixo, dtype=float)
    alto = np.array(alto, dtype=float)
    for _ in range(_PASSOS_BISSECAO):
        meio = (baixo + alto) / 2.0
        positivo = funcao(meio) > 0
        baixo = np.where(positivo, meio, baixo)
        alto = np.where(positivo, alto, meio)
    return (baixo + alto) / 2.0


def _proporcional(probabilidades: np.ndarray) -> np.ndarray:
    """Divide todo mundo pela soma: a comissão foi igual para todos.

    É o método mais comum e o mais fácil de explicar — e é justamente por ser
    multiplicativo que ele superestima a chance do azarão: se a casa cobrou
    mais caro no azarão, dividir tudo pelo mesmo número não desfaz isso.
    """
    return probabilidades / probabilidades.sum(axis=1, keepdims=True)


def _power(probabilidades: np.ndarray) -> np.ndarray:
    """Eleva todas as probabilidades ao mesmo expoente ``k`` até somarem 1.

    Como cada probabilidade é menor que 1, elevar a um ``k > 1`` encolhe
    todas — e encolhe **proporcionalmente mais** as pequenas. É essa assimetria
    que corrige o viés favorito-azarão.

    A soma cai quando ``k`` cresce, então existe um ``k`` único entre 1 (soma
    maior que 1) e 20 (soma praticamente zero) em que ela vale exatamente 1.
    """

    def sobra(k: np.ndarray) -> np.ndarray:
        return np.power(probabilidades, k[:, None]).sum(axis=1) - 1.0

    linhas = probabilidades.shape[0]
    k = _bissecao(sobra, np.ones(linhas), np.full(linhas, 20.0))
    return np.power(probabilidades, k[:, None])


def z_de_shin(probabilidades: np.ndarray) -> np.ndarray:
    """A fração de apostadores com informação privilegiada, no modelo de Shin.

    O modelo de Shin (1993) conta uma história concreta: a casa sabe que uma
    parte ``z`` do dinheiro vem de quem sabe de algo que ela não sabe (lesão,
    escalação, jogo combinado). Ela se protege inflando mais as odds onde o
    estrago seria maior — e é por isso que o azarão paga comissão maior.

    Um ``z`` de 0,02 quer dizer "a casa se protege como se 2% do volume fosse
    de gente com informação".
    """
    soma = probabilidades.sum(axis=1)

    def sobra(z: np.ndarray) -> np.ndarray:
        return _shin_com_z(probabilidades, soma, z).sum(axis=1) - 1.0

    linhas = probabilidades.shape[0]
    # Em z = 0 a soma é sqrt(soma das implícitas) > 1; ela cai quando z cresce.
    # O limite superior 0,4 é folgado: mercados reais ficam abaixo de 0,1.
    return _bissecao(sobra, np.zeros(linhas), np.full(linhas, 0.4))


def _shin_com_z(
    probabilidades: np.ndarray, soma: np.ndarray, z: np.ndarray
) -> np.ndarray:
    """A fórmula fechada de Shin para as probabilidades verdadeiras."""
    z = z[:, None]
    soma = soma[:, None]
    dentro = z**2 + 4.0 * (1.0 - z) * probabilidades**2 / soma
    return (np.sqrt(dentro) - z) / (2.0 * (1.0 - z))


def _shin(probabilidades: np.ndarray) -> np.ndarray:
    soma = probabilidades.sum(axis=1)
    return _shin_com_z(probabilidades, soma, z_de_shin(probabilidades))


_IMPLEMENTACOES = {
    "proporcional": _proporcional,
    "power": _power,
    "shin": _shin,
}


def remover_margem(odds, metodo: str = "proporcional"):
    """Tira a comissão da casa e devolve probabilidades que somam 1.

    Args:
        odds: as odds de **um mercado completo** — as três do 1X2, ou as duas
            do Over/Under. Um jogo (``[1.8, 3.6, 4.2]``) ou uma tabela inteira
            (``(n, 3)``).
        metodo: ``"proporcional"``, ``"power"`` ou ``"shin"``.

    Retorna:
        Probabilidades no mesmo formato da entrada, somando 1 em cada linha.
        Linha com odd faltando volta toda como ``NaN`` — nunca chutada.

    Levanta:
        ErroDeMercado: se o método não existir ou alguma odd for ≤ 1,00.
    """
    if metodo not in _IMPLEMENTACOES:
        raise ErroDeMercado(
            f"Método {metodo!r} não existe. Conhecidos: {', '.join(METODOS)}."
        )

    matriz, era_um_jogo = _como_matriz(odds)
    probabilidades = np.atleast_2d(probabilidade_implicita(matriz))

    # Jogo sem odd completa não vira probabilidade: vira NaN. A bisseção não
    # sabe lidar com NaN, então ela roda sobre as linhas completas e o resto
    # volta vazio.
    completas = np.isfinite(probabilidades).all(axis=1)
    resultado = np.full_like(probabilidades, np.nan)
    if completas.any():
        resultado[completas] = _IMPLEMENTACOES[metodo](probabilidades[completas])

    return resultado[0] if era_um_jogo else resultado


# ----------------------------------------------------------------------------
# Da tabela de jogos para as matrizes de probabilidade
# ----------------------------------------------------------------------------
#: As colunas de odd de cada mercado, por momento. A ordem importa: ela define
#: o índice de cada opção nas matrizes, e é a mesma usada em
#: :func:`resultado_observado`.
COLUNAS: dict[tuple[str, str], tuple[str, ...]] = {
    ("1x2", "pre"): ("odd_pre_H", "odd_pre_D", "odd_pre_A"),
    ("1x2", "fech"): ("odd_fech_H", "odd_fech_D", "odd_fech_A"),
    ("ou25", "pre"): ("odd_pre_over25", "odd_pre_under25"),
    ("ou25", "fech"): ("odd_fech_over25", "odd_fech_under25"),
}

#: O que cada índice significa, para o relatório não trocar as colunas.
OPCOES: dict[str, tuple[str, ...]] = {
    "1x2": ("mandante", "empate", "visitante"),
    "ou25": ("mais de 2,5", "menos de 2,5"),
}


def _colunas(mercado_: str, momento: str) -> tuple[str, ...]:
    if (mercado_, momento) not in COLUNAS:
        conhecidos = ", ".join(f"{m}/{t}" for m, t in COLUNAS)
        raise ErroDeMercado(
            f"Mercado {mercado_!r} no momento {momento!r} não existe. "
            f"Conhecidos: {conhecidos}."
        )
    return COLUNAS[(mercado_, momento)]


def odds_da_tabela(jogos, mercado_: str = "1x2", momento: str = "pre"):
    """Recorta da tabela de jogos as colunas de odd de um mercado."""
    return jogos[list(_colunas(mercado_, momento))].to_numpy(dtype=float)


def probabilidades_do_mercado(
    jogos, mercado_: str = "1x2", momento: str = "pre", metodo: str = "proporcional"
):
    """As probabilidades do mercado, já sem a margem, para a tabela inteira.

    É o atalho que liga :mod:`futebol.dados.limpeza` a
    :mod:`futebol.avaliacao.metricas`: entra a tabela de jogos, saem as
    probabilidades comparáveis com as de um modelo.

    Jogo sem a odd completa daquele mercado sai como ``NaN`` — e as métricas
    sabem deixá-lo de fora.
    """
    return remover_margem(odds_da_tabela(jogos, mercado_, momento), metodo)


def resultado_observado(jogos, mercado_: str = "1x2"):
    """O índice da opção que aconteceu em cada jogo.

    No 1X2: 0 = vitória do mandante, 1 = empate, 2 = vitória do visitante.
    No Over/Under 2,5: 0 = saíram 3 gols ou mais, 1 = saíram 2 ou menos.

    A ordem é a mesma de :data:`COLUNAS`, e é o que faz as métricas casarem
    probabilidade com resultado sem trocar as colunas.
    """
    import numpy as _np

    if mercado_ == "1x2":
        resultado = jogos["resultado"].to_numpy()
        indices = _np.full(len(resultado), -1, dtype=int)
        for posicao, letra in enumerate(("H", "D", "A")):
            indices[resultado == letra] = posicao
        return indices

    if mercado_ == "ou25":
        gols = (jogos["gols_mandante"] + jogos["gols_visitante"]).to_numpy()
        return _np.where(gols > 2.5, 0, 1)

    raise ErroDeMercado(f"Mercado {mercado_!r} não existe. Conhecidos: 1x2, ou25.")
