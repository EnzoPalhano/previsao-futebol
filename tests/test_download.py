"""Testes do download dos CSVs.

Quase tudo aqui roda **sem internet**: o que interessa testar é a montagem das
URLs, a decisão de pular arquivos já baixados e o tratamento dos dois modos de
falha silenciosa (corpo vazio, download interrompido). Para isso trocamos o
``requests.get`` por um dublê.

Só um teste toca a rede de verdade, marcado com ``@pytest.mark.rede`` — ele não
roda no CI (ver ``.github/workflows/ci.yml``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from futebol.config import Config, carregar_config
from futebol.dados import download


# ----------------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------------
@pytest.fixture
def cfg_temporario(tmp_path: Path) -> Config:
    """Uma Config real, mas com a raiz apontando para uma pasta descartável."""
    real = carregar_config()
    return Config(bruto=real.bruto, seed=real.seed, raiz=tmp_path)


class RespostaFalsa:
    """Dublê de ``requests.Response`` suficiente para o download."""

    def __init__(self, conteudo: bytes, status: int = 200) -> None:
        self._conteudo = conteudo
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int = 1):
        for i in range(0, len(self._conteudo), chunk_size):
            yield self._conteudo[i : i + chunk_size]


# ----------------------------------------------------------------------------
# Montagem de URLs e caminhos
# ----------------------------------------------------------------------------
def test_url_do_grupo1_usa_temporada_e_liga(cfg_temporario: Config) -> None:
    alvo = download.alvo_grupo1(cfg_temporario, "E0", 2425)
    assert alvo.url == "https://www.football-data.co.uk/mmz4281/2425/E0.csv"
    assert alvo.destino.parts[-3:] == ("mmz4281", "2425", "E0.csv")
    assert alvo.temporada == 2425


def test_url_do_grupo2_nao_tem_temporada(cfg_temporario: Config) -> None:
    """Grupo 2 vem num arquivo único por país, com todas as temporadas dentro."""
    alvo = download.alvo_grupo2(cfg_temporario, "BRA")
    assert alvo.url == "https://www.football-data.co.uk/new/BRA.csv"
    assert alvo.destino.parts[-2:] == ("new", "BRA.csv")
    assert alvo.temporada is None


def test_camada_ativa_multiplica_ligas_por_temporadas(cfg_temporario: Config) -> None:
    ligas = cfg_temporario.ligas_ativas()
    temporadas = cfg_temporario.temporadas_grupo1()
    alvos = download.alvos_da_camada_ativa(cfg_temporario)

    esperado = len(ligas["grupo1"]) * len(temporadas) + len(ligas["grupo2"])
    assert len(alvos) == esperado
    assert len({a.url for a in alvos}) == esperado, "URLs duplicadas na camada ativa"


# ----------------------------------------------------------------------------
# Comportamento do download
# ----------------------------------------------------------------------------
def test_nao_rebaixa_arquivo_que_ja_existe(
    cfg_temporario: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    alvo = download.alvo_grupo1(cfg_temporario, "E0", 2425)
    alvo.destino.parent.mkdir(parents=True)
    alvo.destino.write_bytes(b"Date,HomeTeam\n2024-08-01,Arsenal\n")

    def explodir(*_a, **_k):  # pragma: no cover - não deve ser chamado
        raise AssertionError("tentou baixar um arquivo que já existia")

    monkeypatch.setattr(requests, "get", explodir)

    resultado = download.baixar_alvo(alvo, user_agent="teste", timeout=5)
    assert resultado.baixado is False
    assert resultado.bytes_gravados == alvo.destino.stat().st_size


def test_forcar_rebaixa_mesmo_existindo(
    cfg_temporario: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O site corrige placares e acrescenta odds; forçar é como capturar isso."""
    alvo = download.alvo_grupo1(cfg_temporario, "E0", 2425)
    alvo.destino.parent.mkdir(parents=True)
    alvo.destino.write_bytes(b"antigo\n")

    monkeypatch.setattr(
        requests, "get", lambda *_a, **_k: RespostaFalsa(b"Date,HomeTeam\nnovo\n")
    )

    resultado = download.baixar_alvo(alvo, user_agent="teste", timeout=5, forcar=True)
    assert resultado.baixado is True
    assert alvo.destino.read_bytes() == b"Date,HomeTeam\nnovo\n"


