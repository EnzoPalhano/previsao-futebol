"""O modelo burro: "o que costuma acontecer nesta liga".

Este modelo não olha quem está jogando. Ele responde toda pergunta com a
distribuição histórica de placares da liga: na Premier League, 1x1 aconteceu em
tantos por cento dos jogos, 2x0 em tantos, e é isso que ele prevê para
Arsenal x Chelsea e para Luton x Sheffield United — os mesmos números.

**Por que gastar código num modelo que ignora os times?**

Porque sem ele não existe régua. Um modelo de verdade que chegue a log loss
0,99 pode ser excelente ou pode ser inútil, e a única forma de saber é
comparar com o que se consegue **sem esforço nenhum**. Três referências que a
Fase 4 vai usar lado a lado:

===========================  ==========  ==================================
referência                   log loss    o que ela representa
===========================  ==========  ==================================
chute uniforme (33/33/33)      1,0986    nada de informação
este baseline                  ~1,03     só a estatística da liga
mercado de fechamento          0,9984    tudo que o mercado sabe (Fase 2)
===========================  ==========  ==================================

Um modelo que não bata o baseline não aprendeu nada sobre times. Um que bata o
baseline e não chegue perto do mercado aprendeu algo, mas menos que a casa —
e aí não há aposta com valor. Esse é o padrão: **o mercado ganha**, e isso é
normal, não fracasso (Fase 4 da especificação).

Detalhe de implementação que parece pequeno e não é: o baseline também entrega
uma **matriz de placares**, e não só as três probabilidades do 1X2. Assim ele
passa pelo mesmo caminho de código dos outros modelos, e o Over 2,5 e o "ambos
marcam" dele saem da mesma matriz — exatamente como no Dixon-Coles. Um
baseline com contas próprias seria um segundo lugar onde errar.

⚠️ A matriz deste modelo tem zeros nas casas exóticas (nenhum 7x6 no
histórico). Isso torna o baseline inadequado para o mercado de placar exato —
dizer "0%" para algo possível é o erro que a log loss pune com infinito. Para
os mercados que o projeto aposta (1X2, Over/Under, ambos marcam) não há
problema: nenhuma dessas regiões da matriz fica vazia.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from futebol.config import Config
from futebol.modelos import base

#: Quantos jogos uma liga precisa ter para valer a estatística dela própria.
#: Abaixo disso, a frequência de cada placar é mais ruído que informação e o
#: modelo usa a distribuição do conjunto todo. Nenhuma liga do projeto chega
#: perto disso (a menor tem mais de mil jogos) — o corte existe para o modelo
#: se comportar bem em amostra pequena, como nos testes e no app.
MINIMO_DE_JOGOS = 30


@dataclass(frozen=True)
class FrequenciasDaLiga:
    """A distribuição histórica de placares de uma liga.

    Atributos:
        liga: o código da liga (``E0``), ou ``"(todas)"`` na distribuição de
            reserva calculada com o conjunto inteiro.
        jogos: quantos jogos entraram na contagem.
        matriz: ``matriz[i, j]`` = frequência do placar ``i x j``, somando 1.
    """

    liga: str
    jogos: int
    matriz: np.ndarray

    def mercados(self) -> dict[str, float]:
        """As probabilidades de mercado desta liga."""
        return base.mercados_da_matriz(self.matriz)


def contar_placares(jogos: pd.DataFrame, max_gols: int) -> np.ndarray:
    """Conta quantas vezes cada placar aconteceu, e devolve as frequências.

    Args:
        jogos: tabela com ``gols_mandante`` e ``gols_visitante``.
        max_gols: maior número de gols da matriz.

    Placar acima do limite (um 9x0 numa matriz de 8) é **somado na borda**, não
    descartado: jogar fora um jogo mexeria no total e a frequência dos outros
    placares ficaria levemente inflada. Como são goleadas raríssimas, o efeito
    na borda é irrelevante, e o total continua honesto.
    """
    lado_mandante = np.clip(jogos["gols_mandante"].to_numpy(dtype=int), 0, max_gols)
    lado_visitante = np.clip(jogos["gols_visitante"].to_numpy(dtype=int), 0, max_gols)

    tamanho = max_gols + 1
    # Um índice único por placar (i, j) -> i * tamanho + j, contado de uma vez.
    contagem = np.bincount(
        lado_mandante * tamanho + lado_visitante, minlength=tamanho * tamanho
    )
    return base.normalizar_matriz(contagem.reshape(tamanho, tamanho).astype(float))


class Baseline(base.Modelo):
    """Prevê a média histórica da liga, ignorando quem joga.

    Uso::

        modelo = Baseline().treinar(jogos, ate_data="2024-08-01")
        modelo.prever(Jogo("E0", "ENG:Arsenal", "ENG:Chelsea"))
    """

    nome = "baseline"

    def __init__(self, max_gols: int | None = None, cfg: Config | None = None) -> None:
        super().__init__()
        self.max_gols = _max_gols(max_gols, cfg)
        #: Frequências por liga, preenchidas no treino.
        self.ligas: dict[str, FrequenciasDaLiga] = {}
        #: Distribuição de reserva, do conjunto inteiro. É o que responde por
        #: liga desconhecida — o app pode pedir uma liga que não estava no
        #: treino, e devolver a média geral é melhor que quebrar.
        self.geral: FrequenciasDaLiga | None = None

    def _ajustar(self, jogos: pd.DataFrame) -> None:
        self.geral = FrequenciasDaLiga(
            liga="(todas)",
            jogos=len(jogos),
            matriz=contar_placares(jogos, self.max_gols),
        )
        self.ligas = {
            str(liga): FrequenciasDaLiga(
                liga=str(liga),
                jogos=len(da_liga),
                matriz=contar_placares(da_liga, self.max_gols),
            )
            for liga, da_liga in jogos.groupby("liga", sort=True)
            if len(da_liga) >= MINIMO_DE_JOGOS
        }

    def matriz_de_placares(self, jogo: base.Jogo) -> np.ndarray:
        return self.frequencias(jogo.liga).matriz

    def frequencias(self, liga: str) -> FrequenciasDaLiga:
        """As frequências usadas para uma liga — a dela, ou a de reserva."""
        self._exigir_treinado()
        if liga in self.ligas:
            return self.ligas[liga]
        assert self.geral is not None  # garantido por `treinar`
        return self.geral

    def resumo(self) -> pd.DataFrame:
        """Uma linha por liga, com os mercados históricos dela.

        É a tabela que entra no relatório: dá para ler de uma vez em quais
        ligas o mandante ganha mais, onde há mais gol e onde há mais empate.
        """
        self._exigir_treinado()
        linhas = []
        for frequencias in self.ligas.values():
            linha = {"liga": frequencias.liga, "jogos": frequencias.jogos}
            linha.update(frequencias.mercados())
            linhas.append(linha)
        return pd.DataFrame(linhas)


def _max_gols(max_gols: int | None, cfg: Config | None) -> int:
    """Tamanho da matriz: o pedido, o do ``config.yaml``, ou 10.

    O baseline não tem seção própria no ``config.yaml``; ele usa o mesmo
    ``max_gols`` do Poisson, para as matrizes dos modelos terem todas o mesmo
    tamanho e poderem ser comparadas casa a casa.
    """
    if max_gols is not None:
        return int(max_gols)
    if cfg is not None:
        return int(cfg.secao("modelos")["poisson"]["max_gols"])
    return 10
