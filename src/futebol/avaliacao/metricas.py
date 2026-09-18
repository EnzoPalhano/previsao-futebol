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


def acuracia(probabilidades, observado) -> float:
    """Fração de jogos em que a opção mais provável foi a que aconteceu.

    ⚠️ **Esta é a métrica que o projeto reporta e não usa para decidir nada.**
    Ela está aqui porque é a primeira pergunta que todo mundo faz ("quantos por
    cento o modelo acerta?") e porque, sozinha, ela engana de três formas:

    1. **ignora a confiança.** Dizer 95% e errar conta igual a dizer 34% e errar;
    2. **ignora o empate.** No 1X2, o empate quase nunca é a opção mais
       provável — ele fica em torno de 26%. Um modelo que **nunca** aponta
       empate pode ter acurácia alta e ser inútil para apostar;
    3. **depende da liga.** Onde o mandante ganha 48% dos jogos, apontar sempre
       o mandante já dá 48% de acerto sem modelo nenhum.

    Por isso a escolha de modelo é por log loss (regra 9). A acurácia serve de
    conferência de sanidade e de tradução para quem está começando.
    """
    probabilidades, observado = _validar(probabilidades, observado)
    if len(observado) == 0:
        return float("nan")
    return float((probabilidades.argmax(axis=1) == observado).mean())


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


# ----------------------------------------------------------------------------
# Poder estatístico e incerteza
# ----------------------------------------------------------------------------
# Esta seção existe por causa da regra 10, e ela é o coração honesto da Fase 6.
#
# Um ROI sozinho não quer dizer nada. "+2,1% de ROI" pode ser uma vantagem real
# ou o resultado de jogar uma moeda algumas centenas de vezes. O que separa os
# dois casos não é o número: é **quanto ruído cabe naquela amostra**. As funções
# abaixo respondem as duas perguntas que precisam acompanhar todo ROI e todo CLV
# do projeto:
#
# - *quantas apostas seriam necessárias para enxergar um efeito deste tamanho?*
#   (:func:`tamanho_amostra`);
# - *com as apostas que eu tenho, qual é o menor efeito que eu enxergaria?*
#   (:func:`efeito_detectavel`).
#
# As duas são a mesma conta, resolvida para variáveis diferentes.

#: Multiplicador de 95% de confiança: o intervalo é a estimativa ± 1,96 erros-padrão.
#: Responde "este efeito **apareceu**?".
Z_95 = 1.959963984540054

#: Multiplicador de 95% de confiança **com 80% de poder**. Responde a outra
#: pergunta: "esta amostra teria boa chance de **ver** um efeito deste tamanho,
#: se ele existisse?". É o número usado em
#: :attr:`futebol.avaliacao.validacao.Diferenca.efeito_minimo_detectavel`.
#:
#: ⚠️ Os dois convivem e não se contradizem. Um efeito entre 1,96 e 2,8
#: erros-padrão é um achado **frágil**: apareceu, mas a amostra tinha boa chance
#: de não tê-lo visto.
Z_PODER_80 = 2.8

#: Quantos números o bootstrap sorteia por bloco. Segura o pico de memória em
#: torno de 80 MB, independente do tamanho da amostra.
_NUMEROS_POR_BLOCO = 10_000_000


def desvio_padrao_da_aposta(odd: float) -> float:
    """Volatilidade de uma aposta de 1 unidade numa odd justa: ``√(odd − 1)``.

    É a conta da seção 8.1 da especificação, e ela é **exata** (não uma
    aproximação) quando a odd é justa, isto é, quando ``p = 1/odd``. Nesse caso
    o retorno vale ``odd − 1`` com probabilidade ``1/odd`` e ``−1`` com o resto,
    tem média zero e variância::

        (1/odd)·(odd−1)² + (1 − 1/odd)·1² = odd − 1

    Como ler o número: odd 2,00 dá desvio-padrão **1,0** — ou seja, **100% de
    volatilidade por aposta**. Odd 5,00 dá 2,0. É por isso que ROI precisa de
    dezenas de milhares de apostas para ser medido e log loss não (regra 9):
    cada aposta carrega uma quantidade absurda de ruído, e a log loss usa a
    probabilidade inteira de **todos** os jogos, não só o que deu certo.

    ⚠️ Esta função serve para **planejar** (a tabela da seção 8.2 sai dela). Para
    reportar o que de fato aconteceu, o projeto usa o desvio-padrão **medido**
    nos próprios retornos, que é o que a seção 8.3 exige para o CLV.
    """
    if odd <= 1:
        raise ValueError(f"Odd tem de ser maior que 1; veio {odd}.")
    return float(np.sqrt(odd - 1.0))


