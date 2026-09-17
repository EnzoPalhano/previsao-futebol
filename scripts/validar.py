"""Roda o walk-forward de validacao e escolhe o modelo (regra 9).

Uso::

    python scripts/validar.py                 # mede tudo (usa cache) e mostra a tabela
    python scripts/validar.py --forcar        # recalcula tudo, ignorando o cache
    python scripts/validar.py --inicio 2022-07-01
    python scripts/validar.py --so-um dixon-coles

DEMORA. Sao 13 configuracoes, cada uma reajustando o modelo antes de CADA data
em que cada uma das 38 competicoes jogou - mais de dez mil ajustes por
configuracao. A primeira rodada leva de 20 a 40 minutos; as seguintes leem o
cache em data/processed/validacao/ e sao instantaneas.

ATENCAO: as temporadas de teste final ficam trancadas (regra 7), e a escolha e
por LOG LOSS, nunca por ROI (regra 9). Quem escreve o relatorio e o grafico e o
scripts/relatorio_fase4.py, que le este mesmo cache.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from futebol import relatorio
from futebol.avaliacao import divisao, selecao, validacao
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.terminal import preparar_saida


def main(argv: list[str] | None = None) -> int:
    preparar_saida()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inicio",
        default=selecao.INICIO_VALIDACAO,
        help="inicio da janela de validacao (padrao: %(default)s)",
    )
    parser.add_argument(
        "--forcar", action="store_true", help="ignora o cache e mede de novo"
    )
    parser.add_argument(
        "--so-um",
        default=None,
        help="mede apenas o candidato com este nome (ex.: dixon-coles)",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    try:
        jogos = limpeza.carregar(cfg)
    except limpeza.ErroDeLimpeza as erro:
        print(f"ERRO: {erro}")
        return 1

    separacao = divisao.separar(jogos, cfg)
    liberados = separacao.jogos
    print(f"Camada ativa: {cfg.camada_ativa}")
    print(separacao.resumo())

    fim = pd.Timestamp(liberados["data"].max()) + pd.Timedelta(days=1)
    print(f"Janela de validacao: {pd.Timestamp(args.inicio).date()} a {fim.date()}")

    lista = selecao.candidatos(cfg, liberados, args.inicio)
    if args.so_um is not None:
        lista = [c for c in lista if c.nome == args.so_um]
        if not lista:
            print(f"ERRO: nao existe candidato chamado {args.so_um!r}.")
            return 2

    print(f"\n{len(lista)} configuracao(oes) a medir:")
    for candidato in lista:
        print(f"  {candidato.nome:<16s} {candidato.descricao}")

    print()
    previsoes = {
        candidato.nome: selecao.rodar_candidato(
            liberados, candidato, cfg, args.inicio, fim, args.forcar, aviso=print
        )
        for candidato in lista
    }

    print("\nAcrescentando o mercado de fechamento como referencia...")
    do_mercado = validacao.previsoes_do_mercado(
        liberados.loc[
            (liberados["data"] >= pd.Timestamp(args.inicio)) & (liberados["data"] < fim)
        ]
    )

    escolha = selecao.escolher(previsoes, lista)
    medidas, _ = validacao.medir_nos_mesmos_jogos(
        {**previsoes, "mercado (fechamento)": do_mercado}
    )
    ordenadas = sorted(medidas, key=lambda m: m.log_loss)

    print(
        f"\n{'configuracao':<22s} {'jogos':>7s} {'log loss':>9s} {'brier':>8s} "
        f"{'acuracia':>9s} {'ECE':>7s}"
    )
    for medida in ordenadas:
        print(
            f"{medida.nome:<22s} {medida.n:7d} {medida.log_loss:9.4f} "
            f"{medida.brier:8.4f} {medida.acuracia:9.1%} {medida.ece:7.4f}"
        )

    print(
        f"\nESCOLHIDO (regra 9, menor log loss entre modelos): {escolha.vencedor.nome}"
    )
    print(f"  parametros: {escolha.parametros}")
    print(f"  log loss: {relatorio.num(escolha.vencedor.log_loss)}")
    print(
        f"  margem sobre o segundo colocado: {relatorio.num(escolha.margem, 5)} "
        "de log loss"
    )
    print(f"  configuracoes disputando (regra 11): {escolha.n_configuracoes}")
    print(
        "\nO mercado nao disputa a escolha: ele e a referencia. "
        "Modelo nao se escolhe por ROI (regra 9)."
    )
    print("\nPara o relatorio e os graficos: python scripts/relatorio_fase4.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
