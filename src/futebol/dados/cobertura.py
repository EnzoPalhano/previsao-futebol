"""Quantos jogos existem, e em quantos deles existe odd.

A tabela de jogos parece completa quando a gente olha o total. O buraco
aparece por liga, por temporada e por mercado: a Premier League de 2024/25 tem
odd de Over/Under em todo jogo, mas a Segunda Divisão grega de 2019/20 pode não
ter. Sem esta contagem, um backtest "de 53.800 jogos" vira, na prática, um
backtest de 30.000 sem ninguém notar.

Dois avisos que este módulo existe para deixar visíveis:

- ⚠️ **Jogo sem odd não é jogo sorteado.** Falta odd em time pequeno, em
  divisão menor, em jogo adiado e remarcado. Tirar esses jogos do backtest é
  uma escolha, não uma limpeza neutra: o que sobra é mais fácil de prever do
  que o conjunto real. A Fase 6 tem que declarar o que faz com eles.
- ⚠️ **Sem odd pré-jogo não existe aposta simulável** (regra 12). É por isso
  que as 16 competições do Grupo 2 entram no treino e na calibração, mas nunca
  no backtest de apostas nem no CLV.

Por isso toda tabela daqui sai quebrada por liga e temporada, e sempre com a
coluna ``grupo`` junto (regra 13).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from futebol.relatorio import pct as _pct
from futebol.relatorio import tabela_markdown as _tabela_markdown

#: Os quatro mercados que o projeto mede, e as colunas que cada um exige.
#: Um jogo só "tem" o mercado se **todas** as colunas dele estiverem
#: preenchidas: odd de empate faltando torna o 1X2 inutilizável, mesmo com as
#: outras duas lá.
MERCADOS: dict[str, tuple[str, ...]] = {
    "1x2_pre": ("odd_pre_H", "odd_pre_D", "odd_pre_A"),
    "ou25_pre": ("odd_pre_over25", "odd_pre_under25"),
    "1x2_fech": ("odd_fech_H", "odd_fech_D", "odd_fech_A"),
    "ou25_fech": ("odd_fech_over25", "odd_fech_under25"),
}

#: Como cada mercado se lê num relatório.
NOMES_MERCADOS: dict[str, str] = {
    "1x2_pre": "1X2 pré-jogo",
    "ou25_pre": "Over/Under 2,5 pré-jogo",
    "1x2_fech": "1X2 fechamento",
    "ou25_fech": "Over/Under 2,5 fechamento",
}

#: O mercado que decide se um jogo pode virar aposta simulada (regras 8 e 12).
MERCADO_DE_APOSTA = "1x2_pre"


def tem_mercado(jogos: pd.DataFrame, mercado: str) -> pd.Series:
    """``True`` para cada jogo em que o mercado está completo."""
    colunas = list(MERCADOS[mercado])
    return jogos[colunas].notna().all(axis=1)


def marcar_mercados(jogos: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta uma coluna booleana por mercado (``tem_1x2_pre``, ...)."""
    marcado = jogos.copy()
    for mercado in MERCADOS:
        marcado[f"tem_{mercado}"] = tem_mercado(jogos, mercado)
    return marcado


