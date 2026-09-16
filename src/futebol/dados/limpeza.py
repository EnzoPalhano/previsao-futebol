"""De 38 arquivos em três formatos para **uma** tabela de jogos.

Esta é a etapa em que os dados param de ser "arquivos que eu baixei" e viram
"a tabela do projeto". Tudo que vier depois — modelos, backtest, aplicativo —
lê o Parquet que este módulo grava, e nunca mais o CSV cru.

O caminho de um jogo até a tabela:

1. :func:`ler_bruto` abre o CSV tratando BOM e encoding antigo;
2. :func:`converter` detecta o formato (A, B ou C) e renomeia as colunas para
   o padrão, usando os dicionários de :mod:`futebol.dados.formatos`;
3. :func:`construir_tabela` junta todos os arquivos da camada ativa, padroniza
   os nomes dos times **de uma vez só** e devolve a tabela;
4. :func:`salvar` grava ``data/processed/jogos.parquet``.

Três decisões que valem a pena entender:

- **O nome do time vira chave ``PAIS:nome``** (regra 14). A tabela não guarda
  "Palmeiras": guarda ``BRA:Palmeiras``. Existe Nacional no Uruguai e em
  Portugal, River Plate na Argentina e no Uruguai, Everton na Inglaterra e no
  Chile. Juntar dois deles por engano corromperia o Elo e as médias móveis sem
  dar nenhum aviso.
- **Os nomes são padronizados numa passada só**, depois de ler todos os
  arquivos. Assim um nome novo aparece uma única vez em
  ``data/nomes_pendentes.csv``, e não uma vez por temporada.
- **O resultado é recalculado a partir do placar**, nunca copiado da fonte.
  Se a fonte disser "H" num jogo que terminou 1x2, quem manda é o placar — e a
  divergência é contada em :class:`ResumoLimpeza` para aparecer no relatório.

Linha descartada nunca some em silêncio: cada motivo de descarte é contado, e
a contagem entra no relatório de cobertura da Fase 1d.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from futebol.config import Config
from futebol.dados import download, formatos, nomes_times

#: Colunas de odd na tabela final. Separadas do resto porque recebem tratamento
#: próprio: viram número, e o que não for número vira vazio (nunca zero).
COLUNAS_ODDS: tuple[str, ...] = tuple(
    c for c in formatos.COLUNAS_PADRAO if c.startswith("odd_")
)

#: Colunas acrescentadas às :data:`~futebol.dados.formatos.COLUNAS_PADRAO`.
#: Existem por causa das regras 12 e 13: toda análise precisa saber de qual
#: grupo e de qual formato cada jogo veio, senão é impossível dizer quais ligas
#: entraram numa tabela de resultado.
COLUNAS_EXTRAS: tuple[str, ...] = ("pais", "competicao", "grupo", "formato")

#: A ordem final das colunas do Parquet.
COLUNAS_TABELA: tuple[str, ...] = formatos.COLUNAS_PADRAO + COLUNAS_EXTRAS

#: Formatos de data que a fonte usa. Os arquivos recentes têm ano com quatro
#: dígitos; os antigos, dois. Tentamos os dois antes de desistir da linha.
FORMATOS_DE_DATA: tuple[str, ...] = ("%d/%m/%Y", "%d/%m/%y")


class ErroDeLimpeza(Exception):
    """O arquivo não tem o mínimo para virar linha de tabela."""


# ----------------------------------------------------------------------------
# Temporada: um nome só para a mesma coisa
# ----------------------------------------------------------------------------
def temporada_do_codigo(codigo: int | str) -> str:
    """Traduz o código do site (``2425``) para a forma legível (``2024/25``).

    O ``config.yaml`` fala em códigos (``temporadas.grupo1: [1920, ...]``)
    porque é assim que a URL do site funciona. A tabela fala em ``2024/25``
    porque é assim que um relatório se lê. Esta função é a ponte entre os dois.
    """
    texto = str(codigo).strip()
    if len(texto) != 4 or not texto.isdigit():
        raise ErroDeLimpeza(
            f"Código de temporada inválido: {codigo!r}. "
            "Esperado quatro dígitos no formato do site, como 2425."
        )
    inicio, fim = texto[:2], texto[2:]
    # 93/94 é do século passado; 19/20 é deste. O site cobre de 1993 em diante.
    seculo = "19" if int(inicio) >= 90 else "20"
    return f"{seculo}{inicio}/{fim}"


def normalizar_temporada(valor: str) -> str:
    """Põe a temporada do formato C na mesma forma da dos formatos A e B.

    O arquivo único do Grupo 2 traz dois estilos, porque nem todo país joga
    de agosto a maio:

    - ``"2012/2013"`` (Áustria, Dinamarca) vira ``"2012/13"``;
    - ``"2012"`` (Brasil, Noruega, EUA — calendário civil) fica ``"2012"``.
    """
    texto = str(valor).strip()
    if "/" in texto:
        inicio, fim = (parte.strip() for parte in texto.split("/", 1))
        return f"{inicio}/{fim[-2:]}"
    return texto


def ano_inicial(temporada: str) -> int:
    """Ano em que a temporada começou — ``"2024/25"`` e ``"2024"`` dão 2024.

    É por este ano que o corte ``temporadas.grupo2_ano_minimo`` filtra.
    """
    return int(str(temporada).split("/", 1)[0])


# ----------------------------------------------------------------------------
# Leitura
# ----------------------------------------------------------------------------
def ler_bruto(caminho: Path) -> pd.DataFrame:
    """Lê um CSV da fonte sem interpretar nada: tudo como texto.

    Ler tudo como texto é proposital. A conversão para número acontece depois,
    coluna por coluna, com controle do que fazer quando ela falha. Deixar o
    pandas adivinhar faria uma coluna de gols virar texto só porque uma linha
    de jogo adiado está vazia.

    Trata as duas chatices conhecidas dos arquivos: o BOM dos arquivos do
    Grupo 2 (``utf-8-sig``) e os arquivos antigos que não são UTF-8 válido
    (fallback para ``latin-1``, que aceita qualquer byte).
    """
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(
                caminho,
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
                on_bad_lines="skip",
                skip_blank_lines=True,
            )
        except UnicodeDecodeError:
            continue
    raise ErroDeLimpeza(
        f"Não consegui decodificar {caminho} nem como UTF-8 nem como latin-1."
    )


def _para_numero(serie: pd.Series) -> pd.Series:
    """Texto para número, com o que não for número virando vazio (``NaN``)."""
    return pd.to_numeric(serie.replace("", None), errors="coerce")


def _para_data(serie: pd.Series) -> pd.Series:
    """Texto para data, tentando os formatos que a fonte usa, na ordem."""
    resultado = pd.Series(pd.NaT, index=serie.index, dtype="datetime64[ns]")
    restante = serie.fillna("").str.strip()
    for formato in FORMATOS_DE_DATA:
        faltando = resultado.isna()
        if not faltando.any():
            break
        resultado[faltando] = pd.to_datetime(
            restante[faltando], format=formato, errors="coerce"
        )
    return resultado


def resultado_do_placar(
    gols_mandante: pd.Series, gols_visitante: pd.Series
) -> pd.Series:
    """``H``, ``D`` ou ``A`` a partir do placar — a fonte não tem voto aqui."""
    return pd.Series(
        [
            "H" if m > v else "A" if v > m else "D"
            for m, v in zip(gols_mandante, gols_visitante, strict=True)
        ],
        index=gols_mandante.index,
        dtype=object,
    ).astype("str")


# ----------------------------------------------------------------------------
# Conversão de um arquivo
# ----------------------------------------------------------------------------
@dataclass
class ResumoLimpeza:
    """O que entrou, o que saiu e por quê.

    Descarte silencioso é o pior tipo de bug de dados: o relatório fica bonito
    e errado. Por isso todo motivo é contado aqui e aparece no relatório.

    Atributos:
        linhas_lidas: linhas lidas dos CSVs, antes de qualquer filtro.
        jogos: linhas que sobraram na tabela.
        descartes: motivo -> quantidade de linhas descartadas.
        divergencias_resultado: jogos em que a coluna de resultado da fonte não
            batia com o placar. O placar prevaleceu.
        arquivos: quantos arquivos foram lidos.
    """

    linhas_lidas: int = 0
    jogos: int = 0
    descartes: Counter = field(default_factory=Counter)
    divergencias_resultado: int = 0
    arquivos: int = 0

    @property
    def descartadas(self) -> int:
        """Total de linhas descartadas, somando todos os motivos."""
        return int(sum(self.descartes.values()))

    def __add__(self, outro: ResumoLimpeza) -> ResumoLimpeza:
        return ResumoLimpeza(
            linhas_lidas=self.linhas_lidas + outro.linhas_lidas,
            jogos=self.jogos + outro.jogos,
            descartes=self.descartes + outro.descartes,
            divergencias_resultado=(
                self.divergencias_resultado + outro.divergencias_resultado
            ),
            arquivos=self.arquivos + outro.arquivos,
        )


def converter(
    caminho: Path,
    *,
    liga: str | None = None,
    temporada: str | None = None,
    grupo: str | None = None,
) -> tuple[pd.DataFrame, ResumoLimpeza]:
    """Transforma um CSV da fonte nas colunas padrão do projeto.

    Os nomes dos times ainda saem **como vieram da fonte**: quem os troca pela
    chave ``PAIS:nome`` é :func:`construir_tabela`, numa passada só, para que
    um nome novo apareça uma vez em ``nomes_pendentes.csv`` e não uma por
    temporada.

    Args:
        caminho: o CSV baixado.
        liga: código da competição (``"E0"``). Nos formatos A e B vem do
            caminho do arquivo (``mmz4281/2425/E0.csv``); no formato C é
            ignorado, porque o código sai do nome do arquivo.
        temporada: temporada já legível (``"2024/25"``). Ignorada no formato C,
            que traz a temporada dentro do arquivo, linha a linha.
        grupo: ``"grupo1"`` ou ``"grupo2"``. Se omitido, é deduzido do formato.

    Retorna:
        A tabela do arquivo e o resumo do que foi descartado.
    """
    bruto = ler_bruto(caminho)
    formato = formatos.detectar_formato(list(bruto.columns))
    mapa = formatos.MAPAS[formato]
    resumo = ResumoLimpeza(linhas_lidas=len(bruto), arquivos=1)

    if formato != "C" and (liga is None or temporada is None):
        raise ErroDeLimpeza(
            f"{caminho.name} é do formato {formato}: liga e temporada vêm do "
            "caminho do arquivo e precisam ser informadas."
        )

    tabela = pd.DataFrame(index=bruto.index)
    for padrao, origem in mapa.items():
        # Coluna prevista que o arquivo não traz (RUS sem B365, por exemplo)
        # vira coluna vazia. Quem cobra coluna faltando é o teste de inventário.
        tabela[padrao] = bruto[origem] if origem in bruto.columns else None

    # Colunas do padrão que este formato simplesmente não tem (Over/Under no
    # formato C, fechamento de Over/Under no B) existem e ficam vazias.
    for coluna in formatos.COLUNAS_PADRAO:
        if coluna not in tabela.columns:
            tabela[coluna] = None

    if formato == "C":
        codigo = caminho.stem  # BRA.csv -> "BRA": é a chave usada no config.
        tabela["liga"] = codigo
        tabela["competicao"] = bruto[mapa["liga"]].str.strip()
        tabela["temporada"] = bruto[mapa["temporada"]].map(normalizar_temporada)
    else:
        codigo = str(liga)
        tabela["liga"] = codigo
        tabela["competicao"] = ""
        tabela["temporada"] = temporada

    tabela["pais"] = nomes_times.pais_do_codigo(codigo)
    tabela["grupo"] = grupo or ("grupo2" if formato == "C" else "grupo1")
    tabela["formato"] = formato

    tabela["data"] = _para_data(tabela["data"])
    for coluna in ("gols_mandante", "gols_visitante", *COLUNAS_ODDS):
        tabela[coluna] = _para_numero(tabela[coluna])
    for coluna in ("mandante", "visitante"):
        tabela[coluna] = tabela[coluna].fillna("").astype(str).str.strip()

    tabela, resumo = _descartar_invalidas(tabela, resumo)
    return tabela[list(COLUNAS_TABELA)], resumo


def _descartar_invalidas(
    tabela: pd.DataFrame, resumo: ResumoLimpeza
) -> tuple[pd.DataFrame, ResumoLimpeza]:
    """Tira da tabela o que não é jogo, contando cada motivo.

    Os motivos são reais e frequentes: o CSV da temporada em andamento traz
    linhas vazias no fim, e jogo adiado fica sem placar até ser remarcado.
    """
    motivos: list[tuple[str, pd.Series]] = [
        ("sem_times", (tabela["mandante"] == "") | (tabela["visitante"] == "")),
        ("data_invalida", tabela["data"].isna()),
        (
            "sem_placar",
            tabela["gols_mandante"].isna() | tabela["gols_visitante"].isna(),
        ),
        (
            "gols_negativos",
            (tabela["gols_mandante"] < 0) | (tabela["gols_visitante"] < 0),
        ),
    ]
    manter = pd.Series(True, index=tabela.index)
    for nome, condicao in motivos:
        # `fillna(False)` porque uma linha sem placar já saiu por outro motivo:
        # cada linha é contada uma vez só, no primeiro motivo que a pegou.
        ruim = condicao.fillna(False) & manter
        if ruim.any():
            resumo.descartes[nome] += int(ruim.sum())
            manter &= ~ruim

    tabela = tabela[manter].copy()
    for coluna in ("gols_mandante", "gols_visitante"):
        tabela[coluna] = tabela[coluna].astype("int16")

    recalculado = resultado_do_placar(tabela["gols_mandante"], tabela["gols_visitante"])
    da_fonte = tabela["resultado"].fillna("").astype(str).str.strip().str.upper()
    divergentes = (da_fonte != "") & (da_fonte != recalculado)
    resumo.divergencias_resultado += int(divergentes.sum())
    tabela["resultado"] = recalculado

    resumo.jogos = len(tabela)
    return tabela, resumo


# ----------------------------------------------------------------------------
# A tabela inteira
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class ResultadoLimpeza:
    """A tabela pronta e o resumo de como ela ficou pronta."""

    jogos: pd.DataFrame
    resumo: ResumoLimpeza


def caminho_parquet(cfg: Config) -> Path:
    """Onde a tabela final mora: ``data/processed/jogos.parquet``."""
    return cfg.raiz / "data" / "processed" / "jogos.parquet"


def caminho_pendencias(cfg: Config) -> Path:
    """Onde os nomes de time ainda não mapeados são anotados para revisão."""
    return cfg.raiz / "data" / "nomes_pendentes.csv"


def arquivos_da_camada_ativa(cfg: Config) -> list[download.Alvo]:
    """Os arquivos que a camada ativa manda ler, conferindo se estão em disco.

    Levanta:
        ErroDeLimpeza: se algum arquivo ainda não foi baixado, dizendo quais e
            o comando que resolve.
    """
    alvos = download.alvos_da_camada_ativa(cfg)
    faltando = [a for a in alvos if not a.destino.is_file()]
    if faltando:
        lista = ", ".join(sorted(a.destino.name for a in faltando[:8]))
        reticencias = ", ..." if len(faltando) > 8 else ""
        raise ErroDeLimpeza(
            f"{len(faltando)} arquivo(s) da camada {cfg.camada_ativa} não estão "
            f"em data/raw/: {lista}{reticencias}. "
            "Rode `python scripts/baixar_dados.py` antes da limpeza."
        )
    return alvos


def construir_tabela(
    cfg: Config,
    *,
    mapa: nomes_times.MapaTimes | None = None,
    salvar_pendencias: bool = True,
) -> ResultadoLimpeza:
    """Lê todos os arquivos da camada ativa e devolve a tabela única.

    A padronização dos nomes acontece no fim, com todos os pares
    ``(competição, nome)`` de todos os arquivos juntos.

    Levanta:
        nomes_times.NomeDesconhecido: se algum time não estiver no
            ``mapa_times.csv``. É proposital que isso interrompa tudo: seguir
            com um time não reconhecido significa perder jogos na junção sem
            ninguém perceber. Os nomes vão para ``data/nomes_pendentes.csv``.
    """
    ano_minimo = int(cfg.bruto["temporadas"]["grupo2_ano_minimo"])
    partes: list[pd.DataFrame] = []
    resumo = ResumoLimpeza()

    for alvo in arquivos_da_camada_ativa(cfg):
        temporada = (
            temporada_do_codigo(alvo.temporada) if alvo.temporada is not None else None
        )
        parte, resumo_arquivo = converter(
            alvo.destino, liga=alvo.codigo, temporada=temporada, grupo=alvo.grupo
        )

        if alvo.grupo == "grupo2":
            antigas = parte["temporada"].map(ano_inicial) < ano_minimo
            if antigas.any():
                resumo_arquivo.descartes["anterior_ao_corte"] += int(antigas.sum())
                parte = parte[~antigas]
                resumo_arquivo.jogos = len(parte)

        partes.append(parte)
        resumo = resumo + resumo_arquivo

    if not partes:
        raise ErroDeLimpeza(
            f"A camada {cfg.camada_ativa} não tem nenhuma liga. "
            "Ajuste `ligas.ativa` no config.yaml."
        )

    jogos = pd.concat(partes, ignore_index=True)
    jogos, duplicadas = _remover_duplicatas(jogos)
    if duplicadas:
        resumo.descartes["duplicata"] += duplicadas

    jogos = _aplicar_nomes_padrao(
        jogos,
        mapa=mapa if mapa is not None else nomes_times.carregar_mapa(),
        pendencias=caminho_pendencias(cfg) if salvar_pendencias else None,
    )

    jogos = jogos.sort_values(["data", "liga", "mandante"]).reset_index(drop=True)
    resumo.jogos = len(jogos)
    return ResultadoLimpeza(jogos=jogos, resumo=resumo)


def _remover_duplicatas(jogos: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Um jogo é único por liga, temporada, data e as duas equipes.

    Duplicata acontece de verdade: no arquivo único do Grupo 2 alguns países
    repetem o mesmo jogo em competições diferentes, e a temporada em andamento
    é rebaixada por cima da anterior.
    """
    chave = ["liga", "temporada", "data", "mandante", "visitante"]
    antes = len(jogos)
    jogos = jogos.drop_duplicates(subset=chave, keep="first")
    return jogos, antes - len(jogos)


