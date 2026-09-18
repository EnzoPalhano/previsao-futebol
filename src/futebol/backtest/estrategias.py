"""Quanto apostar: stake fixa, Kelly fracionado, banca fixa e banca composta.

Este módulo responde a pergunta que vem **depois** de "em que apostar". A
escolha das apostas é do :mod:`futebol.backtest.simulador`; aqui só se decide o
tamanho de cada uma e se faz a conta da banca ao longo do tempo.

**Por que isso merece um módulo inteiro.** Porque o tamanho da aposta muda o
resultado do relatório de forma enorme — sem mudar nada sobre o modelo. As
mesmas apostas, nas mesmas odds, com os mesmos acertos, produzem lucros
completamente diferentes conforme a regra de stake. Duas escolhas em especial:

1. **Stake fixa × Kelly.** A stake fixa aposta sempre o mesmo. O Kelly aposta
   mais quando acha que a vantagem é maior — e como a vantagem é calculada com a
   probabilidade **do modelo**, o Kelly amplifica o erro do modelo junto com o
   acerto dele. Um modelo mal calibrado perde mais rápido no Kelly do que na
   stake fixa, e é exatamente por isso que o projeto reporta os dois.
2. **Banca fixa × banca composta** (a especificação chama de "as DUAS variantes",
   e omitir qual foi usada é uma das formas mais comuns de relatório enganoso):

   - **banca fixa**: a stake sai sempre da banca **inicial**. 1% de 1.000 é
     10 reais na primeira aposta e 10 reais na milésima. O lucro final é a soma
     simples dos resultados;
   - **banca composta**: a stake sai da banca **atual**. Ganhando, aposta-se
     mais; perdendo, menos. Compõe como juros — para cima e para baixo.

   ⚠️ A composta **melhora** o número quando a série é vencedora e **suaviza** o
   prejuízo quando ela é perdedora (apostando cada vez menos, nunca se chega a
   zero). Mostrar só a composta num backtest positivo infla o resultado; mostrar
   só a composta num backtest negativo esconde o tamanho do estrago. Por isso as
   duas sempre aparecem lado a lado.

**A aposta é resolvida por bloco de data, não uma a uma.** Todas as apostas de um
sábado são dimensionadas com a banca de sexta à noite e só depois liquidadas.
É o que acontece na vida real — ninguém espera o jogo das 16h terminar para
decidir quanto apostar no das 18h — e tem o efeito colateral de tornar o
resultado **independente da ordem** dos jogos dentro do dia, que é arbitrária na
tabela. É o mesmo cuidado que o Elo e as médias móveis tomam em
:mod:`futebol.features.construtor`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd

#: As duas variantes de banca que todo relatório do projeto precisa mostrar.
TIPOS_DE_BANCA: tuple[str, ...] = ("fixa", "composta")

#: As colunas que uma tabela de apostas precisa ter para virar uma banca.
COLUNAS_DA_APOSTA: tuple[str, ...] = ("data", "prob", "odd", "retorno_unitario")


class Estrategia(ABC):
    """Regra que diz qual fração da banca de referência vai em cada aposta."""

    #: Como a estratégia aparece nas tabelas do relatório.
    nome: str

    #: Uma linha em português, para quem lê o relatório sem ler o código.
    descricao: str

    @abstractmethod
    def fracao(self, prob: np.ndarray, odd: np.ndarray) -> np.ndarray:
        """A fração da banca de referência apostada em cada linha.

        Args:
            prob: probabilidade que **o modelo** dá ao evento.
            odd: odd média pré-jogo em que se aposta (regra 8).

        Retorna:
            Um vetor de frações, entre 0 e 1, do mesmo tamanho das entradas.
        """

    def stake(self, banca: float, prob, odd) -> np.ndarray:
        """Quanto dinheiro vai em cada aposta, dada a banca de referência."""
        return banca * self.fracao(np.asarray(prob, float), np.asarray(odd, float))


class StakeFixa(Estrategia):
    """Sempre a mesma fração da banca, independente do tamanho da vantagem.

    É a estratégia de referência do projeto, e a mais informativa das duas: com
    stake constante e banca fixa, o **ROI** (lucro dividido pelo total apostado)
    é exatamente a média do retorno por aposta. Nenhuma aposta pesa mais que
    outra, então o número não pode ser dominado por dois ou três palpites
    grandes que deram certo.
    """

    def __init__(self, fracao_da_banca: float = 0.01) -> None:
        if not 0 < fracao_da_banca <= 1:
            raise ValueError(
                f"A fração da banca tem de ficar entre 0 e 1; veio {fracao_da_banca}."
            )
        self.fracao_da_banca = float(fracao_da_banca)
        self.nome = "stake fixa"
        self.descricao = f"{fracao_da_banca:.1%} da banca de referência por aposta"

    def fracao(self, prob: np.ndarray, odd: np.ndarray) -> np.ndarray:
        return np.full(len(np.asarray(prob)), self.fracao_da_banca)


class KellyFracionado(Estrategia):
    """Kelly com dois freios: uma fração dele, e um teto por aposta.

    A fórmula de Kelly diz qual fração da banca maximiza o crescimento de longo
    prazo, se as probabilidades estiverem certas::

        f* = (p · odd − 1) / (odd − 1)

    ⚠️ **O "se" da frase acima é tudo.** Kelly é ótimo quando ``p`` é a
    probabilidade verdadeira. Com a probabilidade de um modelo, ``f*`` é uma
    estimativa **com erro**, e o erro entra elevado ao quadrado no risco:
    superestimar a vantagem em 50% mais que dobra a volatilidade. Kelly cheio
    com probabilidade estimada é uma das formas mais rápidas de quebrar.

    Daí as duas travas, as duas exigidas pela especificação:

    - **fração de Kelly** (1/4 no projeto): aposta-se um quarto do que a fórmula
      manda. Isso corta a volatilidade para perto de um quarto e ainda entrega a
      maior parte do crescimento teórico — barato pela margem de erro que compra;
    - **teto por aposta**: nenhuma aposta passa de ``teto`` da banca, por maior
      que a vantagem pareça. Vantagem enorme calculada num azarão de odd 15 quase
      sempre é erro de modelo, não oportunidade.

    Aposta com vantagem negativa recebe fração zero — o Kelly nunca aposta contra
    si mesmo. Na prática o filtro de EV do simulador já removeu essas linhas.
    """

    def __init__(self, fracao: float = 0.25, teto: float = 0.05) -> None:
        if not 0 < fracao <= 1:
            raise ValueError(f"A fração de Kelly fica entre 0 e 1; veio {fracao}.")
        if not 0 < teto <= 1:
            raise ValueError(f"O teto fica entre 0 e 1; veio {teto}.")
        self.fracao_kelly = float(fracao)
        self.teto = float(teto)
        self.nome = "Kelly fracionado"
        self.descricao = (
            f"{fracao:.2g} de Kelly, com teto de {teto:.1%} da banca por aposta"
        )

    def fracao(self, prob: np.ndarray, odd: np.ndarray) -> np.ndarray:
        prob = np.asarray(prob, dtype=float)
        odd = np.asarray(odd, dtype=float)
        ganho = odd - 1.0
        with np.errstate(divide="ignore", invalid="ignore"):
            cheio = (prob * odd - 1.0) / ganho
        cheio = np.nan_to_num(cheio, nan=0.0, posinf=0.0, neginf=0.0)
        return np.clip(self.fracao_kelly * cheio, 0.0, self.teto)


def criar(nome: str, cfg_backtest: dict) -> Estrategia:
    """Monta a estratégia pedida a partir da seção ``backtest`` do ``config.yaml``.

    Args:
        nome: ``"stake_fixa"`` ou ``"kelly_fracionado"``.
        cfg_backtest: o dicionário da seção ``backtest``.
    """
    if nome == "stake_fixa":
        return StakeFixa(float(cfg_backtest.get("stake_fixa_pct", 0.01)))
    if nome == "kelly_fracionado":
        return KellyFracionado(
            fracao=float(cfg_backtest.get("kelly_fracao", 0.25)),
            teto=float(cfg_backtest.get("kelly_teto_pct", 0.05)),
        )
    raise ValueError(
        f"Estratégia {nome!r} não existe. Conhecidas: stake_fixa, kelly_fracionado."
    )


def drawdown_maximo(banca, banca_inicial: float) -> float:
    """A maior queda percentual do topo até o fundo seguinte.

    Responde "qual foi o pior momento desta série?", que o lucro final esconde
    por completo: duas séries podem terminar iguais tendo passado por sustos
    muito diferentes — e quem aposta de verdade desiste no susto, não no fim.

    A conta é a usual: para cada momento, quanto a banca está abaixo do máximo
    que ela já atingiu; o drawdown é o pior desses valores. O topo começa na
    banca inicial, porque perder logo na primeira aposta também é drawdown.

    Retorna:
        Uma fração entre 0 e 1. 0,25 quer dizer "chegou a valer 25% menos do que
        já tinha valido".
    """
    valores = np.concatenate([[float(banca_inicial)], np.asarray(banca, dtype=float)])
    topos = np.maximum.accumulate(valores)
    with np.errstate(divide="ignore", invalid="ignore"):
        quedas = np.where(topos > 0, 1.0 - valores / topos, 1.0)
    return float(np.max(quedas))


@dataclass(frozen=True)
class Evolucao:
    """O que aconteceu com a banca ao longo do backtest.

    Atributos:
        estrategia: o nome da regra de stake usada.
        tipo_banca: ``"fixa"`` ou ``"composta"``.
        banca_inicial: de quanto se partiu.
        curva: uma linha por **data**, com a banca ao fim do dia. É o que o
            gráfico desenha, e o passo é a data justamente porque a ordem dos
            jogos dentro de um dia é arbitrária.
        total_apostado: soma de todas as stakes.
        banca_final: o que sobrou no fim.

            ⚠️ Guardado direto, e não recalculado a partir do lucro. Uma banca
            que cai de 1.000 para 0,00000000001 tem lucro de exatamente
            −1.000,0 em ponto flutuante, e refazer ``inicial + lucro`` devolveria
            **zero** — apagando a diferença entre "sobrou um décimo de bilionésimo
            de real" e "acabou". São coisas diferentes: a primeira ainda tem uma
            curva, a segunda para de apostar.
        drawdown_maximo: a maior queda, em fração, do topo até o fundo seguinte.
        datas_racionadas: em quantos dias a soma das stakes pedidas passou da
            banca disponível e teve de ser reduzida proporcionalmente.
        quebrou: a banca chegou a zero em algum momento, e a simulação parou ali.
    """

    estrategia: str
    tipo_banca: str
    banca_inicial: float
    curva: pd.DataFrame
    total_apostado: float
    banca_final: float
    drawdown_maximo: float
    datas_racionadas: int
    quebrou: bool

    @property
    def lucro(self) -> float:
        return self.banca_final - self.banca_inicial

    @property
    def roi(self) -> float:
        """Lucro dividido pelo **total apostado** — não pela banca.

        ⚠️ É esta a definição de ROI em todo o projeto, e ela não é a única que
        circula por aí. "Lucro sobre a banca" dá um número muito maior com a
        mesma performance (basta apostar mais vezes) e não é comparável entre
        estratégias. Lucro sobre o que passou pela mesa é.
        """
        return self.lucro / self.total_apostado if self.total_apostado else float("nan")


def simular_banca(
    apostas: pd.DataFrame,
    estrategia: Estrategia,
    banca_inicial: float = 1000.0,
    tipo_banca: str = "fixa",
) -> Evolucao:
    """Passeia pelas apostas, dia a dia, e conta o que aconteceu com a banca.

    Args:
        apostas: uma linha por aposta, com as colunas de
            :data:`COLUNAS_DA_APOSTA`. ``retorno_unitario`` é o lucro de apostar
            1 unidade: ``odd − 1`` se ganhou, ``−1`` se perdeu.
        estrategia: a regra de stake.
        banca_inicial: de quanto se parte.
        tipo_banca: ``"fixa"`` (stake sobre a banca inicial) ou ``"composta"``
            (sobre a banca atual).

    Retorna:
        Uma :class:`Evolucao`.

    ⚠️ **O racionamento.** Num sábado de vinte apostas, o Kelly com teto de 5%
    pediria 100% da banca. Ninguém aposta o que não tem, então quando a soma das
    stakes de um dia passa da banca disponível todas elas são reduzidas pelo
    mesmo fator, e o dia é contado em ``datas_racionadas``. Sem essa trava a
    simulação apostaria dinheiro inventado; sem a contagem, a trava agiria em
    silêncio e mudaria o resultado sem aparecer no relatório.
    """
    if tipo_banca not in TIPOS_DE_BANCA:
        raise ValueError(
            f"tipo_banca deve ser 'fixa' ou 'composta'; veio {tipo_banca!r}."
        )
    faltando = [c for c in COLUNAS_DA_APOSTA if c not in apostas.columns]
    if faltando:
        raise ValueError(
            f"A tabela de apostas não tem as colunas: {', '.join(faltando)}."
        )

    banca = float(banca_inicial)
    total_apostado = 0.0
    racionadas = 0
    quebrou = False
    linhas: list[dict[str, object]] = []

    for data, do_dia in apostas.groupby("data", sort=True):
        if banca <= 0:
            quebrou = True
            break

        referencia = banca_inicial if tipo_banca == "fixa" else banca
        stakes = estrategia.stake(
            referencia, do_dia["prob"].to_numpy(float), do_dia["odd"].to_numpy(float)
        )
        pedido = float(stakes.sum())
        if pedido > banca:
            stakes = stakes * (banca / pedido)
            racionadas += 1
            pedido = float(stakes.sum())

        lucro_do_dia = float(
            (stakes * do_dia["retorno_unitario"].to_numpy(float)).sum()
        )
        banca += lucro_do_dia
        total_apostado += pedido
        if banca <= 0:
            banca = 0.0
            quebrou = True

        linhas.append(
            {
                "data": data,
                "apostas": len(do_dia),
                "apostado": pedido,
                "lucro_do_dia": lucro_do_dia,
                "banca": banca,
            }
        )
        if quebrou:
            break

    curva = pd.DataFrame(
        linhas, columns=["data", "apostas", "apostado", "lucro_do_dia", "banca"]
    )
    return Evolucao(
        estrategia=estrategia.nome,
        tipo_banca=tipo_banca,
        banca_inicial=float(banca_inicial),
        curva=curva,
        total_apostado=total_apostado,
        banca_final=banca,
        drawdown_maximo=drawdown_maximo(curva["banca"], banca_inicial),
        datas_racionadas=racionadas,
        quebrou=quebrou,
    )
