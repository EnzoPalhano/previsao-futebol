"""Pedaços de tela usados por mais de uma página.

Nada aqui decide nada: são só formas de mostrar. O que importa é que a forma
seja **a mesma** em todas as telas — um aviso que aparece como caixa amarela
numa página e como texto cinza em outra ensina o leitor a ignorá-lo.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from futebol import relatorio
from futebol.app import avisos, dados


def reais(valor: float) -> str:
    r"""Um valor em reais seguro para escrever dentro de Markdown.

    ⚠️ **O cifrão abre fórmula matemática no Streamlit.** O Markdown dele aceita
    LaTeX entre ``$...$``, então um texto com *dois* ``R$`` — "ganha R\$ 6,10 por
    bilhete de R\$ 10,00" — faz tudo o que está entre os dois cifrões virar
    fórmula: o negrito deixa de funcionar, os ``**`` aparecem crus e os números
    saem em fonte de equação. Era exatamente o que a linha de valor esperado da
    página de múltiplas mostrava.

    Escapar o cifrão resolve, e vale mesmo quando há só um na frase: a frase de
    hoje com um vira a frase de amanhã com dois, e o defeito volta calado.

    ⚠️ Serve para texto em Markdown (``st.markdown``, ``st.caption``,
    ``st.info``…). Em ``st.metric``, em tabela e em rótulo de gráfico o valor
    **não** passa por Markdown, e ali se usa ``relatorio.dinheiro`` direto.
    """
    return f"R\\$ {relatorio.dinheiro(valor)}"


def mostrar_aviso(aviso: avisos.Aviso, tipo: str = "warning") -> None:
    """Desenha um aviso obrigatório.

    Args:
        aviso: o aviso, de :mod:`futebol.app.avisos`.
        tipo: ``"warning"`` (amarelo), ``"error"`` (vermelho) ou ``"info"``.

    ⚠️ O ``origem`` sempre aparece. Um aviso que cita número sem dizer onde ele
    foi medido é indistinguível de um aviso inventado, e este projeto inteiro é
    sobre essa diferença.
    """
    caixa = {"warning": st.warning, "error": st.error, "info": st.info}[tipo]
    caixa(aviso.como_markdown(), icon="⚠️" if tipo != "info" else "ℹ️")


def rodape() -> None:
    """O aviso de jogo responsável, no pé de toda página (seção 9)."""
    st.divider()
    st.caption(avisos.JOGO_RESPONSAVEL.texto)


def escolher_jogo(chave: str) -> tuple[str, str, str, pd.Timestamp] | None:
    """Os seletores de liga, mandante, visitante e data.

    Args:
        chave: prefixo dos widgets. Duas páginas com os mesmos seletores
            precisam de chaves diferentes, senão o Streamlit as trata como o
            mesmo widget e elas passam a se mexer juntas.

    Retorna:
        ``(liga, mandante, visitante, data)``, ou ``None`` se a liga escolhida
        não tiver dois times.
    """
    jogos = dados.carregar()
    liga = st.selectbox("Competição", dados.ligas(), key=f"{chave}_liga")
    times = dados.times_da_liga(jogos, liga)
    if len(times) < 2:
        st.error(f"A competição {liga} tem menos de dois times na tabela.")
        return None

    coluna_casa, coluna_fora = st.columns(2)
    with coluna_casa:
        mandante = st.selectbox("Mandante", times, key=f"{chave}_mandante")
    with coluna_fora:
        restantes = [time for time in times if time != mandante]
        visitante = st.selectbox("Visitante", restantes, key=f"{chave}_visitante")

    ultima = pd.Timestamp(jogos.loc[jogos["liga"] == liga, "data"].max())
    data = st.date_input(
        "Data do jogo",
        value=(ultima + pd.Timedelta(days=1)).date(),
        key=f"{chave}_data",
        help=(
            "O modelo é treinado só com jogos ANTERIORES a esta data (regra 6). "
            "Mudar a data muda a previsão, e é assim que tem de ser."
        ),
    )
    return liga, mandante, visitante, pd.Timestamp(data)


def tabela_de_probabilidades(previsoes: pd.DataFrame) -> pd.DataFrame:
    """A previsão de cada modelo, formatada para a tela."""
    rotulos = {
        "H": "Mandante",
        "D": "Empate",
        "A": "Visitante",
        "over25": "+2,5 gols",
        "under25": "−2,5 gols",
        "ambos_marcam": "Ambos marcam",
    }
    tabela = previsoes[["modelo", *rotulos]].copy()
    for chave in rotulos:
        tabela[chave] = tabela[chave].map(lambda v: relatorio.pct(v))
    return tabela.rename(columns={**rotulos, "modelo": "Modelo"})


def tabela_de_odds_justas(previsoes: pd.DataFrame, modelo: str) -> pd.DataFrame:
    """A odd justa (``1/prob``) de cada mercado, para um modelo.

    ⚠️ Ela não é uma odd que exista no mercado: não tem a comissão da casa
    dentro. Ver :data:`futebol.app.avisos.ODD_JUSTA`.
    """
    linha = previsoes.loc[previsoes["modelo"] == modelo].iloc[0]
    rotulos = {
        "H": "Vitória do mandante",
        "D": "Empate",
        "A": "Vitória do visitante",
        "over25": "Mais de 2,5 gols",
        "under25": "Menos de 2,5 gols",
        "ambos_marcam": "Ambos marcam",
    }
    return pd.DataFrame(
        [
            {
                "Mercado": rotulo,
                "Probabilidade": relatorio.pct(linha[chave]),
                "Odd justa": relatorio.num(1 / linha[chave], 2)
                if linha[chave] > 0
                else "—",
            }
            for chave, rotulo in rotulos.items()
        ]
    )


def metrica_com_intervalo(
    titulo: str, valor: float, baixo: float, alto: float, n: int, casas: int = 2
) -> None:
    """Uma métrica que **nunca** aparece sem o intervalo e o número de apostas.

    ⚠️ É a regra 10 virada em componente de tela. Um ROI sozinho não quer dizer
    nada, e a forma mais fácil de um app enganar é mostrar o número grande e
    esconder a incerteza numa nota de rodapé.
    """
    sinal = "+" if valor >= 0 else ""
    st.metric(titulo, f"{sinal}{relatorio.pct(valor, casas)}")
    st.caption(
        f"IC 95%: {'+' if baixo >= 0 else ''}{relatorio.pct(baixo, casas)} a "
        f"{'+' if alto >= 0 else ''}{relatorio.pct(alto, casas)} · "
        f"{relatorio.inteiro(n)} apostas"
    )
