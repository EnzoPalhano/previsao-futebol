"""Testes da limpeza: os três formatos viram uma tabela só, sem perder jogo.

Os testes da fase exigidos pela especificação estão todos aqui: sem duplicatas,
datas válidas, gols não negativos, resultado coerente com o placar, colunas
esperadas por formato, e nome de time desconhecido faz falhar.

Tudo roda sobre CSVs sintéticos escritos em ``tmp_path``. Nenhum teste depende
de ter ``data/raw/`` preenchido ou de internet — o CI roda sem os dois.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from futebol.dados import formatos, limpeza, nomes_times


# ----------------------------------------------------------------------------
# Arquivos sintéticos: só as colunas essenciais de cada formato
# ----------------------------------------------------------------------------
def escrever_csv(caminho: Path, colunas: list[str], linhas: list[dict[str, str]]) -> Path:
    """Escreve um CSV com as colunas pedidas, vazio onde a linha não disser nada."""
    conteudo = [",".join(colunas)]
    conteudo += [",".join(str(linha.get(c, "")) for c in colunas) for linha in linhas]
    caminho.write_text("\n".join(conteudo) + "\n", encoding="utf-8")
    return caminho


def csv_formato_a(tmp_path: Path, linhas: list[dict[str, str]]) -> Path:
    colunas = sorted(formatos.COLUNAS_ESSENCIAIS["A"])
    return escrever_csv(tmp_path / "E0.csv", colunas, linhas)


def csv_formato_c(tmp_path: Path, linhas: list[dict[str, str]], nome: str = "BRA") -> Path:
    colunas = sorted(formatos.COLUNAS_ESSENCIAIS["C"])
    return escrever_csv(tmp_path / f"{nome}.csv", colunas, linhas)


#: Um jogo completo do formato A, para variar só o que o teste quer variar.
JOGO_A: dict[str, str] = {
    "Date": "16/08/2024",
    "HomeTeam": "Arsenal",
    "AwayTeam": "Chelsea",
    "FTHG": "2",
    "FTAG": "1",
    "FTR": "H",
    "AvgH": "1.80",
    "AvgD": "3.60",
    "AvgA": "4.20",
    "Avg>2.5": "1.90",
    "Avg<2.5": "1.95",
    "AvgCH": "1.75",
    "AvgCD": "3.70",
    "AvgCA": "4.40",
    "AvgC>2.5": "1.88",
    "AvgC<2.5": "1.97",
}

#: Um jogo completo do formato C (Grupo 2): só fechamento de 1X2.
JOGO_C: dict[str, str] = {
    "Country": "Brazil",
    "League": "Serie A",
    "Season": "2024",
    "Date": "19/05/2024",
    "Home": "Palmeiras",
    "Away": "Santos",
    "HG": "1",
    "AG": "1",
    "Res": "D",
    "AvgCH": "1.69",
    "AvgCD": "3.50",
    "AvgCA": "4.90",
}


def mapa_de(pares: list[tuple[str, str]]) -> nomes_times.MapaTimes:
    """Mapa de times em memória, no formato ``(pais, nome)``."""
    return nomes_times.MapaTimes(
        [{"pais": pais, "nome_fonte": nome, "nome_padrao": nome} for pais, nome in pares]
    )


# ----------------------------------------------------------------------------
# Temporada
# ----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [(2425, "2024/25"), ("1920", "2019/20"), (2526, "2025/26"), (9394, "1993/94")],
)
def test_codigo_do_site_vira_temporada_legivel(codigo: int | str, esperado: str) -> None:
    assert limpeza.temporada_do_codigo(codigo) == esperado


def test_codigo_de_temporada_invalido_falha() -> None:
    with pytest.raises(limpeza.ErroDeLimpeza):
        limpeza.temporada_do_codigo("2024/25")


@pytest.mark.parametrize(
    ("bruta", "esperada"),
    [("2012/2013", "2012/13"), ("2012", "2012"), (" 2019/2020 ", "2019/20")],
)
def test_temporada_do_formato_c_vira_a_mesma_forma(bruta: str, esperada: str) -> None:
    """O Grupo 2 mistura calendário civil e temporada cruzada no mesmo arquivo."""
    assert limpeza.normalizar_temporada(bruta) == esperada


@pytest.mark.parametrize(("temporada", "ano"), [("2024/25", 2024), ("2012", 2012)])
def test_ano_inicial(temporada: str, ano: int) -> None:
    assert limpeza.ano_inicial(temporada) == ano


# ----------------------------------------------------------------------------
# Conversão: as colunas esperadas por formato
# ----------------------------------------------------------------------------
def test_formato_a_traz_pre_jogo_e_fechamento(tmp_path: Path) -> None:
    arquivo = csv_formato_a(tmp_path, [JOGO_A])
    tabela, _ = limpeza.converter(arquivo, liga="E0", temporada="2024/25")

    assert list(tabela.columns) == list(limpeza.COLUNAS_TABELA)
    linha = tabela.iloc[0]
    assert linha["formato"] == "A"
    assert linha["grupo"] == "grupo1"
    assert linha["pais"] == "ENG"
    assert linha["data"] == pd.Timestamp("2024-08-16")
    assert linha["odd_pre_H"] == 1.80
    assert linha["odd_fech_over25"] == 1.88


def test_formato_c_fica_sem_odd_pre_jogo(tmp_path: Path) -> None:
    """Regra 12: o Grupo 2 só tem fechamento de 1X2 — o resto fica vazio."""
    arquivo = csv_formato_c(tmp_path, [JOGO_C])
    tabela, _ = limpeza.converter(arquivo)

    linha = tabela.iloc[0]
    assert linha["formato"] == "C"
    assert linha["grupo"] == "grupo2"
    assert linha["liga"] == "BRA"
    assert linha["competicao"] == "Serie A"
    assert linha["temporada"] == "2024"
    assert linha["odd_fech_H"] == 1.69
    for coluna in ("odd_pre_H", "odd_pre_over25", "odd_fech_over25"):
        assert pd.isna(linha[coluna]), f"{coluna} não pode ter valor no formato C"


def test_odd_impossivel_vira_vazia_e_o_jogo_fica(tmp_path: Path) -> None:
    """Odd <= 1,00 não existe: ela pagaria menos do que o apostador arriscou.

    A fonte tem esse erro de digitação — o Colônia x RB Leipzig de 01/06/2020
    está com ``0.42`` no fechamento de Over 2,5. Precisa morrer aqui, na
    limpeza, porque ``1/0,42`` dá 238% de probabilidade implícita e um jogo
    desses entra na média de margem de uma liga inteira sem dar erro nenhum.

    O jogo continua na tabela: o problema é da odd, não da partida.
    """
    arquivo = csv_formato_a(
        tmp_path, [{**JOGO_A, "AvgC>2.5": "0.42", "AvgH": "1.00"}]
    )
    tabela, resumo = limpeza.converter(arquivo, liga="E0", temporada="2024/25")

    assert len(tabela) == 1, "o placar do jogo continua valendo para treinar"
    linha = tabela.iloc[0]
    assert pd.isna(linha["odd_fech_over25"]), "a odd de 0,42 tinha que sumir"
    assert pd.isna(linha["odd_pre_H"]), "odd de 1,00 também é impossível"
    assert linha["odd_pre_D"] == 3.60, "as odds boas do mesmo jogo continuam"
    assert resumo.odds_impossiveis == 2
    assert resumo.descartes == {}, "nenhuma LINHA foi descartada por isso"


def test_coluna_opcional_ausente_vira_coluna_vazia(tmp_path: Path) -> None:
    """RUS não traz B365 nem Betfair, e ainda assim tem que virar tabela."""
    colunas = [c for c in sorted(formatos.COLUNAS_ESSENCIAIS["C"]) if c != "AvgCD"]
    arquivo = escrever_csv(tmp_path / "RUS.csv", colunas, [JOGO_C])

    tabela, _ = limpeza.converter(arquivo)
    assert pd.isna(tabela.iloc[0]["odd_fech_D"])
    assert tabela.iloc[0]["odd_fech_H"] == 1.69


def test_formato_a_sem_liga_e_temporada_falha(tmp_path: Path) -> None:
    """Nos formatos A e B a liga vem do caminho: esquecer disso é erro, não vazio."""
    arquivo = csv_formato_a(tmp_path, [JOGO_A])
    with pytest.raises(limpeza.ErroDeLimpeza, match="formato A"):
        limpeza.converter(arquivo)


def test_data_com_ano_de_dois_digitos(tmp_path: Path) -> None:
    arquivo = csv_formato_a(tmp_path, [{**JOGO_A, "Date": "16/08/24"}])
    tabela, _ = limpeza.converter(arquivo, liga="E0", temporada="2024/25")
    assert tabela.iloc[0]["data"] == pd.Timestamp("2024-08-16")


def test_arquivo_com_bom_e_lido(tmp_path: Path) -> None:
    """Os arquivos do Grupo 2 começam com três bytes invisíveis."""
    arquivo = csv_formato_c(tmp_path, [JOGO_C])
    arquivo.write_bytes(b"\xef\xbb\xbf" + arquivo.read_bytes())

    tabela, _ = limpeza.converter(arquivo)
    assert tabela.iloc[0]["competicao"] == "Serie A"


# ----------------------------------------------------------------------------
# Descartes: nada some em silêncio
# ----------------------------------------------------------------------------
def test_jogo_adiado_e_descartado_e_contado(tmp_path: Path) -> None:
    adiado = {**JOGO_A, "FTHG": "", "FTAG": "", "FTR": ""}
    arquivo = csv_formato_a(tmp_path, [JOGO_A, adiado])

    tabela, resumo = limpeza.converter(arquivo, liga="E0", temporada="2024/25")
    assert len(tabela) == 1
    assert resumo.linhas_lidas == 2
    assert resumo.descartes["sem_placar"] == 1
    assert resumo.descartadas == 1


def test_linha_vazia_e_data_invalida_sao_descartadas(tmp_path: Path) -> None:
    sem_times = {**JOGO_A, "HomeTeam": "", "AwayTeam": ""}
    data_ruim = {**JOGO_A, "Date": "16-ago-2024"}
    arquivo = csv_formato_a(tmp_path, [JOGO_A, sem_times, data_ruim])

    tabela, resumo = limpeza.converter(arquivo, liga="E0", temporada="2024/25")
    assert len(tabela) == 1
    assert resumo.descartes["sem_times"] == 1
    assert resumo.descartes["data_invalida"] == 1


def test_gols_negativos_sao_descartados(tmp_path: Path) -> None:
    arquivo = csv_formato_a(tmp_path, [JOGO_A, {**JOGO_A, "FTHG": "-1"}])

    tabela, resumo = limpeza.converter(arquivo, liga="E0", temporada="2024/25")
    assert resumo.descartes["gols_negativos"] == 1
    assert (tabela[["gols_mandante", "gols_visitante"]] >= 0).all().all()


def test_cada_linha_descartada_conta_uma_vez_so(tmp_path: Path) -> None:
    """Linha vazia falha em vários motivos; ela é contada no primeiro."""
    vazia = {c: "" for c in JOGO_A}
    arquivo = csv_formato_a(tmp_path, [JOGO_A, vazia])

    _, resumo = limpeza.converter(arquivo, liga="E0", temporada="2024/25")
    assert resumo.descartadas == 1


# ----------------------------------------------------------------------------
# Resultado: quem manda é o placar
# ----------------------------------------------------------------------------
def test_resultado_vem_do_placar_nao_da_fonte(tmp_path: Path) -> None:
    errado = {**JOGO_A, "FTHG": "1", "FTAG": "2", "FTR": "H"}
    arquivo = csv_formato_a(tmp_path, [errado])

    tabela, resumo = limpeza.converter(arquivo, liga="E0", temporada="2024/25")
    assert tabela.iloc[0]["resultado"] == "A"
    assert resumo.divergencias_resultado == 1


@pytest.mark.parametrize(
    ("casa", "fora", "esperado"), [("3", "0", "H"), ("0", "0", "D"), ("0", "2", "A")]
)
def test_resultado_coerente_com_o_placar(
    tmp_path: Path, casa: str, fora: str, esperado: str
) -> None:
    arquivo = csv_formato_a(tmp_path, [{**JOGO_A, "FTHG": casa, "FTAG": fora}])
    tabela, _ = limpeza.converter(arquivo, liga="E0", temporada="2024/25")
    assert tabela.iloc[0]["resultado"] == esperado


# ----------------------------------------------------------------------------
# Duplicatas e nomes de time
# ----------------------------------------------------------------------------
def test_jogo_repetido_e_removido_uma_vez() -> None:
    jogos = pd.DataFrame(
        {
            "liga": ["E0", "E0", "E0"],
            "temporada": ["2024/25"] * 3,
            "data": [pd.Timestamp("2024-08-16")] * 3,
            "mandante": ["Arsenal", "Arsenal", "Chelsea"],
            "visitante": ["Chelsea", "Chelsea", "Arsenal"],
        }
    )
    sem_duplicata, removidas = limpeza._remover_duplicatas(jogos)
    assert removidas == 1
    assert len(sem_duplicata) == 2


def test_nome_de_time_fora_do_mapa_faz_falhar(tmp_path: Path) -> None:
    """Falhar aqui é o ponto: nome não reconhecido some na junção sem aviso."""
    jogos = pd.DataFrame(
        {"liga": ["E0"], "mandante": ["Arsenal"], "visitante": ["Time Novo FC"]}
    )
    pendencias = tmp_path / "nomes_pendentes.csv"

    with pytest.raises(nomes_times.NomeDesconhecido) as erro:
        limpeza._aplicar_nomes_padrao(
            jogos, mapa=mapa_de([("ENG", "Arsenal")]), pendencias=pendencias
        )

    assert [p.nome_fonte for p in erro.value.pendentes] == ["Time Novo FC"]
    assert "Time Novo FC" in pendencias.read_text(encoding="utf-8")


def test_time_vira_chave_com_pais() -> None:
    """Regra 14: a chave é ``PAIS:nome``, nunca o nome sozinho."""
    jogos = pd.DataFrame(
        {"liga": ["E0"], "mandante": ["Arsenal"], "visitante": ["Chelsea"]}
    )
    padronizados = limpeza._aplicar_nomes_padrao(
        jogos,
        mapa=mapa_de([("ENG", "Arsenal"), ("ENG", "Chelsea")]),
        pendencias=None,
    )
    assert padronizados.iloc[0]["mandante"] == "ENG:Arsenal"
    assert padronizados.iloc[0]["visitante"] == "ENG:Chelsea"


# ----------------------------------------------------------------------------
# A tabela inteira, de ponta a ponta
# ----------------------------------------------------------------------------
@pytest.fixture
def projeto(tmp_path: Path) -> Path:
    """Uma raiz de projeto de mentira, com data/raw/ já preenchido."""
    raw = tmp_path / "data" / "raw"
    (raw / "mmz4281" / "2425").mkdir(parents=True)
    (raw / "new").mkdir(parents=True)
    csv_formato_a(raw / "mmz4281" / "2425", [JOGO_A])
    csv_formato_c(raw / "new", [JOGO_C, {**JOGO_C, "Season": "2005"}])
    return tmp_path


def config_de_teste(raiz: Path):
    from futebol.config import Config

    bruto = {
        "seed": 42,
        "ligas": {
            "ativa": "teste",
            "camadas": {"teste": {"grupo1": ["E0"], "grupo2": ["BRA"]}},
        },
        "temporadas": {"grupo1": [2425], "grupo2_ano_minimo": 2012},
        "fontes": {
            "url_grupo1": "http://exemplo/{temporada}/{liga}.csv",
            "url_grupo2": "http://exemplo/new/{pais}.csv",
        },
    }
    return Config(bruto=bruto, seed=42, raiz=raiz)


def test_tabela_junta_os_grupos_e_marca_cada_um(projeto: Path) -> None:
    cfg = config_de_teste(projeto)
    mapa = mapa_de(
        [("ENG", "Arsenal"), ("ENG", "Chelsea"), ("BRA", "Palmeiras"), ("BRA", "Santos")]
    )

    resultado = limpeza.construir_tabela(cfg, mapa=mapa, salvar_pendencias=False)
    jogos = resultado.jogos

    assert len(jogos) == 2
    assert set(jogos["grupo"]) == {"grupo1", "grupo2"}
    assert set(jogos["mandante"]) == {"ENG:Arsenal", "BRA:Palmeiras"}
    # A temporada de 2005 está antes do corte grupo2_ano_minimo.
    assert resultado.resumo.descartes["anterior_ao_corte"] == 1


def test_arquivo_que_falta_diz_o_comando_que_resolve(tmp_path: Path) -> None:
    cfg = config_de_teste(tmp_path)
    with pytest.raises(limpeza.ErroDeLimpeza, match="baixar_dados.py"):
        limpeza.arquivos_da_camada_ativa(cfg)


def test_parquet_guarda_os_tipos(projeto: Path) -> None:
    """Parquet e não CSV: data volta data, odd vazia volta vazia."""
    cfg = config_de_teste(projeto)
    mapa = mapa_de(
        [("ENG", "Arsenal"), ("ENG", "Chelsea"), ("BRA", "Palmeiras"), ("BRA", "Santos")]
    )
    resultado = limpeza.construir_tabela(cfg, mapa=mapa, salvar_pendencias=False)

    destino = limpeza.salvar(resultado.jogos, cfg)
    assert destino == limpeza.caminho_parquet(cfg)

    lida = limpeza.carregar(cfg)
    assert list(lida.columns) == list(limpeza.COLUNAS_TABELA)
    assert pd.api.types.is_datetime64_any_dtype(lida["data"])
    grupo2 = lida[lida["grupo"] == "grupo2"]
    assert grupo2["odd_pre_H"].isna().all()


def test_carregar_sem_parquet_diz_o_que_rodar(tmp_path: Path) -> None:
    cfg = config_de_teste(tmp_path)
    with pytest.raises(limpeza.ErroDeLimpeza, match="preparar_dados.py"):
        limpeza.carregar(cfg)


# ----------------------------------------------------------------------------
# A trava contra fusão errada de clubes
# ----------------------------------------------------------------------------
def test_fusao_errada_de_clubes_e_pega_pelo_confronto_direto() -> None:
    """A prova de que duas grafias são clubes diferentes: elas se enfrentaram.

    Juntar dois clubes distintos sob o mesmo ``nome_padrao`` não daria erro
    nenhum — só misturaria dois históricos. A não ser que exista o jogo de um
    contra o outro, que depois da fusão vira um time contra si mesmo.
    """
    jogos = pd.DataFrame(
        {
            "liga": ["I1"],
            "data": [pd.Timestamp("2024-09-01")],
            "mandante": ["ITA:Reggiana"],
            "visitante": ["ITA:Reggiana"],
        }
    )
    with pytest.raises(limpeza.ErroDeLimpeza, match="ITA:Reggiana"):
        limpeza._conferir_time_contra_si(jogos)


def test_tabela_normal_passa_pela_trava(projeto: Path) -> None:
    cfg = config_de_teste(projeto)
    mapa = mapa_de(
        [("ENG", "Arsenal"), ("ENG", "Chelsea"), ("BRA", "Palmeiras"), ("BRA", "Santos")]
    )
    resultado = limpeza.construir_tabela(cfg, mapa=mapa, salvar_pendencias=False)
    assert (resultado.jogos["mandante"] != resultado.jogos["visitante"]).all()


def test_mapa_que_junta_dois_clubes_faz_a_tabela_falhar(projeto: Path) -> None:
    """O mapa é quem decide que duas grafias são o mesmo clube — e pode errar."""
    cfg = config_de_teste(projeto)
    mapa = nomes_times.MapaTimes(
        [
            {"pais": "ENG", "nome_fonte": "Arsenal", "nome_padrao": "Arsenal"},
            # Errado de propósito: Chelsea apontando para a chave do Arsenal.
            {"pais": "ENG", "nome_fonte": "Chelsea", "nome_padrao": "Arsenal"},
            {"pais": "BRA", "nome_fonte": "Palmeiras", "nome_padrao": "Palmeiras"},
            {"pais": "BRA", "nome_fonte": "Santos", "nome_padrao": "Santos"},
        ]
    )
    with pytest.raises(limpeza.ErroDeLimpeza, match="mesmo time nos dois lados"):
        limpeza.construir_tabela(cfg, mapa=mapa, salvar_pendencias=False)
