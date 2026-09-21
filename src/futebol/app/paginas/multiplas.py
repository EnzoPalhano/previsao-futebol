"""Página "Múltiplas": monta bilhetes e mostra o que eles custam.

A tela faz as três coisas que a especificação pede — montar por tamanho, montar
por prêmio alvo e comparar tamanhos lado a lado — e mais uma que ela não pede:
deixa montar o bilhete **na mão**, escolhendo seleção por seleção, porque é isso
que a pessoa faz no site da casa.

⚠️ **Toda chance de ganhar mostrada nesta página vem acompanhada de dois
avisos**, e os dois são exigência medida, não cortesia:

1. a chance é o produto das chances, o que supõe jogos independentes (seção 7.1
   da especificação);
2. a chance é a **do modelo**, que exagera cerca de 4% por seleção — e numa
   múltipla esse errinho é elevado à potência do número de jogos.

⚠️ **A limitação honesta desta tela:** o projeto não tem jogos futuros, só
histórico. Então "a rodada" aqui é uma **data do passado** que você escolhe.
Inventar uma rodada futura seria inventar os dados dela.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from futebol import relatorio
from futebol.app import avisos, dados
from futebol.app.paginas import comum
from futebol.backtest import montador, multiplas


def _rotulo_da_selecao(linha: pd.Series) -> str:
    """Como uma seleção aparece na lista de escolha manual."""
    nomes = {
        "H": "vitória do mandante",
        "D": "empate",
        "A": "vitória do visitante",
        "over25": "+2,5 gols",
        "under25": "−2,5 gols",
    }
    return (
        f"{linha['mandante']} × {linha['visitante']} — "
        f"{nomes.get(linha['selecao'], linha['selecao'])} "
        f"(odd {relatorio.num(linha['odd'], 2)})"
    )


def mostrar_bilhete(opcao: montador.Opcao) -> None:
    """As seleções, as contas e os dois avisos obrigatórios."""
    st.dataframe(
        pd.DataFrame(
            {
                "Liga": opcao.pernas["liga"],
                "Jogo": opcao.pernas["mandante"] + " × " + opcao.pernas["visitante"],
                "Seleção": opcao.pernas["selecao"],
                "Odd": opcao.pernas["odd"].map(lambda v: relatorio.num(v, 2)),
                "Chance": opcao.pernas["prob"].map(lambda v: relatorio.pct(v)),
            }
        ),
        hide_index=True,
        width="stretch",
    )

    primeira, segunda, terceira, quarta = st.columns(4)
    with primeira:
        st.metric("Odd total", relatorio.num(opcao.odd_total, 2))
    with segunda:
        st.metric("Prêmio", f"R$ {relatorio.dinheiro(opcao.premio)}")
    with terceira:
        st.metric("Chance de ganhar", relatorio.pct(opcao.prob_modelo))
        st.caption(f"ou seja, 1 em {relatorio.num(opcao.uma_em, 1)}")
    with quarta:
        st.metric("Comissão da casa", relatorio.pct(opcao.margem_acumulada))
        st.caption("acumulada no bilhete inteiro")

    exagero = avisos.exagero_da_multipla(opcao.tamanho)
    st.markdown(
        f"Valor esperado: **{'+' if opcao.ev >= 0 else ''}"
        f"{comum.reais(opcao.ev)}** por bilhete de "
        f"{comum.reais(opcao.valor)}. "
        f"Corrigindo pelo exagero medido do modelo ({relatorio.pct(exagero)} num "
        f"bilhete de {opcao.tamanho} jogos), a chance real fica perto de "
        f"**{relatorio.pct(opcao.prob_modelo * (1 - exagero))}**."
    )

    comum.mostrar_aviso(avisos.INDEPENDENCIA)
    comum.mostrar_aviso(avisos.EXAGERO_POR_SELECAO)


def mostrar() -> None:
    st.title("Montador de múltiplas")
    st.markdown(
        "Uma múltipla paga o produto das odds — e cobra o produto das comissões. "
        "Esta tela monta o bilhete e mostra as duas coisas lado a lado."
    )

    cfg = dados.config()
    medidos = dados.modelos_medidos(cfg)
    if not medidos:
        st.error(
            "Nenhum modelo tem walk-forward gravado. Rode "
            "`python scripts/validar.py` antes."
        )
        return

    modelo = dados.nome_do_modelo_oficial()
    modelo = modelo if modelo in medidos else sorted(medidos)[0]
    datas = dados.rodadas_disponiveis(modelo)
    if not datas:
        st.error("Nenhuma rodada apostável na janela avaliada.")
        return

    st.info(
        "O projeto trabalha com **histórico**, não com jogos futuros. Escolha uma "
        "rodada do passado: o modelo foi treinado só com o que se sabia antes "
        "dela, e as odds são as que existiam de verdade naquele dia.",
        icon="ℹ️",
    )
    data = st.selectbox(
        "Rodada",
        datas,
        format_func=lambda d: pd.Timestamp(d).strftime("%d/%m/%Y"),
    )
    candidatos = dados.candidatos_de_aposta(modelo)
    rodada = candidatos.loc[candidatos["data"] == data]
    elegiveis = multiplas.elegiveis(rodada, cfg)
    por_jogo = multiplas.melhor_selecao_por_jogo(elegiveis)

    limites = multiplas.limites(cfg)
    st.caption(
        f"{relatorio.inteiro(len(por_jogo))} jogos nesta rodada, com odd entre "
        f"{relatorio.num(limites['odd_minima'], 2)} e "
        f"{relatorio.num(limites['odd_maxima'], 2)}. No máximo **uma seleção por "
        "jogo**: mercados da mesma partida andam juntos, e multiplicar as "
        "chances deles daria um número inflado."
    )

    valor = st.number_input(
        "Quanto apostar (R$)", min_value=1.0, max_value=10_000.0, value=10.0, step=5.0
    )

    por_tamanho, por_premio, manual, comparar = st.tabs(
        ["Por número de jogos", "Por prêmio alvo", "Montar na mão", "Comparar tamanhos"]
    )

    with por_tamanho:
        tamanho = st.slider(
            "Quantos jogos no bilhete",
            min_value=1,
            max_value=min(int(limites["max_selecoes"]), len(por_jogo)),
            value=min(4, len(por_jogo)),
        )
        opcao = montador.por_tamanho(elegiveis, tamanho, valor)
        if opcao is None:
            st.warning("A rodada não tem jogos suficientes para esse tamanho.")
        else:
            mostrar_bilhete(opcao)

    with por_premio:
        alvo = st.number_input(
            "Quero ganhar (R$)",
            min_value=float(valor) * 1.1,
            max_value=1_000_000.0,
            value=max(200.0, float(valor) * 2),
            step=10.0,
        )
        achado = montador.montar(rodada, cfg, premio_alvo=alvo, valor=valor)
        if achado is None:
            st.warning(
                f"Nem juntando {int(limites['max_selecoes'])} seleções desta rodada "
                f"dá para chegar a {comum.reais(alvo)}. Baixe o alvo ou "
                "aumente o valor apostado."
            )
        else:
            st.caption(
                f"O bilhete **mais provável** que alcança o alvo tem "
                f"{achado.tamanho} seleções."
            )
            mostrar_bilhete(achado)

    with manual:
        st.caption(
            "Escolha as seleções na mão, como você faria no site da casa. A lista "
            "traz a melhor seleção de cada jogo desta rodada."
        )
        opcoes = {_rotulo_da_selecao(linha): i for i, linha in por_jogo.iterrows()}
        escolhidas = st.multiselect(
            "Seleções",
            list(opcoes),
            max_selections=int(limites["max_selecoes"]),
        )
        if not escolhidas:
            st.info("Escolha pelo menos uma seleção.", icon="ℹ️")
        else:
            pernas = por_jogo.loc[[opcoes[rotulo] for rotulo in escolhidas]]
            mostrar_bilhete(montador.avaliar(pernas, valor))

    with comparar:
        st.caption(
            "Cada jogo a mais faz três coisas ao mesmo tempo: multiplica o "
            "prêmio, multiplica a comissão e divide a chance de ganhar."
        )
        tabela = montador.comparar_tamanhos(rodada, cfg, valor=valor)
        if tabela.empty:
            st.warning("A rodada não tem jogos suficientes.")
        else:
            st.dataframe(
                pd.DataFrame(
                    {
                        "Jogos": tabela["tamanho"],
                        "Odd total": tabela["odd_total"].map(
                            lambda v: relatorio.num(v, 2)
                        ),
                        "Prêmio": tabela["premio"].map(
                            lambda v: f"R$ {relatorio.dinheiro(v)}"
                        ),
                        "Chance": tabela["prob_modelo"].map(
                            lambda v: relatorio.pct(v)
                        ),
                        "Ou seja": tabela["uma_em"].map(
                            lambda v: f"1 em {relatorio.num(v, 1)}"
                        ),
                        "Comissão": tabela["margem_acumulada"].map(
                            lambda v: relatorio.pct(v)
                        ),
                    }
                ),
                hide_index=True,
                width="stretch",
            )
            st.line_chart(
                tabela.set_index("tamanho")[["prob_modelo", "margem_acumulada"]].rename(
                    columns={
                        "prob_modelo": "chance de ganhar",
                        "margem_acumulada": "comissão da casa",
                    }
                ),
                x_label="jogos no bilhete",
            )
            comum.mostrar_aviso(avisos.INDEPENDENCIA)

    comum.rodape()