def test_manda_user_agent_e_segue_redirecionamento(
    cfg_temporario: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Armadilha conhecida: sem User-Agent e sem seguir o 302, vem vazio."""
    capturado: dict[str, object] = {}

    def espiao(url, **kwargs):
        capturado["url"] = url
        capturado.update(kwargs)
        return RespostaFalsa(b"Date,HomeTeam\nx,y\n")

    monkeypatch.setattr(requests, "get", espiao)

    alvo = download.alvo_grupo1(cfg_temporario, "E0", 2425)
    download.baixar_alvo(alvo, user_agent="meu-agente", timeout=7)

    assert capturado["headers"] == {"User-Agent": "meu-agente"}
    assert capturado["allow_redirects"] is True
    assert capturado["timeout"] == 7


def test_corpo_vazio_levanta_erro_claro(
    cfg_temporario: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falhar alto é melhor que gravar um CSV vazio e seguir em frente."""
    monkeypatch.setattr(requests, "get", lambda *_a, **_k: RespostaFalsa(b""))

    alvo = download.alvo_grupo1(cfg_temporario, "E0", 2425)
    with pytest.raises(download.ErroDeDownload, match="vazio"):
        download.baixar_alvo(alvo, user_agent="teste", timeout=5)

    assert not alvo.destino.exists(), "arquivo vazio não pode sobrar no disco"


def test_download_interrompido_nao_deixa_arquivo_pela_metade(
    cfg_temporario: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O risco real: como não rebaixamos o que existe, um CSV truncado ficaria
    para sempre. A escrita em arquivo temporário evita isso."""

    class RespostaQueQuebra(RespostaFalsa):
        def iter_content(self, chunk_size: int = 1):
            yield b"Date,HomeTeam\n"
            raise requests.ConnectionError("conexão caiu no meio")

    monkeypatch.setattr(
        requests, "get", lambda *_a, **_k: RespostaQueQuebra(b"irrelevante")
    )

    alvo = download.alvo_grupo1(cfg_temporario, "E0", 2425)
    with pytest.raises(download.ErroDeDownload):
        download.baixar_alvo(alvo, user_agent="teste", timeout=5)

    assert not alvo.destino.exists()
    assert list(alvo.destino.parent.glob("*.parcial")) == []


def test_erro_http_vira_erro_de_download(
    cfg_temporario: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        requests, "get", lambda *_a, **_k: RespostaFalsa(b"nao importa", status=404)
    )

    alvo = download.alvo_grupo1(cfg_temporario, "E0", 9999)
    with pytest.raises(download.ErroDeDownload):
        download.baixar_alvo(alvo, user_agent="teste", timeout=5)


# ----------------------------------------------------------------------------
# Teste que toca a rede (não roda no CI)
# ----------------------------------------------------------------------------
@pytest.mark.rede
def test_baixa_de_verdade_da_fonte(cfg_temporario: Config) -> None:
    fontes = cfg_temporario.secao("fontes")
    alvo = download.alvo_grupo1(cfg_temporario, "E0", 2425)

    resultado = download.baixar_alvo(
        alvo,
        user_agent=str(fontes["user_agent"]),
        timeout=int(fontes["timeout_segundos"]),
    )

    assert resultado.baixado is True
    assert resultado.bytes_gravados > 10_000
    cabecalho = alvo.destino.read_text(encoding="latin-1").splitlines()[0]
    assert "HomeTeam" in cabecalho
