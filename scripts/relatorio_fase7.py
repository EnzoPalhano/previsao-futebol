"""Gera o relatorio da Fase 7 em docs/relatorios/fase7.md, com os dois graficos.

Uso::

    python scripts/relatorio_fase7.py             # le o cache e escreve tudo
    python scripts/relatorio_fase7.py --so-ver    # mostra o comeco, nao grava
    python scripts/relatorio_fase7.py --forcar    # refaz o walk-forward do modelo

Le as previsoes do modelo OFICIAL gravadas por scripts/validar.py. Se o cache
nao existir, ele e criado - e ai o comando demora uns minutos.

Escreve tres arquivos em docs/relatorios/:
  fase7.md                  o relatorio
  fase7_margem.png          a comissao acumulada por tamanho de bilhete
  fase7_previsto_real.png   a chance prometida contra a que aconteceu

ATENCAO: no maximo UMA selecao por jogo (mercados da mesma partida sao
correlacionados), a aposta e na odd media pre-jogo (regra 8) e nada aqui
escolhe modelo (regra 9).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from futebol.avaliacao import divisao, graficos, relatorio_fase7, selecao
from futebol.backtest import cash_out, montador, multiplas, simulador
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.terminal import preparar_saida

#: Onde os arquivos da fase sao gravados.
PASTA = "docs/relatorios"

#: Quanto a rodada de exemplo do montador aposta, em reais.
VALOR_DE_EXEMPLO = 10.0

#: O premio alvo da demonstracao do montador.
PREMIO_DE_EXEMPLO = 200.0


def _rodada_de_exemplo(candidatos: pd.DataFrame) -> pd.DataFrame:
    """A data com mais jogos da janela — a que melhor mostra o montador."""
    contagem = candidatos.groupby("data")["mandante"].nunique()
    return candidatos.loc[candidatos["data"] == contagem.idxmax()]


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

    print("Montando as multiplas do historico...")
    historico = multiplas.montar_historico(amostra.candidatos, cfg)
    print(
        f"  {len(historico.multiplas)} bilhetes em "
        f"{historico.multiplas['data'].nunique()} rodadas"
    )

    print("Medindo previsto x real, tamanho a tamanho...")
    bootstrap = int(cfg.secao("backtest")["bootstrap_amostras"])
    por_tamanho = multiplas.medir_por_tamanho(
        historico.multiplas, amostras_bootstrap=bootstrap, seed=cfg.seed
    )

    print("Simulando o cash out...")
    tabelas = {}
    for tamanho in relatorio_fase7.TAMANHOS_DO_CASH_OUT:
        tabelas[tamanho] = cash_out.como_tabela(
            cash_out.simular(
                historico, cfg, tamanho, amostras_bootstrap=bootstrap, seed=cfg.seed
            )
        )
        print(f"  {tamanho} selecoes: {len(tabelas[tamanho])} estrategias")

    maior = max(relatorio_fase7.TAMANHOS_DO_CASH_OUT)
    do_maior = historico.multiplas.loc[historico.multiplas["tamanho"] == maior]
    pernas = historico.pernas.loc[historico.pernas["id"] == do_maior["id"].iloc[0]]
    distribuicao = (
        maior,
        cash_out.distribuicao_de_acertos(
            pernas["prob_justa"].to_numpy(), seed=cfg.seed
        ),
    )

    print("Rodando o montador numa rodada de exemplo...")
    rodada = _rodada_de_exemplo(amostra.candidatos)
    comparativo = montador.comparar_tamanhos(rodada, cfg, valor=VALOR_DE_EXEMPLO)
    exemplo = montador.montar(
        rodada, cfg, premio_alvo=PREMIO_DE_EXEMPLO, valor=VALOR_DE_EXEMPLO
    )

    print("Desenhando os graficos...")
    caminho_margem = cfg.raiz / PASTA / "fase7_margem.png"
    graficos.margem_da_multipla(
        por_tamanho,
        caminho_margem,
        subtitulo=(
            f"{len(historico.multiplas)} bilhetes, 18 ligas, "
            f"{inicio.date()} a {fim.date()}"
        ),
    )
    caminho_previsto = cfg.raiz / PASTA / "fase7_previsto_real.png"
    graficos.previsto_contra_real(
        por_tamanho,
        caminho_previsto,
        subtitulo="uma seleção por jogo; os favoritos de cada rodada",
    )

    texto = relatorio_fase7.montar(
        cfg=cfg,
        historico=historico,
        por_tamanho=por_tamanho,
        tabelas_de_cash_out=tabelas,
        distribuicao=distribuicao,
        exemplo=exemplo,
        comparativo=comparativo,
        caminho_margem=caminho_margem,
        caminho_previsto=caminho_previsto,
        janela=(inicio, fim),
        gerado_em=date.today().isoformat(),
    )

    if args.so_ver:
        print("\n" + "\n".join(texto.splitlines()[:45]))
        print("\n--so-ver: nada foi gravado.")
        return 0

    destino = cfg.raiz / PASTA / "fase7.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(f"\nRelatorio gravado: {destino} ({len(texto.splitlines())} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
