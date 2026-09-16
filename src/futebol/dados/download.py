"""Download dos CSVs do football-data.co.uk.

O site publica os dados em dois lugares diferentes, e isso decide a URL:

- **Grupo 1** (ligas principais): um arquivo por liga *e* por temporada, em
  ``mmz4281/{temporada}/{liga}.csv``. Ex.: ``mmz4281/2425/E0.csv``.
- **Grupo 2** (Brasil, Argentina, EUA…): um único arquivo por país com todas
  as temporadas juntas, em ``new/{pais}.csv``. Ex.: ``new/BRA.csv``.

Duas armadilhas já mapeadas, ambas tratadas aqui:

1. O site responde **HTTP 302** (redirecionamento). Sem seguir o redirecionamento
   e sem mandar um ``User-Agent``, o download volta vazio — sem erro nenhum, o que
   é pior do que falhar.
2. Um download interrompido no meio deixaria um CSV pela metade no disco. Como o
   módulo não rebaixa arquivo que já existe, esse arquivo quebrado seria usado para
   sempre. Por isso escrevemos primeiro num arquivo temporário e só renomeamos no
   final: ou o arquivo existe inteiro, ou não existe.

Uso típico::

    from futebol.config import carregar_config
    from futebol.dados import download

    cfg = carregar_config()
    resultados = download.baixar_camada_ativa(cfg)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import requests

from futebol.config import Config

# Tamanho do pedaço lido por vez ao gravar o arquivo (64 KB).
# Evita carregar o CSV inteiro na memória de uma vez.
_TAMANHO_BLOCO = 64 * 1024


class ErroDeDownload(Exception):
    """Falha ao baixar um arquivo da fonte."""


@dataclass(frozen=True)
class Alvo:
    """Um arquivo a baixar: de onde vem e onde vai parar.

    Atributos:
        grupo: ``"grupo1"`` ou ``"grupo2"``.
        codigo: código da liga (``"E0"``) ou do país (``"BRA"``).
        temporada: temporada no formato do site (``2425``). ``None`` no Grupo 2,
            porque lá o arquivo já traz todas as temporadas juntas.
        url: endereço completo do CSV.
        destino: caminho onde o arquivo será gravado.
    """

    grupo: str
    codigo: str
    temporada: int | None
    url: str
    destino: Path


@dataclass(frozen=True)
class ResultadoDownload:
    """O que aconteceu com um alvo.

    Atributos:
        alvo: o alvo processado.
        baixado: ``True`` se foi buscado na rede agora, ``False`` se já existia
            em disco e foi reaproveitado.
        bytes_gravados: tamanho final do arquivo em disco.
    """

    alvo: Alvo
    baixado: bool
    bytes_gravados: int


# ----------------------------------------------------------------------------
# Montagem das URLs e dos caminhos locais
# ----------------------------------------------------------------------------
def pasta_raw(cfg: Config) -> Path:
    """Pasta onde os CSVs baixados ficam (``data/raw/``).

    Essa pasta **não** vai para o Git: são dezenas de MB que o site reescreve
    com o tempo. Quem garante a reprodutibilidade é o ``data/manifesto.json``.
    """
    return cfg.raiz / "data" / "raw"


def alvo_grupo1(cfg: Config, liga: str, temporada: int) -> Alvo:
    """Monta o alvo de uma liga do Grupo 1 numa temporada."""
    modelo = str(cfg.bruto["fontes"]["url_grupo1"])
    url = modelo.format(temporada=temporada, liga=liga)
    destino = pasta_raw(cfg) / "mmz4281" / str(temporada) / f"{liga}.csv"
    return Alvo(
        grupo="grupo1", codigo=liga, temporada=temporada, url=url, destino=destino
    )


def alvo_grupo2(cfg: Config, pais: str) -> Alvo:
    """Monta o alvo de um país do Grupo 2 (arquivo único, todas as temporadas)."""
    modelo = str(cfg.bruto["fontes"]["url_grupo2"])
    url = modelo.format(pais=pais)
    destino = pasta_raw(cfg) / "new" / f"{pais}.csv"
    return Alvo(grupo="grupo2", codigo=pais, temporada=None, url=url, destino=destino)


def alvos_da_camada_ativa(cfg: Config) -> list[Alvo]:
    """Lista tudo que a camada de ligas ativa manda baixar.

    O Grupo 1 multiplica ligas por temporadas (10 ligas × 7 temporadas = 70
    arquivos). O Grupo 2 é um arquivo por país, independente de temporada.
    """
    ligas = cfg.ligas_ativas()
    temporadas = cfg.temporadas_grupo1()

    alvos = [
        alvo_grupo1(cfg, liga, temporada)
        for liga in ligas["grupo1"]
        for temporada in temporadas
    ]
    alvos += [alvo_grupo2(cfg, pais) for pais in ligas["grupo2"]]
    return alvos


# ----------------------------------------------------------------------------
# Download propriamente dito
# ----------------------------------------------------------------------------
def baixar_alvo(
    alvo: Alvo,
    *,
    user_agent: str,
    timeout: int,
    forcar: bool = False,
) -> ResultadoDownload:
    """Baixa um :class:`Alvo`, pulando o que já está em disco.

    Args:
        alvo: o que baixar e para onde.
        user_agent: identificação enviada ao servidor. Obrigatório.
        timeout: segundos de espera antes de desistir.
        forcar: se ``True``, rebaixa mesmo que o arquivo já exista. Use quando
            quiser capturar correções que o site fez nos placares ou nas odds.

    Levanta:
        ErroDeDownload: se o HTTP falhar ou o corpo vier vazio.
    """
    if alvo.destino.exists() and not forcar:
        return ResultadoDownload(
            alvo=alvo, baixado=False, bytes_gravados=alvo.destino.stat().st_size
        )

    alvo.destino.parent.mkdir(parents=True, exist_ok=True)
    # Arquivo temporário ao lado do definitivo: se o download morrer no meio,
    # o que fica pela metade é o .parcial, que nunca é lido por ninguém.
    temporario = alvo.destino.with_suffix(alvo.destino.suffix + ".parcial")

    try:
        resposta = requests.get(
            alvo.url,
            headers={"User-Agent": user_agent},
            timeout=timeout,
            allow_redirects=True,  # o site responde 302; sem isso vem vazio
            stream=True,
        )
        resposta.raise_for_status()

        gravados = 0
        with temporario.open("wb") as arquivo:
            for bloco in resposta.iter_content(chunk_size=_TAMANHO_BLOCO):
                if bloco:
                    arquivo.write(bloco)
                    gravados += len(bloco)
    except requests.RequestException as erro:
        temporario.unlink(missing_ok=True)
        raise ErroDeDownload(f"Falha ao baixar {alvo.url}: {erro}") from erro

    if gravados == 0:
        temporario.unlink(missing_ok=True)
        raise ErroDeDownload(
            f"O servidor devolveu um arquivo vazio para {alvo.url}. "
            "Normalmente isso significa User-Agent ausente ou redirecionamento "
            "não seguido."
        )

    # replace (e não rename) sobrescreve no Windows sem reclamar.
    temporario.replace(alvo.destino)
    return ResultadoDownload(alvo=alvo, baixado=True, bytes_gravados=gravados)


def baixar_camada_ativa(
    cfg: Config, *, forcar: bool = False
) -> list[ResultadoDownload]:
    """Baixa todos os arquivos da camada de ligas ativa.

    Args:
        cfg: configuração carregada.
        forcar: rebaixa arquivos já existentes.

    Retorna:
        Um resultado por alvo, na ordem em que foram processados.
    """
    fontes = cfg.secao("fontes")
    user_agent = str(fontes["user_agent"])
    timeout = int(fontes["timeout_segundos"])

    return [
        baixar_alvo(alvo, user_agent=user_agent, timeout=timeout, forcar=forcar)
        for alvo in alvos_da_camada_ativa(cfg)
    ]
