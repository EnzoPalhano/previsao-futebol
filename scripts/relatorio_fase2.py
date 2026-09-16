"""Gera o relatorio da Fase 2 em docs/relatorios/fase2.md.

Uso::

    python scripts/relatorio_fase2.py            # gera o relatorio
    python scripts/relatorio_fase2.py --so-ver   # mostra o resumo, nao grava

Le data/processed/jogos.parquet e responde as quatro perguntas da fase:
margem por liga, calibracao do mercado, evolucao do fator casa e quais ligas
passaram no filtro de qualidade.

Rode antes: scripts/preparar_dados.py e scripts/filtro_ligas.py.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from futebol.avaliacao import filtro, relatorio_fase2
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.terminal import preparar_saida


def main(argv: list[str] | None = None) -> int:
    preparar_saida()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--so-ver", action="store_true", help="mostra o resumo sem gravar o arquivo"
    )
    parser.add_argument(
        "--repeticoes",
        type=int,
        default=filtro.REPETICOES_PISO,
        help="simulacoes do piso de ruido do ECE (padrao: %(default)s)",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    try:
        jogos = limpeza.carregar(cfg)
    except limpeza.ErroDeLimpeza as erro:
        print(f"ERRO: {erro}")
        return 1

    print(f"Camada ativa: {cfg.camada_ativa}  |  {len(jogos)} jogos")
    print("Medindo margem, calibracao, mando e filtro de qualidade...")

    texto = relatorio_fase2.gerar(
        jogos, cfg, gerado_em=date.today().isoformat(), repeticoes=args.repeticoes
    )

    if args.so_ver:
        print(texto[:3000])
        print("\n[...] --so-ver: nada foi gravado.")
        return 0

    destino = cfg.raiz / "docs" / "relatorios" / "fase2.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    linhas = texto.count("\n") + 1
    print(f"\nRelatorio gravado: {destino.relative_to(cfg.raiz)} ({linhas} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
