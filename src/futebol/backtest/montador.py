"""O montador de múltiplas: "quero ganhar R$ 200 com R$ 10 — o que eu jogo?".

Este é o módulo que vira tela na Fase 8. Ele recebe os jogos de uma rodada e
monta o melhor bilhete possível para o que a pessoa pediu, que pode ser uma de
três coisas:

- **um número de seleções** ("quero um bilhete de 4 jogos");
- **um prêmio alvo** ("quero ganhar R$ 200 apostando R$ 10");
- **uma faixa** ("entre 3 e 6 jogos"), para comparar as opções lado a lado.

⚠️ **"Melhor" aqui quer dizer maior chance de ganhar, não maior valor
esperado** — e a escolha é deliberada, com o preço declarado. A Fase 6 mediu o
que acontece quando se escolhe por EV: o filtro empurra a carteira para os
azarões, que é onde a casa cobra mais caro, e o ROI **piora**. Numa múltipla
isso seria pior ainda, porque cada azarão multiplica a chance de o bilhete
inteiro morrer. Então o montador maximiza a probabilidade e **reporta** o EV ao
lado, com aviso quando ele é negativo — que é o caso quase sempre.

**A restrição que não é negociável:** no máximo uma seleção por jogo. Mercados
da mesma partida são fortemente correlacionados, e multiplicar as
probabilidades deles daria um número errado para mais
(ver :mod:`futebol.backtest.multiplas`).

**Por que busca em feixe, e não força bruta.** Numa rodada de 30 jogos há 30
escolhas de 4 jogos vezes as seleções de cada um — dezenas de milhares de
combinações, e o número explode com o tamanho do bilhete. A busca em feixe
guarda só as ``beam_width`` melhores possibilidades parciais a cada passo. Não
garante o ótimo global quando há alvo de prêmio, e o módulo diz isso em voz
alta em vez de fingir.

⚠️ Com **um** caso, porém, a resposta é provadamente ótima: quando só se pede um
tamanho, sem alvo de prêmio, basta pegar as ``n`` seleções mais prováveis, uma
por jogo. Isso é ótimo de verdade (maximizar um produto é maximizar a soma dos
logaritmos, e escolher o melhor de cada jogo sem repetir é o caso clássico em
que o guloso acerta). Ver :func:`por_tamanho`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from futebol.backtest import multiplas
from futebol.config import Config

#: O aviso de independência que a especificação manda acompanhar **toda** chance
#: de ganhar mostrada — no relatório e na tela do app (seção 7.1).
AVISO_DE_INDEPENDENCIA = (
    "A chance de ganhar supõe que os jogos são independentes entre si. A chance "
    "real tende a ser um pouco menor, principalmente em bilhetes grandes."
)


@dataclass(frozen=True)
class Opcao:
    """Um bilhete montado, com tudo o que a pessoa precisa saber antes de apostar.

    Atributos:
        pernas: as seleções escolhidas, uma linha por jogo.
        valor: quanto se aposta, em reais.
        odd_total: o produto das odds.
        premio: ``valor × odd_total`` — o que se recebe se tudo der certo.
        prob_modelo: a chance de ganhar segundo o modelo. ⚠️ Sempre acompanhada
            de :data:`AVISO_DE_INDEPENDENCIA`.
        prob_implicita: a chance que o **preço** sugere (produto de ``1/odd``).
        prob_mercado: a chance segundo o mercado, já sem a comissão.
        margem_acumulada: quanto a casa cobra no bilhete inteiro.
        ev: o valor esperado em reais. Negativo quer dizer que, em média, a
            aposta perde dinheiro.
    """

    pernas: pd.DataFrame
    valor: float
    odd_total: float
    premio: float
    prob_modelo: float
    prob_implicita: float
    prob_mercado: float
    margem_acumulada: float
    ev: float

    @property
    def tamanho(self) -> int:
        return len(self.pernas)

    @property
    def uma_em(self) -> float:
        """A chance escrita como "1 em X", que é como as pessoas pensam."""
        return 1.0 / self.prob_modelo if self.prob_modelo > 0 else float("inf")

    @property
    def ev_negativo(self) -> bool:
        return self.ev < 0

    def como_linha(self) -> dict[str, object]:
        return {
            "tamanho": self.tamanho,
            "odd_total": self.odd_total,
            "premio": self.premio,
            "prob_modelo": self.prob_modelo,
            "uma_em": self.uma_em,
            "prob_implicita": self.prob_implicita,
            "prob_mercado": self.prob_mercado,
            "margem_acumulada": self.margem_acumulada,
            "ev": self.ev,
        }


def _montar_opcao(pernas: pd.DataFrame, valor: float) -> Opcao:
    """As contas de um bilhete, a partir das seleções escolhidas."""
    resumo = multiplas.resumir(pernas, len(pernas), bloco=0)
    odd_total = float(resumo["odd_total"])
    prob_modelo = float(resumo["prob_modelo"])
    return Opcao(
        pernas=pernas.reset_index(drop=True),
        valor=float(valor),
        odd_total=odd_total,
        premio=float(valor) * odd_total,
        prob_modelo=prob_modelo,
        prob_implicita=float(resumo["prob_implicita"]),
        prob_mercado=float(resumo["prob_mercado"]),
        margem_acumulada=float(resumo["margem_acumulada"]),
        # O que se ganha em média: a chance de levar o prêmio vezes o lucro,
        # menos a chance de perder vezes o que foi apostado.
        ev=float(valor) * (prob_modelo * odd_total - 1.0),
    )


# ----------------------------------------------------------------------------
# 1. Tamanho pedido: a resposta ótima é o guloso
# ----------------------------------------------------------------------------
def por_tamanho(
    candidatos_da_rodada: pd.DataFrame, tamanho: int, valor: float = 10.0
) -> Opcao | None:
    """O bilhete de ``tamanho`` seleções com a **maior** chance de ganhar.

    A resposta é provadamente ótima, e a prova é curta: maximizar o produto das
    probabilidades é maximizar a soma dos logaritmos; a restrição "no máximo uma
    seleção por jogo" só proíbe repetir partida; então pegar a melhor seleção de
    cada jogo e ficar com as ``tamanho`` maiores não pode ser batido por
    nenhuma outra combinação.

    Retorna:
        A :class:`Opcao`, ou ``None`` se a rodada não tiver jogos suficientes.
    """
    por_jogo = multiplas.melhor_selecao_por_jogo(candidatos_da_rodada)
    if len(por_jogo) < tamanho or tamanho < 1:
        return None
    escolhidas = por_jogo.sort_values("prob", ascending=False).head(tamanho)
    return _montar_opcao(escolhidas, valor)


# ----------------------------------------------------------------------------
# 2. Prêmio alvo: aí sim é busca
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class _Parcial:
    """Um bilhete pela metade, durante a busca em feixe."""

    indices: tuple[int, ...] = ()
    log_prob: float = 0.0
    log_odd: float = 0.0
    jogos: frozenset = field(default_factory=frozenset)


def busca_em_feixe(
    candidatos_da_rodada: pd.DataFrame,
    odd_alvo: float,
    max_selecoes: int,
    beam_width: int = 50,
    valor: float = 10.0,
) -> Opcao | None:
    """O bilhete mais provável que alcança ``odd_alvo``, pela busca em feixe.

    A busca cresce o bilhete uma seleção por vez. A cada passo ela gera todas as
    extensões possíveis das possibilidades que tem na mão, ordena pela
    probabilidade e **joga fora todas menos as ``beam_width`` melhores**. É isso
    que impede a explosão combinatória.

    ⚠️ **Isso é uma heurística, não um ótimo garantido.** Um bilhete que começa
    ruim e terminaria ótimo pode ser cortado no meio do caminho. Na prática o
    corte quase nunca custa caro aqui, porque a função a maximizar é uma soma de
    logaritmos e caminhos bons tendem a ter começos bons — mas "quase nunca" não
    é "nunca", e é por isso que está escrito.

    Args:
        candidatos_da_rodada: as seleções disponíveis.
        odd_alvo: a odd total mínima que o bilhete precisa alcançar.
        max_selecoes: teto de seleções.
        beam_width: quantas possibilidades parciais sobrevivem a cada passo.
        valor: quanto se aposta.

    Retorna:
        A melhor :class:`Opcao` encontrada, ou ``None`` se nem juntando
        ``max_selecoes`` seleções dá para alcançar o alvo.
    """
    por_jogo = multiplas.melhor_selecao_por_jogo(candidatos_da_rodada)
    por_jogo = por_jogo.sort_values("prob", ascending=False).reset_index(drop=True)
    if por_jogo.empty or max_selecoes < 1:
        return None

    log_prob = np.log(por_jogo["prob"].to_numpy(float))
    log_odd = np.log(por_jogo["odd"].to_numpy(float))
    chaves = por_jogo[list(multiplas.CHAVE_DO_JOGO)].astype(str).agg("|".join, axis=1)
    chaves = chaves.to_numpy()
    alvo = float(np.log(odd_alvo))

    feixe = [_Parcial()]
    melhor: _Parcial | None = None

    for _ in range(max_selecoes):
        proximo: list[_Parcial] = []
        for parcial in feixe:
            # A busca só olha para a frente na lista: as seleções estão ordenadas
            # e um bilhete é um conjunto, não uma sequência. Sem isso, a mesma
            # combinação seria gerada em todas as ordens possíveis.
            inicio = parcial.indices[-1] + 1 if parcial.indices else 0
            for i in range(inicio, len(por_jogo)):
                if chaves[i] in parcial.jogos:
                    continue
                novo = _Parcial(
                    indices=(*parcial.indices, i),
                    log_prob=parcial.log_prob + log_prob[i],
                    log_odd=parcial.log_odd + log_odd[i],
                    jogos=parcial.jogos | {chaves[i]},
                )
                if novo.log_odd >= alvo:
                    # Alcançou o alvo. Guardar o mais provável entre os que
                    # alcançaram, e não continuar crescendo este: acrescentar
                    # seleção a um bilhete que já serve só diminui a chance.
                    if melhor is None or novo.log_prob > melhor.log_prob:
                        melhor = novo
                else:
                    proximo.append(novo)

        if not proximo:
            break
        proximo.sort(key=lambda p: p.log_prob, reverse=True)
        feixe = proximo[:beam_width]

    if melhor is None:
        return None
    return _montar_opcao(por_jogo.iloc[list(melhor.indices)], valor)


# ----------------------------------------------------------------------------
# 3. A tabela comparativa
# ----------------------------------------------------------------------------
def comparar_tamanhos(
    candidatos_da_rodada: pd.DataFrame,
    cfg: Config,
    faixa: tuple[int, int] | None = None,
    valor: float = 10.0,
) -> pd.DataFrame:
    """Lado a lado: como a chance cai e a margem sobe ao acrescentar jogos.

    É a tabela que a especificação pede, e ela é o argumento inteiro da fase numa
    figura só. Cada jogo a mais multiplica o prêmio — e multiplica a comissão, e
    divide a chance de ganhar.
    """
    valores = multiplas.limites(cfg)
    primeiro = valores["min_selecoes"] if faixa is None else faixa[0]
    ultimo = valores["max_selecoes"] if faixa is None else faixa[1]

    elegiveis = multiplas.elegiveis(candidatos_da_rodada, cfg)
    linhas = []
    for tamanho in range(max(1, primeiro), ultimo + 1):
        opcao = por_tamanho(elegiveis, tamanho, valor)
        if opcao is not None:
            linhas.append(opcao.como_linha())
    return pd.DataFrame(linhas)


def montar(
    candidatos_da_rodada: pd.DataFrame,
    cfg: Config,
    tamanho: int | None = None,
    premio_alvo: float | None = None,
    valor: float = 10.0,
) -> Opcao | None:
    """A porta de entrada: monta pelo tamanho **ou** pelo prêmio alvo.

    Args:
        candidatos_da_rodada: as seleções disponíveis na rodada.
        cfg: a configuração (faixa de odd, teto de seleções, largura do feixe).
        tamanho: número de seleções desejado.
        premio_alvo: o prêmio em reais que se quer alcançar apostando ``valor``.
        valor: quanto se aposta.

    Levanta:
        ValueError: se os dois forem pedidos ao mesmo tempo, ou nenhum. São
            perguntas diferentes e a resposta seria ambígua — melhor falhar do
            que escolher por conta própria qual delas a pessoa quis fazer.
    """
    if (tamanho is None) == (premio_alvo is None):
        raise ValueError(
            "Peça o tamanho OU o prêmio alvo, nunca os dois nem nenhum dos dois."
        )
    valores = multiplas.limites(cfg)
    disponiveis = multiplas.elegiveis(candidatos_da_rodada, cfg)

    if tamanho is not None:
        return por_tamanho(disponiveis, tamanho, valor)

    if valor <= 0:
        raise ValueError(f"O valor apostado tem de ser positivo; veio {valor}.")
    return busca_em_feixe(
        disponiveis,
        odd_alvo=premio_alvo / valor,
        max_selecoes=valores["max_selecoes"],
        beam_width=valores["beam_width"],
        valor=valor,
    )
