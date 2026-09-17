"""Gera o relatorio da Fase 3 em docs/relatorios/fase3.md.

Uso::

    python scripts/relatorio_fase3.py             # mede tudo e gera o relatorio
    python scripts/relatorio_fase3.py --so-ver    # mostra o inicio, nao grava
    python scripts/relatorio_fase3.py --inicio 2022-07-01

Mede os tres modelos da fase fora da amostra, reajustando cada um no dia 1o de
cada mes, e responde: eles batem o baseline burro? a que distancia ficam do
mercado? o fator casa por liga vale a pena? o decaimento temporal ajuda?

DEMORA alguns minutos: sao treze configuracoes, cada uma com um ajuste por liga
por mes da janela.

ATENCAO: nada aqui toca as temporadas de teste final (regra 7) - a trava esta em
futebol/avaliacao/divisao.py. E nenhum numero daqui escolhe modelo nem
parametro: o criterio oficial e a log loss no walk-forward da Fase 4 (regra 9).

Rode antes: scripts/preparar_dados.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from futebol.avaliacao import relatorio_fase3
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.terminal import preparar_saida


def main(argv: list[str] | None = None) -> int:
    preparar_saida()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--so-ver", action="store_true", help="mostra o comeco sem gravar o arquivo"
    )
    parser.add_argument(
        "--inicio",
        default=relatorio_fase3.INICIO_PADRAO,
        help="inicio da janela de avaliacao (padrao: %(default)s)",
    )
    parser.add_argument(
        "--passo",
        default=relatorio_fase3.PASSO_PADRAO,
        help="frequencia de reajuste do modelo, no padrao do pandas "
        "(MS = mensal, W = semanal). Padrao: %(default)s",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    try:
        jogos = limpeza.carregar(cfg)
    except limpeza.ErroDeLimpeza as erro:
        print(f"ERRO: {erro}")
        return 1

    print(f"Camada ativa: {cfg.camada_ativa}  |  {len(jogos)} jogos na tabela")
    texto = relatorio_fase3.gerar(
        jogos,
        cfg,
        gerado_em=date.today().isoformat(),
        inicio=args.inicio,
        passo=args.passo,
    )

    if args.so_ver:
        print(texto[:3000])
        print("\n[...] --so-ver: nada foi gravado.")
        return 0

    destino = cfg.raiz / "docs" / "relatorios" / "fase3.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    linhas = texto.count("\n") + 1
    print(f"\nRelatorio gravado: {destino.relative_to(cfg.raiz)} ({linhas} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
