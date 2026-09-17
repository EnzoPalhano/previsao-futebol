"""Os dois gráficos da Fase 4, em PNG, para o relatório em Markdown.

A Fase 4 pede "gráficos de calibração salvos em `docs/relatorios/`". São dois
aqui, e cada um existe porque responde uma pergunta que a tabela de log loss
**não** responde:

1. :func:`curva_calibracao` — *quando o modelo diz 60%, acontece 60%?* A log
   loss junta duas coisas num número só: o quanto o modelo sabe e o quanto ele
   exagera. A curva separa. Um modelo pode ter log loss decente e estar
   sistematicamente confiante demais, e isso é fatal para apostar: o valor
   esperado de uma aposta é calculado **com** a probabilidade do modelo, e se
   ela for inflada o EV é inflado junto;
2. :func:`distancia_do_mercado` — *em que competições o modelo chega perto do
   mercado?* A média nacional não importa: aposta se faz jogo a jogo, e só onde
   a diferença é pequena pode existir valor. Este gráfico é a ponte para a
   Fase 6.

**Decisões de desenho, para não terem que ser refeitas depois.**

- **Paleta Okabe-Ito.** Foi construída para ser distinguível por quem tem
  daltonismo (deuteranopia, protanopia) e é a referência mais citada para isso.
  Aqui ela vale para as quatro séries da curva de calibração, sempre na mesma
  ordem — a cor identifica **o modelo**, e nunca a posição dele no ranking. Se
  um modelo sai do gráfico, os outros não mudam de cor.
- **A identidade nunca é só a cor.** Cada série tem marcador próprio e legenda;
  quem imprimir em preto e branco continua conseguindo ler.
- **Uma escala por eixo.** Nenhum gráfico com dois eixos y — é o erro de gráfico
  mais comum que existe, e faz duas medidas de escalas diferentes parecerem
  comparáveis.
- **Fundo branco explícito.** O PNG vai para um Markdown lido em qualquer tema;
  fundo transparente ficaria ilegível em tema escuro.
- **Vírgula decimal nos eixos.** O relatório é lido em português.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

# Backend sem janela: estes gráficos são gerados por script, nunca na tela.
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402 - depende do backend acima
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from futebol.avaliacao import metricas, validacao  # noqa: E402

#: Paleta categórica Okabe-Ito, na ordem fixa em que é atribuída.
#: Azul, laranja, verde, vermelhão, roxo — nunca sorteada, nunca reciclada.
PALETA: tuple[str, ...] = ("#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7")

#: Marcadores, na mesma ordem: a identidade da série não depende só da cor.
MARCADORES: tuple[str, ...] = ("o", "s", "^", "D", "v")

#: Tinta do texto e dos elementos recessivos. Texto nunca usa a cor da série.
TINTA = "#1A1A1A"
TINTA_SECUNDARIA = "#5A5A5A"
GRADE = "#DDDDDD"

#: Cor do fundo. Explícita, e não transparente (ver o topo do módulo).
FUNDO = "#FFFFFF"

#: Resolução dos arquivos. 150 dpi deixa o texto nítido num monitor comum sem
#: gerar arquivo grande — os dois PNG somados ficam abaixo de 300 KB.
DPI = 150


def _virgula(casas: int = 2) -> FuncFormatter:
    """Formata o eixo com vírgula decimal, como se lê em português."""
    return FuncFormatter(lambda valor, _: f"{valor:.{casas}f}".replace(".", ","))


def _porcentagem() -> FuncFormatter:
    return FuncFormatter(lambda valor, _: f"{valor:.0%}".replace("%", "%"))


def _eixos(largura: float = 8.0, altura: float = 5.2):
    """Uma figura com eixos recessivos: sem moldura, grade fraca, texto escuro."""
    figura, eixo = plt.subplots(figsize=(largura, altura), dpi=DPI)
    figura.patch.set_facecolor(FUNDO)
    eixo.set_facecolor(FUNDO)
    for lado in ("top", "right"):
        eixo.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        eixo.spines[lado].set_color(GRADE)
    eixo.tick_params(colors=TINTA_SECUNDARIA, labelsize=9, length=3)
    eixo.grid(True, color=GRADE, linewidth=0.8, alpha=0.9)
    eixo.set_axisbelow(True)
    return figura, eixo


def _salvar(figura, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    figura.tight_layout()
    figura.savefig(destino, facecolor=FUNDO, bbox_inches="tight")
    plt.close(figura)
    return destino


# ----------------------------------------------------------------------------
# 1. Calibração
# ----------------------------------------------------------------------------
def dados_de_calibracao(previsoes: pd.DataFrame) -> pd.DataFrame:
    """A tabela de calibração de um conjunto de previsões, pronta para o gráfico.

    Cada linha é uma faixa de probabilidade: o que foi previsto na média e o que
    de fato aconteceu. Um jogo de 1X2 contribui com **três** afirmações (a
    chance do mandante, a do empate e a do visitante), porque calibração se mede
    por afirmação de probabilidade, não por partida.
    """
    probabilidades = previsoes[list(validacao.CHAVES_1X2)].to_numpy(dtype=float)
    observado = previsoes["observado"].to_numpy(dtype=int)
    return pd.DataFrame(metricas.tabela_calibracao(probabilidades, observado))


def curva_calibracao(
    previsoes: dict[str, pd.DataFrame],
    destino: Path,
    titulo: str = "Calibração no 1X2 — o que foi dito contra o que aconteceu",
    subtitulo: str = "",
) -> Path:
    """Desenha a curva de calibração de cada conjunto de previsões.

    Args:
        previsoes: ``{nome: previsões}``, já recortadas para os mesmos jogos.
        destino: caminho do PNG.
        titulo: título do gráfico.
        subtitulo: linha menor, para dizer a janela e as ligas (regra 13).

    Como ler: a diagonal é a calibração perfeita. Um ponto **abaixo** dela quer
    dizer que o evento aconteceu menos do que o modelo prometeu — confiança
    demais. Acima, o contrário: o modelo foi tímido.
    """
    figura, eixo = _eixos(largura=6.8, altura=6.8)
    # Proporção 1:1: num gráfico de calibração os dois eixos são a mesma coisa
    # (probabilidade), e só com aspecto igual a diagonal fica de fato a 45° —
    # que é o que deixa "acima da linha" e "abaixo da linha" legíveis de relance.
    eixo.set_aspect("equal", adjustable="box")

    # A diagonal é referência, não série: cinza, tracejada, sem entrada própria
    # na legenda que competisse com os modelos.
    eixo.plot(
        [0, 1], [0, 1], color=TINTA_SECUNDARIA, linewidth=1.0, linestyle=(0, (4, 4))
    )
    eixo.annotate(
        "calibração perfeita",
        xy=(0.78, 0.78),
        xytext=(0.80, 0.755),
        color=TINTA_SECUNDARIA,
        fontsize=8,
        rotation=45,
        rotation_mode="anchor",
    )

    for posicao, (nome, conjunto) in enumerate(previsoes.items()):
        tabela = dados_de_calibracao(conjunto)
        eixo.plot(
            tabela["previsto"],
            tabela["observado"],
            color=PALETA[posicao % len(PALETA)],
            marker=MARCADORES[posicao % len(MARCADORES)],
            markersize=5,
            linewidth=2.0,
            label=nome,
        )

    eixo.set_xlim(0, 1)
    eixo.set_ylim(0, 1)
    eixo.xaxis.set_major_formatter(_porcentagem())
    eixo.yaxis.set_major_formatter(_porcentagem())
    eixo.set_xlabel("probabilidade que o modelo deu", color=TINTA, fontsize=10)
    eixo.set_ylabel("frequência com que aconteceu", color=TINTA, fontsize=10)
    eixo.set_title(titulo, color=TINTA, fontsize=12, loc="left", pad=22)
    if subtitulo:
        eixo.text(
            0.0,
            1.015,
            subtitulo,
            transform=eixo.transAxes,
            color=TINTA_SECUNDARIA,
            fontsize=9,
        )

    legenda = eixo.legend(
        frameon=False, fontsize=9, loc="upper left", labelcolor=TINTA
    )
    for texto in legenda.get_texts():
        texto.set_color(TINTA)
    return _salvar(figura, destino)


# ----------------------------------------------------------------------------
# 2. Distância do mercado, por liga
# ----------------------------------------------------------------------------
def distancia_do_mercado(
    tabela: pd.DataFrame,
    destino: Path,
    coluna_modelo: str,
    coluna_mercado: str = "mercado (fechamento)",
    titulo: str = "Quanto o modelo perde do mercado, por competição",
    subtitulo: str = "",
) -> Path:
    """Barras horizontais com a diferença de log loss entre modelo e mercado.

    Args:
        tabela: saída de :func:`futebol.avaliacao.validacao.por_liga`.
        destino: caminho do PNG.
        coluna_modelo: nome da coluna do modelo escolhido.
        coluna_mercado: nome da coluna do mercado.
        titulo: título.
        subtitulo: linha menor (janela, número de jogos, ligas).

    Uma série só, então não há legenda: o título já diz o que a barra é. Barra
    curta é competição onde o modelo quase empata com o mercado — e é lá que a
    Fase 6 vai procurar aposta com valor. Barra negativa (se houver) é
    competição onde o modelo **ganhou** do mercado, e merece desconfiança antes
    de comemoração.
    """
    dados = tabela.assign(distancia=tabela[coluna_modelo] - tabela[coluna_mercado])
    dados = dados.sort_values("distancia")

    altura = max(4.0, 0.26 * len(dados) + 1.6)
    figura, eixo = _eixos(altura=altura)
    eixo.grid(False)
    eixo.xaxis.grid(True, color=GRADE, linewidth=0.8)

    posicoes = np.arange(len(dados))
    # Uma cor só, porque é uma medida só. O destaque vai para o sinal: perder do
    # mercado (o caso normal) em azul, ganhar do mercado em laranja, que é a
    # exceção que pede conferência.
    cores = [PALETA[0] if valor >= 0 else PALETA[1] for valor in dados["distancia"]]
    eixo.barh(posicoes, dados["distancia"], color=cores, height=0.62)

    # Folga lateral: sem ela, o rótulo da barra mais negativa é desenhado por
    # cima do nome da competição.
    eixo.margins(x=0.14)
    eixo.set_yticks(posicoes)
    eixo.set_yticklabels(dados["liga"], fontsize=8.5, color=TINTA)
    eixo.axvline(0, color=TINTA_SECUNDARIA, linewidth=1.0)
    eixo.xaxis.set_major_formatter(_virgula(3))
    eixo.set_xlabel(
        "log loss do modelo − log loss do mercado  (menor é melhor)",
        color=TINTA,
        fontsize=10,
    )
    eixo.set_title(titulo, color=TINTA, fontsize=12, loc="left", pad=22)
    if subtitulo:
        eixo.text(
            0.0,
            1.012,
            subtitulo,
            transform=eixo.transAxes,
            color=TINTA_SECUNDARIA,
            fontsize=9,
        )

    # Rótulo direto só nas pontas: o valor de cada barra numa lista de 38 seria
    # ruído. Quem quiser o número de todas tem a tabela no relatório.
    for posicao, valor, liga in zip(
        posicoes, dados["distancia"], dados["liga"], strict=True
    ):
        if liga in (dados["liga"].iloc[0], dados["liga"].iloc[-1]):
            eixo.annotate(
                f"{valor:+.3f}".replace(".", ","),
                xy=(valor, posicao),
                xytext=(4 if valor >= 0 else -4, 0),
                textcoords="offset points",
                va="center",
                ha="left" if valor >= 0 else "right",
                fontsize=8.5,
                color=TINTA,
            )

    return _salvar(figura, destino)


# ----------------------------------------------------------------------------
# 3. Importancia das features (Fase 5)
# ----------------------------------------------------------------------------
def importancia_das_features(
    importancia: pd.DataFrame,
    destino: Path,
    titulo: str = "De onde o LightGBM tira o que ele sabe",
) -> Path:
    """Barras horizontais da importancia relativa de cada feature.

    Args:
        importancia: colunas ``feature``, ``pct`` e ``familia``, ja ordenada da
            mais importante para a menos.
        destino: caminho do PNG.

    As barras sao coloridas por **familia** de feature, e nao uma cor por
    feature: o que a figura tem a dizer e de qual origem vem o conhecimento do
    modelo, e vinte e tres cores distintas esconderiam isso atras de um
    arco-iris. A legenda traz a soma de cada familia, que e o numero que
    responde a pergunta.
    """
    ordenada = importancia.sort_values("pct")
    familias = list(dict.fromkeys(importancia["familia"]))
    cor_da_familia = {
        familia: PALETA[indice % len(PALETA)]
        for indice, familia in enumerate(familias)
    }

    altura = max(4.0, 0.28 * len(ordenada) + 1.4)
    figura, eixo = _eixos(largura=8.5, altura=altura)
    eixo.grid(axis="y", visible=False)

    eixo.barh(
        ordenada["feature"],
        ordenada["pct"],
        color=[cor_da_familia[f] for f in ordenada["familia"]],
        height=0.72,
    )
    eixo.xaxis.set_major_formatter(_virgula(0))
    eixo.set_xlabel("participacao no ganho das arvores (%)", color=TINTA_SECUNDARIA)
    eixo.set_title(titulo, color=TINTA, fontsize=12, pad=12, loc="left")

    somas = importancia.groupby("familia")["pct"].sum()
    alcas = [
        Patch(
            facecolor=cor_da_familia[familia],
            label=f"{familia} ({somas[familia]:.0f}%)".replace(".", ","),
        )
        for familia in familias
    ]
    eixo.legend(
        handles=alcas,
        frameon=False,
        fontsize=9,
        labelcolor=TINTA,
        loc="lower right",
    )
    return _salvar(figura, destino)
