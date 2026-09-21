"""Página "Desempenho": as tabelas das Fases 4 e 5, medidas na hora.

Os números não são copiados dos relatórios: a página lê o **mesmo cache de
previsões** que os relatórios leram e refaz as contas. Assim não existe a
possibilidade de a tela e o relatório discordarem — que é o tipo de divergência
que aparece meses depois, quando ninguém lembra qual dos dois está velho.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from futebol import relatorio
from futebol.app import avisos, dados
from futebol.app.paginas import comum
from futebol.avaliacao import metricas, validacao

#: Nome do mercado nas tabelas, o mesmo das Fases 4 e 5.
NOME_MERCADO = "mercado (fechamento)"


@st.cache_data(ttl=dados.VALIDADE)
def medir_todos() -> pd.DataFrame:
    """A log loss de cada candidato medido, **nos mesmos jogos**.

    ⚠️ A interseção não é detalhe: um candidato que tenha pulado rodadas por
    histórico curto apareceria com vantagem ou desvantagem que não é dele. É a
    mesma função que a Fase 4 usou para escolher o modelo do projeto.
    """
    cfg = dados.config()
    jogos = dados.carregar()
    conjuntos = {nome: dados.previsoes(nome) for nome in dados.modelos_medidos(cfg)}
    if not conjuntos:
        return pd.DataFrame()

    alguma = next(iter(conjuntos.values()))
    janela = (alguma["data"].min(), alguma["data"].max())
    na_janela = jogos.loc[
        (jogos["data"] >= janela[0]) & (jogos["data"] <= janela[1])
    ]
    conjuntos[NOME_MERCADO] = validacao.previsoes_do_mercado(na_janela)

    medidas, _ = validacao.medir_nos_mesmos_jogos(conjuntos)
    return pd.DataFrame([m.como_linha() for m in medidas]).sort_values("log_loss")


def mostrar() -> None:
    st.title("Desempenho dos modelos")
    st.markdown(
        "Cada modelo foi medido do jeito que vale: **walk-forward rodada a "
        "rodada**, reajustando o modelo antes de cada data em que cada "
        "competição jogou. Nenhuma previsão viu o próprio jogo."
    )

    tabela = medir_todos()
    if tabela.empty:
        st.error(
            "Nenhum modelo tem walk-forward gravado. Rode, no terminal:\n\n"
            "    python scripts/validar.py"
        )
        return

    oficial = dados.nome_do_modelo_oficial()
    do_mercado = tabela.loc[tabela["modelo"] == NOME_MERCADO]
    do_oficial = tabela.loc[tabela["modelo"] == oficial]

    st.markdown("### A distância que importa")
    esquerda, meio, direita = st.columns(3)
    with esquerda:
        st.metric("Modelo oficial", relatorio.num(float(do_oficial["log_loss"].iloc[0])))
        st.caption(f"`{oficial}` — log loss, menor é melhor")
    with meio:
        st.metric("Mercado", relatorio.num(float(do_mercado["log_loss"].iloc[0])))
        st.caption("odds de fechamento, sem a comissão")
    with direita:
        distancia = float(do_oficial["log_loss"].iloc[0]) - float(
            do_mercado["log_loss"].iloc[0]
        )
        st.metric("Diferença", f"+{relatorio.num(distancia)}")
        st.caption("quanto o modelo fica atrás")

    comum.mostrar_aviso(avisos.MODELO_PERDE_DO_MERCADO)

    st.markdown("### Todos os candidatos")
    formatada = pd.DataFrame(
        {
            "Quem prevê": tabela["modelo"],
            "Jogos": tabela["jogos"].map(relatorio.inteiro),
            "Log loss": tabela["log_loss"].map(lambda v: relatorio.num(v)),
            "Brier": tabela["brier"].map(lambda v: relatorio.num(v)),
            "Acurácia": tabela["acuracia"].map(lambda v: relatorio.pct(v)),
            "Calibração (ECE)": tabela["ece"].map(lambda v: relatorio.num(v)),
        }
    )
    st.dataframe(formatada, hide_index=True, width="stretch")
    st.caption(
        f"Todos medidos nas **mesmas {relatorio.inteiro(tabela['jogos'].iloc[0])} "
        "partidas** — a interseção das previsões de todos. Comparar log loss de "
        "conjuntos diferentes não significa nada."
    )

    st.markdown("### Como ler a log loss")
    st.markdown(
        """
| Referência | Valor |
|---|---|
| Chutar "33% para cada" | 1,0986 |
| O histórico da liga, sem olhar quem joga | ~1,074 |
| O modelo do projeto | ~1,019 |
| As odds de fechamento | ~0,997 |

A log loss pune **erro confiante** de forma brutal: dizer 95% e errar custa
muito mais que dizer 40% e errar. É por isso que ela — e não a taxa de acerto —
é o critério de escolha de modelo do projeto. Um modelo que nunca aponta empate
pode ter acurácia alta e ser inútil para apostar.
"""
    )

    st.markdown("### Por competição")
    st.caption(
        "Onde o modelo chega mais perto do mercado. Barra curta é competição em "
        "que a diferença é pequena — e só onde a diferença é pequena poderia "
        "existir alguma vantagem."
    )
    por_liga = _por_liga(oficial)
    if por_liga.empty:
        st.info("Sem ligas com jogos suficientes para a tabela.", icon="ℹ️")
    else:
        st.bar_chart(
            por_liga.set_index("liga")["distancia"],
            x_label="",
            y_label="log loss do modelo − log loss do mercado",
            horizontal=True,
        )

    st.markdown("### O que a calibração mostra")
    st.caption(
        "Dos jogos em que o modelo disse 60%, aconteceu perto de 60%? A diagonal "
        "seria a calibração perfeita."
    )
    st.line_chart(
        _calibracao(oficial).set_index("previsto"),
        x_label="probabilidade que o modelo deu",
        y_label="frequência com que aconteceu",
    )

    comum.rodape()


@st.cache_data(ttl=dados.VALIDADE)
def _por_liga(nome: str) -> pd.DataFrame:
    """A distância para o mercado, competição a competição."""
    jogos = dados.carregar()
    do_modelo = dados.previsoes(nome)
    na_janela = jogos.loc[
        (jogos["data"] >= do_modelo["data"].min())
        & (jogos["data"] <= do_modelo["data"].max())
    ]
    conjuntos = {
        nome: do_modelo,
        NOME_MERCADO: validacao.previsoes_do_mercado(na_janela),
    }
    _, alinhados = validacao.medir_nos_mesmos_jogos(conjuntos)
    tabela = validacao.por_liga(alinhados)
    if tabela.empty:
        return tabela
    return tabela.assign(distancia=tabela[nome] - tabela[NOME_MERCADO]).sort_values(
        "distancia"
    )


@st.cache_data(ttl=dados.VALIDADE)
def _calibracao(nome: str) -> pd.DataFrame:
    """A curva de calibração do modelo, com a diagonal perfeita ao lado."""
    previsoes = dados.previsoes(nome)
    probabilidades = previsoes[list(validacao.CHAVES_1X2)].to_numpy(dtype=float)
    observado = previsoes["observado"].to_numpy(dtype=int)
    tabela = pd.DataFrame(metricas.tabela_calibracao(probabilidades, observado))
    return pd.DataFrame(
        {
            "previsto": tabela["previsto"],
            "aconteceu": tabela["observado"],
            "calibração perfeita": tabela["previsto"],
        }
    )
