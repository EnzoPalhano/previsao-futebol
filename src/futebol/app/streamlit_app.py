"""O app do projeto. Rode com::

    streamlit run src/futebol/app/streamlit_app.py

Oito telas, na ordem em que fazem sentido: o que o projeto é, o que o modelo
acha de um jogo, o que isso vale contra as odds, o que teria acontecido com o
dinheiro, o que as múltiplas custam, se o cash out compensa, como os modelos
se saem uns contra os outros — e, por último, a hipótese que a Fase 10 ainda
está testando.

⚠️ **Este arquivo é só a navegação.** Cada tela mora em
``futebol/app/paginas/``, e as contas moram nos módulos de sempre
(``futebol/modelos``, ``futebol/backtest``, ``futebol/avaliacao``). O app não
tem matemática própria: se um número aparece aqui, ele veio do mesmo código que
gerou os relatórios — e é por isso que a tela não pode discordar do documento.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as componentes

from futebol.app import dados
from futebol.app.paginas import (
    backtest,
    cash_out,
    comparar,
    desempenho,
    desfalques,
    inicio,
    multiplas,
    prever,
)

#: As telas, na ordem do menu: ``(função, título, ícone, caminho na URL)``.
#:
#: O ícone não é enfeite: com oito páginas, é ele que permite achar a certa sem
#: ler. E o **caminho na URL é obrigatório**: todas as telas expõem uma função
#: chamada ``mostrar``, e o Streamlit deriva o endereço do nome da função quando
#: ninguém o informa — as oito viram ``/mostrar`` e o app se recusa a abrir,
#: porque endereço repetido tornaria impossível saber em que página se está.
PAGINAS = (
    (inicio.mostrar, "Início", "🏠", "inicio"),
    (prever.mostrar, "Prever jogo", "🔮", "prever"),
    (comparar.mostrar, "Comparar com odds", "⚖️", "comparar"),
    (backtest.mostrar, "Backtest", "📉", "backtest"),
    (multiplas.mostrar, "Múltiplas", "🎟️", "multiplas"),
    (cash_out.mostrar, "Cash out", "💸", "cash-out"),
    (desempenho.mostrar, "Desempenho", "📊", "desempenho"),
    # ⚠️ A tela da Fase 10 fica por ÚLTIMO de propósito. Ela é a única do app
    # que mostra uma hipótese em teste em vez de uma medição, e pô-la antes das
    # telas medidas passaria a impressão contrária.
    (desfalques.mostrar, "Desfalques", "🏥", "desfalques"),
)


def declarar_idioma() -> None:
    """Avisa ao navegador que a página está em português.

    ⚠️ **Sem isto o Chrome traduz o app — de português para português.** O
    Streamlit serve a página com ``<html lang="en">`` e não expõe jeito de mudar
    isso; o navegador acredita na declaração, não no texto, e oferece (ou aplica
    sozinho, para quem tem tradução automática ligada) uma tradução do inglês.
    O resultado é um texto remoído: "Apostas envolvem risco real de perda" vira
    "Apostas de envolvimento risco real de perda", "Início" vira "Não se trata de
    uma questão de", e "o mínimo que o próprio projeto exigiu de si mesmo" vira
    "o projeto de sucesso de si mesmo", que não quer dizer nada.

    Num app qualquer isso seria feio. Aqui é grave: **os avisos obrigatórios são
    o produto desta fase**, e eles dependem de dizer exatamente o que dizem. Um
    aviso de jogo responsável parafraseado por tradutor automático é um aviso
    que ninguém revisou.

    O componente é um iframe de altura zero servido da mesma origem, que é o
    único caminho que o Streamlit deixa aberto para tocar no ``<html>`` da
    página. ``_top`` alcança o documento de fora do iframe.
    """
    componentes.html(
        "<script>window.top.document.documentElement.lang = 'pt-BR';</script>",
        height=0,
    )


def main() -> None:
    st.set_page_config(
        page_title="Previsão probabilística de futebol",
        page_icon="⚽",
        layout="wide",
    )
    declarar_idioma()

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
