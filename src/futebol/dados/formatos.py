"""Os três formatos de CSV da fonte, e como cada um vira as colunas padrão.

A fonte não tem um formato só. Tem três, e a diferença entre eles decide o que
o projeto **pode** fazer com cada liga:

======  =====================================  ==========================
Formato Quem usa                               O que tem
======  =====================================  ==========================
A       Ligas principais, 2019/20 em diante    Tudo: 1X2 e Over/Under, pré-jogo e fechamento
B       Ligas principais, até 2018/19          1X2 pré e fechamento; Over/Under só pré
C       Grupo 2 (BRA, ARG, USA…), arquivo      Só fechamento de 1X2
        único por país
======  =====================================  ==========================

Os mapeamentos são **dados declarativos** (dicionários), não ``if`` espalhado
pelo código: acrescentar um formato novo é acrescentar um dicionário.

Armadilhas já confirmadas em inspeção real (16/09/2026), todas tratadas aqui:

- **A quebra A↔B é exatamente entre 1819 e 1920.** Antes disso o prefixo das
  odds médias é ``Bb`` (Betbrain); depois é ``Avg``.
- **Os arquivos do formato C começam com BOM** (três bytes invisíveis no
  início). Sem tratar, a primeira coluna vira ``"\\ufeffCountry"`` e qualquer
  acesso a ``Country`` estoura com ``KeyError``.
- **RUS tem 19 colunas, não 25**: não traz B365 nem Betfair. Por isso as odds
  dessas duas casas são *opcionais* no formato C — só as ``AvgC*`` são exigidas.
- ⚠️ **No formato B, a odd de fechamento é da Pinnacle (``PSC*``), não a média
  do mercado.** Nos formatos A e C o fechamento é ``AvgC*``, que é média. Comparar
  uma média pré-jogo com um fechamento da Pinnacle **não é** a mesma medida de
  CLV — a Pinnacle costuma pagar mais que a média. Ver :data:`AVISO_CLV_FORMATO_B`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ----------------------------------------------------------------------------
# As colunas padrão que todo formato precisa produzir
# ----------------------------------------------------------------------------
#: Colunas da tabela unificada, na ordem em que aparecem no Parquet.
#: Quem não tem a odd deixa a coluna vazia — nunca inventa valor.
COLUNAS_PADRAO: tuple[str, ...] = (
    "data",
    "liga",
    "temporada",
    "mandante",
    "visitante",
    "gols_mandante",
    "gols_visitante",
    "resultado",
    "odd_pre_H",
    "odd_pre_D",
    "odd_pre_A",
    "odd_pre_over25",
    "odd_pre_under25",
    "odd_fech_H",
    "odd_fech_D",
    "odd_fech_A",
    "odd_fech_over25",
    "odd_fech_under25",
)

# ----------------------------------------------------------------------------
# Mapeamentos: coluna padrão -> coluna no arquivo de origem
# ----------------------------------------------------------------------------
# Só as colunas que vêm direto do arquivo aparecem aqui. `liga` e `temporada`
# no formato A/B vêm do caminho do arquivo (mmz4281/2425/E0.csv), não de dentro
# dele, por isso estão ausentes nos mapas A e B.

#: Formato A — ligas principais, 2019/20 em diante. A odd pré-jogo é ``Avg*``
#: (média do mercado), que é a odd em que o projeto aposta (regra 8).
MAPA_A: dict[str, str] = {
    "data": "Date",
    "mandante": "HomeTeam",
    "visitante": "AwayTeam",
    "gols_mandante": "FTHG",
    "gols_visitante": "FTAG",
    "resultado": "FTR",
    "odd_pre_H": "AvgH",
    "odd_pre_D": "AvgD",
    "odd_pre_A": "AvgA",
    "odd_pre_over25": "Avg>2.5",
    "odd_pre_under25": "Avg<2.5",
    "odd_fech_H": "AvgCH",
    "odd_fech_D": "AvgCD",
    "odd_fech_A": "AvgCA",
    "odd_fech_over25": "AvgC>2.5",
    "odd_fech_under25": "AvgC<2.5",
}

#: Formato B — ligas principais, até 2018/19. Prefixo ``Bb`` (Betbrain) no lugar
#: de ``Avg``. Não existe fechamento de Over/Under nessas temporadas.
MAPA_B: dict[str, str] = {
    "data": "Date",
    "mandante": "HomeTeam",
    "visitante": "AwayTeam",
    "gols_mandante": "FTHG",
    "gols_visitante": "FTAG",
    "resultado": "FTR",
    "odd_pre_H": "BbAvH",
    "odd_pre_D": "BbAvD",
    "odd_pre_A": "BbAvA",
    "odd_pre_over25": "BbAv>2.5",
    "odd_pre_under25": "BbAv<2.5",
    # ⚠️ Pinnacle, não média do mercado. Ver AVISO_CLV_FORMATO_B.
    "odd_fech_H": "PSCH",
    "odd_fech_D": "PSCD",
    "odd_fech_A": "PSCA",
    # odd_fech_over25 / odd_fech_under25 não existem no formato B.
}

#: Formato C — Grupo 2, arquivo único por país. Nomes de coluna diferentes
#: (``Home`` em vez de ``HomeTeam``, ``HG`` em vez de ``FTHG``) e **nenhuma**
#: odd pré-jogo: tudo termina em "C", de closing.
MAPA_C: dict[str, str] = {
    "data": "Date",
    "liga": "League",
    "temporada": "Season",
    "mandante": "Home",
    "visitante": "Away",
    "gols_mandante": "HG",
    "gols_visitante": "AG",
    "resultado": "Res",
    "odd_fech_H": "AvgCH",
    "odd_fech_D": "AvgCD",
    "odd_fech_A": "AvgCA",
    # Nenhuma odd pré-jogo e nenhum Over/Under: por isso o Grupo 2 não pode
    # entrar em backtest de apostas nem em CLV (regra 12).
}

MAPAS: dict[str, dict[str, str]] = {"A": MAPA_A, "B": MAPA_B, "C": MAPA_C}

#: Explicação do porquê o CLV do formato B não é comparável ao dos outros.
AVISO_CLV_FORMATO_B: str = (
    "No formato B (até 2018/19) a única odd de fechamento disponível é a da "
    "Pinnacle (PSC*), enquanto a odd pré-jogo é a média do mercado (BbAv*). "
    "A Pinnacle costuma pagar acima da média, então um CLV calculado assim "
    "mistura duas coisas: o ganho real de timing e a diferença entre casas. "
    "CLV do formato B não pode ser somado ao CLV do formato A sem ressalva."
)

# ----------------------------------------------------------------------------
# Colunas que precisam existir para o arquivo ser utilizável
# ----------------------------------------------------------------------------
# A diferença entre "essencial" e "opcional" é o que decide se o teste de
# inventário falha. Essencial = sem isso o projeto não funciona.

#: Colunas sem as quais o arquivo é inútil, por formato.
COLUNAS_ESSENCIAIS: dict[str, frozenset[str]] = {
    "A": frozenset(MAPA_A.values()),
    "B": frozenset(MAPA_B.values()),
    "C": frozenset(MAPA_C.values()),
}

#: Colunas que a seção 4.4 lista mas que nem todo arquivo traz.
#: RUS, por exemplo, não tem B365 nem Betfair — e ainda assim é utilizável,
#: porque as ``AvgC*`` (que é o que usamos) estão lá.
COLUNAS_OPCIONAIS: dict[str, frozenset[str]] = {
    "A": frozenset(),
    "B": frozenset(),
    "C": frozenset(
        {
            "Country",
            "Time",
            "B365CH",
            "B365CD",
            "B365CA",
            "BFECH",
            "BFECD",
            "BFECA",
            "MaxCH",
            "MaxCD",
            "MaxCA",
            "PSCH",
            "PSCD",
            "PSCA",
        }
    ),
}

#: Colunas que denunciam cada formato, usadas para detectá-lo.
_ASSINATURAS: dict[str, frozenset[str]] = {
    # "Home" (e não "HomeTeam") só existe no arquivo único do Grupo 2.
    "C": frozenset({"Home", "Away", "HG", "AG", "Res"}),
    # "AvgH" é a média moderna; só existe de 2019/20 em diante.
    "A": frozenset({"HomeTeam", "AvgH"}),
    # "BbAvH" é a média legada (Betbrain); some a partir de 2019/20.
    "B": frozenset({"HomeTeam", "BbAvH"}),
}


class ErroDeFormato(Exception):
    """O arquivo não corresponde a nenhum dos três formatos conhecidos."""


def ler_cabecalho(caminho: Path) -> list[str]:
    """Lê os nomes das colunas de um CSV da fonte.

    Trata duas chatices reais dos arquivos:

    - **BOM**: os arquivos do Grupo 2 começam com três bytes invisíveis.
      ``utf-8-sig`` os remove; sem isso a primeira coluna viria com lixo colado.
    - **Encoding**: alguns arquivos antigos não são UTF-8 válido (nomes de times
      com acento em codificação antiga). Caímos para ``latin-1``, que aceita
      qualquer byte, em vez de estourar.
    """
    bruto = caminho.read_bytes()
    primeira_linha = bruto.split(b"\n", 1)[0]
    try:
        texto = primeira_linha.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = primeira_linha.lstrip(b"\xef\xbb\xbf").decode("latin-1")
    return [coluna.strip() for coluna in texto.rstrip("\r").split(",")]


def detectar_formato(colunas: list[str] | set[str]) -> str:
    """Descobre se as colunas são do formato A, B ou C.

    A ordem do teste importa: C é checado primeiro porque é o mais distinto
    (usa ``Home``/``HG`` em vez de ``HomeTeam``/``FTHG``). Depois A, depois B —
    e a diferença entre eles é exatamente ``AvgH`` contra ``BbAvH``.

    Levanta:
        ErroDeFormato: se nenhuma assinatura bater, com a lista do que faltou.
    """
    presentes = set(colunas)
    for formato in ("C", "A", "B"):
        if _ASSINATURAS[formato] <= presentes:
            return formato

    detalhe = "; ".join(
        f"{f}: faltou {', '.join(sorted(_ASSINATURAS[f] - presentes))}"
        for f in ("A", "B", "C")
    )
    raise ErroDeFormato(
        f"Nenhum formato conhecido bate com as {len(presentes)} colunas do arquivo. "
        f"({detalhe})"
    )


@dataclass(frozen=True)
class Inventario:
    """O resultado de conferir um arquivo contra o inventário esperado.

    Atributos:
        caminho: arquivo inspecionado.
        formato: ``"A"``, ``"B"`` ou ``"C"``.
        colunas: todas as colunas encontradas, na ordem do arquivo.
        essenciais_faltando: colunas exigidas que **não** estão no arquivo.
            Lista vazia significa arquivo utilizável.
        opcionais_faltando: colunas previstas na seção 4.4 mas ausentes sem
            que isso impeça o uso (ex.: RUS sem B365).
    """

    caminho: Path
    formato: str
    colunas: tuple[str, ...]
    essenciais_faltando: tuple[str, ...]
    opcionais_faltando: tuple[str, ...]

    @property
    def utilizavel(self) -> bool:
        """``True`` se nenhuma coluna essencial está faltando."""
        return not self.essenciais_faltando


def inventariar(caminho: Path) -> Inventario:
    """Confere um arquivo contra o inventário de colunas esperado.

    É isto que transforma a seção 4.4 da especificação em verificação
    automática: se a fonte renomear ou remover uma coluna, o teste de
    inventário aponta exatamente qual.
    """
    colunas = ler_cabecalho(caminho)
    formato = detectar_formato(colunas)
    presentes = set(colunas)

    essenciais = COLUNAS_ESSENCIAIS[formato]
    opcionais = COLUNAS_OPCIONAIS[formato]

    return Inventario(
        caminho=caminho,
        formato=formato,
        colunas=tuple(colunas),
        essenciais_faltando=tuple(sorted(essenciais - presentes)),
        opcionais_faltando=tuple(sorted(opcionais - presentes)),
    )
