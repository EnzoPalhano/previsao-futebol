"""Página "Prever jogo": as probabilidades do modelo para um confronto.

Mostra os três modelos lado a lado de propósito. Um número sozinho ("68% para o
mandante") parece um fato; três números diferentes para a mesma pergunta lembram
quem está lendo que **isto é uma estimativa**, e que estimativas dependem de
quem as faz.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from futebol import relatorio
from futebol.app import avisos, dados
from futebol.app.paginas import comum


def mostrar() -> None:
    st.title("Prever jogo")
    st.markdown(
        "Escolha um confronto e veja o que cada modelo do projeto acha dele. As "
        "probabilidades de **todos** os mercados saem da mesma matriz de "
        "placares — nunca de contas separadas, que poderiam se contradizer."
    )

    comum.mostrar_aviso(avisos.MODELO_PERDE_DO_MERCADO)

    escolha = comum.escolher_jogo("prever")
    if escolha is None:
        return
    liga, mandante, visitante, data = escolha

    jogos = dados.carregar()
    cfg = dados.config()
    da_liga = jogos.loc[jogos["liga"] == liga]
    antes = da_liga.loc[da_liga["data"] < data]
    if antes.empty:
        primeira = pd.Timestamp(da_liga["data"].min()).date()
        st.error(
            f"Não há jogo da {liga} antes de {data.date()}. O primeiro jogo desta "
            f"competição na tabela é de {primeira} — escolha uma data posterior."
        )
        return

    with st.spinner("Treinando os modelos com o que se sabia até essa data..."):
        previsoes = dados.prever(jogos, liga, mandante, visitante, data, cfg)
        matriz = dados.matriz_de_placares(jogos, liga, mandante, visitante, data, cfg)

    st.subheader(f"{mandante} × {visitante}")
    st.caption(
        f"{liga} · treinado com {relatorio.inteiro(len(antes))} jogos anteriores a "
        f"{data.date()}"
    )

    st.markdown("### O que cada modelo acha")
    st.dataframe(
        comum.tabela_de_probabilidades(previsoes),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Os três discordam, e a diferença entre eles é uma boa medida de quanto "
        "qualquer um deles deve ser levado a sério."
    )

    oficial = next(iter(dados.MODELOS))
    st.markdown("### Odds justas do modelo oficial")
    st.dataframe(
        comum.tabela_de_odds_justas(previsoes, oficial),
        hide_index=True,
        width="stretch",
    )
    comum.mostrar_aviso(avisos.ODD_JUSTA)

    st.markdown("### Placares mais prováveis")
    placares = dados.placares_mais_provaveis(matriz)
    tabela = placares.assign(
        probabilidade=placares["probabilidade"].map(lambda v: relatorio.pct(v))
    ).rename(columns={"placar": "Placar", "probabilidade": "Chance"})
    st.dataframe(tabela, hide_index=True, width="stretch")
    st.caption(
        "Mesmo o placar mais provável de um jogo de futebol raramente passa de "
        "10% — o que é, por si, um bom lembrete de quanto o resultado de uma "
        "partida é acaso."
    )

    comum.rodape()
