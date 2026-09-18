"""Simula as apostas do modelo oficial e responde "teria dado lucro?".

Uso::

    python scripts/backtest.py                          # o do config.yaml
    python scripts/backtest.py --ev 0.10                # so aposta com EV > 10%
    python scripts/backtest.py --estrategia kelly_fracionado --tipo-banca composta
    python scripts/backtest.py --liga E0 --liga SP1     # so essas ligas
    python scripts/backtest.py --grade                  # varre os 4 limites de EV
    python scripts/backtest.py --gravar apostas.csv     # grava o registro de cada aposta

Le as previsoes do walk-forward gravadas por scripts/validar.py. Se o cache nao
existir, ele e criado - e ai o comando demora uns minutos, porque sao mais de
dez mil ajustes de modelo.

ATENCAO (regra 8): a aposta e SEMPRE na odd media pre-jogo (Avg*). A odd de
fechamento entra apenas para medir CLV. A Max nao e usada em lugar nenhum.

ATENCAO (regra 9): nada aqui escolhe modelo. A escolha foi por log loss na
Fase 4; o ROI e consequencia reportada, nunca criterio.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from futebol import relatorio
from futebol.avaliacao import divisao, selecao
from futebol.backtest import estrategias, simulador
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.terminal import preparar_saida


def _com_sinal(valor: float, casas: int = 2) -> str:
    return ("+" if valor >= 0 else "") + relatorio.pct(valor, casas)


def _mostrar(resultado: simulador.Resultado, titulo: str) -> None:
    print(f"\n{titulo}")
    print(f"  apostas ......... {relatorio.inteiro(resultado.n)}")
    print(f"  taxa de acerto .. {relatorio.pct(resultado.taxa_acerto)}")
    print(f"  odd media ....... {relatorio.num(resultado.odd_media, 2)}")
    print(
        f"  ROI ............. {_com_sinal(resultado.roi)}  "
        f"(IC 95%: {_com_sinal(resultado.roi_ic[0])} a {_com_sinal(resultado.roi_ic[1])}; "
        f"menor ROI detectavel: {relatorio.pct(resultado.roi_detectavel)})"
    )
    print(
        f"  CLV ............. {_com_sinal(resultado.clv)}  "
        f"(IC 95%: {_com_sinal(resultado.clv_ic[0])} a {_com_sinal(resultado.clv_ic[1])}; "
        f"n = {relatorio.inteiro(resultado.n_clv)})"
    )
    print(f"  CLV bruto ....... {_com_sinal(resultado.clv_bruto, 3)}")


def main(argv: list[str] | None = None) -> int:
    preparar_saida()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ev", type=float, default=None,
        help="limite de valor esperado (padrao: o ev_minimo do config.yaml)",
    )
    parser.add_argument(
        "--banca", type=float, default=None, help="banca inicial em reais"
    )
    parser.add_argument(
        "--estrategia", default=None, choices=["stake_fixa", "kelly_fracionado"],
        help="qual regra de stake detalhar na tela (padrao: a do config.yaml)",
    )
    parser.add_argument(
        "--tipo-banca", default=None, choices=list(estrategias.TIPOS_DE_BANCA),
        help="qual variante de banca detalhar na tela (as quatro sao calculadas)",
    )
    parser.add_argument(
        "--liga", action="append", default=None,
        help="restringe a uma liga (pode repetir). Padrao: as 18 aprovadas",
    )
    parser.add_argument(
        "--grade", action="store_true",
        help="varre os limites de EV da Fase 6 em vez de rodar um so",
    )
    parser.add_argument(
        "--gravar", nargs="?", const="data/processed/apostas.csv", default=None,
        help="grava o registro de cada aposta em CSV (padrao: %(const)s)",
    )
    parser.add_argument(
        "--forcar", action="store_true",
        help="ignora o cache de previsoes e roda o walk-forward de novo",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    try:
        jogos = limpeza.carregar(cfg)
    except limpeza.ErroDeLimpeza as erro:
        print(f"ERRO: {erro}")
        return 1

    liberados = divisao.separar(jogos, cfg).jogos
    inicio = pd.Timestamp(selecao.INICIO_VALIDACAO)
    fim = pd.Timestamp(liberados["data"].max()) + pd.Timedelta(days=1)

    oficial = selecao.candidato_oficial(cfg, liberados, inicio)
    print(f"Modelo oficial: {oficial.nome} — {oficial.descricao}")
    previsoes = selecao.rodar_candidato(
        liberados, oficial, cfg, inicio, fim, args.forcar, aviso=print
    )

    if args.liga:
        # O recorte e feito ANTES de montar as candidatas, e nao depois. Filtrar
        # a tabela pronta deixaria as contagens de "jogos pulados" valendo para
        # as 18 ligas enquanto o resto da tela fala de uma so - dois escopos na
        # mesma saida, sem aviso nenhum.
        pedidas = [liga.upper() for liga in args.liga]
        aprovadas = set(cfg.bruto["ligas_aprovadas_backtest"])
        desconhecidas = sorted(set(pedidas) - aprovadas)
        if desconhecidas:
            print(
                f"ERRO: liga(s) fora do backtest: {', '.join(desconhecidas)}. "
                f"Aprovadas na Fase 2: {', '.join(sorted(aprovadas))}."
            )
            return 1
        do_recorte = liberados.loc[previsoes.index, "liga"].isin(pedidas)
        previsoes = previsoes.loc[do_recorte.to_numpy()]

    amostra = simulador.preparar(liberados, previsoes, cfg)

    print(f"\nJanela: {inicio.date()} a {fim.date()}")
    plural = "liga" if len(amostra.ligas) == 1 else "ligas"
    print(f"{len(amostra.ligas)} {plural}: {', '.join(amostra.ligas)}")
    print(amostra.resumo())

    if args.grade:
        print("\nVarredura dos limites de EV (regra 11: sao 4 configuracoes):")
        for limite in simulador.GRADE_EV:
            apostas = simulador.selecionar(amostra.candidatos, limite)
            medida = simulador.medir(
                apostas, f"EV>{limite:.0%}", amostras_bootstrap=2000, seed=cfg.seed
            )
            print(
                f"  EV>{limite:>5.0%}: n = {relatorio.inteiro(medida.n):>7}  "
                f"odd {relatorio.num(medida.odd_media, 2)}  "
                f"ROI {_com_sinal(medida.roi):>8}  "
                f"CLV {_com_sinal(medida.clv):>8}"
            )
        return 0

    resultado = simulador.rodar(
        liberados, previsoes, cfg, ev_minimo=args.ev,
        banca_inicial=args.banca, amostra=amostra,
    )
    print(f"\nLimite de EV: {relatorio.pct(resultado.ev_minimo, 0)}")
    _mostrar(resultado.resultado, "MODELO")
    _mostrar(resultado.aleatorio, "ALEATORIA (mesmo numero de apostas, regra 2.6d)")

    print("\nA banca, nas quatro combinacoes (as DUAS variantes sempre):")
    for (estrategia, tipo), evolucao in resultado.evolucoes.items():
        marca = " <--" if (
            estrategia == (args.estrategia or cfg.secao("backtest")["estrategia"])
            and tipo == (args.tipo_banca or cfg.secao("backtest")["tipo_banca"])
        ) else ""
        print(
            f"  {estrategia:<18} banca {tipo:<8} "
            f"final R$ {relatorio.num(evolucao.banca_final, 2):>10}  "
            f"ROI {_com_sinal(evolucao.roi):>8}  "
            f"drawdown {relatorio.pct(evolucao.drawdown_maximo):>7}"
            f"{'  QUEBROU' if evolucao.quebrou else ''}{marca}"
        )

    if args.gravar:
        destino = cfg.raiz / args.gravar
        destino.parent.mkdir(parents=True, exist_ok=True)
        resultado.apostas.to_csv(destino, index=False, encoding="utf-8")
        print(
            f"\nRegistro de {relatorio.inteiro(len(resultado.apostas))} apostas "
            f"gravado em {destino}"
        )

    print(
        "\nLembrete: ROI e CLV sao consequencias reportadas, nunca criterio de "
        "escolha de modelo (regra 9). O relatorio completo da fase, com as "
        "tabelas por liga e por mercado, sai de scripts/relatorio_fase6.py."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
