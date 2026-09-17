"""Gera o relatorio da Fase 5 em docs/relatorios/fase5.md, com o grafico.

Uso::

    python scripts/relatorio_fase5.py             # le o cache e escreve tudo
    python scripts/relatorio_fase5.py --so-ver    # mostra o comeco, nao grava
    python scripts/relatorio_fase5.py --forcar    # remede tudo (demora ~15 min)

Le o cache de previsoes gravado por `scripts/validar.py --com-gbm`. Se o cache
nao existir, ele e criado - e ai o comando demora, porque sao 16 configuracoes e
cada LightGBM leva cerca de 4 minutos.

Escreve dois arquivos em docs/relatorios/:
  fase5.md                    o relatorio
  fase5_importancia.png       de onde o LightGBM tira o que ele sabe

ATENCAO: as temporadas de teste final ficam trancadas (regra 7) e a escolha de
modelo e por log loss (regra 9), nunca por novidade nem por sofisticacao.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from futebol.avaliacao import divisao, graficos, relatorio_fase5, selecao
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.features import construtor
from futebol.terminal import preparar_saida

#: Onde os arquivos da fase sao gravados.
PASTA = "docs/relatorios"


def main(argv: list[str] | None = None) -> int:
    preparar_saida()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--so-ver", action="store_true", help="mostra o comeco sem gravar o .md"
    )
    parser.add_argument(
        "--forcar", action="store_true", help="ignora o cache e mede de novo"
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

    features = construtor.carregar_ou_construir(cfg, liberados, aviso=print)
    lista = selecao.candidatos(cfg, liberados, inicio) + selecao.candidatos_fase5(
        cfg, features, jogos=liberados
    )
    print(f"\n{len(lista)} configuracoes:")
    previsoes = {
        candidato.nome: selecao.rodar_candidato(
            liberados, candidato, cfg, inicio, fim, args.forcar, aviso=print
        )
        for candidato in lista
    }

    print("\nMedindo a importancia das features...")
    do_gbm = next(c for c in lista if c.nome == "gbm")
    treinado = do_gbm.construir().treinar(liberados, ate_data=fim)
    importancia = treinado.importancia()

    caminho_grafico = cfg.raiz / PASTA / "fase5_importancia.png"
    print("Desenhando o grafico...")
    graficos.importancia_das_features(importancia, caminho_grafico)

    texto = relatorio_fase5.montar(
        cfg=cfg,
        liberados=liberados,
        previsoes=previsoes,
        importancia=importancia,
        caminho_importancia=caminho_grafico,
        janela=(inicio, fim),
        gerado_em=date.today().isoformat(),
    )

    if args.so_ver:
        print("\n" + "\n".join(texto.splitlines()[:40]))
        print("\n--so-ver: nada foi gravado.")
        return 0

    destino = cfg.raiz / PASTA / "fase5.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(f"\nRelatorio gravado: {destino} ({len(texto.splitlines())} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