def _aplicar_nomes_padrao(
    jogos: pd.DataFrame,
    *,
    mapa: nomes_times.MapaTimes,
    pendencias: Path | None,
) -> pd.DataFrame:
    """Troca o nome como veio da fonte pela chave ``PAIS:nome`` (regra 14)."""
    pares = set(zip(jogos["liga"], jogos["mandante"], strict=True))
    pares |= set(zip(jogos["liga"], jogos["visitante"], strict=True))

    traducao = nomes_times.padronizar(sorted(pares), mapa, caminho_pendencias=pendencias)
    jogos = jogos.copy()
    for coluna in ("mandante", "visitante"):
        jogos[coluna] = [
            traducao[(liga, nome)] for liga, nome in zip(jogos["liga"], jogos[coluna], strict=True)
        ]
    return jogos


def salvar(jogos: pd.DataFrame, cfg: Config) -> Path:
    """Grava ``data/processed/jogos.parquet`` e devolve o caminho.

    Parquet e não CSV porque ele guarda o tipo de cada coluna: data volta como
    data, e odd vazia volta vazia em vez de virar o texto ``"nan"``.
    """
    destino = caminho_parquet(cfg)
    destino.parent.mkdir(parents=True, exist_ok=True)
    jogos.to_parquet(destino, index=False)
    return destino


def carregar(cfg: Config) -> pd.DataFrame:
    """Lê a tabela já processada, para quem só quer consumir os jogos."""
    destino = caminho_parquet(cfg)
    if not destino.is_file():
        raise ErroDeLimpeza(
            f"{destino} não existe ainda. Rode `python scripts/preparar_dados.py`."
        )
    return pd.read_parquet(destino)