def tamanho_amostra(efeito: float, desvio_padrao: float, z: float = Z_95) -> float:
    """Quantas apostas seriam necessárias para enxergar um efeito deste tamanho.

    A fórmula da seção 8.2 da especificação::

        n ≈ ( z · desvio_padrão / efeito )²

    Args:
        efeito: o efeito verdadeiro que se quer detectar, na mesma unidade dos
            retornos (ROI de 2% = ``0.02``).
        desvio_padrao: volatilidade de uma aposta. Use
            :func:`desvio_padrao_da_aposta` para planejar ou o desvio medido
            para reportar.
        z: ``Z_95`` (o padrão) responde "quantas apostas para o IC 95% não
            cruzar o zero"; ``Z_PODER_80`` responde "quantas para eu ter 80% de
            chance de ver o efeito".

    Retorna:
        O número de apostas. Vem como ``float`` de propósito: arredondar para
        cima é decisão de quem usa, e o número costuma ser grande demais para a
        última casa importar.

    Exemplo — a linha da tabela da especificação (ROI verdadeiro de 2% em odd
    média 2,00) dá cerca de 9.600 apostas.
    """
    if efeito == 0:
        return float("inf")
    if desvio_padrao < 0:
        raise ValueError(f"Desvio-padrão não pode ser negativo; veio {desvio_padrao}.")
    return float((z * desvio_padrao / abs(efeito)) ** 2)


def efeito_detectavel(n: int, desvio_padrao: float, z: float = Z_95) -> float:
    """O menor efeito que **esta** amostra conseguiria enxergar.

    É :func:`tamanho_amostra` resolvida para o outro lado::

        efeito ≈ z · desvio_padrão / √n

    É o número que a regra 10 manda publicar ao lado de todo ROI e todo CLV.
    Sem ele, "não houve vantagem" fica indistinguível de "não dava para saber",
    e as duas frases significam coisas muito diferentes.

    Args:
        n: número de apostas.
        desvio_padrao: o desvio-padrão **medido** dos retornos.
        z: ver :func:`tamanho_amostra`.
    """
    if n <= 0:
        return float("nan")
    return float(z * desvio_padrao / np.sqrt(n))


def bootstrap_ic(
    valores,
    confianca: float = 0.95,
    amostras: int = 10_000,
    seed: int = 42,
) -> tuple[float, float]:
    """Intervalo de confiança da média por bootstrap (regra 10 e regra 2.6c).

    Bootstrap é a ideia de reamostrar **os próprios dados**, com reposição, mil
    vezes, e olhar como a média balança. A vantagem sobre a fórmula normal é não
    supor forma nenhuma para a distribuição — e a distribuição de lucro de
    aposta é tudo menos normal: é uma pilha de ``−1`` com alguns ``+4`` no meio,
    torta e de cauda pesada. Com poucas apostas em odd alta, o intervalo normal
    mente; o bootstrap não.

    Args:
        valores: os retornos, um por aposta.
        confianca: 0,95 dá o intervalo de 2,5% a 97,5%.
        amostras: quantas reamostragens. 10.000 é o padrão do ``config.yaml``.
        seed: semente fixa — dois relatórios do mesmo dado dão o mesmo intervalo.

    Retorna:
        ``(limite inferior, limite superior)``. Com menos de duas observações
        volta ``(nan, nan)``: intervalo de uma amostra só não existe.
    """
    valores = np.asarray(valores, dtype=float)
    valores = valores[np.isfinite(valores)]
    if len(valores) < 2:
        return (float("nan"), float("nan"))

    gerador = np.random.default_rng(seed)
    # Sortear de uma vez uma matriz (amostras x n) troca dez mil laços de Python
    # por uma operação de NumPy — mas com cem mil apostas e dez mil repetições
    # essa matriz teria um bilhão de números e não caberia na memória. Daí os
    # blocos: vetorizado o suficiente para ser rápido, pequeno o suficiente para
    # caber. O resultado é idêntico ao da matriz inteira.
    por_bloco = max(1, _NUMEROS_POR_BLOCO // len(valores))
    medias = np.empty(amostras, dtype=float)
    feitas = 0
    while feitas < amostras:
        agora = min(por_bloco, amostras - feitas)
        sorteios = gerador.integers(0, len(valores), size=(agora, len(valores)))
        medias[feitas : feitas + agora] = valores[sorteios].mean(axis=1)
        feitas += agora

    resto = (1.0 - confianca) / 2.0
    baixo, alto = np.quantile(medias, [resto, 1.0 - resto])
    return (float(baixo), float(alto))
