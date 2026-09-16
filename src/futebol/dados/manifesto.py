"""Registro do que foi baixado: URL, data, linhas e SHA-256 de cada arquivo.

**Por que isto existe.** A pasta ``data/raw/`` não vai para o Git — são dezenas
de MB. Mas o football-data **reescreve** os CSVs com o tempo: corrige placares
errados, acrescenta odds que faltavam, ajusta datas de jogos adiados. Isso quer
dizer que baixar ``E0.csv`` hoje e daqui a seis meses pode dar arquivos
diferentes, e portanto números diferentes no relatório.

Sem um registro, ninguém — nem o Enzo daqui a seis meses — consegue responder
"de qual versão do arquivo saiu este ROI?". O ``data/manifesto.json`` responde:
ele guarda o **SHA-256** de cada arquivo, que é uma impressão digital. Se um byte
mudar, o SHA-256 muda inteiro.

Este arquivo **vai para o Git**. É a única parte dos dados que vai.

Uso típico::

    from futebol.dados import manifesto

    registro = manifesto.registrar_arquivo(caminho, url="https://...")
    manifesto.salvar(cfg, {registro.chave: registro})

    # mais tarde, para conferir se algo mudou:
    divergencias = manifesto.conferir(cfg)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from futebol.config import Config

# Lido em blocos para não carregar um CSV de 60 MB inteiro na memória.
_TAMANHO_BLOCO = 64 * 1024


class ErroDeManifesto(Exception):
    """Falha ao ler, gravar ou conferir o manifesto."""


@dataclass(frozen=True)
class RegistroArquivo:
    """A ficha de um arquivo baixado.

    Atributos:
        chave: identificador estável dentro do manifesto, no formato
            ``grupo1/2425/E0.csv`` ou ``grupo2/BRA.csv``.
        url: endereço de onde veio.
        baixado_em: data e hora do download, em UTC (ISO 8601).
        linhas: número de linhas do arquivo, **incluindo o cabeçalho**.
        sha256: impressão digital do conteúdo.
        bytes: tamanho em disco.
    """

    chave: str
    url: str
    baixado_em: str
    linhas: int
    sha256: str
    bytes: int


def caminho_manifesto(cfg: Config) -> Path:
    """Caminho do ``data/manifesto.json``."""
    return cfg.raiz / "data" / "manifesto.json"


def chave_do_arquivo(caminho: Path, raiz_raw: Path) -> str:
    """Traduz o caminho em disco para a chave usada no manifesto.

    ``data/raw/mmz4281/2425/E0.csv`` vira ``grupo1/2425/E0.csv``.
    ``data/raw/new/BRA.csv`` vira ``grupo2/BRA.csv``.

    Usamos uma chave própria em vez do caminho literal para que o manifesto
    não dependa de onde a pasta do projeto está no computador de cada um.
    """
    relativo = caminho.resolve().relative_to(raiz_raw.resolve())
    partes = relativo.parts
    if partes[0] == "mmz4281":
        return "/".join(("grupo1", *partes[1:]))
    if partes[0] == "new":
        return "/".join(("grupo2", *partes[1:]))
    raise ErroDeManifesto(
        f"Caminho inesperado dentro de data/raw/: {relativo}. "
        "Esperado começar com 'mmz4281/' (Grupo 1) ou 'new/' (Grupo 2)."
    )


def sha256_e_linhas(caminho: Path) -> tuple[str, int]:
    """Calcula o SHA-256 e conta as linhas de um arquivo, numa passada só.

    Contamos linhas pelo byte ``\\n`` em modo binário: é o único jeito que não
    depende de encoding, e alguns CSVs da fonte têm bytes que não são UTF-8
    válido (nomes de times com acento em codificação antiga).
    """
    digest = hashlib.sha256()
    quebras = 0
    ultimo_byte = b""

    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(_TAMANHO_BLOCO):
            digest.update(bloco)
            quebras += bloco.count(b"\n")
            ultimo_byte = bloco[-1:]

    # Se o arquivo não termina em quebra de linha, a última linha não foi contada.
    linhas = quebras + (1 if ultimo_byte not in (b"", b"\n") else 0)
    return digest.hexdigest(), linhas


def registrar_arquivo(caminho: Path, *, url: str, raiz_raw: Path) -> RegistroArquivo:
    """Monta a ficha de um arquivo que está em disco."""
    if not caminho.is_file():
        raise ErroDeManifesto(f"Arquivo não encontrado para registro: {caminho}")

    sha, linhas = sha256_e_linhas(caminho)
    return RegistroArquivo(
        chave=chave_do_arquivo(caminho, raiz_raw),
        url=url,
        baixado_em=datetime.now(UTC).isoformat(timespec="seconds"),
        linhas=linhas,
        sha256=sha,
        bytes=caminho.stat().st_size,
    )


def carregar(cfg: Config) -> dict[str, RegistroArquivo]:
    """Lê o manifesto do disco. Devolve vazio se ele ainda não existe."""
    caminho = caminho_manifesto(cfg)
    if not caminho.is_file():
        return {}

    try:
        with caminho.open(encoding="utf-8") as arquivo:
            bruto = json.load(arquivo)
    except json.JSONDecodeError as erro:
        raise ErroDeManifesto(
            f"{caminho} não é um JSON válido: {erro}. "
            "Se estiver corrompido, apague-o e rode o download de novo."
        ) from erro

    return {
        chave: RegistroArquivo(chave=chave, **dados)
        for chave, dados in sorted(bruto.get("arquivos", {}).items())
    }


def salvar(cfg: Config, registros: dict[str, RegistroArquivo]) -> Path:
    """Grava o manifesto, com as chaves ordenadas.

    A ordenação importa: sem ela, cada rodada geraria um diff enorme no Git
    só porque os dicionários mudaram de ordem.
    """
    caminho = caminho_manifesto(cfg)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    conteudo = {
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "arquivos": {
            chave: {k: v for k, v in asdict(registro).items() if k != "chave"}
            for chave, registro in sorted(registros.items())
        },
    }

    with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
        json.dump(conteudo, arquivo, indent=2, ensure_ascii=False)
        arquivo.write("\n")
    return caminho


@dataclass(frozen=True)
class Divergencia:
    """Um arquivo cujo conteúdo hoje não bate com o que o manifesto registrou.

    Atributos:
        chave: identificador do arquivo no manifesto.
        motivo: ``"ausente"`` (registrado mas não está em disco) ou
            ``"conteudo_mudou"`` (está em disco com outro SHA-256).
        sha_registrado: o que o manifesto diz.
        sha_atual: o que o arquivo em disco tem agora. ``None`` se ausente.
    """

    chave: str
    motivo: str
    sha_registrado: str
    sha_atual: str | None


def conferir(cfg: Config) -> list[Divergencia]:
    """Compara o manifesto com o que está em disco hoje.

    Retorna:
        Lista de divergências. Vazia significa que os arquivos em disco são
        exatamente os que geraram os resultados registrados.

    Arquivos que estão em disco mas **não** no manifesto não são divergência:
    são simplesmente arquivos ainda não registrados.
    """
    from futebol.dados.download import pasta_raw  # import tardio: evita ciclo

    raiz_raw = pasta_raw(cfg)
    divergencias: list[Divergencia] = []

    for chave, registro in carregar(cfg).items():
        grupo, *resto = chave.split("/")
        subpasta = "mmz4281" if grupo == "grupo1" else "new"
        caminho = raiz_raw.joinpath(subpasta, *resto)

        if not caminho.is_file():
            divergencias.append(
                Divergencia(chave, "ausente", registro.sha256, None)
            )
            continue

        sha_atual, _ = sha256_e_linhas(caminho)
        if sha_atual != registro.sha256:
            divergencias.append(
                Divergencia(chave, "conteudo_mudou", registro.sha256, sha_atual)
            )

    return divergencias
