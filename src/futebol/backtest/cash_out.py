"""Cash out: sacar no meio do bilhete vale a pena?

*Cash out* é o botão que a casa oferece com a múltipla em andamento: "você
acertou 3 de 5, aceita R$ 43 agora em vez de arriscar os R$ 120?". Ele é
vendido como controle de risco, e a pergunta que esta fase responde é se ele
devolve dinheiro ou se é só mais um lugar onde a comissão é cobrada.

**A conta que a casa faz.** O valor **justo** de uma múltipla viva é a chance de
ela ainda dar certo vezes o prêmio::

    valor justo = (produto das chances das seleções que faltam) × prêmio

E a oferta é esse valor **menos uma margem**. Ou seja: o cash out é uma segunda
comissão, cobrada por cima da que já estava no preço de cada seleção. Sacar
sempre é pagar duas vezes.

⚠️ **De quem são as probabilidades da conta?** Da casa, não do modelo — e essa
distinção é o que torna a análise interessante em vez de trivial. Se os dois
usassem os mesmos números, a oferta seria **sempre** menor que o valor justo do
modelo, e "sacar quando vale a pena" nunca aconteceria. Como as probabilidades
são diferentes, existem bilhetes em que o modelo acha que a casa está pagando
bem. O módulo simula exatamente isso: a oferta sai das probabilidades justas do
**mercado**, e a decisão compara com a do **modelo**.

⚠️ **A limitação, dita antes do resultado.** O cash out acontece à medida que os
jogos vão terminando, e a fonte de dados não traz o horário de cada partida.
Então a ordem em que as seleções se resolvem é uma **convenção**: da mais
provável para a menos provável, que é a ordem em que elas entram no bilhete.
Num sábado real, a ordem seria a dos horários de início. Isso afeta as
estratégias do tipo "sacar depois de X acertos" — não afeta "nunca sacar", nem
o valor justo, nem a margem.

**O Monte Carlo entra aqui, e só aqui.** A seção 7.1 avisa que sortear jogos
independentes **não** conserta a correlação entre partidas — seria o mesmo
número por um caminho mais caro. Mas ele serve para outra coisa, que é o que
:func:`distribuicao_de_acertos` faz: dizer com que frequência um bilhete de dez
jogos termina com 7, 8 ou 9 acertos. Essa distribuição é justamente o que
descreve as situações em que o botão de cash out aparece.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from futebol.avaliacao import metricas
from futebol.config import Config


def margem_da_casa(cfg: Config) -> float:
    """Quanto a oferta de cash out fica abaixo do valor justo (``config.yaml``)."""
    return float(cfg.secao("multiplas").get("cash_out_margem_casa", 0.08))


def valor_justo(prob_restante: float, premio: float) -> float:
    """O que a múltipla viva vale: chance do que falta × prêmio."""
    return float(prob_restante) * float(premio)


def oferta(prob_restante: float, premio: float, margem: float) -> float:
    """A oferta da casa: o valor justo menos a margem dela.

    Args:
        prob_restante: a chance, **segundo a casa**, de as seleções que faltam
            darem certo.
        premio: o que o bilhete pagaria inteiro.
        margem: a fatia que a casa retém (0,08 = 8%).
    """
    return valor_justo(prob_restante, premio) * (1.0 - float(margem))


def distribuicao_de_acertos(
    probabilidades, repeticoes: int = 20_000, seed: int = 42
) -> np.ndarray:
    """Com que frequência o bilhete termina com 0, 1, 2… acertos.

    Args:
        probabilidades: a chance de cada seleção do bilhete.
        repeticoes: quantos bilhetes sortear.
        seed: semente fixa — dois relatórios do mesmo bilhete dão o mesmo número.

    Retorna:
        Um vetor de tamanho ``n+1``: a posição ``k`` é a fração das simulações
        que terminaram com ``k`` acertos.

    ⚠️ **Este é o uso legítimo do Monte Carlo nesta fase**, e vale saber por quê.
    Sortear os jogos de forma independente **não** corrige a correlação entre
    partidas — a simulação só reproduz o produto das probabilidades com ruído a
    mais (seção 7.1). Mas a pergunta aqui é outra: não "qual a chance de ganhar
    tudo" (para essa basta multiplicar), e sim "como se distribuem os acertos
    parciais". Essa conta exata existiria — é uma convolução de Bernoullis com
    probabilidades diferentes — e o sorteio é o caminho curto para ela.
    """
    probabilidades = np.asarray(probabilidades, dtype=float)
    gerador = np.random.default_rng(seed)
    sorteios = gerador.random((repeticoes, len(probabilidades))) < probabilidades
    acertos = sorteios.sum(axis=1)
    return np.bincount(acertos, minlength=len(probabilidades) + 1) / repeticoes


# ----------------------------------------------------------------------------
# As estratégias, medidas no histórico
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Estrategia:
    """O resultado de uma regra de cash out sobre as múltiplas do histórico.

    Atributos:
        nome: como a linha aparece na tabela.
        n: quantos bilhetes.
        roi: o lucro médio **que de fato aconteceu**, por unidade apostada.
        roi_ic: intervalo de 95% por bootstrap.
        ev_mercado: o lucro médio **esperado**, calculado com as probabilidades
            justas do mercado.
        sacou: em que fração dos bilhetes o cash out chegou a acontecer.
        ganhou_tudo: fração que foi até o fim e acertou.

    ⚠️ **``roi`` e ``ev_mercado`` respondem a mesma pergunta com ruídos muito
    diferentes, e é por isso que os dois aparecem.** O ``roi`` depende de quais
    bilhetes acertaram, e num bilhete de oito jogos que acerta 1,7% das vezes
    isso é uma loteria: o intervalo de confiança dele passa de 40 pontos. O
    ``ev_mercado`` não depende de resultado nenhum — é a conta do valor esperado
    feita com os preços — e por isso separa as estratégias de verdade.

    Sem essa distinção, a tabela levaria à conclusão oposta da correta: "sacar
    após 1 acerto" aparece com ROI melhor que "nunca sacar" simplesmente porque
    tem menos variância, e não porque devolva mais dinheiro.
    """

    nome: str
    n: int
    roi: float
    roi_ic: tuple[float, float]
    ev_mercado: float
    sacou: float
    ganhou_tudo: float


def _matrizes(historico, tamanho: int) -> dict[str, np.ndarray]:
    """As múltiplas de um tamanho, em matrizes ``(bilhetes × seleções)``.

    Trabalhar em matriz e não em laço não é capricho: são dezenas de milhares de
    bilhetes, e cada estratégia precisa olhar cada ponto de decisão de cada um.
    """
    do_tamanho = historico.multiplas.loc[historico.multiplas["tamanho"] == tamanho]
    pernas = historico.pernas.loc[historico.pernas["id"].isin(set(do_tamanho["id"]))]
    pernas = pernas.sort_values(["id", "ordem"])

    forma = (len(do_tamanho), tamanho)
    return {
        "prob_modelo": pernas["prob"].to_numpy(float).reshape(forma),
        "prob_mercado": pernas["prob_justa"].to_numpy(float).reshape(forma),
        "ganhou": pernas["ganhou"].to_numpy(bool).reshape(forma),
        "premio": do_tamanho["odd_total"].to_numpy(float),
    }


def simular(
    historico,
    cfg: Config,
    tamanho: int,
    amostras_bootstrap: int = 2000,
    seed: int = 42,
) -> list[Estrategia]:
    """Compara as regras de cash out num tamanho de múltipla.

    As regras, que são as que a especificação pede:

    - **nunca sacar** — a referência. Ganha o prêmio inteiro ou perde tudo;
    - **sacar após N acertos** — a regra que as pessoas de fato usam, uma linha
      para cada ponto de decisão possível;
    - **sacar quando a oferta compensa** — só aceita quando a oferta da casa
      passa do valor justo **segundo o modelo**. É a única das três que usa
      informação, e por isso a única que poderia ganhar da referência.

    Retorna:
        Uma :class:`Estrategia` por regra, na ordem em que o relatório as mostra.
    """
    margem = margem_da_casa(cfg)
    dados = _matrizes(historico, tamanho)
    ganhou, premio = dados["ganhou"], dados["premio"]
    n = len(premio)
    if n == 0:
        return []

    # Sobreviveu até o ponto de decisão j = acertou as j primeiras seleções.
    sobrevive = np.cumprod(ganhou, axis=1).astype(bool)
    # O que falta depois de j seleções: o produto total dividido pelo acumulado.
    restante_mercado = _restante(dados["prob_mercado"])
    restante_modelo = _restante(dados["prob_modelo"])
    ofertas = restante_mercado * premio[:, None] * (1.0 - margem)
    justos_modelo = restante_modelo * premio[:, None]

    ganhou_tudo = ganhou.all(axis=1)
    # O valor esperado de levar o bilhete até o fim, segundo os preços: a chance
    # justa de acertar tudo vezes o prêmio. É o que a múltipla vale antes de
    # qualquer botão ser apertado.
    ev_ate_o_fim = dados["prob_mercado"].prod(axis=1) * premio - 1.0

    def montar(nome, retornos, ev_mercado, sacou, ganhou_tudo_da_regra):
        return Estrategia(
            nome=nome,
            n=n,
            roi=float(retornos.mean()),
            roi_ic=metricas.bootstrap_ic(
                retornos, amostras=amostras_bootstrap, seed=seed
            ),
            ev_mercado=float(ev_mercado),
            sacou=float(sacou),
            ganhou_tudo=float(ganhou_tudo_da_regra),
        )

    resultados = [
        montar(
            "nunca sacar",
            np.where(ganhou_tudo, premio - 1.0, -1.0),
            ev_ate_o_fim.mean(),
            0.0,
            ganhou_tudo.mean(),
        )
    ]

    for acertos in range(1, tamanho):
        # Sacou se chegou vivo ao ponto de decisão; senão, perdeu a aposta antes.
        vivo = sobrevive[:, acertos - 1]
        retornos = np.where(vivo, ofertas[:, acertos - 1] - 1.0, -1.0)
        # ⚠️ O valor esperado de sacar num ponto fixo **não depende do ponto**: a
        # chance de chegar vivo até lá, multiplicada pelo que falta, dá sempre o
        # produto inteiro — e o que sobra é o desconto do cash out. Ou seja, o
        # botão cobra a mesma taxa seja apertado no primeiro ou no último jogo.
        ev = ((1.0 + ev_ate_o_fim) * (1.0 - margem) - 1.0).mean()
        resultados.append(
            montar(f"sacar após {acertos} acerto(s)", retornos, ev, vivo.mean(), 0.0)
        )

    retornos, sacou, ev_da_regra = _sacar_quando_compensa(
        sobrevive, ofertas, justos_modelo, premio, ganhou_tudo, ev_ate_o_fim, margem
    )
    resultados.append(
        montar(
            "sacar só quando a oferta compensa",
            retornos,
            ev_da_regra.mean(),
            sacou.mean(),
            (ganhou_tudo & ~sacou).mean(),
        )
    )
    return resultados


def _restante(probabilidades: np.ndarray) -> np.ndarray:
    """Para cada ponto de decisão, o produto das seleções que **faltam**.

    A coluna ``j`` é o produto das seleções de ``j+1`` em diante. Sai da divisão
    do produto total pelo acumulado até ``j`` — uma conta só, em vez de um laço
    por bilhete.
    """
    acumulado = np.cumprod(probabilidades, axis=1)
    total = acumulado[:, -1:]
    return total / acumulado


def _sacar_quando_compensa(
    sobrevive: np.ndarray,
    ofertas: np.ndarray,
    justos_modelo: np.ndarray,
    premio: np.ndarray,
    ganhou_tudo: np.ndarray,
    ev_ate_o_fim: np.ndarray,
    margem: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A regra que usa informação: sacar no **primeiro** ponto em que compensa.

    Compensa quando a oferta da casa passa do valor justo segundo o modelo — ou
    seja, quando o modelo acha que a casa está pagando caro demais para se livrar
    do risco. Se isso nunca acontece, o bilhete vai até o fim.

    ⚠️ Repare que **o ponto de saque é decidido só com preços e probabilidades**,
    nunca com resultado. O que depende do resultado é apenas se o bilhete chegou
    vivo até lá. Sem essa separação, a regra estaria olhando o futuro.

    Retorna:
        ``(retornos, sacou, valor esperado de cada bilhete sob a regra)``.
    """
    n, pontos = ofertas.shape
    retornos = np.where(ganhou_tudo, premio - 1.0, -1.0)
    sacou = np.zeros(n, dtype=bool)
    tem_ponto_de_saque = np.zeros(n, dtype=bool)

    # Percorre os pontos de decisão do primeiro ao último: no máximo dez passos,
    # cada um vetorizado sobre todos os bilhetes.
    for j in range(pontos - 1):
        vale_a_pena = ofertas[:, j] > justos_modelo[:, j]
        tem_ponto_de_saque = tem_ponto_de_saque | vale_a_pena

        compensa = sobrevive[:, j] & vale_a_pena & ~sacou
        retornos = np.where(compensa, ofertas[:, j] - 1.0, retornos)
        sacou = sacou | compensa
        # Quem não chegou vivo aqui já perdeu, e não decide mais nada.
        perdeu_antes = ~sobrevive[:, j] & ~sacou
        retornos = np.where(perdeu_antes, -1.0, retornos)

    # Bilhete com ponto de saque paga a taxa do cash out; o resto vai inteiro.
    ev = np.where(
        tem_ponto_de_saque,
        (1.0 + ev_ate_o_fim) * (1.0 - margem) - 1.0,
        ev_ate_o_fim,
    )
    return retornos, sacou, ev


def como_tabela(estrategias: list[Estrategia]) -> pd.DataFrame:
    """As estratégias numa tabela, para o relatório."""
    return pd.DataFrame(
        [
            {
                "estrategia": e.nome,
                "bilhetes": e.n,
                "roi": e.roi,
                "roi_baixo": e.roi_ic[0],
                "roi_alto": e.roi_ic[1],
                "ev_mercado": e.ev_mercado,
                "sacou": e.sacou,
                "ganhou_tudo": e.ganhou_tudo,
            }
            for e in estrategias
        ]
    )
