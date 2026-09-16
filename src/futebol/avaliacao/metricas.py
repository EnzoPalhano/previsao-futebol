"""As notas de uma previsão: log loss, Brier e calibração.

Dizer "o modelo acertou 55% dos jogos" não serve para nada aqui. Um modelo que
crava 90% num jogo e erra é muito pior que um que disse 55% e errou — e a taxa
de acerto trata os dois igual. Previsão probabilística se mede com *regras de
pontuação própria*: notas construídas de um jeito que **a melhor estratégia é
dizer exatamente o que você acredita**. Se exagerar na confiança, a nota piora.

Três notas, que respondem a perguntas diferentes:

- **Log loss** (:func:`log_loss`) — pune erro confiante de forma brutal
  (tende a infinito quando você diz 0% e acontece). É a métrica de escolha de
  modelo do projeto (regra 9), justamente por ser a mais severa.
- **Brier** (:func:`brier`) — o erro quadrático médio das probabilidades. Pune
  menos as catástrofes e é mais fácil de interpretar: 0 é perfeito, e um chute
  de "33% para cada" num 1X2 dá 0,667.
- **Calibração** (:func:`ece`, :func:`tabela_calibracao`) — dos jogos em que
  você disse 60%, aconteceu perto de 60%? Um modelo pode estar bem calibrado e
  ser inútil (dizer sempre a média da liga acerta a calibração e não informa
  nada), então calibração nunca aparece sozinha neste projeto.

⚠️ **Por que "escolher por log loss, nunca por ROI" (regra 9).** O ROI de um
backtest é dominado por ruído: poucas centenas de apostas, cada uma com
resultado 0 ou 1, e a diferença entre um modelo bom e um sortudo não aparece.
A log loss usa **todos** os jogos e a probabilidade inteira, não só o que deu
certo — converge com muito menos dados.
"""

from __future__ import annotations

import numpy as np

#: Piso e teto aplicados às probabilidades antes do logaritmo.
#: Sem isso, uma probabilidade 0 num resultado que aconteceu daria log loss
#: infinita — um único jogo apagaria a avaliação inteira.
_LIMITE = 1e-15


