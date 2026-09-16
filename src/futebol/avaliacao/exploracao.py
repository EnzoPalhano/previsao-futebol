"""As perguntas da Fase 2: como é o futebol nos dados, e quão bom é o mercado.

Antes de treinar qualquer modelo, vale saber com o que estamos lidando. Este
módulo responde, com número e por liga:

- **quantos gols saem por jogo** e o quanto isso se parece com uma Poisson
  (:func:`distribuicao_gols`) — é a hipótese em que a Fase 3 inteira se apoia;
- **quanto vale jogar em casa**, por liga **e por temporada**
  (:func:`vantagem_mando`) — a análise mais interessante da fase, pelo motivo
  abaixo;
- **com que frequência saem mais de 2,5 gols** (:func:`frequencia_over25`);
- **quanto a casa cobra**, por liga, mercado e momento (:func:`margem`), e se
  isso mudou ao longo dos anos (:func:`evolucao_margem`).

🔎 **Por que o fator casa por temporada importa tanto.** Em 2020 e 2021, com
estádios vazios, a vantagem de jogar em casa caiu em quase todas as ligas do
mundo. Um modelo que trate o mando como uma constante ao longo de sete
temporadas vai estar errado num pedaço grande do treino — e errado justamente
nas temporadas que ele usa para aprender. Este é o gráfico que justifica o
fator casa variável da Fase 3.

⚠️ Toda função aqui devolve tabelas **quebradas por liga** (regra 13). Uma
média juntando Premier League com quarta divisão da Escócia não descreve
nenhuma das duas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from futebol.odds import mercado

#: Pontos que cada resultado dá ao mandante. Serve para medir mando numa escala
#: que o futebol já usa: pontos por jogo.
_PONTOS = {"H": 3.0, "D": 1.0, "A": 0.0}


def _com_gols(jogos: pd.DataFrame) -> pd.Series:
    return jogos["gols_mandante"] + jogos["gols_visitante"]


# ----------------------------------------------------------------------------
# Gols
# ----------------------------------------------------------------------------
def distribuicao_gols(jogos: pd.DataFrame, maximo: int = 8) -> pd.DataFrame:
    """Quantos jogos tiveram 0, 1, 2… gols, contra o que a Poisson previa.

    A Poisson é a distribuição de "quantas vezes um evento raro acontece num
    intervalo", e é o alicerce dos modelos da Fase 3. Se os gols reais se
    afastarem muito dela, o modelo de Poisson nasce torto — por isso a
    comparação vem antes do modelo, não depois.

    O que costuma aparecer: a Poisson **subestima os placares empatados de
    poucos gols** (0-0 e 1-1 acontecem mais do que ela prevê). É exatamente
    essa falha que o ajuste de Dixon-Coles corrige.

    Retorna:
        Uma linha por quantidade de gols, com a frequência observada, a
        prevista pela Poisson de mesma média, e a diferença.
    """
    total = _com_gols(jogos)
    media = float(total.mean())

    contagem = total.value_counts().reindex(range(maximo + 1), fill_value=0)
    observado = contagem / len(total)
    esperado = pd.Series(stats.poisson.pmf(range(maximo + 1), media), index=contagem.index)

    return pd.DataFrame(
        {
            "gols": contagem.index,
            "jogos": contagem.to_numpy(),
            "observado": observado.to_numpy(),
            "poisson": esperado.to_numpy(),
            "diferenca": (observado - esperado).to_numpy(),
        }
    )


def frequencia_over25(jogos: pd.DataFrame, por: list[str] | None = None) -> pd.DataFrame:
    """Com que frequência o jogo termina com 3 gols ou mais.

    É o mercado de Over/Under 2,5 visto pelo lado do resultado, e varia muito
    entre ligas: campeonatos travados ficam perto de 45%, campeonatos abertos
    passam de 55%.
    """
    por = por or ["liga"]
    tabela = jogos.assign(gols=_com_gols(jogos), over25=_com_gols(jogos) > 2.5)
    return (
        tabela.groupby(por, observed=True)
        .agg(jogos=("over25", "size"), gols_por_jogo=("gols", "mean"), over25=("over25", "mean"))
        .reset_index()
    )


# ----------------------------------------------------------------------------
# Vantagem de jogar em casa
# ----------------------------------------------------------------------------
def vantagem_mando(jogos: pd.DataFrame, por: list[str] | None = None) -> pd.DataFrame:
    """Quanto vale jogar em casa, medido de três formas.

    Três medidas porque elas podem discordar, e a discordância é informação:

    - ``vitorias_casa``: fração de jogos que o mandante venceu;
    - ``pontos_casa``: pontos por jogo do mandante (3 por vitória, 1 por
      empate). É a escala que a tabela do campeonato usa;
    - ``saldo_gols``: gols do mandante menos gols do visitante, por jogo. É a
      medida que entra direto num modelo de Poisson.

    Args:
        por: por onde quebrar. ``["liga"]`` dá o retrato geral;
            ``["liga", "temporada"]`` é o que mostra a queda de 2020-21.
    """
    por = por or ["liga"]
    tabela = jogos.assign(
        vitoria_casa=jogos["resultado"] == "H",
        empate=jogos["resultado"] == "D",
        pontos=jogos["resultado"].map(_PONTOS),
        saldo=jogos["gols_mandante"] - jogos["gols_visitante"],
    )
    return (
        tabela.groupby(por, observed=True)
        .agg(
            jogos=("pontos", "size"),
            vitorias_casa=("vitoria_casa", "mean"),
            empates=("empate", "mean"),
            pontos_casa=("pontos", "mean"),
            saldo_gols=("saldo", "mean"),
        )
        .reset_index()
    )


#: As temporadas jogadas total ou parcialmente sem público.
#: ⚠️ Precisa das **duas** formas: as ligas europeias chamam esse período de
#: ``2019/20`` e ``2020/21``, mas Brasil, EUA, Japão e os outros campeonatos de
#: calendário civil chamam de ``2020`` e ``2021``. Esquecer as segundas faz
#: metade das competições sair da conta sem avisar.
TEMPORADAS_SEM_PUBLICO: tuple[str, ...] = ("2019/20", "2020/21", "2020", "2021")


def queda_do_mando_na_pandemia(
    jogos: pd.DataFrame, temporadas_vazias: tuple[str, ...] = TEMPORADAS_SEM_PUBLICO
) -> pd.DataFrame:
    """Compara o mando das temporadas de portões fechados com as demais.

    Não é um teste estatístico: é a tabela que mostra o tamanho do efeito por
    liga, para a Fase 3 decidir se vale um fator casa que muda no tempo.

    ⚠️ 2019/20 entra na lista porque foi interrompida em março de 2020 e
    terminou sem público — só a parte final dela foi afetada, o que **dilui** o
    efeito medido nessa temporada.

    Liga sem nenhuma temporada de um dos dois lados fica **fora** da tabela, em
    vez de aparecer com a coluna vazia: ela não pode ser comparada, e contá-la
    no denominador de "o mando caiu em X de Y ligas" seria mentira.
    """
    por_temporada = vantagem_mando(jogos, ["liga", "temporada"])
    vazias = por_temporada["temporada"].isin(temporadas_vazias)

    com_publico = (
        por_temporada[~vazias]
        .groupby("liga", observed=True)[["pontos_casa", "saldo_gols", "vitorias_casa"]]
        .mean()
    )
    sem_publico = (
        por_temporada[vazias]
        .groupby("liga", observed=True)[["pontos_casa", "saldo_gols", "vitorias_casa"]]
        .mean()
    )

    comparacao = com_publico.join(sem_publico, lsuffix="_publico", rsuffix="_vazio")
    for medida in ("pontos_casa", "saldo_gols", "vitorias_casa"):
        comparacao[f"queda_{medida}"] = (
            comparacao[f"{medida}_publico"] - comparacao[f"{medida}_vazio"]
        )
    return comparacao.dropna().reset_index()


# ----------------------------------------------------------------------------
# Margem da casa
# ----------------------------------------------------------------------------
def margem(
    jogos: pd.DataFrame,
    mercado_: str = "1x2",
    momento: str = "fech",
    por: list[str] | None = None,
) -> pd.DataFrame:
    """A margem média da casa, por liga.

    O número é o *overround*: a soma das probabilidades implícitas menos 1.
    É a mesma definição da seção 4.3 da especificação, para as tabelas serem
    comparáveis (Premier League ≈ 4,2% no 1X2 de fechamento).

    Retorna:
        Uma linha por grupo, com ``jogos`` (quantos tinham a odd completa),
        ``margem_media``, ``margem_mediana`` e ``cobertura`` (a fração de jogos
        daquela liga em que a odd existia).
    """
    por = por or ["liga"]
    colunas = list(mercado.COLUNAS[(mercado_, momento)])

    over = np.full(len(jogos), np.nan)
    completas = jogos[colunas].notna().all(axis=1).to_numpy()
    if completas.any():
        over[completas] = mercado.overround(jogos.loc[completas, colunas].to_numpy(float))

    tabela = jogos.assign(margem=over, tem_odd=completas)
    return (
        tabela.groupby(por, observed=True)
        .agg(
            jogos=("margem", "count"),
            cobertura=("tem_odd", "mean"),
            margem_media=("margem", "mean"),
            margem_mediana=("margem", "median"),
        )
        .reset_index()
    )


def ranking_de_margem(jogos: pd.DataFrame, momento: str = "fech") -> pd.DataFrame:
    """A tabela da seção 4.3, recalculada com **todas** as temporadas.

    A especificação mediu o Grupo 1 só em 2024/25. Aqui entram as sete
    temporadas, então os números mudam um pouco — e é esta versão que vale.
    """
    tabela = margem(jogos, "1x2", momento, ["grupo", "liga"])
    return tabela.sort_values("margem_media").reset_index(drop=True)


def evolucao_margem(jogos: pd.DataFrame, mercado_: str = "1x2", momento: str = "fech"):
    """A margem de cada liga, temporada a temporada. O mercado ficou mais duro?

    Retorna:
        Tabela com uma linha por liga e temporada, mais as colunas
        ``primeira``, ``ultima`` e ``variacao`` (última − primeira) quando a
        liga tem pelo menos duas temporadas medidas.
    """
    por_temporada = margem(jogos, mercado_, momento, ["liga", "temporada"])
    por_temporada = por_temporada.sort_values(["liga", "temporada"])

    resumo = (
        por_temporada.groupby("liga", observed=True)["margem_media"]
        .agg(primeira="first", ultima="last", temporadas="size")
        .reset_index()
    )
    resumo["variacao"] = resumo["ultima"] - resumo["primeira"]
    return por_temporada, resumo


def pre_contra_fechamento(jogos: pd.DataFrame, mercado_: str = "1x2") -> pd.DataFrame:
    """A margem pré-jogo comparada com a de fechamento, liga a liga.

    O mercado costuma **apertar** a margem até o apito: mais dinheiro entrou,
    mais informação chegou. Onde isso não acontece, ou acontece ao contrário,
    vale desconfiar do dado.

    ⚠️ Nas temporadas até 2018/19 (formato B) a odd de fechamento é da
    Pinnacle, não a média do mercado — comparar as duas ali mistura duas
    coisas. Por isso a tabela sai também quebrada por formato.
    """
    pre = margem(jogos, mercado_, "pre", ["liga", "formato"]).rename(
        columns={"margem_media": "margem_pre", "cobertura": "cobertura_pre"}
    )
    fech = margem(jogos, mercado_, "fech", ["liga", "formato"]).rename(
        columns={"margem_media": "margem_fech", "cobertura": "cobertura_fech"}
    )
    junto = pre[["liga", "formato", "jogos", "cobertura_pre", "margem_pre"]].merge(
        fech[["liga", "formato", "cobertura_fech", "margem_fech"]],
        on=["liga", "formato"],
        how="outer",
    )
    junto["aperto"] = junto["margem_pre"] - junto["margem_fech"]
    return junto
