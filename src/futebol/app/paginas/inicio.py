"""Página inicial: o que o projeto é, e o que ele descobriu.

⚠️ **Esta página existe para ser lida antes das outras, e por isso ela dá o
resultado logo de cara — inclusive o ruim.** Um app de previsão de futebol que
abre com gráficos bonitos e esconde "o modelo perde do mercado" na sétima aba é
um app que engana por omissão. Aqui o veredito vem antes da ferramenta.
"""

from __future__ import annotations

import streamlit as st

from futebol import relatorio
from futebol.app import avisos
from futebol.app.paginas import comum


def mostrar() -> None:
    st.title("⚽ Previsão probabilística de futebol")
    st.markdown(
        "Um projeto de *machine learning* que calcula probabilidades de jogos, "
        "compara com as odds das casas de aposta e mede — com honestidade "
        "estatística — se existe alguma vantagem sobre o mercado."
    )

    comum.mostrar_aviso(avisos.JOGO_RESPONSAVEL, tipo="info")

    st.header("A resposta curta: não há vantagem")
    st.markdown(
        "O projeto foi construído para responder uma pergunta, e a resposta está "
        "medida. Ela vem antes das telas porque é o contexto de tudo o que elas "
        "mostram."
    )

    primeira, segunda, terceira = st.columns(3)
    with primeira:
        st.metric("ROI do backtest", relatorio.pct(avisos.ROI_FASE_6))
        st.caption("21.682 apostas · IC 95%: −14,97% a −10,89%")
    with segunda:
        st.metric("CLV médio", relatorio.pct(avisos.CLV_FASE_6))
        st.caption("O critério primário · IC 95%: −7,95% a −7,69%")
    with terceira:
        st.metric("Ligas com lucro", "0 de 18")
        st.caption("E 0 de 3 temporadas")

    st.markdown(
        f"""
**E o achado mais interessante:** apostar **ao acaso** entre as mesmas
oportunidades teria perdido menos
({relatorio.pct(abs(avisos.ROI_ALEATORIO_FASE_6))}) do que apostar seguindo o
modelo ({relatorio.pct(abs(avisos.ROI_FASE_6))}). O filtro de valor esperado não
seleciona onde o modelo sabe mais — seleciona **onde ele erra para cima**, que é
sistematicamente o azarão, que é onde a casa cobra mais caro.

A amostra é grande o suficiente para isso significar alguma coisa: 21.682
apostas, quatro vezes o mínimo que o próprio projeto exigiu de si mesmo. A
conclusão **não** é "faltaram dados". É que não há vantagem, medida com folga.
"""
    )

    st.header("O que dá para fazer aqui")
    st.markdown(
        """
| Página | Para quê |
|---|---|
| **Prever jogo** | As probabilidades do modelo para qualquer confronto, e os placares mais prováveis |
| **Comparar com odds** | Você digita as odds que viu; o app calcula o valor esperado |
| **Backtest** | O que teria acontecido com o dinheiro, com intervalo de confiança à vista |
| **Múltiplas** | Monta bilhetes e mostra quanto a comissão cresce a cada jogo |
| **Cash out** | Se a oferta da casa está acima ou abaixo do valor justo |
| **Desempenho** | As tabelas de log loss das Fases 4 e 5, modelo a modelo |
"""
    )

    st.header("Como este projeto evita se enganar")
    st.markdown(
        """
Backtest de aposta é um campo minado, e quase todo projeto amador que mostra
lucro tropeça em uma destas armadilhas. Aqui elas são **testes automatizados**,
não promessas:

- **sem olhar o futuro.** A previsão para um jogo do dia D é feita por um modelo
  treinado só com jogos anteriores a D, e há um teste que confere isso partida a
  partida;
- **aposta na odd média, nunca na máxima.** Usar a melhor odd entre vinte casas
  infla o ROI artificialmente — é o erro que invalida a maioria dos backtests que
  circulam por aí;
- **modelo se escolhe por log loss, nunca por lucro.** O ROI é dominado por
  ruído: escolher por ele é a forma mais rápida de se enganar;
- **tudo com intervalo de confiança**, mais o número de apostas e o menor efeito
  que aquela amostra conseguiria detectar;
- **as temporadas de teste final estão trancadas** e serão abertas uma única vez,
  com a configuração registrada antes;
- **resultado negativo é resultado**, e está reportado com destaque — inclusive
  nesta primeira tela.
"""
    )

    st.caption(
        "Relatórios completos em `docs/relatorios/`, guias para leigos em "
        "`docs/guias/`. Código em `src/futebol/`."
    )
    comum.rodape()
