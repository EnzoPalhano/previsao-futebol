"""Gera o relatorio da Fase 6 em docs/relatorios/fase6.md, com os dois graficos.

Uso::

    python scripts/relatorio_fase6.py             # le o cache e escreve tudo
    python scripts/relatorio_fase6.py --so-ver    # mostra o comeco, nao grava
    python scripts/relatorio_fase6.py --forcar    # refaz o walk-forward do modelo

Le as previsoes do modelo OFICIAL gravadas por scripts/validar.py. Se o cache
nao existir, ele e criado - e ai o comando demora uns minutos.

Escreve tres arquivos em docs/relatorios/:
  fase6.md                 o relatorio
  fase6_banca.png          as quatro variantes de banca, em escala log
  fase6_lucro_acumulado.png  o lucro com stake de 1 unidade, ao longo de 3 anos

ATENCAO: a aposta e na odd media pre-jogo (regra 8), o CLV so sai das 18 ligas
aprovadas (regra 12) e o ROI nunca escolhe modelo (regra 9).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from futebol.avaliacao import divisao, graficos, relatorio_fase6, selecao
from futebol.backtest import simulador
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.terminal import preparar_saida

#: Onde os arquivos da fase sao gravados.
PASTA = "docs/relatorios"

#: Como cada combinacao de estrategia e banca aparece na legenda do grafico.
ROTULOS = {
    ("stake_fixa", "fixa"): "stake fixa · banca fixa",
    ("stake_fixa", "composta"): "stake fixa · banca composta",
    ("kelly_fracionado", "fixa"): "Kelly 1/4 · banca fixa",
    ("kelly_fracionado", "composta"): "Kelly 1/4 · banca composta",
}


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

    oficial = selecao.candidato_oficial(cfg, liberados, inicio)
    print(f"Modelo oficial: {oficial.nome}")
    previsoes = selecao.rodar_candidato(
        liberados, oficial, cfg, inicio, fim, args.forcar, aviso=print
    )

    print("Montando as apostas candidatas...")
    amostra = simulador.preparar(liberados, previsoes, cfg)
    print(f"  {amostra.resumo()}")

    print("Rodando o backtest principal...")
    principal = simulador.rodar(liberados, previsoes, cfg, amostra=amostra)

    print("Varrendo os limites de EV...")
    bootstrap = int(cfg.secao("backtest")["bootstrap_amostras"])
    grade = {}
    for limite in simulador.GRADE_EV:
        if limite == principal.ev_minimo:
            # O limite principal ja foi medido. Medi-lo de novo daria um
            # intervalo de confianca ligeiramente diferente (bootstrap e
            # sorteio), e o relatorio mostraria dois numeros para a mesma coisa
            # em duas secoes - exatamente o defeito que a Fase 4 corrigiu.
            grade[limite] = principal.resultado
        else:
            apostas = simulador.selecionar(amostra.candidatos, limite)
            grade[limite] = simulador.medir(
                apostas, f"EV>{limite:.0%}", amostras_bootstrap=bootstrap, seed=cfg.seed
            )
        print(f"  EV>{limite:.0%}: {grade[limite].n} apostas")

    print("Medindo a regua (todas as candidatas, sem filtro)...")
    referencia = simulador.medir(
        amostra.candidatos, "todas as candidatas", amostras_bootstrap=2000, seed=cfg.seed
    )

    print("Desenhando os graficos...")
    caminho_banca = cfg.raiz / PASTA / "fase6_banca.png"
    graficos.evolucao_da_banca(
        {ROTULOS[chave]: evolucao for chave, evolucao in principal.evolucoes.items()},
        caminho_banca,
        banca_inicial=float(cfg.secao("backtest")["banca_inicial"]),
        subtitulo=(
            f"{len(principal.apostas)} apostas com EV > "
            f"{principal.ev_minimo:.0%}, em 18 ligas, {inicio.date()} a {fim.date()}"
        ),
    )
    caminho_lucro = cfg.raiz / PASTA / "fase6_lucro_acumulado.png"
    graficos.lucro_acumulado(
        {
            "modelo (EV > 5%)": principal.apostas,
            "aleatoria (mesmo n)": simulador.aleatorias(
                amostra.candidatos, len(principal.apostas), seed=cfg.seed
            ),
        },
        caminho_lucro,
        subtitulo="stake de 1 unidade por aposta; nada quebra, nada é racionado",
    )

    texto = relatorio_fase6.montar(
        cfg=cfg,
        principal=principal,
        grade=grade,
        referencia=referencia,
        caminho_banca=caminho_banca,
        caminho_lucro=caminho_lucro,
        janela=(inicio, fim),
        modelo=oficial.nome,
        gerado_em=date.today().isoformat(),
    )

    if args.so_ver:
        print("\n" + "\n".join(texto.splitlines()[:45]))
        print("\n--so-ver: nada foi gravado.")
        return 0

    destino = cfg.raiz / PASTA / "fase6.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(f"\nRelatorio gravado: {destino} ({len(texto.splitlines())} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
