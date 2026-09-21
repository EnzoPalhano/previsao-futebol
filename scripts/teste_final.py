"""Abre o cofre e mede, uma vez. A Fase 9.

Uso::

    python scripts/teste_final.py            # roda e grava o relatorio
    python scripts/teste_final.py --so-ver   # mede e mostra, sem gravar

ATENCAO, e nao e formalidade: este comando le as temporadas que estiveram
TRANCADAS desde a Fase 1. Elas existem para responder uma pergunta uma vez. Se
o resultado desagradar, o resultado e esse - mexer num parametro e rodar de
novo transforma o teste final em mais um conjunto de validacao, e ai o numero
nao significa mais nada.

A configuracao vem do pre-registro congelado em futebol.avaliacao.teste_final,
e conferir_config() compara ela com o config.yaml ANTES de abrir qualquer
coisa. Config mexido depois do pre-registro para o comando.

Escreve em docs/relatorios/:
  final.md                    o relatorio final
  final_banca.png             a banca no teste final, em escala log
  final_clv_por_liga.png      o CLV liga a liga, com o intervalo de cada uma
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from futebol.avaliacao import relatorio_final, teste_final
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.terminal import preparar_saida

#: Onde os arquivos da fase sao gravados.
PASTA = "docs/relatorios"


def main() -> int:
    preparar_saida()
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument(
        "--so-ver",
        action="store_true",
        help="mede e mostra o resumo, sem gravar o relatorio",
    )
    analise.add_argument(
        "--forcar",
        action="store_true",
        help="refaz o walk-forward do teste final em vez de ler o cache",
    )
    argumentos = analise.parse_args()

    cfg = carregar_config()

    print("Conferindo o pre-registro contra o config.yaml...")
    try:
        teste_final.conferir_config(cfg)
    except teste_final.PreRegistroViolado as erro:
        print(f"\nPARADO: {erro}", file=sys.stderr)
        return 1
    print("  confere: a configuracao e a que foi registrada em 21/09/2026.\n")

    print("Carregando a tabela de jogos (INTEIRA, inclusive o cofre)...")
    jogos = limpeza.carregar(cfg)
    print(f"  {len(jogos)} jogos.\n")

    print("Abrindo o cofre e medindo. Isto leva alguns minutos.")
    resultado = teste_final.rodar(
        jogos, cfg, aviso=lambda linha: print(linha), forcar=argumentos.forcar
    )
    print()

    print(relatorio_final.resumo_para_o_terminal(resultado))

    if argumentos.so_ver:
        print("\n(--so-ver: nada foi gravado.)")
        return 0

    caminhos = relatorio_final.escrever(resultado, cfg, PASTA, hoje=date.today())
    print("\nGravado:")
    for caminho in caminhos:
        print(f"  {caminho}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
