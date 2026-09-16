"""Gera ``docs/dicionario_dados.md`` a partir das colunas reais dos arquivos.

O dicionário de dados não é escrito à mão: ele é **gerado** do que a fonte
publica hoje. Assim ele não envelhece em silêncio.

Uso::

    python scripts/gerar_dicionario.py

Baixa uma amostra de cada formato (reaproveita o que já está em ``data/raw/``),
inspeciona os cabeçalhos e escreve o documento.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from futebol.config import Config, carregar_config
from futebol.dados import download, formatos

# Amostras inspecionadas. Cobrem os três formatos e os casos de borda
# conhecidos: liga com menos casas de aposta (RUS) e temporada de fronteira.
AMOSTRAS: tuple[tuple[str, str, int | None], ...] = (
    ("grupo1", "E0", 2425),
    ("grupo1", "SP1", 2425),
    ("grupo1", "D1", 1920),
    ("grupo1", "E0", 1819),
    ("grupo1", "E0", 1718),
    ("grupo2", "BRA", None),
    ("grupo2", "RUS", None),
    # ARG e JPN misturam os dois formatos de Season no mesmo arquivo.
    ("grupo2", "ARG", None),
    ("grupo2", "JPN", None),
)


def baixar_amostras(cfg: Config) -> list[Path]:
    """Garante as amostras em disco e devolve os caminhos."""
    fontes = cfg.secao("fontes")
    caminhos = []
    for grupo, codigo, temporada in AMOSTRAS:
        alvo = (
            download.alvo_grupo1(cfg, codigo, temporada)
            if grupo == "grupo1"
            else download.alvo_grupo2(cfg, codigo)
        )
        download.baixar_alvo(
            alvo,
            user_agent=str(fontes["user_agent"]),
            timeout=int(fontes["timeout_segundos"]),
        )
        caminhos.append(alvo.destino)
    return caminhos


def temporadas_do_grupo2(caminho: Path) -> list[str]:
    """Valores distintos de ``Season`` num arquivo do Grupo 2."""
    texto = caminho.read_bytes().decode("utf-8-sig", errors="replace")
    linhas = texto.splitlines()
    indice = formatos.ler_cabecalho(caminho).index("Season")
    return sorted(
        {linha.split(",")[indice] for linha in linhas[1:] if linha.strip()}
    )


def tabela_mapeamento(formato: str) -> list[str]:
    """Linhas de tabela markdown com o mapa coluna padrão -> coluna de origem."""
    mapa = formatos.MAPAS[formato]
    linhas = []
    for padrao in formatos.COLUNAS_PADRAO:
        origem = mapa.get(padrao)
        if origem is None:
            if padrao in ("liga", "temporada") and formato in ("A", "B"):
                valor = "_(vem do nome do arquivo)_"
            else:
                valor = "**vazia** — não existe neste formato"
        else:
            valor = f"`{origem}`"
        linhas.append(f"| `{padrao}` | {valor} |")
    return linhas


def gerar(cfg: Config) -> Path:
    caminhos = baixar_amostras(cfg)
    inventarios = [formatos.inventariar(c) for c in caminhos]

    partes: list[str] = []
    a = partes.append

    a("# Dicionário de dados")
    a("")
    a(
        "> Documento **gerado** por `scripts/gerar_dicionario.py` a partir dos "
        "arquivos reais da fonte. Não edite à mão — rode o script de novo."
    )
    a("")
    a(f"Gerado em: {datetime.now(UTC).strftime('%d/%m/%Y %H:%M UTC')}")
    a("Fonte: <https://www.football-data.co.uk>")
    a("")
    a("## 1. Os três formatos encontrados")
    a("")
    a("| Arquivo inspecionado | Formato | Colunas | Essenciais faltando |")
    a("|---|:---:|---:|---|")
    for inv in inventarios:
        faltando = ", ".join(inv.essenciais_faltando) or "nenhuma"
        nome = "/".join(inv.caminho.parts[-2:])
        a(f"| `{nome}` | {inv.formato} | {len(inv.colunas)} | {faltando} |")
    a("")
    a(
        "O número de colunas varia dentro do mesmo formato (ligas diferentes têm "
        "casas de aposta diferentes). O que importa não é a contagem, e sim se as "
        "colunas **essenciais** estão presentes."
    )
    a("")

    a("## 2. Colunas padrão e de onde cada uma vem")
    a("")
    a(
        "Todo arquivo, seja qual for o formato, vira esta mesma tabela. Onde a "
        "odd não existe na fonte, a coluna fica **vazia** — nunca é preenchida "
        "com estimativa."
    )
    for formato, titulo in (
        ("A", "Formato A — ligas principais, 2019/20 em diante"),
        ("B", "Formato B — ligas principais, até 2018/19"),
        ("C", "Formato C — Grupo 2 (arquivo único por país)"),
    ):
        a("")
        a(f"### {titulo}")
        a("")
        a("| Coluna padrão | Coluna de origem |")
        a("|---|---|")
        partes.extend(tabela_mapeamento(formato))
    a("")

    a("## 3. O que cada formato permite")
    a("")
    a("| Capacidade | A | B | C |")
    a("|---|:---:|:---:|:---:|")
    a("| Resultado e placar | ✅ | ✅ | ✅ |")
    a("| Odd pré-jogo de 1X2 (é nela que se aposta) | ✅ | ✅ | ❌ |")
    a("| Odd pré-jogo de Over/Under 2,5 | ✅ | ✅ | ❌ |")
    a("| Odd de fechamento de 1X2 | ✅ | ⚠️ | ✅ |")
    a("| Odd de fechamento de Over/Under 2,5 | ✅ | ❌ | ❌ |")
    a("| Backtest de apostas | ✅ | ✅ | ❌ |")
    a("| Medição de CLV | ✅ | ⚠️ | ❌ |")
    a("")
    a(f"⚠️ **Formato B:** {formatos.AVISO_CLV_FORMATO_B}")
    a("")

    a("## 4. Armadilhas confirmadas na inspeção")
    a("")
    a(
        "### 4.1 Os arquivos do Grupo 2 começam com BOM\n\n"
        "Três bytes invisíveis (`EF BB BF`) antes da primeira coluna. Lidos sem "
        "cuidado, `Country` vira `\\ufeffCountry` e o acesso pelo nome estoura. "
        "Tratado em `formatos.ler_cabecalho` com `utf-8-sig`."
    )
    a("")
    a(
        "### 4.2 `Season` tem dois formatos — dentro do mesmo arquivo\n\n"
        "A especificação dizia que no Grupo 2 `Season` é o ano civil. É verdade "
        "para uns países e falso para outros — e há arquivos que misturam os dois, "
        "porque o país mudou de calendário no meio do período:"
    )
    a("")
    for caminho in caminhos:
        if caminho.parent.name != "new":
            continue
        temporadas = temporadas_do_grupo2(caminho)
        cruza = sum("/" in t for t in temporadas)
        a(
            f"- **{caminho.stem}**: {len(temporadas)} temporadas, "
            f"{cruza} no formato `2012/2013` e {len(temporadas) - cruza} no "
            f"formato `2012`. Exemplos: {', '.join(temporadas[:4])}…"
        )
    a("")
    a(
        "Consequência: a normalização de temporada precisa decidir linha a linha, "
        "não arquivo a arquivo."
    )
    a("")
    a(
        "### 4.3 Nem todo país tem todas as casas de aposta\n\n"
        "`RUS` traz 19 colunas em vez de 25: não tem B365 nem Betfair. Continua "
        "utilizável porque as `AvgC*`, que são as que o projeto usa, estão lá. "
        "Por isso o inventário separa colunas **essenciais** de **opcionais**."
    )
    a("")

    a("## 5. Inventário completo das colunas encontradas")
    a("")
    for inv in inventarios:
        nome = "/".join(inv.caminho.parts[-2:])
        a(f"<details><summary><code>{nome}</code> — formato {inv.formato}, "
          f"{len(inv.colunas)} colunas</summary>")
        a("")
        a("```")
        a(", ".join(inv.colunas))
        a("```")
        a("</details>")
        a("")

    contagem = Counter(inv.formato for inv in inventarios)
    a(
        f"Amostras inspecionadas: {len(inventarios)} arquivos "
        f"({contagem['A']} do formato A, {contagem['B']} do B, {contagem['C']} do C)."
    )
    a("")

    destino = cfg.raiz / "docs" / "dicionario_dados.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(partes), encoding="utf-8", newline="\n")
    return destino


def main() -> None:
    cfg = carregar_config()
    destino = gerar(cfg)
    print(f"Dicionário gerado em: {destino.relative_to(cfg.raiz)}")


if __name__ == "__main__":
    main()
