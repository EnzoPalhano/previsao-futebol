"""Página "Cash out": a oferta da casa está acima ou abaixo do valor justo?

A tela faz uma conta só, e ela é simples: o que ainda falta acontecer, vezes o
prêmio. O que ela acrescenta é o contexto que nenhuma casa de apostas mostra —
que o botão cobra uma taxa, e que essa taxa é a mesma em qualquer momento.

⚠️ **A limitação desta tela:** as probabilidades das seleções que faltam são
digitadas por você. Se elas vierem do modelo deste projeto, carregam o exagero
que a Fase 7 mediu; se vierem das odds da casa, carregam a comissão dela. A tela
diz qual é qual em vez de fingir que existe um número neutro.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from futebol import relatorio
from futebol.app import avisos, dados
from futebol.app.paginas import comum
from futebol.backtest import cash_out as conta


def mostrar() -> None:
    st.title("Cash out")
    st.markdown(
        "Você tem uma múltipla em andamento e a casa ofereceu um valor para "
        "encerrar. Vale a pena aceitar?"
    )

    comum.mostrar_aviso(avisos.CASH_OUT_COBRA_SEMPRE)

    cfg = dados.config()
    margem_padrao = conta.margem_da_casa(cfg)

    st.markdown("### O bilhete")
    esquerda, meio, direita = st.columns(3)
    with esquerda:
        valor = st.number_input(
            "Quanto você apostou (R$)", min_value=1.0, value=10.0, step=5.0
        )
    with meio:
        odd_total = st.number_input(
            "Odd total do bilhete", min_value=1.01, value=20.0, step=1.0
        )
    with direita:
        faltam = st.number_input(
            "Quantas seleções ainda faltam", min_value=1, max_value=10, value=3, step=1
        )

    premio = valor * odd_total
    st.caption(
        f"Se tudo der certo você recebe **R$ {relatorio.dinheiro(premio)}**."
    )

    st.markdown("### As seleções que faltam")
    st.caption(
        "A chance de cada uma, segundo você ou segundo o modelo. Se estiver "
        "usando as odds da casa, lembre que `1 ÷ odd` já inclui a comissão dela "
        "— a chance real que a casa atribui é um pouco maior que isso."
    )
    colunas = st.columns(min(int(faltam), 5))
    chances = []
    for i in range(int(faltam)):
        with colunas[i % len(colunas)]:
            chances.append(
                st.number_input(
                    f"Seleção {i + 1}",
                    min_value=0.01,
                    max_value=0.99,
                    value=0.60,
                    step=0.05,
                    format="%.2f",
                    key=f"cash_chance_{i}",
                )
            )

    restante = float(np.prod(chances))
    justo = conta.valor_justo(restante, premio)

    st.markdown("### A oferta")
    coluna_oferta, coluna_margem = st.columns(2)
    with coluna_oferta:
        oferta = st.number_input(
            "Quanto a casa está oferecendo (R$)",
            min_value=0.0,
            value=round(justo * (1 - margem_padrao), 2),
            step=1.0,
        )
    with coluna_margem:
        st.metric("Taxa embutida na oferta", relatorio.pct(1 - oferta / justo)
                  if justo > 0 else "—")
        st.caption(f"Referência do projeto: {relatorio.pct(margem_padrao, 0)}")

    st.markdown("### O veredito")
    primeira, segunda, terceira = st.columns(3)
    with primeira:
        st.metric("Chance de o bilhete fechar", relatorio.pct(restante))
        st.caption(f"1 em {relatorio.num(1 / restante, 1)}" if restante > 0 else "")
    with segunda:
        st.metric("Valor justo", f"R$ {relatorio.dinheiro(justo)}")
        st.caption("a chance do que falta × o prêmio")
    with terceira:
        diferenca = oferta - justo
        st.metric(
            "A oferta está",
            f"{'+' if diferenca >= 0 else '−'}R$ {relatorio.dinheiro(abs(diferenca))}",
        )
        st.caption("acima do justo" if diferenca >= 0 else "abaixo do justo")

    if oferta > justo:
        st.success(
            "**A oferta está acima do valor justo** — pelas chances que você "
            "digitou, aceitar é vantajoso. ⚠️ Mas repare no que isso realmente "
            "significa: você está apostando que **as suas probabilidades são "
            "melhores que as da casa**. O projeto mediu que as dele não são "
            f"(o modelo fica {relatorio.num(avisos.DISTANCIA_DO_MERCADO)} de log "
            "loss atrás do mercado), e é por isso que a estratégia 'sacar só "
            "quando compensa' também perdeu no backtest da Fase 7.",
            icon="✅",
        )
    else:
        st.info(
            "**A oferta está abaixo do valor justo**, que é o caso normal: a "
            "diferença é a taxa do cash out. Aceitar troca dinheiro esperado por "
            "tranquilidade — uma troca legítima, desde que feita com o preço à "
            "vista.",
            icon="ℹ️",
        )

    st.markdown("### Como o bilhete costuma terminar")
    st.caption(
        "Simulação das seleções que faltam, dez mil vezes. Ela mostra a "
        "experiência real de quem leva o bilhete até o fim."
    )
    distribuicao = conta.distribuicao_de_acertos(chances, repeticoes=10_000, seed=cfg.seed)
    tabela = pd.DataFrame(
        {
            "Acertos ainda por vir": range(len(distribuicao)),
            "Frequência": [relatorio.pct(v, 1) for v in distribuicao],
            "Paga": ["nada"] * (len(distribuicao) - 1)
            + [f"R$ {relatorio.dinheiro(premio)}"],
        }
    )
    st.dataframe(tabela, hide_index=True, width="stretch")
    st.caption(
        f"Só a última linha paga. As outras {len(distribuicao) - 1} terminam em "
        "zero — e juntas elas somam "
        f"{relatorio.pct(1 - float(distribuicao[-1]))} dos casos."
    )

    comum.rodape()