def por(jogos: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    """Cobertura agregada pelas chaves pedidas.

    Args:
        jogos: a tabela vinda de :mod:`futebol.dados.limpeza`.
        chaves: por onde agrupar — normalmente ``["liga", "temporada"]``.

    Retorna:
        Uma linha por grupo, com ``jogos``, a data do primeiro e do último
        jogo, e uma coluna ``falta_<mercado>`` com a **fração** de jogos sem
        aquele mercado (0,0 = tem tudo; 1,0 = não tem nada).
    """
    marcado = marcar_mercados(jogos)
    agregacoes: dict[str, tuple[str, str]] = {
        "jogos": ("data", "size"),
        "primeiro": ("data", "min"),
        "ultimo": ("data", "max"),
    }
    tabela = marcado.groupby(chaves, observed=True).agg(**agregacoes)

    for mercado in MERCADOS:
        presentes = marcado.groupby(chaves, observed=True)[f"tem_{mercado}"].mean()
        tabela[f"falta_{mercado}"] = 1.0 - presentes

    return tabela.reset_index()


@dataclass(frozen=True)
class ViesDeSelecao:
    """O retrato dos jogos que ficariam de fora de um backtest.

    Atributos:
        jogos_sem_odd: quantos jogos não têm 1X2 pré-jogo.
        fracao: quanto isso representa do total elegível.
        por_liga: quantos por liga e temporada, para ver onde o buraco se
            concentra.
        times_mais_afetados: os times que mais aparecem nos jogos sem odd.
        media_gols_com: média de gols nos jogos **com** odd.
        media_gols_sem: média de gols nos jogos **sem** odd.
    """

    jogos_sem_odd: int
    fracao: float
    por_liga: pd.DataFrame
    times_mais_afetados: pd.Series
    media_gols_com: float
    media_gols_sem: float

    @property
    def parece_aleatorio(self) -> bool:
        """Heurística grosseira: se o buraco se concentra, não é sorteio.

        Não é teste estatístico — é um alarme. Diferença de 0,15 gol por jogo
        entre quem tem e quem não tem odd já é sinal de que os jogos sem odd
        são de outro tipo, e não uma amostra aleatória do resto.
        """
        return abs(self.media_gols_com - self.media_gols_sem) < 0.15


def vies_de_selecao(jogos: pd.DataFrame, *, mercado: str = MERCADO_DE_APOSTA) -> ViesDeSelecao:
    """Descreve quem são os jogos que não têm odd naquele mercado.

    Só faz sentido nas ligas que **deveriam** ter a odd: rodar isso incluindo o
    Grupo 2, que nunca tem odd pré-jogo, responderia sempre "faltam 100%".
    Por isso a função já filtra pelo grupo que tem o mercado por natureza.
    """
    elegiveis = jogos[jogos["grupo"] == "grupo1"] if mercado.endswith("_pre") else jogos
    tem = tem_mercado(elegiveis, mercado)
    sem_odd = elegiveis[~tem]
    com_odd = elegiveis[tem]

    gols = elegiveis["gols_mandante"] + elegiveis["gols_visitante"]
    times = pd.concat([sem_odd["mandante"], sem_odd["visitante"]])

    return ViesDeSelecao(
        jogos_sem_odd=len(sem_odd),
        fracao=len(sem_odd) / len(elegiveis) if len(elegiveis) else 0.0,
        por_liga=(
            sem_odd.groupby(["liga", "temporada"], observed=True)
            .size()
            .reset_index(name="jogos_sem_odd")
            .sort_values("jogos_sem_odd", ascending=False)
        ),
        times_mais_afetados=times.value_counts().head(10),
        media_gols_com=float(gols[tem].mean()) if len(com_odd) else float("nan"),
        media_gols_sem=float(gols[~tem].mean()) if len(sem_odd) else float("nan"),
    )


# ----------------------------------------------------------------------------
# Relatório em Markdown
# ----------------------------------------------------------------------------
def _secao_por_liga(jogos: pd.DataFrame) -> str:
    tabela = por(jogos, ["grupo", "liga"])
    linhas = [
        [
            str(linha["liga"]),
            "1" if linha["grupo"] == "grupo1" else "2",
            f"{int(linha['jogos']):,}".replace(",", "."),
            f"{linha['primeiro'].date()} a {linha['ultimo'].date()}",
            *[_pct(linha[f"falta_{m}"]) for m in MERCADOS],
        ]
        for _, linha in tabela.iterrows()
    ]
    cabecalho = [
        "Liga",
        "Grupo",
        "Jogos",
        "Período",
        *[f"Falta {NOMES_MERCADOS[m]}" for m in MERCADOS],
    ]
    return _tabela_markdown(linhas, cabecalho)


def _secao_por_temporada(jogos: pd.DataFrame) -> str:
    tabela = por(jogos, ["liga", "temporada"]).sort_values(["liga", "temporada"])
    linhas = [
        [
            str(linha["liga"]),
            str(linha["temporada"]),
            f"{int(linha['jogos']):,}".replace(",", "."),
            *[_pct(linha[f"falta_{m}"]) for m in MERCADOS],
        ]
        for _, linha in tabela.iterrows()
    ]
    cabecalho = [
        "Liga",
        "Temporada",
        "Jogos",
        *[f"Falta {NOMES_MERCADOS[m]}" for m in MERCADOS],
    ]
    return _tabela_markdown(linhas, cabecalho)


def _secao_vies(vies: ViesDeSelecao) -> str:
    if vies.jogos_sem_odd == 0:
        return (
            "Nenhum jogo do Grupo 1 está sem odd 1X2 pré-jogo. Não há, aqui, "
            "decisão a tomar sobre jogos descartados — mas a conferência continua "
            "obrigatória a cada ampliação de camada, porque as divisões menores "
            "são exatamente onde a odd costuma faltar."
        )

    partes = [
        f"**{vies.jogos_sem_odd} jogo(s)** do Grupo 1 ({_pct(vies.fracao)}) não têm "
        "odd 1X2 pré-jogo e, portanto, não podem virar aposta simulada.",
        "",
        f"- Média de gols **com** odd: {vies.media_gols_com:.2f}",
        f"- Média de gols **sem** odd: {vies.media_gols_sem:.2f}",
        "",
    ]
    if vies.parece_aleatorio:
        partes.append(
            "A diferença de gols entre os dois conjuntos é pequena, mas isso **não** "
            "prova que a falta é aleatória: gols são só uma dimensão."
        )
    else:
        partes.append(
            "⚠️ Os jogos sem odd têm média de gols claramente diferente dos demais. "
            "Descartá-los muda a amostra do backtest, e a Fase 6 precisa declarar "
            "explicitamente o que faz com eles."
        )

    if not vies.por_liga.empty:
        partes += ["", "Onde a falta se concentra:", ""]
        linhas = [
            [str(linha["liga"]), str(linha["temporada"]), str(int(linha["jogos_sem_odd"]))]
            for _, linha in vies.por_liga.head(15).iterrows()
        ]
        partes.append(_tabela_markdown(linhas, ["Liga", "Temporada", "Jogos sem odd"]))

    if not vies.times_mais_afetados.empty:
        partes += ["", "Times que mais aparecem nesses jogos:", ""]
        linhas = [[str(time), str(int(n))] for time, n in vies.times_mais_afetados.items()]
        partes.append(_tabela_markdown(linhas, ["Time", "Jogos sem odd"]))

    return "\n".join(partes)


def relatorio_markdown(jogos: pd.DataFrame, *, camada: str, gerado_em: str) -> str:
    """Monta o relatório de cobertura da Fase 1d inteiro, em Markdown."""
    grupo1 = sorted(jogos.loc[jogos["grupo"] == "grupo1", "liga"].unique())
    grupo2 = sorted(jogos.loc[jogos["grupo"] == "grupo2", "liga"].unique())
    total = len(jogos)

    return "\n".join(
        [
            "# Relatório de cobertura de dados — Fase 1",
            "",
            f"- Camada de ligas: **{camada}**",
            f"- Jogos na tabela: **{total:,}**".replace(",", "."),
            f"- Grupo 1 (backtest + CLV): **{', '.join(grupo1) or 'nenhuma'}**",
            f"- Grupo 2 (treino e calibração apenas): **{', '.join(grupo2) or 'nenhuma'}**",
            f"- Gerado em: {gerado_em}",
            "",
            "> Regra 13: toda tabela abaixo vale **apenas** para as ligas listadas acima.",
            "> Regra 12: as ligas do Grupo 2 só têm odd de fechamento — elas servem para",
            "> treino e calibração, nunca para backtest de apostas nem para CLV.",
            "",
            "## Cobertura por liga",
            "",
            _secao_por_liga(jogos),
            "",
            "## Cobertura por liga e temporada",
            "",
            _secao_por_temporada(jogos),
            "",
            "## Viés de seleção: os jogos sem odd",
            "",
            _secao_vies(vies_de_selecao(jogos)),
            "",
        ]
    )
