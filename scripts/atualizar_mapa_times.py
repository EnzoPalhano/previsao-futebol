"""Varre os CSVs baixados e separa nomes de time conhecidos dos pendentes.

Uso::

    python scripts/atualizar_mapa_times.py             # relata pendências
    python scripts/atualizar_mapa_times.py --semear    # cria as linhas faltantes

O fluxo previsto na especificação é: o script encontra nomes novos, grava
``data/nomes_pendentes.csv`` com uma sugestão de correspondência, e **o Enzo
revisa** antes de mover para ``src/futebol/dados/mapa_times.csv``.

O ``--semear`` existe para o arranque: numa liga onde a fonte já usa nomes
limpos e consistentes (o caso da E0), ele escreve as linhas com
``nome_padrao = nome_fonte``. Continua sendo uma **proposta** — o diff do Git
é a revisão, e é por isso que o mapa é versionado.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from futebol.config import Config, carregar_config
from futebol.dados import download, formatos, limpeza, nomes_times
from futebol.terminal import preparar_saida


def pares_dos_arquivos(cfg: Config) -> list[tuple[str, str]]:
    """Colhe todos os pares ``(codigo_competicao, nome_do_time)`` da camada ativa.

    A leitura passa por :func:`futebol.dados.limpeza.ler_bruto` de propósito:
    ele é o mesmo leitor que monta a tabela de jogos, com a mesma cascata de
    encoding. Ler aqui com uma regra e lá com outra produziria nomes
    diferentes para o mesmo time — ``Preußen Münster`` num lado e
    ``PreuÃen MÃ¼nster`` no outro — e o mapa nunca casaria com os dados.
    """
    pares: set[tuple[str, str]] = set()

    for alvo in download.alvos_da_camada_ativa(cfg):
        if not alvo.destino.is_file():
            print(
                f"  aviso: {alvo.destino.name} nao esta em data/raw/. "
                "Rode scripts/baixar_dados.py primeiro.",
                file=sys.stderr,
            )
            continue

        quadro = limpeza.ler_bruto(alvo.destino)
        formato = formatos.detectar_formato(list(quadro.columns))
        mapa = formatos.MAPAS[formato]

        for coluna in (mapa["mandante"], mapa["visitante"]):
            for nome in quadro[coluna].dropna().unique():
                nome = nome.strip()
                if nome:
                    pares.add((alvo.codigo, nome))

    return sorted(pares)


def main(argv: list[str] | None = None) -> int:
    # Nome de clube estrangeiro derruba o console cp1252 do Windows.
    preparar_saida()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--semear",
        action="store_true",
        help="cria as linhas faltantes no mapa com nome_padrao = nome_fonte",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    print(f"Camada ativa: {cfg.camada_ativa}")

    pares = pares_dos_arquivos(cfg)
    mapa = nomes_times.carregar_mapa()
    print(f"{len(pares)} par(es) competicao/time nos arquivos.")
    print(f"{len(mapa)} linha(s) ja no mapa_times.csv.\n")

    faltantes: list[dict[str, str]] = []
    vistos: set[tuple[str, str]] = set()
    for codigo, nome in pares:
        pais = nomes_times.pais_do_codigo(codigo)
        if mapa.resolver(pais, nome) is not None or (pais, nome) in vistos:
            continue
        vistos.add((pais, nome))
        faltantes.append(
            {
                "pais": pais,
                "nome_fonte": nome,
                "nome_padrao": mapa.sugerir(pais, nome) or nome,
            }
        )

    if not faltantes:
        print("Nenhuma pendencia: todos os nomes estao no mapa.")
        Path(cfg.raiz / "data" / "nomes_pendentes.csv").unlink(missing_ok=True)
        return 0

    print(f"{len(faltantes)} nome(s) fora do mapa:\n")
    for linha in faltantes:
        print(f"  {linha['pais']}:{linha['nome_fonte']}")

    if not args.semear:
        pendentes = [
            nomes_times.Pendencia(
                pais=f["pais"],
                nome_fonte=f["nome_fonte"],
                normalizado=nomes_times.normalizar(f["nome_fonte"]),
                sugestao=mapa.sugerir(f["pais"], f["nome_fonte"]),
            )
            for f in faltantes
        ]
        destino = nomes_times.salvar_pendencias(
            pendentes, cfg.raiz / "data" / "nomes_pendentes.csv"
        )
        print(f"\nPendencias gravadas em: {destino.relative_to(cfg.raiz)}")
        print("Revise, ajuste o nome_padrao e mova para src/futebol/dados/mapa_times.csv")
        print("(ou rode com --semear para aceitar os nomes da fonte como padrao).")
        return 1

    existentes = []
    caminho_mapa = nomes_times.CAMINHO_MAPA_PADRAO
    if caminho_mapa.is_file():
        import csv

        with caminho_mapa.open(encoding="utf-8", newline="") as arquivo:
            existentes = list(csv.DictReader(arquivo))

    destino = nomes_times.salvar_mapa(existentes + faltantes)
    print(f"\n{len(faltantes)} linha(s) acrescentada(s) em {destino.name}.")
    print("Confira o diff do Git antes de commitar: esta e a revisao.")
    Path(cfg.raiz / "data" / "nomes_pendentes.csv").unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
