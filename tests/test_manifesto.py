"""Testes do manifesto.

O manifesto é a única defesa contra um problema silencioso: o football-data
reescreve os CSVs, e sem registro ninguém consegue dizer de qual versão do
arquivo saiu um número do relatório. Estes testes cobrem o cálculo da impressão
digital, a ida e volta do JSON e a detecção de arquivo alterado.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from futebol.config import Config, carregar_config
from futebol.dados import manifesto


@pytest.fixture
def cfg_temporario(tmp_path: Path) -> Config:
    real = carregar_config()
    return Config(bruto=real.bruto, seed=real.seed, raiz=tmp_path)


def criar_csv(cfg: Config, subpasta: str, *partes: str, conteudo: bytes) -> Path:
    """Cria um CSV dentro de data/raw/<subpasta>/... e devolve o caminho."""
    caminho = cfg.raiz.joinpath("data", "raw", subpasta, *partes)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    return caminho


# ----------------------------------------------------------------------------
# Impressão digital e contagem de linhas
# ----------------------------------------------------------------------------
def test_sha256_bate_com_o_da_biblioteca(tmp_path: Path) -> None:
    conteudo = b"Date,HomeTeam,AwayTeam\n01/08/24,Arsenal,Chelsea\n"
    arquivo = tmp_path / "x.csv"
    arquivo.write_bytes(conteudo)

    sha, linhas = manifesto.sha256_e_linhas(arquivo)
    assert sha == hashlib.sha256(conteudo).hexdigest()
    assert linhas == 2


def test_conta_ultima_linha_sem_quebra_no_final(tmp_path: Path) -> None:
    """Muitos CSVs da fonte não terminam em quebra de linha."""
    arquivo = tmp_path / "x.csv"
    arquivo.write_bytes(b"cabecalho\nlinha1\nlinha2")
    _, linhas = manifesto.sha256_e_linhas(arquivo)
    assert linhas == 3


def test_um_byte_diferente_muda_a_impressao_digital(tmp_path: Path) -> None:
    """É isso que detecta um placar corrigido pela fonte."""
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_bytes(b"Arsenal,Chelsea,2,1\n")
    b.write_bytes(b"Arsenal,Chelsea,3,1\n")
    assert manifesto.sha256_e_linhas(a)[0] != manifesto.sha256_e_linhas(b)[0]


# ----------------------------------------------------------------------------
# Chave do manifesto
# ----------------------------------------------------------------------------
def test_chave_traduz_pastas_para_grupos(cfg_temporario: Config) -> None:
    raiz_raw = cfg_temporario.raiz / "data" / "raw"
    g1 = criar_csv(cfg_temporario, "mmz4281", "2425", "E0.csv", conteudo=b"a\n")
    g2 = criar_csv(cfg_temporario, "new", "BRA.csv", conteudo=b"a\n")

    assert manifesto.chave_do_arquivo(g1, raiz_raw) == "grupo1/2425/E0.csv"
    assert manifesto.chave_do_arquivo(g2, raiz_raw) == "grupo2/BRA.csv"


def test_chave_recusa_pasta_desconhecida(cfg_temporario: Config) -> None:
    raiz_raw = cfg_temporario.raiz / "data" / "raw"
    estranho = criar_csv(cfg_temporario, "inventada", "X.csv", conteudo=b"a\n")
    with pytest.raises(manifesto.ErroDeManifesto, match="mmz4281"):
        manifesto.chave_do_arquivo(estranho, raiz_raw)


# ----------------------------------------------------------------------------
# Gravar e ler
# ----------------------------------------------------------------------------
def test_salvar_e_carregar_preserva_os_dados(cfg_temporario: Config) -> None:
    raiz_raw = cfg_temporario.raiz / "data" / "raw"
    arquivo = criar_csv(
        cfg_temporario, "mmz4281", "2425", "E0.csv", conteudo=b"cab\nlinha\n"
    )
    registro = manifesto.registrar_arquivo(
        arquivo, url="https://exemplo/E0.csv", raiz_raw=raiz_raw
    )

    manifesto.salvar(cfg_temporario, {registro.chave: registro})
    lido = manifesto.carregar(cfg_temporario)

    assert lido == {registro.chave: registro}
    assert lido[registro.chave].linhas == 2
    assert lido[registro.chave].url == "https://exemplo/E0.csv"


def test_manifesto_inexistente_carrega_vazio(cfg_temporario: Config) -> None:
    assert manifesto.carregar(cfg_temporario) == {}


def test_json_gravado_fica_ordenado(cfg_temporario: Config) -> None:
    """Sem ordenação, cada rodada geraria um diff gigante no Git à toa."""
    raiz_raw = cfg_temporario.raiz / "data" / "raw"
    registros = {}
    for liga in ("SP1", "E0", "D1"):
        arquivo = criar_csv(
            cfg_temporario, "mmz4281", "2425", f"{liga}.csv", conteudo=b"cab\n"
        )
        r = manifesto.registrar_arquivo(arquivo, url=f"u/{liga}", raiz_raw=raiz_raw)
        registros[r.chave] = r

    caminho = manifesto.salvar(cfg_temporario, registros)
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    chaves = list(bruto["arquivos"])
    assert chaves == sorted(chaves)


def test_json_corrompido_da_mensagem_util(cfg_temporario: Config) -> None:
    caminho = manifesto.caminho_manifesto(cfg_temporario)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("{ isto nao e json", encoding="utf-8")

    with pytest.raises(manifesto.ErroDeManifesto, match="JSON"):
        manifesto.carregar(cfg_temporario)


# ----------------------------------------------------------------------------
# Conferência
# ----------------------------------------------------------------------------
def test_conferir_nao_acusa_nada_quando_tudo_bate(cfg_temporario: Config) -> None:
    raiz_raw = cfg_temporario.raiz / "data" / "raw"
    arquivo = criar_csv(
        cfg_temporario, "mmz4281", "2425", "E0.csv", conteudo=b"cab\nlinha\n"
    )
    r = manifesto.registrar_arquivo(arquivo, url="u", raiz_raw=raiz_raw)
    manifesto.salvar(cfg_temporario, {r.chave: r})

    assert manifesto.conferir(cfg_temporario) == []


def test_conferir_detecta_arquivo_reescrito_pela_fonte(cfg_temporario: Config) -> None:
    """O caso que motiva o manifesto existir."""
    raiz_raw = cfg_temporario.raiz / "data" / "raw"
    arquivo = criar_csv(
        cfg_temporario, "mmz4281", "2425", "E0.csv", conteudo=b"Arsenal,Chelsea,2,1\n"
    )
    r = manifesto.registrar_arquivo(arquivo, url="u", raiz_raw=raiz_raw)
    manifesto.salvar(cfg_temporario, {r.chave: r})

    # A fonte corrige o placar.
    arquivo.write_bytes(b"Arsenal,Chelsea,3,1\n")

    divergencias = manifesto.conferir(cfg_temporario)
    assert len(divergencias) == 1
    assert divergencias[0].motivo == "conteudo_mudou"
    assert divergencias[0].chave == "grupo1/2425/E0.csv"
    assert divergencias[0].sha_atual != divergencias[0].sha_registrado


def test_conferir_detecta_arquivo_apagado(cfg_temporario: Config) -> None:
    raiz_raw = cfg_temporario.raiz / "data" / "raw"
    arquivo = criar_csv(cfg_temporario, "new", "BRA.csv", conteudo=b"cab\n")
    r = manifesto.registrar_arquivo(arquivo, url="u", raiz_raw=raiz_raw)
    manifesto.salvar(cfg_temporario, {r.chave: r})
    arquivo.unlink()

    divergencias = manifesto.conferir(cfg_temporario)
    assert [d.motivo for d in divergencias] == ["ausente"]
    assert divergencias[0].sha_atual is None


def test_arquivo_nao_registrado_nao_e_divergencia(cfg_temporario: Config) -> None:
    """Baixar algo novo não é 'divergência' — é só ainda não registrado."""
    criar_csv(cfg_temporario, "mmz4281", "2425", "E0.csv", conteudo=b"cab\n")
    assert manifesto.conferir(cfg_temporario) == []
