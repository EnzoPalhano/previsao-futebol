"""O app do projeto. Rode com::

    streamlit run src/futebol/app/streamlit_app.py

Sete telas, na ordem em que fazem sentido: o que o projeto é, o que o modelo
acha de um jogo, o que isso vale contra as odds, o que teria acontecido com o
dinheiro, o que as múltiplas custam, se o cash out compensa, e como os modelos
se saem uns contra os outros.

⚠️ **Este arquivo é só a navegação.** Cada tela mora em
``futebol/app/paginas/``, e as contas moram nos módulos de sempre
(``futebol/modelos``, ``futebol/backtest``, ``futebol/avaliacao``). O app não
tem matemática própria: se um número aparece aqui, ele veio do mesmo código que
gerou os relatórios — e é por isso que a tela não pode discordar do documento.
"""

from __future__ import annotations

import streamlit as st

from futebol.app import dados
from futebol.app.paginas import (
    backtest,
    cash_out,
    comparar,
    desempenho,
    inicio,
    multiplas,
    prever,
)

#: As telas, na ordem do menu: ``(função, título, ícone, caminho na URL)``.
#:
#: O ícone não é enfeite: com sete páginas, é ele que permite achar a certa sem
#: ler. E o **caminho na URL é obrigatório**: todas as telas expõem uma função
#: chamada ``mostrar``, e o Streamlit deriva o endereço do nome da função quando
#: ninguém o informa — as sete viram ``/mostrar`` e o app se recusa a abrir,
#: porque endereço repetido tornaria impossível saber em que página se está.
PAGINAS = (
    (inicio.mostrar, "Início", "🏠", "inicio"),
    (prever.mostrar, "Prever jogo", "🔮", "prever"),
    (comparar.mostrar, "Comparar com odds", "⚖️", "comparar"),
    (backtest.mostrar, "Backtest", "📉", "backtest"),
    (multiplas.mostrar, "Múltiplas", "🎟️", "multiplas"),
    (cash_out.mostrar, "Cash out", "💸", "cash-out"),
    (desempenho.mostrar, "Desempenho", "📊", "desempenho"),
)


def main() -> None:
    st.set_page_config(
        page_title="Previsão probabilística de futebol",
        page_icon="⚽",
        layout="wide",
    )

    try:
        dados.carregar()
    except dados.ErroDeDados as erro:
        st.title("⚽ Previsão probabilística de futebol")
        st.error(str(erro))
        st.info(
            "O app precisa da tabela de jogos para funcionar. Ela não vai para o "
            "Git (são mais de cem mil partidas), então na primeira vez é preciso "
            "gerá-la localmente.",
            icon="ℹ️",
        )
        return

    navegacao = st.navigation(
        [
            st.Page(funcao, title=titulo, icon=icone, url_path=caminho)
            for funcao, titulo, icone, caminho in PAGINAS
        ]
    )
    with st.sidebar:
        st.caption(
            "Projeto educacional. **Não** é recomendação de aposta — e o que ele "
            "mediu é que não há vantagem sobre o mercado."
        )
    navegacao.run()


main()
