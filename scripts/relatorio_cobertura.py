"""Gera o relatorio de cobertura de dados da Fase 1d.

Uso::

    python scripts/relatorio_cobertura.py          # grava o .md e resume no terminal
    python scripts/relatorio_cobertura.py --so-ver # so mostra, nao grava

Le ``data/processed/jogos.parquet`` (rode ``python scripts/preparar_dados.py``
antes) e responde a pergunta que decide o tamanho real do projeto: quantos
jogos existem e em quantos deles existe odd, por liga, por temporada e por
mercado.

O relatorio vai para ``docs/relatorios/cobertura_fase1.md`` e VAI para o Git:
ele e a fotografia dos dados que geraram os resultados daquela fase.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from futebol.config import carregar_config
from futebol.dados import cobertura, limpeza
from futebol.terminal import preparar_saida


def main(argv: list[str] | None = None) -> int:
    # Nome de clube estrangeiro derruba o console cp1252 do Windows.
    preparar_saida()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--so-ver",
        action="store_true",
        help="mostra o resumo no terminal sem gravar o arquivo",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    try:
        jogos = limpeza.carregar(cfg)
    except limpeza.ErroDeLimpeza as erro:
        print(f"ERRO: {erro}")
        return 1

    texto = cobertura.relatorio_markdown(
        jogos, camada=cfg.camada_ativa, gerado_em=date.today().isoformat()
    )

    print(f"Camada ativa: {cfg.camada_ativa}")
    print(f"Jogos na tabela: {len(jogos)}\n")

    resumo = cobertura.por(jogos, ["grupo", "liga"])
    for _, linha in resumo.iterrows():
        # No terminal usamos a chave do mercado (1x2_pre), sem acento: o console
        # do Windows nao usa UTF-8 por padrao e trocaria "pre-jogo" por lixo.
        faltas = "  ".join(
            f"{m}: {(linha[f'falta_{m}'] * 100):.1f}% faltando" for m in cobertura.MERCADOS
        )
        print(f"  {linha['liga']:<5s} ({linha['grupo']}) {int(linha['jogos']):>7d} jogos")
        print(f"        {faltas}")

    vies = cobertura.vies_de_selecao(jogos)
    print(
        f"\nJogos do Grupo 1 sem odd 1X2 pre-jogo: {vies.jogos_sem_odd} "
        f"({vies.fracao * 100:.1f}%) - nao podem virar aposta simulada."
    )
    if vies.jogos_sem_odd and not vies.parece_aleatorio:
        print(
            "ATENCAO: esses jogos tem media de gols diferente dos demais. "
            "Descarta-los muda a amostra; a Fase 6 precisa declarar o que faz com eles."
        )

    if args.so_ver:
        print("\n--so-ver: nada foi gravado.")
        return 0

    destino = cfg.raiz / "docs" / "relatorios" / "cobertura_fase1.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(f"\nRelatorio gravado: {destino.relative_to(cfg.raiz)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
