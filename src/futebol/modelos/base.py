"""A interface que todo modelo obedece — e a matriz de placares que os une.

Este módulo não contém modelo nenhum. Ele contém o **contrato**: o que
significa "um modelo" neste projeto, e como uma previsão de placar vira uma
probabilidade de mercado. Tudo que vem depois (Poisson, Dixon-Coles, o
LightGBM da Fase 5) preenche este contrato, e por isso a Fase 4 consegue
comparar todos eles com o mesmo código de avaliação.

**A ideia central: o modelo prevê o PLACAR, não o resultado.**

Um modelo que preveja diretamente "45% mandante, 27% empate, 28% visitante"
sabe responder uma pergunta só. Um modelo que preveja a matriz de placares —
a chance de 0x0, de 1x0, de 2x1, de cada combinação — responde todas as
perguntas de uma vez, e responde de forma **coerente entre si**::

    P(mandante ganha)  = soma da matriz abaixo da diagonal
    P(mais de 2,5)     = soma das casas em que os gols somam 3 ou mais
    P(ambos marcam)    = soma das casas com pelo menos 1 gol de cada lado

Coerência aqui não é elegância: é proteção. Se as probabilidades de 1X2 e de
Over/Under saíssem de dois lugares diferentes, o projeto poderia acabar
apostando ao mesmo tempo em "empate" e em "muitos gols" com uma inconsistência
que nenhum teste pegaria. Vindo todas da mesma matriz, isso é impossível por
construção.

**O contrato, em duas funções** (Fase 3 da especificação):

- ``treinar(jogos, ate_data)`` — aprende com os jogos **anteriores** a uma data;
- ``prever(jogo)`` — devolve um dicionário de probabilidades.

⚠️ **O ``ate_data`` é a trava contra data leakage (regra 6).** Ele não é um
detalhe de conveniência: é o motivo de o projeto ser confiável. Treinar com um
jogo do próprio dia da previsão — ou pior, do mês seguinte — produz um modelo
que parece excelente no backtest e perde dinheiro na vida real. Como a
filtragem mora aqui, na classe base, nenhum modelo pode "esquecer" de fazê-la.
O corte é **estritamente menor** (``<``), nunca ``<=``: jogo do mesmo dia da
previsão já é informação que não existia na hora de apostar.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

#: As chaves que um ``prever`` sempre devolve, nesta ordem. Existem três pares
#: de mercados complementares; guardar os dois lados de cada par (``over25`` e
#: ``under25``) é redundante de propósito, para que um teste consiga conferir
#: que somam 1 e apanhar um erro de sinal.
CHAVES_PREVISAO: tuple[str, ...] = (
    "H",
    "D",
    "A",
    "over25",
    "under25",
    "ambos_marcam",
    "ambos_nao_marcam",
)

#: Os grupos que precisam somar 1 em qualquer previsão válida.
GRUPOS_COMPLEMENTARES: tuple[tuple[str, ...], ...] = (
    ("H", "D", "A"),
    ("over25", "under25"),
    ("ambos_marcam", "ambos_nao_marcam"),
)

#: Colunas que um modelo precisa encontrar na tabela de treino.
COLUNAS_TREINO: tuple[str, ...] = (
    "data",
    "liga",
    "mandante",
    "visitante",
    "gols_mandante",
    "gols_visitante",
)

#: Tolerância ao conferir que uma matriz de placares soma 1. A matriz é
#: truncada em 10 gols por lado, e a cauda que fica de fora é redistribuída na
#: normalização — sobra só erro de ponto flutuante.
TOLERANCIA_SOMA = 1e-9


class ErroDeModelo(Exception):
    """Modelo usado sem treino, liga desconhecida ou matriz inválida."""


# ----------------------------------------------------------------------------
# O jogo que se quer prever
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Jogo:
    """O mínimo que se precisa saber para prever: a liga e os dois times.

    A ``data`` é opcional e serve a dois propósitos: escolher o corte de treino
    numa avaliação walk-forward e, nos modelos com decaimento temporal, dizer a
    partir de quando o passado começa a pesar menos.

    ⚠️ ``mandante`` e ``visitante`` são as chaves ``PAIS:nome`` da tabela
    (regra 14) — ``ENG:Arsenal``, não ``Arsenal``. Existe Everton na Inglaterra
    e no Chile, River Plate na Argentina e no Uruguai.
    """

    liga: str
    mandante: str
    visitante: str
    data: pd.Timestamp | None = None

    @classmethod
    def de_mapa(cls, linha: Mapping) -> Jogo:
        """Constrói um :class:`Jogo` a partir de uma linha da tabela.

        Aceita qualquer mapeamento — um ``dict`` ou uma linha de ``DataFrame``
        percorrida com ``.iterrows()``.
        """
        faltando = [c for c in ("liga", "mandante", "visitante") if c not in linha]
        if faltando:
            raise ErroDeModelo(
                f"Para prever um jogo faltam as chaves: {', '.join(faltando)}."
            )
        data = linha.get("data")
        tem_data = data is not None and not pd.isna(data)
        return cls(
            liga=str(linha["liga"]),
            mandante=str(linha["mandante"]),
            visitante=str(linha["visitante"]),
            data=pd.Timestamp(data) if tem_data else None,
        )


# ----------------------------------------------------------------------------
# A trava contra data leakage
# ----------------------------------------------------------------------------
def jogos_ate(jogos: pd.DataFrame, data) -> pd.DataFrame:
    """Só os jogos **anteriores** à data. O corte é estrito.

    Args:
        jogos: a tabela de jogos.
        data: a data da previsão. ``None`` devolve a tabela inteira — o que só
            é legítimo quando quem chamou já fez o corte.

    Retorna:
        Uma cópia com apenas as linhas de ``data`` estritamente anterior.

    Por que estrito: numa rodada de sábado, o jogo das 16h não pode ajudar a
    prever o das 18h. Na vida real a aposta foi feita antes de os dois
    acontecerem. Um ``<=`` aqui inflaria toda a avaliação do projeto de um jeito
    invisível — o modelo acertaria mais sem nenhum motivo honesto.
    """
    if data is None:
        return jogos
    corte = pd.Timestamp(data)
    return jogos.loc[jogos["data"] < corte].copy()


def conferir_colunas(jogos: pd.DataFrame) -> None:
    """Confere que a tabela de treino tem as colunas que o modelo precisa."""
    faltando = [c for c in COLUNAS_TREINO if c not in jogos.columns]
    if faltando:
        raise ErroDeModelo(
            f"A tabela de treino não tem as colunas: {', '.join(faltando)}. "
            "Ela deve vir de `futebol.dados.limpeza.carregar`."
        )


# ----------------------------------------------------------------------------
# Da matriz de placares para os mercados
# ----------------------------------------------------------------------------
def normalizar_matriz(matriz: np.ndarray) -> np.ndarray:
    """Deixa a matriz de placares somando exatamente 1.

    Duas correções, nesta ordem:

    1. **piso em zero** — a correção de placares baixos do Dixon-Coles mexe em
       quatro casas da matriz e, com um ``rho`` extremo, poderia empurrar uma
       delas para baixo de zero. Probabilidade negativa não existe, e deixá-la
       passar produziria soma maior que 1 em algum mercado;
    2. **divisão pela soma** — a matriz para em 10 gols por lado, e a cauda que
       fica de fora (menos de um milésimo de por cento) é redistribuída.
    """
    matriz = np.asarray(matriz, dtype=float)
    if matriz.ndim != 2:
        raise ErroDeModelo(
            f"A matriz de placares tem {matriz.ndim} dimensão(ões); esperado 2."
        )
    matriz = np.clip(matriz, 0.0, None)
    total = matriz.sum()
    if not np.isfinite(total) or total <= 0:
        raise ErroDeModelo(
            "A matriz de placares somou zero (ou não-número); não dá para "
            "normalizá-la em probabilidades."
        )
    return matriz / total


def mercados_da_matriz(matriz: np.ndarray) -> dict[str, float]:
    """A matriz de placares vira as probabilidades dos mercados.

    Args:
        matriz: ``matriz[i, j]`` = probabilidade de o mandante fazer ``i`` gols
            e o visitante ``j``. Precisa somar 1 (use :func:`normalizar_matriz`).

    Retorna:
        Dicionário com as chaves de :data:`CHAVES_PREVISAO`.

    A conta é geometria em cima da matriz, e vale olhar um exemplo de 3x3 para
    ver como cada mercado é uma região dela::

                     visitante 0   1   2
        mandante 0         D   A   A
        mandante 1         H   D   A
        mandante 2         H   H   D

    O 1X2 é o triângulo de baixo (``H``), a diagonal (``D``) e o triângulo de
    cima (``A``). O Over 2,5 é tudo em que a soma dos gols chega a 3. O "ambos
    marcam" é tudo menos a primeira linha e a primeira coluna.
    """
    matriz = np.asarray(matriz, dtype=float)
    soma = matriz.sum()
    if abs(soma - 1.0) > TOLERANCIA_SOMA:
        raise ErroDeModelo(
            f"A matriz de placares soma {soma:.12f}, não 1. "
            "Passe-a por `normalizar_matriz` antes de derivar os mercados."
        )
    if (matriz < 0).any():
        raise ErroDeModelo("A matriz de placares tem casa negativa.")

    gols_mandante = np.arange(matriz.shape[0])[:, None]
    gols_visitante = np.arange(matriz.shape[1])[None, :]

    casa = float(matriz[gols_mandante > gols_visitante].sum())
    empate = float(np.trace(matriz))
    fora = float(matriz[gols_mandante < gols_visitante].sum())

    over = float(matriz[(gols_mandante + gols_visitante) >= 3].sum())
    ambos = float(matriz[1:, 1:].sum())

    # Os complementos saem por subtração, e não somando a outra região: assim
    # `over25 + under25 == 1` vale até o último bit, e um teste de soma não
    # falha por erro de arredondamento.
    return {
        "H": casa,
        "D": empate,
        "A": fora,
        "over25": over,
        "under25": 1.0 - over,
        "ambos_marcam": ambos,
        "ambos_nao_marcam": 1.0 - ambos,
    }


def placar_mais_provavel(matriz: np.ndarray) -> tuple[int, int, float]:
    """O placar de maior probabilidade, e qual é essa probabilidade.

    Retorna:
        ``(gols_mandante, gols_visitante, probabilidade)``.

    ⚠️ Este número é para a conversa, não para a aposta. O placar mais provável
    de um jogo de futebol costuma ter 10% a 13% de chance — ou seja, o mais
    provável é que ele **não** aconteça. Ele aparece no projeto porque é a
    pergunta que todo mundo faz, e porque ver "1x1 com 11%" ensina mais sobre
    incerteza do que qualquer explicação.
    """
    matriz = np.asarray(matriz, dtype=float)
    linha, coluna = np.unravel_index(int(np.argmax(matriz)), matriz.shape)
    return int(linha), int(coluna), float(matriz[linha, coluna])


# ----------------------------------------------------------------------------
# O contrato
# ----------------------------------------------------------------------------
class Modelo(ABC):
    """O que todo modelo do projeto sabe fazer.

    Uma classe filha precisa implementar dois métodos:

    - :meth:`_ajustar` — aprender com uma tabela **já filtrada** por data;
    - :meth:`matriz_de_placares` — devolver a matriz de um jogo.

    Tudo o mais vem de graça: o corte de data, a derivação dos mercados, a
    previsão em lote. Isso é de propósito — cada coisa que a classe base faz é
    uma coisa que nenhum modelo pode fazer errado.
    """

    #: Nome curto que aparece nas tabelas de comparação da Fase 4.
    nome: str = "modelo"

    def __init__(self) -> None:
        self._treinado: bool = False
        #: Data do jogo mais recente que entrou no treino. Serve de
        #: conferência: ela nunca pode alcançar o ``ate_data`` pedido.
        self.ultima_data_de_treino: pd.Timestamp | None = None
        #: O ``ate_data`` pedido no treino, quando houve um. É a "data de hoje"
        #: do ponto de vista do modelo, e é dela que o decaimento temporal do
        #: Dixon-Coles conta para trás.
        self.corte_de_treino: pd.Timestamp | None = None

    # -- treino ------------------------------------------------------------
    def treinar(self, jogos: pd.DataFrame, ate_data=None) -> Modelo:
        """Aprende com os jogos anteriores a ``ate_data``.

        Args:
            jogos: a tabela de jogos (de ``limpeza.carregar``).
            ate_data: corte de data. Só entram jogos **estritamente**
                anteriores. ``None`` usa a tabela inteira.

        Retorna:
            O próprio modelo, para permitir ``modelo.treinar(jogos).prever(j)``.
        """
        conferir_colunas(jogos)
        usados = jogos_ate(jogos, ate_data)
        # Jogo sem placar (partida futura, linha quebrada) não ensina nada.
        usados = usados.dropna(subset=["gols_mandante", "gols_visitante"])
        if usados.empty:
            fim = f" antes de {pd.Timestamp(ate_data).date()}." if ate_data else "."
            raise ErroDeModelo("Nenhum jogo sobrou para treinar" + fim)
        self.corte_de_treino = pd.Timestamp(ate_data) if ate_data is not None else None
        self._ajustar(usados)
        self._treinado = True
        self.ultima_data_de_treino = pd.Timestamp(usados["data"].max())
        return self

    @abstractmethod
    def _ajustar(self, jogos: pd.DataFrame) -> None:
        """Aprende com a tabela já filtrada. Chamado só por :meth:`treinar`."""

    # -- previsão ----------------------------------------------------------
    @abstractmethod
    def matriz_de_placares(self, jogo: Jogo) -> np.ndarray:
        """A matriz de probabilidade de cada placar, já normalizada."""

    def prever(self, jogo: Jogo | Mapping) -> dict[str, float]:
        """As probabilidades de mercado de um jogo.

        Args:
            jogo: um :class:`Jogo` ou um mapeamento com ``liga``, ``mandante``
                e ``visitante``.

        Retorna:
            Dicionário com as chaves de :data:`CHAVES_PREVISAO`.
        """
        return mercados_da_matriz(self._matriz_do_pedido(jogo))

    def prever_muitos(self, jogos: pd.DataFrame) -> pd.DataFrame:
        """Previsão de uma tabela inteira de jogos, uma linha por jogo.

        É a forma que a avaliação da Fase 4 usa: o índice devolvido é o mesmo
        da entrada, para dar para colar as previsões ao lado dos resultados
        observados sem risco de desalinhar as linhas.
        """
        self._exigir_treinado()
        previsoes = [self.prever(Jogo.de_mapa(linha)) for _, linha in jogos.iterrows()]
        return pd.DataFrame(previsoes, index=jogos.index, columns=list(CHAVES_PREVISAO))

    def placar_mais_provavel(self, jogo: Jogo | Mapping) -> tuple[int, int, float]:
        """O placar mais provável do jogo. Ver :func:`placar_mais_provavel`."""
        return placar_mais_provavel(self._matriz_do_pedido(jogo))

    # -- apoio -------------------------------------------------------------
    def _matriz_do_pedido(self, jogo: Jogo | Mapping) -> np.ndarray:
        """Confere que há treino e devolve a matriz do jogo pedido."""
        self._exigir_treinado()
        if not isinstance(jogo, Jogo):
            jogo = Jogo.de_mapa(jogo)
        return self.matriz_de_placares(jogo)

    def _exigir_treinado(self) -> None:
        if not self._treinado:
            raise ErroDeModelo(
                f"O modelo {self.nome!r} ainda não foi treinado. "
                "Chame `treinar(jogos, ate_data)` antes de prever."
            )
