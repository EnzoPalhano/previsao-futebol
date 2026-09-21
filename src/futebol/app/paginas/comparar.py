"""Página "Comparar com odds": você digita a odd, o app calcula o valor esperado.

⚠️ **Esta é a página mais perigosa do app**, e vale dizer por quê antes de
qualquer coisa.

As outras telas mostram o que o modelo pensa. Esta mostra um número que **parece
uma recomendação**: "valor esperado +9%" lê-se como "aposte". E o projeto mediu,
em 21.682 apostas, que seguir exatamente esse número perde 12,9% — pior do que
apostar no chute.

Por isso o aviso não fica no rodapé: ele fica **antes** da conta, e a tela nunca
chama nada de "oportunidade".
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from futebol import relatorio
from futebol.app import avisos, dados
from futebol.app.paginas import comum
from futebol.odds import mercado

#: Os mercados em que dá para digitar odd, na ordem da tela. Cada um é um grupo
#: complementar — e a margem da casa é uma propriedade do **grupo**, nunca de
#: uma odd sozinha, por isso elas são pedidas juntas.
GRUPOS: tuple[tuple[str, tuple[tuple[str, str, float], ...]], ...] = (
    (
        "Resultado (1X2)",
        (
            ("H", "Mandante", 2.50),
            ("D", "Empate", 3.40),
            ("A", "Visitante", 2.90),
        ),
    ),
    (
        "Gols (2,5)",
        (
            ("over25", "Mais de 2,5", 1.90),
            ("under25", "Menos de 2,5", 1.95),
        ),
    ),
)


def valor_esperado(probabilidade: float, odd: float) -> float:
    """``p × odd − 1``: o lucro médio de apostar 1 unidade, segundo o modelo."""
    return probabilidade * odd - 1.0


def margem_do_grupo(odds: list[float]) -> float:
    """Quanto a casa cobra no grupo: a soma das probabilidades implícitas − 1.

    Se as três odds do 1X2 dessem 33,3% cada, a soma seria 100% e a casa não
    ganharia nada. Ela sempre soma mais que isso, e o excedente é a comissão.
    """
    return float(sum(1.0 / odd for odd in odds if odd > 0) - 1.0)


def montar_tabela(
    previsao: pd.Series, odds: dict[str, float], metodo: str = "power"
) -> pd.DataFrame:
    """Uma linha por seleção, com probabilidade, odd, valor esperado e o mercado.

    A coluna "o mercado diz" é a probabilidade da odd **sem a comissão**, e ela
    existe para a comparação ser justa: comparar a probabilidade do modelo com
    ``1/odd`` crua embutiria a comissão na diferença e faria todo mercado
    parecer pessimista.
    """
    linhas = []
    for _, selecoes in GRUPOS:
        chaves = [chave for chave, _, _ in selecoes]
        do_grupo = [odds[chave] for chave in chaves]
        justas = (
            mercado.remover_margem([do_grupo], metodo)[0]
            if all(odd > 1 for odd in do_grupo)
            else [float("nan")] * len(chaves)
        )
        for (chave, rotulo, _), odd, justa in zip(selecoes, do_grupo, justas, strict=True):
            linhas.append(
                {
                    "selecao": chave,
                    "Seleção": rotulo,
                    "O modelo diz": float(previsao[chave]),
                    "O mercado diz": float(justa),
                    "Odd": odd,
                    "Valor esperado": valor_esperado(float(previsao[chave]), odd),
                }
            )
    return pd.DataFrame(linhas)


def _formatar(tabela: pd.DataFrame) -> pd.DataFrame:
    formatada = tabela.drop(columns=["selecao"]).copy()
    for coluna in ("O modelo diz", "O mercado diz"):
        formatada[coluna] = formatada[coluna].map(lambda v: relatorio.pct(v))
    formatada["Odd"] = formatada["Odd"].map(lambda v: relatorio.num(v, 2))
    formatada["Valor esperado"] = formatada["Valor esperado"].map(
        lambda v: ("+" if v >= 0 else "") + relatorio.pct(v)
    )
    return formatada


def mostrar() -> None:
    st.title("Comparar com as odds")
    st.markdown(
        "Digite as odds que você viu no site da casa. O app mostra o valor "
        "esperado de cada aposta segundo o modelo — e o que o projeto mediu "
        "sobre confiar nesse número."
    )

    comum.mostrar_aviso(avisos.EV_POSITIVO_NAO_E_OPORTUNIDADE, tipo="error")

    escolha = comum.escolher_jogo("comparar")
    if escolha is None:
        return
    liga, mandante, visitante, data = escolha

    jogos = dados.carregar()
    da_liga = jogos.loc[jogos["liga"] == liga]
    if da_liga.loc[da_liga["data"] < data].empty:
        st.error(
            f"Não há jogo da {liga} antes de {data.date()} para treinar o modelo."
        )
        return

    st.markdown("### As odds que você viu")
    odds: dict[str, float] = {}
    for titulo, selecoes in GRUPOS:
        st.caption(titulo)
        colunas = st.columns(len(selecoes))
        for coluna, (chave, rotulo, padrao) in zip(colunas, selecoes, strict=True):
            with coluna:
                odds[chave] = st.number_input(
                    rotulo,
                    min_value=1.01,
                    max_value=1000.0,
                    value=padrao,
                    step=0.05,
                    key=f"odd_{chave}",
                )

    with st.spinner("Treinando o modelo..."):
        previsoes = dados.prever(
            jogos, liga, mandante, visitante, data, dados.config()
        )
    oficial = previsoes.iloc[0]

    tabela = montar_tabela(oficial, odds)
    st.markdown(f"### {mandante} × {visitante}")
    st.dataframe(_formatar(tabela), hide_index=True, width="stretch")

    esquerda, direita = st.columns(2)
    with esquerda:
        margem_1x2 = margem_do_grupo([odds["H"], odds["D"], odds["A"]])
        st.metric("Comissão da casa no 1X2", relatorio.pct(margem_1x2))
        st.caption(
            "Quanto as três odds somam acima de 100%. É o que a casa cobra — "
            "e é o que qualquer estratégia precisa vencer **antes** de lucrar."
        )
    with direita:
        margem_ou = margem_do_grupo([odds["over25"], odds["under25"]])
        st.metric("Comissão da casa no Over/Under", relatorio.pct(margem_ou))
        st.caption("A mesma conta, no mercado de gols.")

    melhor = tabela.loc[tabela["Valor esperado"].idxmax()]
    if melhor["Valor esperado"] > 0:
        st.markdown(
            f"O maior valor esperado desta tela é **{melhor['Seleção']}**, com "
            f"{'+' if melhor['Valor esperado'] >= 0 else ''}"
            f"{relatorio.pct(melhor['Valor esperado'])}. "
            "⚠️ **Isso não é uma recomendação.** Foi exatamente esta regra — "
            "apostar no maior valor esperado — que o backtest da Fase 6 mediu, e "
            f"ela perdeu {relatorio.pct(abs(avisos.ROI_FASE_6))} em 21.682 "
            "apostas."
        )
    else:
        st.markdown(
            "Nenhuma seleção desta tela tem valor esperado positivo — o caso mais "
            "comum, e o mais honesto. A comissão da casa é justamente o tamanho "
            "da desvantagem com que todo apostador começa."
        )

    comum.rodape()
