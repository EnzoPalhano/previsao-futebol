"""Previsao de um jogo, na linha de comando.

Uso::

    python scripts/prever.py --mandante "Arsenal" --visitante "Chelsea"
    python scripts/prever.py --mandante "Palmeiras" --visitante "Flamengo" --modelo poisson
    python scripts/prever.py --mandante "ENG:Everton" --visitante "Liverpool" --data 2026-10-01
    python scripts/prever.py --mandante Arsenal --visitante Chelsea --forcas

O que o script faz, em ordem:

1. traduz os dois nomes em chaves PAIS:nome e descobre a competicao
   (futebol.consulta). Nome ambiguo e ERRO, nunca chute - existe Everton na
   Inglaterra e no Chile;
2. treina o modelo com os jogos ANTERIORES a data pedida (regra 6). Por isso
   trocar a data muda a previsao: o modelo so ve o passado daquele dia;
3. mostra as probabilidades de 1X2, Over/Under 2,5, ambos marcam e o placar
   mais provavel, todas tiradas da mesma matriz de placares.

ATENCAO: a "odd justa" mostrada e 1/probabilidade, SEM margem de casa. Ela nao
e uma recomendacao de aposta: comparar com a odd da casa, calcular valor
esperado e decidir stake e assunto da Fase 6. Aqui so se ve o que o modelo
pensa.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from futebol.avaliacao import divisao
from futebol.config import carregar_config
from futebol.consulta import ErroDeConsulta, montar
from futebol.dados import limpeza
from futebol.modelos import base
from futebol.modelos.baseline import Baseline
from futebol.modelos.dixon_coles import DixonColes
from futebol.modelos.poisson import Poisson
from futebol.terminal import preparar_saida

#: Os modelos que o script sabe rodar. A chave e o que se escreve em --modelo.
MODELOS = {
    "baseline": Baseline,
    "poisson": Poisson,
    "dixon_coles": DixonColes,
}

#: Como cada mercado aparece na tela: (titulo, chaves da previsao).
MERCADOS = (
    ("1X2", ("H", "D", "A")),
    ("Gols (2,5)", ("over25", "under25")),
    ("Ambos marcam", ("ambos_marcam", "ambos_nao_marcam")),
)

#: Nome legivel de cada chave de previsao.
ROTULOS = {
    "H": "vitoria do mandante",
    "D": "empate",
    "A": "vitoria do visitante",
    "over25": "mais de 2,5 gols",
    "under25": "menos de 2,5 gols",
    "ambos_marcam": "ambos marcam",
    "ambos_nao_marcam": "nao ambos marcam",
}


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--mandante", required=True, help="time da casa")
    parser.add_argument("--visitante", required=True, help="time visitante")
    parser.add_argument(
        "--liga", default=None, help="codigo da competicao (E0, SP1...); padrao: deduzida"
    )
    parser.add_argument(
        "--modelo",
        default="dixon_coles",
        choices=sorted(MODELOS),
        help="modelo a usar (padrao: %(default)s)",
    )
    parser.add_argument(
        "--data",
        default=None,
        help="data do jogo (AAAA-MM-DD). O treino usa so o que veio antes dela. "
        "Padrao: o dia seguinte ao ultimo jogo da tabela",
    )
    parser.add_argument(
        "--forcas",
        action="store_true",
        help="mostra tambem a tabela de forcas de ataque e defesa da liga",
    )
    parser.add_argument(
        "--placares",
        type=int,
        default=5,
        help="quantos placares mais provaveis listar (padrao: %(default)s)",
    )
    return parser


def _linha_de_mercado(chave: str, probabilidade: float) -> str:
    odd_justa = 1.0 / probabilidade if probabilidade > 0 else float("inf")
    return (
        f"  {ROTULOS[chave]:<22s} {probabilidade:6.1%}"
        f"   odd justa {odd_justa:6.2f}"
    )


def _placares_mais_provaveis(matriz, quantos: int) -> list[tuple[int, int, float]]:
    """Os ``quantos`` placares de maior probabilidade, do maior para o menor."""
    achatada = matriz.ravel()
    melhores = achatada.argsort()[::-1][:quantos]
    return [
        (int(indice // matriz.shape[1]), int(indice % matriz.shape[1]), float(achatada[indice]))
        for indice in melhores
    ]


def main(argv: list[str] | None = None) -> int:
    preparar_saida()
    args = montar_parser().parse_args(argv)

    cfg = carregar_config()
    jogos = limpeza.carregar(cfg)

    # Sem --data, a previsao e "para amanha": o dia seguinte ao ultimo jogo que
    # existe na tabela. Assim o treino usa tudo que ha de historico, e nunca um
    # jogo do proprio dia (regra 6).
    data = (
        pd.Timestamp(args.data)
        if args.data
        else pd.Timestamp(jogos["data"].max()) + pd.Timedelta(days=1)
    )

    try:
        resolucao = montar(jogos, args.mandante, args.visitante, args.liga, data)
    except ErroDeConsulta as erro:
        print(f"ERRO: {erro}")
        return 2

    jogo = resolucao.jogo

    # Sem jogo daquela liga antes da data, o modelo nem chega a ser ajustado
    # para ela - e o erro que sairia ("liga nao estava no treino") esconderia a
    # causa de verdade, que e a data pedida ser anterior ao inicio da liga na
    # tabela. O Grupo 1 comeca em 2019/20; o Grupo 2, em 2012.
    da_liga = jogos[(jogos["liga"] == jogo.liga) & (jogos["data"] < data)]
    if da_liga.empty:
        primeiro = jogos.loc[jogos["liga"] == jogo.liga, "data"].min()
        print(
            f"ERRO: a liga {jogo.liga} nao tem nenhum jogo anterior a "
            f"{data.date()} na tabela. O primeiro jogo dela e de "
            f"{pd.Timestamp(primeiro).date()} - escolha uma --data depois disso."
        )
        return 2

    modelo = MODELOS[args.modelo](cfg=cfg)
    try:
        modelo.treinar(jogos, ate_data=data)
        previsao = modelo.prever(jogo)
        matriz = modelo.matriz_de_placares(jogo)
    except base.ErroDeModelo as erro:
        print(f"ERRO: {erro}")
        return 2

    print("=" * 66)
    print(f"{jogo.mandante}  x  {jogo.visitante}")
    print("=" * 66)
    print(f"Competicao : {resolucao.explicacao_liga}")
    print(f"Data       : {data.date()}")
    print(f"Modelo     : {modelo.nome}")
    print(
        f"Treino     : jogos anteriores a {data.date()} "
        f"(o mais recente e de {modelo.ultima_data_de_treino.date()})"
    )
    if isinstance(modelo, DixonColes):
        print(
            f"             decaimento xi={modelo.xi} "
            f"(meia-vida de {modelo.meia_vida_em_dias:.0f} dias), "
            f"rho={modelo.rho_da_liga(jogo.liga):+.4f}"
        )
    print(
        f"Historico  : {resolucao.jogos_do_mandante} jogos do mandante e "
        f"{resolucao.jogos_do_visitante} do visitante nesta liga"
    )
    if min(resolucao.jogos_do_mandante, resolucao.jogos_do_visitante) < 10:
        print(
            "             ATENCAO: pouco historico. A forca do time foi encolhida "
            "para a media da liga."
        )
    if divisao.usa_teste_final(base.jogos_ate(jogos, data), cfg):
        print(
            "             NOTA: o treino inclui as temporadas de teste final. "
            "Para prever um jogo de\n"
            "             verdade isso e o correto, mas uma rodada assim NUNCA "
            "serve para comparar\n"
            "             modelos nem escolher parametro (regra 7)."
        )

    if isinstance(modelo, Poisson):
        lam, mu = modelo.medias(jogo)
        print(f"Gols esperados: {lam:.2f} (mandante)  x  {mu:.2f} (visitante)")

    for titulo, chaves in MERCADOS:
        print(f"\n{titulo}")
        for chave in chaves:
            print(_linha_de_mercado(chave, previsao[chave]))

    print("\nPlacares mais provaveis")
    for gols_mandante, gols_visitante, probabilidade in _placares_mais_provaveis(
        matriz, args.placares
    ):
        print(f"  {gols_mandante} x {gols_visitante}   {probabilidade:6.1%}")
    print(
        "  (o placar mais provavel de um jogo de futebol fica em 10%-13%: o mais "
        "provavel e que ele NAO aconteca)"
    )

    if args.forcas:
        if not isinstance(modelo, Poisson):
            print(f"\n(o modelo {modelo.nome} nao tem forcas por time)")
        else:
            print(f"\nForcas da liga {jogo.liga} (ataque e defesa em log; positivo e melhor)")
            tabela = modelo.ajuste_da_liga(jogo.liga).tabela_de_forcas()
            print(
                tabela.to_string(
                    index=False,
                    float_format=lambda v: f"{v:6.3f}",
                    columns=["time", "ataque", "defesa", "jogos", "peso", "peso_proprio"],
                )
            )

    print(
        "\nA odd justa acima NAO tem margem de casa e NAO e recomendacao de "
        "aposta.\nComparar com a odd da casa e decidir stake e a Fase 6."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
