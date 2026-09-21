"""Gera os dados versionados que o app usa quando publicado. A saida da Fase 9.

Uso::

    python scripts/preparar_deploy.py
    python scripts/preparar_deploy.py --conferir   # so confere, nao grava

O PROBLEMA QUE ISTO RESOLVE. O app depende de data/processed/jogos.parquet e do
cache do walk-forward, e nenhum dos dois vai para o Git (regra 4). Um deploy
ingenuo sobe o codigo, nao acha os dados e quebra na primeira tela.

A ESCOLHA, decidida na Fase 8 e medida: versionar os dados reduzidos (opcao a
da especificacao). A alternativa - baixar e processar no primeiro boot - faria
o primeiro visitante esperar minutos e, decisivo, depende de um download que ja
falha em rede com filtro de dominio. Um deploy que depende dele quebra em
silencio, com a causa escondida no servidor.

O QUE SAI DAQUI, em data/app/ (que o .gitignore NAO ignora - ele ignora
data/raw/* e data/processed/*, nao a pasta data inteira):

  jogos.parquet                 a tabela SEM as temporadas de teste final
  previsoes_<candidato>.parquet o walk-forward do modelo oficial, janela de
                                validacao

ATENCAO: o recorte pela regra 7 nao e uma otimizacao de tamanho, e uma trava.
O app nunca pode mostrar as temporadas do cofre, e a forma mais segura de
garantir isso num servidor e o dado nem estar la.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from futebol.avaliacao import divisao, selecao
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.terminal import preparar_saida

#: Onde os dados do deploy ficam. Versionado, ao contrario de data/processed.
PASTA = Path("data") / "app"

#: O teto por arquivo que a regra 4 impoe.
LIMITE_MB = 5.0

#: Compressao: zstd encolhe mais que o snappy padrao e o pyarrow le sem extra.
COMPRESSAO = "zstd"


def _mb(caminho: Path) -> float:
    return caminho.stat().st_size / 1e6


def main() -> int:
    preparar_saida()
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument(
        "--conferir",
        action="store_true",
        help="so confere o que existe em data/app, sem regravar",
    )
    argumentos = analise.parse_args()

    cfg = carregar_config()
    destino = cfg.raiz / PASTA

    if argumentos.conferir:
        if not destino.is_dir():
            print(f"{destino} nao existe. Rode sem --conferir.", file=sys.stderr)
            return 1
        arquivos = sorted(destino.glob("*.parquet"))
        if not arquivos:
            print(f"{destino} esta vazia.", file=sys.stderr)
            return 1
        for caminho in arquivos:
            tabela = pd.read_parquet(caminho)
            print(f"  {caminho.name}: {len(tabela)} linhas, {_mb(caminho):.2f} MB")
        return 0

    destino.mkdir(parents=True, exist_ok=True)

    print("Carregando a tabela e trancando o cofre (regra 7)...")
    completa = limpeza.carregar(cfg)
    separada = divisao.separar(completa, cfg)
    print(f"  {separada.resumo()}\n")

    caminho_jogos = destino / "jogos.parquet"
    separada.jogos.to_parquet(caminho_jogos, compression=COMPRESSAO, index=True)
    print(f"Gravado {caminho_jogos} ({_mb(caminho_jogos):.2f} MB)")

    candidato = selecao.candidato_oficial(cfg, separada.jogos)
    origem = selecao.caminho_do_cache(
        cfg,
        candidato,
        selecao.INICIO_VALIDACAO,
        pd.Timestamp(separada.jogos["data"].max()) + pd.Timedelta(days=1),
    )
    if not origem.is_file():
        print(
            f"\nFALTA o walk-forward do modelo oficial em {origem}.\n"
            "Rode `python scripts/validar.py` antes.",
            file=sys.stderr,
        )
        return 1

    previsoes = pd.read_parquet(origem)
    caminho_prev = destino / f"previsoes_{candidato.nome}.parquet"
    previsoes.to_parquet(caminho_prev, compression=COMPRESSAO, index=True)
    print(f"Gravado {caminho_prev} ({_mb(caminho_prev):.2f} MB)")

    print("\nConferindo o limite da regra 4 (5 MB por arquivo):")
    estourou = False
    for caminho in (caminho_jogos, caminho_prev):
        tamanho = _mb(caminho)
        marca = "OK " if tamanho <= LIMITE_MB else "NAO"
        print(f"  {marca} {caminho.name}: {tamanho:.2f} MB")
        estourou = estourou or tamanho > LIMITE_MB
    if estourou:
        print(
            "\nAlgum arquivo passou de 5 MB. NAO commite: reduza as colunas ou "
            "a janela primeiro.",
            file=sys.stderr,
        )
        return 1

    print(
        "\nPronto. Estes arquivos VAO para o Git - sao a excecao consciente da "
        "regra 4, e o app publicado depende deles."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
