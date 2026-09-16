"""Aplica o filtro de qualidade de mercado e grava a lista de ligas aprovadas.

Uso::

    python scripts/filtro_ligas.py            # mede, mostra e grava no config.yaml
    python scripts/filtro_ligas.py --so-ver   # mede e mostra, nao grava

Esta e a resposta com dados para "quero as ligas em que tem apostas boas": em
vez de escolher no chute, o script mede margem, cobertura, calibracao e
historico de cada liga e aplica os cortes do config.yaml.

O resultado vai para `ligas_aprovadas_backtest` no config.yaml. A partir da
Fase 6, so essas ligas entram no backtest de apostas.

ATENCAO: liga do Grupo 2 nunca e aprovada (regra 12). Sem odd pre-jogo nao
existe aposta para simular.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from futebol.avaliacao import filtro
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.terminal import preparar_saida

#: A chave do config.yaml que guarda o resultado.
CHAVE = "ligas_aprovadas_backtest"


def gravar_no_config(caminho: Path, ligas: list[str]) -> None:
    """Troca so a linha da lista, preservando comentarios e formatacao.

    O pyyaml sabe ler o arquivo, mas ao reescreve-lo joga fora todos os
    comentarios - e este config e metade comentario explicativo. Por isso a
    substituicao e textual, numa linha so.
    """
    texto = caminho.read_text(encoding="utf-8")
    padrao = re.compile(rf"^{CHAVE}:.*$", re.MULTILINE)
    if not padrao.search(texto):
        raise SystemExit(
            f"Nao achei a chave {CHAVE} no {caminho.name}. "
            "Acrescente-a antes de rodar este script."
        )
    lista = ", ".join(ligas)
    caminho.write_text(padrao.sub(f"{CHAVE}: [{lista}]", texto), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    preparar_saida()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--so-ver", action="store_true", help="mostra o resultado sem gravar no config"
    )
    parser.add_argument(
        "--repeticoes",
        type=int,
        default=filtro.REPETICOES_PISO,
        help="simulacoes do piso de ruido do ECE (padrao: %(default)s)",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    criterios = filtro.Criterios.do_config(cfg)
    jogos = limpeza.carregar(cfg)

    print(f"Camada ativa: {cfg.camada_ativa}  |  {len(jogos)} jogos")
    print("\nCortes (config.yaml > filtro_qualidade_mercado):")
    print(f"  margem maxima no 1X2 pre-jogo : {criterios.margem_maxima:.1%}")
    print(f"  cobertura minima de odds      : {criterios.cobertura_minima:.0%}")
    print(f"  jogos minimos                 : {criterios.jogos_minimos}")
    print(f"  ECE maximo                    : {criterios.fator_ece_maximo:.1f}x o piso de ruido")

    avaliacao = filtro.avaliar(jogos, cfg, repeticoes=args.repeticoes)
    grupo1 = avaliacao[avaliacao["grupo"] == "grupo1"]

    print(f"\n{'liga':5s} {'jogos':>6s} {'cobert':>7s} {'margem':>7s} {'ECE/piso':>9s} {'logloss':>8s}")
    for _, linha in grupo1.iterrows():
        marca = "OK " if linha["aprovada"] else "NAO"
        print(
            f"{linha['liga']:5s} {linha['jogos']:6d} {linha['cobertura']:7.1%} "
            f"{linha['margem_pre']:7.2%} {linha['fator_ece']:9.2f} "
            f"{linha['log_loss']:8.4f}  {marca}"
        )

    aprovadas = filtro.ligas_aprovadas(avaliacao)
    reprovadas = grupo1[~grupo1["aprovada"]]

    print(f"\nAPROVADAS ({len(aprovadas)}): {', '.join(aprovadas)}")
    print(f"\nREPROVADAS ({len(reprovadas)}):")
    for _, linha in reprovadas.iterrows():
        print(f"  {linha['liga']}: {linha['motivos']}")

    grupo2 = avaliacao[avaliacao["grupo"] == "grupo2"]
    print(
        f"\nOs {len(grupo2)} paises do Grupo 2 nao entram no backtest por falta de "
        "odd pre-jogo (regra 12), e seguem valendo para treino e calibracao."
    )

    if args.so_ver:
        print("\n--so-ver: config.yaml nao foi alterado.")
        return 0

    gravar_no_config(cfg.raiz / "config.yaml", aprovadas)
    print(f"\nconfig.yaml atualizado: {CHAVE} = [{', '.join(aprovadas)}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
