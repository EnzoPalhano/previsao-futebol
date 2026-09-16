"""Baixa os CSVs da camada de ligas ativa e atualiza o manifesto.

Uso::

    python scripts/baixar_dados.py            # baixa o que falta
    python scripts/baixar_dados.py --forcar   # rebaixa tudo
    python scripts/baixar_dados.py --conferir # só confere, não baixa

Qual liga e qual temporada vêm do ``config.yaml``, na camada apontada por
``ligas.ativa``. Trocar de camada lá muda o que este script baixa, sem mexer
em código.

O ``--conferir`` responde a uma pergunta específica: *os arquivos que estão no
meu disco hoje são os mesmos que geraram os resultados do último relatório?*
Como o football-data reescreve os CSVs, a resposta nem sempre é sim.
"""

from __future__ import annotations

import argparse
import sys

from futebol.config import Config, carregar_config
from futebol.dados import download, manifesto


def conferir(cfg: Config) -> int:
    """Compara o disco com o manifesto. Devolve o código de saída do processo."""
    divergencias = manifesto.conferir(cfg)
    if not divergencias:
        registrados = len(manifesto.carregar(cfg))
        print(f"OK: os {registrados} arquivos do manifesto conferem com o disco.")
        return 0

    print(f"ATENCAO: {len(divergencias)} divergencia(s) entre o disco e o manifesto:\n")
    for d in divergencias:
        if d.motivo == "ausente":
            print(f"  [ausente]  {d.chave} - registrado, mas nao esta em data/raw/")
        else:
            print(f"  [mudou]    {d.chave}")
            print(f"             registrado: {d.sha_registrado[:16]}...")
            print(f"             agora:      {(d.sha_atual or '')[:16]}...")
    print(
        "\nArquivo que mudou significa que a fonte o reescreveu (placar corrigido, "
        "odd acrescentada). Rode com --forcar para adotar a versao nova; os numeros "
        "dos relatorios anteriores passam a nao ser reproduziveis."
    )
    return 1


def baixar(cfg: Config, *, forcar: bool) -> int:
    ligas = cfg.ligas_ativas()
    print(f"Camada ativa: {cfg.camada_ativa}")
    print(f"  Grupo 1 (backtest + CLV): {', '.join(ligas['grupo1']) or 'nenhuma'}")
    print(f"  Grupo 2 (treino apenas):  {', '.join(ligas['grupo2']) or 'nenhuma'}")
    print(f"  Temporadas do Grupo 1:    {cfg.temporadas_grupo1()}")
    print()

    resultados = download.baixar_camada_ativa(cfg, forcar=forcar)

    registros = manifesto.carregar(cfg)
    raiz_raw = download.pasta_raw(cfg)
    baixados = 0

    for resultado in resultados:
        alvo = resultado.alvo
        registro = manifesto.registrar_arquivo(
            alvo.destino, url=alvo.url, raiz_raw=raiz_raw
        )
        registros[registro.chave] = registro
        if resultado.baixado:
            baixados += 1
        estado = "baixado" if resultado.baixado else "ja existia"
        print(
            f"  {registro.chave:28s} {registro.linhas - 1:>6d} jogos  "
            f"{registro.bytes / 1024:>7.1f} KB  ({estado})"
        )

    caminho = manifesto.salvar(cfg, registros)
    reaproveitados = len(resultados) - baixados
    print(
        f"\n{len(resultados)} arquivo(s): {baixados} baixado(s), "
        f"{reaproveitados} reaproveitado(s) do disco."
    )
    print(f"Manifesto atualizado: {caminho.relative_to(cfg.raiz)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="rebaixa arquivos que ja existem (adota correcoes da fonte)",
    )
    parser.add_argument(
        "--conferir",
        action="store_true",
        help="apenas confere o disco contra o manifesto, sem baixar nada",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    if args.conferir:
        return conferir(cfg)
    return baixar(cfg, forcar=args.forcar)


if __name__ == "__main__":
    sys.exit(main())