def _validar(probabilidades: np.ndarray, observado: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Confere formatos e descarta as linhas sem previsão."""
    probabilidades = np.asarray(probabilidades, dtype=float)
    observado = np.asarray(observado)

    if probabilidades.ndim != 2:
        raise ValueError(
            f"As probabilidades precisam ser uma matriz (jogos x opções); "
            f"veio algo com {probabilidades.ndim} dimensão(ões)."
        )
    if len(probabilidades) != len(observado):
        raise ValueError(
            f"{len(probabilidades)} linha(s) de probabilidade para "
            f"{len(observado)} resultado(s) observado(s)."
        )

    # Jogo sem odd (ou sem previsão) não entra na nota. Contar ele como erro
    # castigaria o modelo por um buraco dos dados.
    completas = np.isfinite(probabilidades).all(axis=1) & (observado >= 0)
    return probabilidades[completas], observado[completas]


def _probabilidade_do_que_aconteceu(
    probabilidades: np.ndarray, observado: np.ndarray
) -> np.ndarray:
    """Para cada jogo, a probabilidade que a previsão deu ao resultado real."""
    return probabilidades[np.arange(len(observado)), observado]


def log_loss(probabilidades, observado) -> float:
    """Média de ``-log(p)`` na opção que aconteceu. Menor é melhor.

    Args:
        probabilidades: matriz ``(jogos, opções)``, cada linha somando 1.
        observado: índice da opção que aconteceu em cada jogo (0, 1 ou 2 no
            1X2). Use ``-1`` para jogo que deve ficar de fora.

    Retorna:
        A log loss média. Referências para ler o número no 1X2: chutar
        "33% para cada" dá 1,0986; o mercado de fechamento das grandes ligas
        fica perto de 0,96.
    """
    probabilidades, observado = _validar(probabilidades, observado)
    if len(observado) == 0:
        return float("nan")

    escolhidas = _probabilidade_do_que_aconteceu(probabilidades, observado)
    return float(-np.log(np.clip(escolhidas, _LIMITE, 1.0)).mean())


def brier(probabilidades, observado) -> float:
    """Erro quadrático médio entre a previsão e o que aconteceu.

    A versão multiclasse: para cada jogo, soma ``(p_i - real_i)²`` sobre todas
    as opções, onde ``real_i`` é 1 na que aconteceu e 0 nas outras.

    Referências no 1X2: chute uniforme dá 0,667; o mercado fica perto de 0,57.
    """
    probabilidades, observado = _validar(probabilidades, observado)
    if len(observado) == 0:
        return float("nan")

    real = np.zeros_like(probabilidades)
    real[np.arange(len(observado)), observado] = 1.0
    return float(((probabilidades - real) ** 2).sum(axis=1).mean())


# ----------------------------------------------------------------------------
# Calibração
# ----------------------------------------------------------------------------
#: As faixas de probabilidade em que os jogos são agrupados para conferir
#: calibração. Mais estreitas perto do meio, onde ficam quase todos os jogos.
FAIXAS_PADRAO: tuple[float, ...] = (0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.85, 1.0)


def _achatar(probabilidades: np.ndarray, observado: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Transforma ``(jogos, opções)`` numa lista só de (probabilidade, aconteceu).

    Um jogo de 1X2 vira três pontos: a chance dada à vitória do mandante e se
    ela veio, a do empate e se ele veio, a da vitória do visitante e idem.
    Calibração se mede sobre cada afirmação de probabilidade, não por jogo.
    """
    probabilidades, observado = _validar(probabilidades, observado)
    real = np.zeros_like(probabilidades)
    real[np.arange(len(observado)), observado] = 1.0
    return probabilidades.ravel(), real.ravel()


def tabela_calibracao(probabilidades, observado, faixas=FAIXAS_PADRAO):
    """Compara, faixa a faixa, o que foi previsto com o que aconteceu.

    Retorna:
        Lista de dicionários, uma por faixa, com:

        - ``faixa``: o intervalo, como texto;
        - ``n``: quantas afirmações caíram nela;
        - ``previsto``: a probabilidade média prevista;
        - ``observado``: a frequência com que de fato aconteceu;
        - ``diferenca``: observado − previsto. Positivo quer dizer que o
          evento aconteceu **mais** do que a previsão dizia.
    """
    valores, aconteceu = _achatar(probabilidades, observado)
    linhas = []

    for inicio, fim in zip(faixas[:-1], faixas[1:], strict=True):
        # A última faixa inclui o 1,0; as outras não incluem o limite de cima,
        # senão um valor cairia em duas faixas.
        dentro = (valores >= inicio) & (
            (valores <= fim) if fim == faixas[-1] else (valores < fim)
        )
        if not dentro.any():
            continue
        previsto = float(valores[dentro].mean())
        real = float(aconteceu[dentro].mean())
        linhas.append(
            {
                "faixa": f"{inicio:.0%}-{fim:.0%}",
                "n": int(dentro.sum()),
                "previsto": previsto,
                "observado": real,
                "diferenca": real - previsto,
            }
        )
    return linhas


def ece(probabilidades, observado, faixas=FAIXAS_PADRAO) -> float:
    """Erro de calibração esperado: a distância média entre dito e acontecido.

    É a média das diferenças |observado − previsto| de cada faixa, pesada pelo
    número de jogos da faixa. Zero é calibração perfeita.

    Como ler: 0,01 quer dizer que, na média, quando o mercado diz 60% acontece
    algo entre 59% e 61%. Acima de 0,02 já é um mercado que erra de forma
    sistemática — e é assim que o filtro de qualidade da Fase 2 usa este número.
    """
    linhas = tabela_calibracao(probabilidades, observado, faixas)
    if not linhas:
        return float("nan")

    total = sum(linha["n"] for linha in linhas)
    return float(
        sum(abs(linha["diferenca"]) * linha["n"] for linha in linhas) / total
    )


def piso_de_ruido_ece(
    probabilidades, repeticoes: int = 200, seed: int = 42, faixas=FAIXAS_PADRAO
) -> float:
    """Qual ECE apareceria mesmo num mercado **perfeitamente** calibrado.

    Esta função existe para impedir uma conclusão errada muito fácil de tirar:
    "a liga X é mal calibrada porque o ECE dela é alto". Com 1.200 jogos, o
    ECE é alto **mesmo quando não há erro nenhum** — é só o acaso de uma
    amostra pequena.

    Como funciona: toma as probabilidades como se fossem a verdade, sorteia
    resultados a partir delas e mede o ECE. Repetindo, sai o ECE médio que a
    aleatoriedade sozinha produz naquele tamanho de amostra.

    Um ECE observado só é evidência de descalibração se estiver **bem acima**
    deste piso.
    """
    probabilidades = np.asarray(probabilidades, dtype=float)
    completas = probabilidades[np.isfinite(probabilidades).all(axis=1)]
    if len(completas) == 0:
        return float("nan")

    gerador = np.random.default_rng(seed)
    acumulado = np.cumsum(completas, axis=1)
    medidas = []
    for _ in range(repeticoes):
        sorteio = gerador.random((len(completas), 1))
        # Amostragem por soma acumulada: a primeira coluna cujo acumulado
        # ultrapassa o sorteio é a opção sorteada. O `minimum` cobre o caso em
        # que o acumulado final fica em 0,9999999 por arredondamento e o
        # sorteio cai acima dele — sem ele, sai um índice inexistente.
        simulado = np.minimum(
            (sorteio > acumulado).sum(axis=1), completas.shape[1] - 1
        )
        medidas.append(ece(completas, simulado, faixas))
    return float(np.mean(medidas))
