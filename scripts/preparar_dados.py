"""Transforma os CSVs baixados na tabela unica do projeto.

Uso::

    python scripts/preparar_dados.py             # le data/raw/ e grava o Parquet
    python scripts/preparar_dados.py --conferir  # so mostra o resumo, nao grava

Le as ligas da camada ativa do ``config.yaml``, junta os tres formatos numa
tabela so e grava ``data/processed/jogos.parquet``. Rode
``python scripts/baixar_dados.py`` antes: este script nao vai a rede.

Se aparecer um nome de time que nao esta no ``mapa_times.csv``, o script PARA
e grava ``data/nomes_pendentes.csv`` para revisao. Isso e proposital: seguir
em frente com um time nao reconhecido significa perder jogos na juncao sem
ninguem perceber.
"""

from __future__ import annotations

import argparse
import sys

from futebol.config import Config, carregar_config
from futebol.dados import limpeza, nomes_times

#: Explicacao curta de cada motivo de descarte, para o resumo no terminal.
EXPLICACAO_DESCARTE: dict[str, str] = {
    "sem_times": "linha sem mandante ou visitante (linha vazia no fim do arquivo)",
    "data_invalida": "data ausente ou em formato que nao reconhecemos",
    "sem_placar": "jogo sem placar (adiado ou ainda nao disputado)",
    "gols_negativos": "placar negativo (erro da fonte)",
    "duplicata": "mesmo jogo repetido (liga, temporada, data e as duas equipes)",
    "anterior_ao_corte": "temporada anterior a temporadas.grupo2_ano_minimo",
}


def _mostrar_resumo(resultado: limpeza.ResultadoLimpeza) -> None:
    resumo = resultado.resumo
    jogos = resultado.jogos

    print(f"\n{resumo.arquivos} arquivo(s) lidos, {resumo.linhas_lidas} linha(s).")
    print(f"Jogos na tabela: {resumo.jogos}")

    if resumo.descartes:
        print(f"\nLinhas descartadas: {resumo.descartadas}")
        for motivo, quantas in sorted(resumo.descartes.items()):
            explicacao = EXPLICACAO_DESCARTE.get(motivo, "")
            print(f"  {quantas:>6d}  {motivo:<18s} {explicacao}")
    else:
        print("\nNenhuma linha descartada.")

    if resumo.divergencias_resultado:
        print(
            f"\nATENCAO: em {resumo.divergencias_resultado} jogo(s) a coluna de "
            "resultado da fonte nao batia com o placar. Valeu o placar."
        )

    print("\nJogos por grupo:")
    for grupo, quantos in jogos["grupo"].value_counts().sort_index().items():
        papel = (
            "backtest de apostas + CLV"
            if grupo == "grupo1"
            else "treino e calibracao apenas (regra 12)"
        )
        print(f"  {grupo}: {quantos:>7d} jogos  - {papel}")

    print("\nJogos por liga:")
    por_liga = jogos.groupby("liga", observed=True).agg(
        jogos=("data", "size"),
        primeira=("data", "min"),
        ultima=("data", "max"),
        times=("mandante", "nunique"),
    )
    for liga, linha in por_liga.iterrows():
        print(
            f"  {liga:<5s} {linha['jogos']:>7d} jogos  "
            f"{linha['primeira'].date()} a {linha['ultima'].date()}  "
            f"{linha['times']:>4d} times"
        )


def _explicar_pendencias(erro: nomes_times.NomeDesconhecido, cfg: Config) -> int:
    caminho = limpeza.caminho_pendencias(cfg)
    print(f"\nPAROU: {len(erro.pendentes)} nome(s) de time fora do mapa.\n")
    for pendencia in erro.pendentes[:15]:
        sugestao = pendencia.sugestao or "(sem sugestao parecida)"
        print(f"  {pendencia.pais}:{pendencia.nome_fonte:<28s} -> {sugestao}")
    if len(erro.pendentes) > 15:
        print(f"  ... e mais {len(erro.pendentes) - 15}.")
    print(
        f"\nA lista completa esta em {caminho.relative_to(cfg.raiz)}.\n"
        "Revise a coluna nome_padrao, confirme cada linha e mova para\n"
        "src/futebol/dados/mapa_times.csv (que vai para o Git). Depois rode de novo."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--conferir",
        action="store_true",
        help="monta a tabela e mostra o resumo, mas nao grava o Parquet",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    ligas = cfg.ligas_ativas()
    print(f"Camada ativa: {cfg.camada_ativa}")
    print(f"  Grupo 1 (backtest + CLV): {', '.join(ligas['grupo1']) or 'nenhuma'}")
    print(f"  Grupo 2 (treino apenas):  {', '.join(ligas['grupo2']) or 'nenhuma'}")

    try:
        resultado = limpeza.construir_tabela(cfg)
    except nomes_times.NomeDesconhecido as erro:
        return _explicar_pendencias(erro, cfg)
    except limpeza.ErroDeLimpeza as erro:
        print(f"\nERRO: {erro}")
        return 1

    _mostrar_resumo(resultado)

    if args.conferir:
        print("\n--conferir: nada foi gravado.")
        return 0

    destino = limpeza.salvar(resultado.jogos, cfg)
    tamanho = destino.stat().st_size / 1024
    print(f"\nTabela gravada: {destino.relative_to(cfg.raiz)} ({tamanho:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
