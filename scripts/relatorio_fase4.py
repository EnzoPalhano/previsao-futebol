"""Gera o relatorio da Fase 4 em docs/relatorios/fase4.md, com os graficos.

Uso::

    python scripts/relatorio_fase4.py             # le o cache e escreve tudo
    python scripts/relatorio_fase4.py --so-ver    # mostra o comeco, nao grava
    python scripts/relatorio_fase4.py --forcar    # remede tudo (demora ~30 min)

Le o cache de previsoes gravado por scripts/validar.py. Se o cache nao existir,
ele e criado - e ai o comando demora meia hora, porque sao 13 configuracoes com
mais de dez mil ajustes de modelo cada.

Escreve tres arquivos em docs/relatorios/:
  fase4.md                        o relatorio
  fase4_calibracao.png            curva de calibracao dos modelos e do mercado
  fase4_distancia_do_mercado.png  quanto o modelo perde do mercado, por liga

ATENCAO: as temporadas de teste final ficam trancadas (regra 7) e a escolha de
modelo e por log loss (regra 9).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from futebol.avaliacao import relatorio_fase4, selecao
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.terminal import preparar_saida


def main(argv: list[str] | None = None) -> int:
    preparar_saida()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--so-ver", action="store_true", help="mostra o comeco sem gravar o .md"
    )
    parser.add_argument(
        "--forcar", action="store_true", help="ignora o cache e mede de novo"
    )
    parser.add_argument(
        "--inicio",
        default=selecao.INICIO_VALIDACAO,
        help="inicio da janela de validacao (padrao: %(default)s)",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    try:
        jogos = limpeza.carregar(cfg)
    except limpeza.ErroDeLimpeza as erro:
        print(f"ERRO: {erro}")
        return 1

    print(f"Camada ativa: {cfg.camada_ativa}  |  {len(jogos)} jogos na tabela")
    texto = relatorio_fase4.gerar(
        jogos,
        cfg,
        gerado_em=date.today().isoformat(),
        inicio=args.inicio,
        forcar=args.forcar,
    )

    if args.so_ver:
        print(texto[:3000])
        print("\n[...] --so-ver: o .md nao foi gravado (os graficos, sim).")
        return 0

    destino = cfg.raiz / "docs" / "relatorios" / "fase4.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    linhas = texto.count("\n") + 1
    print(f"\nRelatorio gravado: {destino.relative_to(cfg.raiz)} ({linhas} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
