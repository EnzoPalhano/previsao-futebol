"""Página "Desfalques": a previsão antes e depois, e o que ainda não se sabe.

O critério de pronto da Fase 10 é esta tela: para os jogos da próxima rodada,
os desfalques encontrados e as probabilidades antes/depois do ajuste, **com o
aviso de que o efeito ainda não está validado**.

⚠️ **Esta é a tela mais fácil de o projeto se trair, e vale entender por quê.**
Um ajuste por desfalques *parece* obviamente certo — claro que perder o
artilheiro piora o time —, e é justamente por parecer óbvio que ele dispensaria
medição na cabeça de quem olha. Todas as outras telas do app mostram coisas
medidas; esta mostra uma **hipótese em teste**, e a diferença precisa estar na
cara.

Por isso a tela é construída ao contrário do que seria natural: o veredito do
caderno vem **antes** dos jogos, e a coluna "depois" nunca aparece sozinha.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from futebol import relatorio
from futebol.app import avisos, dados
from futebol.app.paginas import comum
from futebol.noticias import registro


def _formatar_probabilidades(caderno: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por jogo, com as duas previsões lado a lado."""
    def pct(coluna: str):
        return pd.to_numeric(caderno[coluna], errors="coerce").map(
            lambda v: relatorio.pct(v) if pd.notna(v) else "—"
        )

    mudou = (
        pd.to_numeric(caderno["prob_H_ajustado"], errors="coerce")
        - pd.to_numeric(caderno["prob_H_cru"], errors="coerce")
    ).abs() > 1e-9

    return pd.DataFrame(
        {
            "Data": caderno["data_do_jogo"],
            "Liga": caderno["liga"],
            "Jogo": caderno["mandante"] + " × " + caderno["visitante"],
            "Mandante (cru)": pct("prob_H_cru"),
            "Mandante (ajustado)": pct("prob_H_ajustado"),
            "Mudou?": mudou.map({True: "sim", False: "não"}),
            "Desfalques": caderno["desfalques"].fillna("").replace("", "—"),
        }
    )


def mostrar() -> None:
    st.title("Desfalques e notícias")
    st.markdown(
        "A última fase do projeto tenta dar ao modelo uma informação que o "
        "placar não tem: quem não vai jogar. O modelo base olha resultados "
        "passados e mais nada — ele não sabe que o artilheiro está lesionado."
    )

    # ⚠️ O aviso vem ANTES de qualquer número. Nas outras telas ele acompanha o
    # resultado; aqui ele precisa enquadrá-lo, porque o número desta tela é uma
    # hipótese e não uma medição.
    comum.mostrar_aviso(avisos.AJUSTE_NAO_VALIDADO, tipo="error")

    cfg = dados.config()
    caderno = registro.carregar(cfg)
    demonstracao = False
    if caderno.empty:
        caderno = registro.carregar(cfg, falso=True)
        demonstracao = not caderno.empty

    if caderno.empty:
        st.info(
            "O caderno de previsões está vazio. Para preenchê-lo, rode no "
            "terminal:\n\n"
            "    python scripts/desfalques.py --falso    # demonstração\n"
            "    python scripts/desfalques.py            # de verdade, com .env\n\n"
            "A versão de verdade precisa das chaves de API — o guia da Fase 10 "
            "ensina a criá-las.",
            icon="ℹ️",
        )
        comum.rodape()
        return

    if demonstracao:
        st.warning(
            "**Os dados abaixo são de DEMONSTRAÇÃO.** Eles vêm de "
            "`registro_falso.csv`, gerado por `--falso`: os desfalques são "
            "inventados e servem só para mostrar a tela funcionando. O caderno "
            "de verdade está vazio.",
            icon="🎭",
        )

    # ------------------------------------------------------------------
    # O veredito vem antes dos jogos
    # ------------------------------------------------------------------
    st.header("O que já dá para dizer")
    comparacao = registro.avaliar(cfg, caderno=caderno)

    if comparacao.n:
        esquerda, meio, direita = st.columns(3)
        with esquerda:
            st.metric("Jogos com resultado", relatorio.inteiro(comparacao.n))
            st.caption(f"{comparacao.com_ajuste} deles com algum ajuste")
        with meio:
            st.metric(
                "Diferença de log loss",
                f"{comparacao.diferenca:+.4f}",
            )
            st.caption(
                f"IC 95%: {comparacao.ic[0]:+.4f} a {comparacao.ic[1]:+.4f} · "
                "negativo é melhor"
            )
        with direita:
            st.metric("Menor efeito detectável", f"{comparacao.detectavel:.4f}")
            st.caption("o que esta amostra conseguiria enxergar")

    st.info(comparacao.veredito, icon="🧭")

    # ------------------------------------------------------------------
    # Os jogos
    # ------------------------------------------------------------------
    st.header("As duas previsões, jogo a jogo")
    st.caption(
        "A coluna **cru** é o modelo oficial do projeto, exatamente como nas "
        "outras telas. A coluna **ajustado** aplica os desfalques. As duas são "
        "gravadas antes do jogo — é isso que torna a comparação possível."
    )

    recentes = registro.primeira_gravacao(caderno).sort_values(
        "data_do_jogo", ascending=False
    )
    st.dataframe(
        _formatar_probabilidades(recentes.head(50)),
        hide_index=True,
        width="stretch",
    )

    com_ajuste = recentes.loc[
        recentes["desfalques"].fillna("").astype(str).str.strip() != ""
    ]
    st.caption(
        f"{relatorio.inteiro(len(recentes))} jogos no caderno, "
        f"{relatorio.inteiro(len(com_ajuste))} com algum desfalque encontrado. "
        "Jogo sem desfalque tem as duas colunas iguais, e é o caso comum."
    )

    # ------------------------------------------------------------------
    # Como ler
    # ------------------------------------------------------------------
    st.header("Como esta fase pode se enganar")
    st.markdown(
        """
Três armadilhas, e o que o projeto faz contra cada uma:

- **"o ajuste é óbvio, não precisa medir".** Perder o artilheiro obviamente
  piora o time — mas *quanto* não é óbvio, e o mercado **já sabe da lesão**:
  ela saiu no jornal. O que precisaria ser demonstrado não é que a lesão
  importa, é que o projeto a incorpora melhor do que o preço já incorpora;
- **"a log loss melhorou, então funcionou".** Com ~150 jogos, a menor melhora
  detectável é 0,0338 — maior que a distância inteira do modelo para o mercado.
  Qualquer melhora que apareça nesse tamanho de amostra é, muito provavelmente,
  ruído. Por isso o critério do projeto é o CLV;
- **"vou afinar o parâmetro até melhorar".** É o sobreajuste que a Fase 6 já
  documentou. Se o ajuste piorar de forma consistente, a resposta certa é
  **desligá-lo**, não calibrá-lo até ficar bonito.
"""
    )

    st.caption(
        "Pipeline em `src/futebol/noticias/`, executado por "
        "`python scripts/desfalques.py`. O guia da Fase 10 explica passo a "
        "passo, inclusive como criar as chaves de API."
    )
    comum.rodape()
