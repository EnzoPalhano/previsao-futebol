"""As features do jogo: tudo o que se sabia sobre ele **antes** de ele começar.

Um modelo de gols como o Dixon-Coles enxerga uma coisa só: quantos gols cada
time fez e tomou, com os jogos velhos pesando menos. É muito, e é pouco. Ele não
sabe que o mandante jogou anteontem e o visitante descansou dez dias, não sabe
que um deles vem de cinco vitórias, não sabe que a temporada é a de estádio
vazio. Este módulo transforma cada uma dessas coisas em **número por jogo**, para
o LightGBM da Fase 5 ter o que o modelo de gols não tem.

**O que é uma feature causal.** Toda coluna daqui responde à pergunta "o que eu
sabia na manhã do jogo?". Nenhuma pode olhar o próprio jogo nem qualquer outro
do mesmo dia — é a regra 6, e aqui ela é mais escorregadia que nos modelos,
porque uma média móvel mal escrita inclui a própria linha sem ninguém notar. A
diferença aparece como um modelo excelente no relatório e perdedor na vida real.

As três travas, todas conferidas por teste:

1. **``shift(1)`` antes de toda janela móvel.** A média dos "últimos 5 jogos" de
   um time é calculada sobre os 5 jogos **anteriores** ao atual, nunca sobre uma
   janela que o inclua;
2. **um jogo por time por dia.** O ``shift(1)`` ordena por data, então dois jogos
   do mesmo time no mesmo dia fariam o primeiro entrar na feature do segundo. Na
   tabela de hoje isso não acontece nenhuma vez, e
   :func:`conferir_um_jogo_por_time_por_dia` levanta erro se um dia acontecer —
   parar é melhor que produzir número otimista em silêncio;
3. **a feature do Dixon-Coles vem de walk-forward**, nunca de um ajuste único
   sobre a tabela inteira. Ver :func:`probabilidades_do_dixon_coles`.

**Por que a forma recente atravessa temporada e divisão.** Os últimos 5 jogos de
``ENG:Luton`` são os últimos 5 jogos dele, mesmo que dois tenham sido na
segunda divisão em maio e três na primeira em agosto. Zerar a forma na virada da
temporada esconderia justamente a informação mais fresca que existe sobre um
time promovido. É a mesma escolha de chave do :mod:`futebol.modelos.elo`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from futebol.config import Config
from futebol.modelos import elo as modulo_elo

#: Tamanhos das janelas de forma recente, em jogos. Pedidos pela especificação.
JANELAS: tuple[int, ...] = (5, 10)

#: Começo e fim aproximados do período de portões fechados pela pandemia.
#:
#: ⚠️ **É uma aproximação, e assumida como tal.** O público voltou em datas
#: diferentes em cada país, e em alguns voltou parcialmente antes. Marcar pela
#: *temporada* seria pior: a 2019/20 europeia teve metade com torcida e metade
#: sem, e o Brasil chama de "2020" um calendário quase inteiro sem público. O
#: intervalo de datas erra menos, e o que se quer da feature é que o modelo
#: possa aprender que o fator casa encolheu nesse período.
ESTADIO_VAZIO_DE = "2020-03-01"
ESTADIO_VAZIO_ATE = "2021-06-30"

#: Colunas de probabilidade que o Dixon-Coles contribui como feature.
COLUNAS_DC: tuple[str, ...] = ("dc_H", "dc_D", "dc_A", "dc_over25")

#: De quantos em quantos dias o Dixon-Coles é reajustado ao gerar a feature.
#:
#: ⚠️ É mais grosso que o walk-forward oficial da Fase 4, que reajusta antes de
#: **cada** rodada. A escolha acompanha o retreino do LightGBM (30 dias) para
#: que a feature tenha a **mesma qualidade no treino e na previsão** — uma
#: feature mais fresca na hora de prever do que na hora de treinar ensinaria o
#: GBM a confiar nela mais do que deve. O viés que isso cria é contra o GBM:
#: ele recebe uma leitura do Dixon-Coles até 30 dias velha.
PASSO_DE_REAJUSTE_DC = 30


class ErroDeFeatures(Exception):
    """Tabela sem as colunas necessárias, ou com um pressuposto violado."""


# ----------------------------------------------------------------------------
# Travas
# ----------------------------------------------------------------------------
def conferir_um_jogo_por_time_por_dia(jogos: pd.DataFrame) -> None:
    """Levanta erro se algum time tiver dois jogos na mesma data.

    ⚠️ Esta é a hipótese em que todo ``shift(1)`` deste módulo se apoia. Se ela
    falhar, o primeiro jogo do dia entra na feature do segundo e o vazamento não
    dá sintoma nenhum: só um modelo bom demais. Na tabela de hoje não há um caso
    sequer, em 89.455 jogos.
    """
    lados = [
        jogos[["data", lado]].rename(columns={lado: "time"})
        for lado in ("mandante", "visitante")
    ]
    contagem = pd.concat(lados).groupby(["time", "data"]).size()
    repetidos = contagem[contagem > 1]
    if not repetidos.empty:
        exemplo = repetidos.index[0]
        raise ErroDeFeatures(
            f"{len(repetidos)} par(es) (time, data) com mais de um jogo — por "
            f"exemplo {exemplo[0]} em {pd.Timestamp(exemplo[1]).date()}. Toda "
            "janela móvel deste módulo supõe um jogo por time por dia; com dois, "
            "o primeiro entraria na feature do segundo (regra 6)."
        )


def conferir_sem_homonimos(jogos: pd.DataFrame) -> None:
    """Levanta erro se um clube aparecer em duas divisões na mesma temporada.

    Promoção e rebaixamento entre temporadas são normais e desejados: a chave
    ``PAIS:nome`` faz o clube levar o Elo e a forma junto. Duas divisões **na
    mesma temporada**, não: seriam dois clubes homônimos fundidos num histórico
    só, e a seção 4.1 da especificação avisa que isso corrompe o Elo e as médias
    móveis em silêncio.
    """
    problemas = modulo_elo.clubes_em_duas_divisoes_na_mesma_temporada(jogos)
    if not problemas.empty:
        linha = problemas.iloc[0]
        raise ErroDeFeatures(
            f"{len(problemas)} clube(s) aparecem em duas competições na mesma "
            f"temporada — por exemplo {linha['time']} em {linha['temporada']}. "
            "Isso não é promoção: são homônimos, e juntá-los corromperia o Elo "
            "e as médias móveis (regra 14)."
        )


# ----------------------------------------------------------------------------
# A tabela longa: uma linha por time por jogo
# ----------------------------------------------------------------------------
def _formato_longo(jogos: pd.DataFrame) -> pd.DataFrame:
    """Quebra cada jogo em duas linhas, uma por time.

    É o formato em que "os últimos 5 jogos deste time" vira um ``groupby``, em
    vez de um laço. A coluna ``jogo`` guarda o índice original para a volta.
    """
    def lado(time: str, adversario: str, feitos: str, sofridos: str, mando: str):
        parte = jogos[["data", time, adversario, feitos, sofridos]].copy()
        parte.columns = ["data", "time", "adversario", "gols_feitos", "gols_sofridos"]
        parte["mando"] = mando
        parte["jogo"] = jogos.index
        return parte

    longo = pd.concat(
        [
            lado("mandante", "visitante", "gols_mandante", "gols_visitante", "casa"),
            lado("visitante", "mandante", "gols_visitante", "gols_mandante", "fora"),
        ],
        ignore_index=True,
    )
    saldo = longo["gols_feitos"] - longo["gols_sofridos"]
    longo["pontos"] = np.where(saldo > 0, 3.0, np.where(saldo == 0, 1.0, 0.0))
    # Jogo sem placar não pontua nem entra nas médias: fica ausente, e a janela
    # móvel o ignora em vez de contá-lo como zero a zero.
    sem_placar = longo["gols_feitos"].isna() | longo["gols_sofridos"].isna()
    longo.loc[sem_placar, ["gols_feitos", "gols_sofridos", "pontos"]] = np.nan
    return longo.sort_values(["time", "data"], kind="stable")


def _forma_recente(longo: pd.DataFrame) -> pd.DataFrame:
    """Médias móveis, pontos e descanso — todos com ``shift(1)``.

    As médias de gols são calculadas **dentro do mando**: para o mandante valem
    os jogos anteriores dele em casa; para o visitante, os dele fora. Jogar em
    casa e jogar fora são esportes com números diferentes, e misturá-los apagaria
    metade do sinal.

    Os pontos e o descanso, ao contrário, valem para **qualquer mando**: forma e
    cansaço não sabem onde a bola rolou.
    """
    saida = pd.DataFrame(index=longo.index)
    por_time = longo.groupby("time", sort=False)

    # Descanso: quantos dias desde o jogo anterior deste time, em qualquer mando.
    anterior = por_time["data"].shift(1)
    saida["descanso"] = (longo["data"] - anterior).dt.days

    # Pontos e histórico, em qualquer mando.
    pontos_passados = por_time["pontos"].shift(1)
    por_time_deslocado = pontos_passados.groupby(longo["time"], sort=False)
    saida["pontos5"] = _alinhado(por_time_deslocado.rolling(5, min_periods=1).sum())
    saida["historico"] = _alinhado(
        por_time_deslocado.rolling(len(longo), min_periods=1).count()
    )

    # Médias de gols, dentro do mando.
    por_mando = longo.groupby(["time", "mando"], sort=False)
    for coluna in ("gols_feitos", "gols_sofridos"):
        passados = por_mando[coluna].shift(1)
        agrupado = passados.groupby([longo["time"], longo["mando"]], sort=False)
        for janela in JANELAS:
            saida[f"{coluna}{janela}"] = _alinhado(
                agrupado.rolling(janela, min_periods=1).mean()
            )
    return saida


def _alinhado(resultado: pd.Series) -> pd.Series:
    """Tira as chaves do ``groupby`` do índice, deixando só o índice original.

    ⚠️ ``groupby(...).rolling(...)`` devolve um índice de dois (ou três) níveis:
    a chave do grupo e o índice da linha. Aproveitar esse resultado por
    **posição** funciona enquanto a tabela estiver ordenada pelo grupo e quebra
    em silêncio no dia em que não estiver — cada time receberia a forma recente
    de outro. Alinhar pelo índice não tem esse dia.
    """
    return resultado.droplevel(list(range(resultado.index.nlevels - 1)))


def _alargar(longo: pd.DataFrame, calculadas: pd.DataFrame, indice) -> pd.DataFrame:
    """Devolve as features do formato longo para uma linha por jogo."""
    junto = pd.concat([longo[["jogo", "mando"]], calculadas], axis=1)
    partes = []
    for mando, sufixo in (("casa", "mandante"), ("fora", "visitante")):
        parte = junto[junto["mando"] == mando].drop(columns="mando")
        parte = parte.set_index("jogo")
        parte.columns = [f"{nome}_{sufixo}" for nome in parte.columns]
        partes.append(parte)
    return pd.concat(partes, axis=1).reindex(indice)


# ----------------------------------------------------------------------------
# A feature do Dixon-Coles
# ----------------------------------------------------------------------------
def marcos_de_reajuste(
    jogos: pd.DataFrame, passo_dias: int = PASSO_DE_REAJUSTE_DC
) -> pd.DatetimeIndex:
    """As datas em que o Dixon-Coles é reajustado ao gerar a feature.

    De ``passo_dias`` em ``passo_dias``, da primeira à última data da tabela. Um
    jogo do dia ``D`` é previsto pelo ajuste do último marco **anterior ou igual**
    a ``D`` — e esse ajuste só viu jogos anteriores ao marco, portanto anteriores
    a ``D``. É daí que vem a garantia da regra 6.
    """
    primeira = pd.Timestamp(jogos["data"].min())
    ultima = pd.Timestamp(jogos["data"].max())
    return pd.date_range(primeira, ultima + pd.Timedelta(days=passo_dias), freq=f"{passo_dias}D")


def probabilidades_do_dixon_coles(
    jogos: pd.DataFrame,
    cfg: Config,
    passo_dias: int = PASSO_DE_REAJUSTE_DC,
    minimo_de_treino: int = 100,
    aviso=None,
) -> pd.DataFrame:
    """A leitura do Dixon-Coles sobre cada jogo, sem olhar o futuro.

    Para cada marco de reajuste e cada competição, o modelo é ajustado com os
    jogos **anteriores ao marco** e usado para prever os jogos daquela liga até o
    marco seguinte.

    Retorna:
        ``DataFrame`` com :data:`COLUNAS_DC`, no índice da entrada. Jogos cuja
        liga ainda não tinha ``minimo_de_treino`` partidas saem como ausentes —
        o LightGBM lida com ausência nativamente, e inventar um valor ali seria
        pior do que admitir que não se sabe.

    ⚠️ Custa alguns minutos: são um ajuste por liga por marco.
    """
    from futebol.modelos.dixon_coles import DixonColes

    saida = pd.DataFrame(
        np.nan, index=jogos.index, columns=list(COLUNAS_DC), dtype=float
    )
    marcos = marcos_de_reajuste(jogos, passo_dias)

    for liga, da_liga in jogos.groupby("liga", sort=True):
        ajustes = 0
        for inicio, fim in zip(marcos, marcos[1:], strict=False):
            alvo = da_liga.loc[(da_liga["data"] >= inicio) & (da_liga["data"] < fim)]
            if alvo.empty:
                continue
            passado = da_liga.loc[da_liga["data"] < inicio]
            if len(passado.dropna(subset=["gols_mandante", "gols_visitante"])) < minimo_de_treino:
                continue
            modelo = DixonColes(cfg=cfg).treinar(da_liga, ate_data=inicio)
            previsoes = modelo.prever_muitos(alvo)
            saida.loc[alvo.index, "dc_H"] = previsoes["H"].to_numpy()
            saida.loc[alvo.index, "dc_D"] = previsoes["D"].to_numpy()
            saida.loc[alvo.index, "dc_A"] = previsoes["A"].to_numpy()
            saida.loc[alvo.index, "dc_over25"] = previsoes["over25"].to_numpy()
            ajustes += 1
        if aviso is not None and ajustes:
            aviso(f"    {liga}: {ajustes} reajustes")
    return saida


# ----------------------------------------------------------------------------
# A montagem
# ----------------------------------------------------------------------------
def construir(
    jogos: pd.DataFrame,
    cfg: Config | None = None,
    probabilidades_dc: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Monta todas as features de cada jogo, no índice da tabela de entrada.

    Args:
        jogos: a tabela de ``limpeza.carregar``, já sem o teste final (regra 7).
        cfg: de onde o Elo lê ``k`` e ``rating_inicial``.
        probabilidades_dc: a saída de :func:`probabilidades_do_dixon_coles`. É
            parâmetro, e não cálculo interno, porque custa minutos e vale a pena
            guardar em cache entre execuções. Sem ela, as colunas do Dixon-Coles
            simplesmente não aparecem.

    Retorna:
        ``DataFrame`` de features, mesmo índice da entrada, só colunas numéricas.
    """
    faltando = [
        c
        for c in ("data", "liga", "temporada", "mandante", "visitante",
                  "gols_mandante", "gols_visitante")
        if c not in jogos.columns
    ]
    if faltando:
        raise ErroDeFeatures(
            f"A tabela não tem as colunas: {', '.join(faltando)}. "
            "Ela deve vir de `futebol.dados.limpeza.carregar`."
        )
    conferir_um_jogo_por_time_por_dia(jogos)
    conferir_sem_homonimos(jogos)

    longo = _formato_longo(jogos)
    features = _alargar(longo, _forma_recente(longo), jogos.index)

    ratings = modulo_elo.Elo(cfg=cfg).ratings_antes(jogos)
    features[list(modulo_elo.COLUNAS_ELO)] = ratings

    features["descanso_diferenca"] = (
        features["descanso_mandante"] - features["descanso_visitante"]
    )
    features["estadio_vazio"] = (
        (jogos["data"] >= pd.Timestamp(ESTADIO_VAZIO_DE))
        & (jogos["data"] <= pd.Timestamp(ESTADIO_VAZIO_ATE))
    ).astype(float)

    if probabilidades_dc is not None:
        features[list(COLUNAS_DC)] = probabilidades_dc.reindex(jogos.index)
    return features


