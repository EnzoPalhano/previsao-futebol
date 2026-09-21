"""Página "Backtest": o que teria acontecido com o dinheiro.

A especificação pede que esta tela mostre "**sempre com o intervalo de confiança
e o número de apostas visíveis**", e a exigência está em negrito no documento
original por um motivo: é aqui que um app engana com mais facilidade. Basta
mostrar "ROI +8%" num canto grande e esconder que foram quarenta apostas.

Por isso toda métrica desta página passa por
:func:`futebol.app.paginas.comum.metrica_com_intervalo`, que não sabe desenhar
um número sem o intervalo ao lado.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from futebol import relatorio
from futebol.app import avisos, dados
from futebol.app.paginas import comum
from futebol.backtest import estrategias, simulador

#: Os limites de EV oferecidos — os mesmos quatro que a Fase 6 mediu (regra 11).
#: Deixar o usuário digitar qualquer valor seria abrir uma busca por um número
#: bonito, que é exatamente o que a regra 11 existe para conter.
LIMITES = (0.0, 0.02, 0.05, 0.10)

#: As combinações de dinheiro, com o nome que aparece na tela.
ESTRATEGIAS = {
    "Stake fixa (1% da banca)": "stake_fixa",
    "Kelly fracionado (1/4, teto de 5%)": "kelly_fracionado",
}

BANCAS = {"Banca fixa (sempre sobre a inicial)": "fixa", "Banca composta": "composta"}


def filtrar_periodo(
    candidatos: pd.DataFrame, inicio: pd.Timestamp, fim: pd.Timestamp
) -> pd.DataFrame:
    """Recorta as apostas candidatas a um intervalo de datas."""
    dentro = (candidatos["data"] >= inicio) & (candidatos["data"] <= fim)
    return candidatos.loc[dentro]


def mostrar() -> None:
    st.title("Backtest de apostas")
    st.markdown(
        "Simula as apostas que teriam sido feitas, jogo a jogo, com as odds "
        "reais e sem olhar o futuro. Sempre na **odd média pré-jogo** — nunca na "
        "máxima, que é o erro que faz quase todo backtest amador dar lucro."
    )

    comum.mostrar_aviso(avisos.AMOSTRA_E_INTERVALO)

    cfg = dados.config()
    medidos = dados.modelos_medidos(cfg)
    if not medidos:
        st.error(
            "Nenhum modelo tem walk-forward gravado. Rode, no terminal:\n\n"
            "    python scripts/validar.py"
        )
        return

    oficial = dados.nome_do_modelo_oficial()
    nomes = sorted(medidos)
    with st.sidebar:
        st.subheader("Configuração")
        modelo = st.selectbox(
            "Modelo",
            nomes,
            index=nomes.index(oficial) if oficial in nomes else 0,
            help="Só aparecem os candidatos já medidos por scripts/validar.py.",
        )
        limite = st.select_slider(
            "Aposta quando o valor esperado passa de",
            options=LIMITES,
            value=0.05,
            format_func=lambda v: relatorio.pct(v, 0),
        )
        estrategia = st.selectbox("Como dimensionar a aposta", list(ESTRATEGIAS))
        banca = st.selectbox("Que banca usar de referência", list(BANCAS))

    candidatos = dados.candidatos_de_aposta(modelo)
    primeira = pd.Timestamp(candidatos["data"].min())
    ultima = pd.Timestamp(candidatos["data"].max())
    periodo = st.slider(
        "Período",
        min_value=primeira.to_pydatetime(),
        max_value=ultima.to_pydatetime(),
        value=(primeira.to_pydatetime(), ultima.to_pydatetime()),
        format="DD/MM/YYYY",
    )
    do_periodo = filtrar_periodo(
        candidatos, pd.Timestamp(periodo[0]), pd.Timestamp(periodo[1])
    )

    apostas = simulador.selecionar(do_periodo, limite)
    if apostas.empty:
        st.warning(
            "Nenhuma aposta passou no filtro neste período. Baixe o limite de "
            "valor esperado ou amplie o intervalo de datas."
        )
        return

    medida = simulador.medir(apostas, "modelo", amostras_bootstrap=2000, seed=cfg.seed)
    aleatoria = simulador.medir(
        simulador.aleatorias(do_periodo, len(apostas), seed=cfg.seed),
        "aleatória",
        amostras_bootstrap=2000,
        seed=cfg.seed,
    )

    st.markdown("### O resultado")
    esquerda, meio, direita = st.columns(3)
    with esquerda:
        comum.metrica_com_intervalo(
            "ROI", medida.roi, medida.roi_ic[0], medida.roi_ic[1], medida.n
        )
    with meio:
        comum.metrica_com_intervalo(
            "CLV", medida.clv, medida.clv_ic[0], medida.clv_ic[1], medida.n_clv
        )
    with direita:
        st.metric("Taxa de acerto", relatorio.pct(medida.taxa_acerto))
        st.caption(f"Odd média: {relatorio.num(medida.odd_media, 2)}")

    if medida.n < 5000:
        st.info(
            f"Com {relatorio.inteiro(medida.n)} apostas, o menor ROI que esta "
            f"amostra consegue distinguir de zero é "
            f"{relatorio.pct(medida.roi_detectavel, 2)}. O projeto exige **5.000 "
            "apostas** para tratar um ROI como evidência de qualquer coisa — "
            "abaixo disso, a conclusão correta é *amostra insuficiente*, e não "
            "*há vantagem* nem *não há vantagem*.",
            icon="ℹ️",
        )

    st.markdown("### Contra quem apostaria no chute")
    comparacao = pd.DataFrame(
        [
            {
                "Quem aposta": "O modelo",
                "Apostas": relatorio.inteiro(medida.n),
                "ROI": ("+" if medida.roi >= 0 else "") + relatorio.pct(medida.roi),
                "IC 95%": f"{relatorio.pct(medida.roi_ic[0])} a {relatorio.pct(medida.roi_ic[1])}",
            },
            {
                "Quem aposta": "Sorteio (mesmo nº de apostas)",
                "Apostas": relatorio.inteiro(aleatoria.n),
                "ROI": ("+" if aleatoria.roi >= 0 else "")
                + relatorio.pct(aleatoria.roi),
                "IC 95%": f"{relatorio.pct(aleatoria.roi_ic[0])} a {relatorio.pct(aleatoria.roi_ic[1])}",
            },
        ]
    )
    st.dataframe(comparacao, hide_index=True, width="stretch")
    st.caption(
        "A comparação obrigatória do projeto. Um modelo que não fica acima do "
        "sorteio não está acrescentando informação — está pagando a comissão da "
        "casa com passos a mais."
    )

    st.markdown("### A banca ao longo do tempo")
    secao = cfg.secao("backtest")
    evolucao = estrategias.simular_banca(
        apostas,
        estrategias.criar(ESTRATEGIAS[estrategia], secao),
        float(secao["banca_inicial"]),
        BANCAS[banca],
    )
    if evolucao.curva.empty:
        st.warning("A banca acabou antes da primeira liquidação.")
    else:
        st.line_chart(
            evolucao.curva.set_index("data")["banca"],
            y_label="banca (R$)",
            x_label="",
        )

    coluna_a, coluna_b, coluna_c = st.columns(3)
    with coluna_a:
        st.metric("Banca final", f"R$ {relatorio.dinheiro(evolucao.banca_final)}")
    with coluna_b:
        st.metric("Pior queda", relatorio.pct(evolucao.drawdown_maximo))
    with coluna_c:
        st.metric("Dias racionados", relatorio.inteiro(evolucao.datas_racionadas))
        st.caption("Dias em que as apostas pedidas passaram da banca disponível.")

    if evolucao.quebrou:
        st.error(
            "**A banca quebrou.** Vale separar duas coisas que isso mistura: o "
            "ROI acima mede a qualidade das escolhas; a ruína mede a política de "
            "dinheiro. Com cerca de 28 apostas por dia, 1% da banca em cada uma "
            "põe quase 30% do dinheiro em risco por dia — inviável mesmo com um "
            "modelo vencedor.",
            icon="⚠️",
        )

    comum.rodape()