def caminho_do_cache(cfg: Config, jogos: pd.DataFrame) -> Path:
    """Onde as features desta tabela ficam guardadas, fora do Git (regra 4).

    ⚠️ A chave é uma **descrição da tabela**: primeira data, última data e número
    de jogos. Se qualquer uma mudar, o arquivo é outro e as features são
    recalculadas. É deliberadamente conservador — recalcular custa 40 segundos, e
    ler features de uma tabela diferente custaria um relatório inteiro errado,
    do jeito silencioso que a Fase 4 já mostrou ser possível.
    """
    primeira = pd.Timestamp(jogos["data"].min()).date()
    ultima = pd.Timestamp(jogos["data"].max()).date()
    pasta = cfg.raiz / "data" / "processed" / "features"
    return pasta / f"{primeira}_{ultima}_{len(jogos)}.parquet"


def carregar_ou_construir(
    cfg: Config, jogos: pd.DataFrame, forcar: bool = False, aviso=None
) -> pd.DataFrame:
    """As features da tabela, lidas do cache ou calculadas e gravadas.

    A parte cara é a do Dixon-Coles (um ajuste por liga por marco). O resto leva
    segundos.
    """
    caminho = caminho_do_cache(cfg, jogos)
    if caminho.is_file() and not forcar:
        if aviso is not None:
            aviso(f"  features: lidas do cache ({caminho.name})")
        guardadas = pd.read_parquet(caminho)
        if list(guardadas.columns) == nomes_das_features():
            return guardadas.reindex(jogos.index)
        if aviso is not None:
            aviso("  features: o cache tem outras colunas; recalculando")

    if aviso is not None:
        aviso("  features: calculando (a parte do Dixon-Coles leva ~1 min)...")
    probabilidades = probabilidades_do_dixon_coles(jogos, cfg, aviso=aviso)
    features = construir(jogos, cfg=cfg, probabilidades_dc=probabilidades)
    features = features[nomes_das_features()]

    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".parcial")
    try:
        features.to_parquet(temporario)
        temporario.replace(caminho)
    finally:
        temporario.unlink(missing_ok=True)
    return features


def nomes_das_features(com_dixon_coles: bool = True) -> list[str]:
    """A lista de colunas que :func:`construir` produz, na ordem em que sai."""
    nomes = []
    for sufixo in ("mandante", "visitante"):
        nomes += [f"descanso_{sufixo}", f"pontos5_{sufixo}", f"historico_{sufixo}"]
        for coluna in ("gols_feitos", "gols_sofridos"):
            nomes += [f"{coluna}{janela}_{sufixo}" for janela in JANELAS]
    nomes += list(modulo_elo.COLUNAS_ELO)
    nomes += ["descanso_diferenca", "estadio_vazio"]
    if com_dixon_coles:
        nomes += list(COLUNAS_DC)
    return nomes
