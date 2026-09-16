"""Padronização dos nomes de times.

**Por que isto é o maior custo da Fase 1.** Com as 38 competições ligadas são
~1.500 clubes, em vários idiomas. Se dois nomes do mesmo time não forem unidos,
o histórico dele se parte em dois e o Elo e as médias móveis ficam errados —
sem erro nenhum aparecer. Se dois times diferentes forem unidos por engano, é
pior ainda.

**A chave é ``PAIS:nome_padrao``**, nunca o nome sozinho. Dois motivos:

1. Existem homônimos em países diferentes — "Nacional", "River Plate",
   "Racing", "Independiente", e há um "Everton" no Chile. Juntá-los corrompe
   tudo em silêncio.
2. O prefixo é o **país**, não o código da liga. Isso é exigência da própria
   especificação: *"times que mudam de divisão (subidas e descidas) devem
   apontar para a mesma chave"*. O Burnley cai da ``E0`` para a ``E1`` e volta;
   se a chave fosse ``E0:Burnley`` e ``E1:Burnley``, o histórico dele se
   quebraria em dois exatamente no ponto onde ele mais muda de nível. Como
   ``E0`` e ``E1`` são o mesmo país, a chave é ``ENG:Burnley`` nos dois casos.

**Nada entra no mapa automaticamente.** A normalização resolve o trivial
(acentos, maiúsculas, sufixos como ``FC``). O que sobrar ambíguo vai para
``data/nomes_pendentes.csv`` com uma sugestão, e o Enzo revisa. Um nome
desconhecido faz o teste **falhar** — falhar em silêncio aqui significa perder
jogos na junção sem ninguém perceber.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

# ----------------------------------------------------------------------------
# De qual país é cada competição
# ----------------------------------------------------------------------------
#: Código da liga (Grupo 1) -> código do país. É o que faz subida e descida
#: manterem a mesma chave de time.
PAIS_DA_LIGA: dict[str, str] = {
    # Inglaterra: Premier League, Championship, League One, League Two, National
    "E0": "ENG",
    "E1": "ENG",
    "E2": "ENG",
    "E3": "ENG",
    "EC": "ENG",
    # Escócia: Premiership, Championship, League One, League Two
    "SC0": "SCO",
    "SC1": "SCO",
    "SC2": "SCO",
    "SC3": "SCO",
    # Alemanha: Bundesliga, 2. Bundesliga
    "D1": "GER",
    "D2": "GER",
    # Itália: Serie A, Serie B
    "I1": "ITA",
    "I2": "ITA",
    # Espanha: La Liga, Segunda
    "SP1": "ESP",
    "SP2": "ESP",
    # França: Ligue 1, Ligue 2
    "F1": "FRA",
    "F2": "FRA",
    # Um nível só
    "N1": "NED",
    "B1": "BEL",
    "P1": "POR",
    "T1": "TUR",
    "G1": "GRE",
}

#: Códigos do Grupo 2. O arquivo já é por país, então o código é o próprio país.
PAISES_GRUPO2: frozenset[str] = frozenset(
    {
        "ARG",
        "AUT",
        "BRA",
        "CHN",
        "DNK",
        "FIN",
        "IRL",
        "JPN",
        "MEX",
        "NOR",
        "POL",
        "ROU",
        "RUS",
        "SWE",
        "SWZ",
        "USA",
    }
)


class ErroDeNomes(Exception):
    """Problema no mapeamento de nomes de times."""


class NomeDesconhecido(ErroDeNomes):
    """Um nome de time apareceu nos dados e não está no mapa.

    Atributos:
        pendentes: os nomes não reconhecidos, com sugestão de correspondência.
    """

    def __init__(self, pendentes: list[Pendencia]) -> None:
        self.pendentes = pendentes
        exemplos = ", ".join(
            f"{p.pais}:{p.nome_fonte!r}" + (f" (seria {p.sugestao!r}?)" if p.sugestao else "")
            for p in pendentes[:5]
        )
        resto = f" e mais {len(pendentes) - 5}" if len(pendentes) > 5 else ""
        super().__init__(
            f"{len(pendentes)} nome(s) de time fora do mapa: {exemplos}{resto}. "
            "Revise data/nomes_pendentes.csv e mova as linhas corretas para "
            "src/futebol/dados/mapa_times.csv."
        )


def pais_do_codigo(codigo: str) -> str:
    """Devolve o país de um código de liga (``E0`` -> ``ENG``) ou de país.

    Levanta:
        ErroDeNomes: se o código não for conhecido. Melhor estourar aqui do que
        gerar chaves com um prefixo inventado.
    """
    if codigo in PAIS_DA_LIGA:
        return PAIS_DA_LIGA[codigo]
    if codigo in PAISES_GRUPO2:
        return codigo
    conhecidos = ", ".join(sorted(set(PAIS_DA_LIGA) | PAISES_GRUPO2))
    raise ErroDeNomes(
        f"Código de competição desconhecido: {codigo!r}. Conhecidos: {conhecidos}."
    )


# ----------------------------------------------------------------------------
# Normalização automática
# ----------------------------------------------------------------------------
#: Sufixos e prefixos de clube que não distinguem um time de outro.
#: "Ajax" e "AFC Ajax" são o mesmo time; "Bayern Munich" e "FC Bayern" também.
_RUIDO = (
    "fc",
    "cf",
    "afc",
    "sc",
    "ac",
    "cd",
    "sv",
    "bk",
    "if",
    "ff",
    "ik",
    "as",
    "ss",
    "us",
    "rc",
    "sd",
    "ud",
    "ca",
    "club",
    "calcio",
)

# Apóstrofos somem sem deixar espaço: "Nott'm Forest" é "nottm forest", não
# "nott m forest". O resto da pontuação vira separador.
_APOSTROFOS = re.compile(r"['‘’ʼ`]")
_SO_LETRAS_E_ESPACO = re.compile(r"[^a-z0-9 ]+")
_ESPACOS = re.compile(r"\s+")


def normalizar(nome: str) -> str:
    """Reduz um nome à sua forma comparável.

    Faz só o que é seguro fazer automaticamente: tira acentos, baixa para
    minúsculas, remove pontuação e descarta as siglas de clube que não
    distinguem ninguém.

    Exemplos::

        normalizar("Nott'm Forest")   -> "nottm forest"
        normalizar("Atlético Madrid") -> "atletico madrid"
        normalizar("FC Bayern")       -> "bayern"

    Isto **não** decide que dois times são o mesmo. Só prepara a comparação.
    """
    sem_acento = "".join(
        c
        for c in unicodedata.normalize("NFKD", nome)
        if not unicodedata.combining(c)
    )
    sem_apostrofo = _APOSTROFOS.sub("", sem_acento.lower())
    limpo = _SO_LETRAS_E_ESPACO.sub(" ", sem_apostrofo)
    palavras = [p for p in _ESPACOS.split(limpo) if p]

    # Só remove o ruído se sobrar alguma coisa: "AC" sozinho continua "ac".
    sem_ruido = [p for p in palavras if p not in _RUIDO]
    return " ".join(sem_ruido or palavras)


def chave(pais: str, nome_padrao: str) -> str:
    """Monta a chave canônica de um time: ``ENG:Arsenal``."""
    return f"{pais}:{nome_padrao}"


# ----------------------------------------------------------------------------
# O mapa versionado
# ----------------------------------------------------------------------------
CAMINHO_MAPA_PADRAO = Path(__file__).with_name("mapa_times.csv")

#: Cabeçalho do mapa. ``pais`` e não ``liga``, pelo motivo explicado no topo.
COLUNAS_MAPA = ("pais", "nome_fonte", "nome_padrao")


@dataclass(frozen=True)
class Pendencia:
    """Um nome que apareceu nos dados e não está no mapa.

    Atributos:
        pais: país da competição onde apareceu.
        nome_fonte: o nome exatamente como veio do CSV.
        normalizado: a forma comparável.
        sugestao: nome padrão mais parecido já existente no mapa, ou ``None``.
    """

    pais: str
    nome_fonte: str
    normalizado: str
    sugestao: str | None


class MapaTimes:
    """O mapa nome-da-fonte → nome-padrão, carregado do CSV versionado."""

    def __init__(self, linhas: list[dict[str, str]]) -> None:
        # Busca exata pelo nome como veio da fonte.
        self._por_nome_fonte: dict[tuple[str, str], str] = {}
        # Busca tolerante, pela forma normalizada.
        self._por_normalizado: dict[tuple[str, str], str] = {}
        # Nomes padrão conhecidos por país, para sugerir correspondências.
        self._padroes_por_pais: dict[str, set[str]] = {}

        for linha in linhas:
            pais = linha["pais"].strip()
            fonte = linha["nome_fonte"].strip()
            padrao = linha["nome_padrao"].strip()
            if not (pais and fonte and padrao):
                continue
            self._por_nome_fonte[(pais, fonte)] = padrao
            self._por_normalizado[(pais, normalizar(fonte))] = padrao
            self._padroes_por_pais.setdefault(pais, set()).add(padrao)

    def __len__(self) -> int:
        return len(self._por_nome_fonte)

    @property
    def paises(self) -> set[str]:
        return set(self._padroes_por_pais)

    def resolver(self, pais: str, nome_fonte: str) -> str | None:
        """Devolve o nome padrão, ou ``None`` se o nome não estiver no mapa."""
        exato = self._por_nome_fonte.get((pais, nome_fonte.strip()))
        if exato is not None:
            return exato
        return self._por_normalizado.get((pais, normalizar(nome_fonte)))

    def sugerir(self, pais: str, nome_fonte: str) -> str | None:
        """Nome padrão mais parecido no mesmo país, para revisão humana.

        A sugestão **nunca** é aplicada sozinha: ela vai para o arquivo de
        pendências para o Enzo confirmar.
        """
        candidatos = self._padroes_por_pais.get(pais)
        if not candidatos:
            return None
        alvo = normalizar(nome_fonte)
        pares = {normalizar(c): c for c in candidatos}
        proximos = get_close_matches(alvo, list(pares), n=1, cutoff=0.82)
        return pares[proximos[0]] if proximos else None


def carregar_mapa(caminho: Path | None = None) -> MapaTimes:
    """Lê o ``mapa_times.csv``. Devolve um mapa vazio se ele ainda não existe."""
    caminho = caminho or CAMINHO_MAPA_PADRAO
    if not caminho.is_file():
        return MapaTimes([])

    with caminho.open(encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        faltando = set(COLUNAS_MAPA) - set(leitor.fieldnames or ())
        if faltando:
            raise ErroDeNomes(
                f"{caminho} precisa ter as colunas {', '.join(COLUNAS_MAPA)}. "
                f"Faltando: {', '.join(sorted(faltando))}."
            )
        return MapaTimes(list(leitor))


def salvar_mapa(linhas: list[dict[str, str]], caminho: Path | None = None) -> Path:
    """Grava o mapa ordenado por país e nome, para o diff no Git ficar legível."""
    caminho = caminho or CAMINHO_MAPA_PADRAO
    caminho.parent.mkdir(parents=True, exist_ok=True)
    ordenadas = sorted(linhas, key=lambda x: (x["pais"], x["nome_padrao"], x["nome_fonte"]))

    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(COLUNAS_MAPA), lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(ordenadas)
    return caminho


def salvar_pendencias(pendentes: list[Pendencia], caminho: Path) -> Path:
    """Grava ``data/nomes_pendentes.csv`` para revisão do Enzo.

    O arquivo tem as mesmas colunas do mapa, mais a forma normalizada e a
    sugestão. Revisar é conferir a sugestão, corrigir o ``nome_padrao`` e mover
    a linha para o ``mapa_times.csv``.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    colunas = ("pais", "nome_fonte", "nome_padrao", "normalizado", "sugestao")

    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(colunas), lineterminator="\n")
        escritor.writeheader()
        for p in sorted(pendentes, key=lambda x: (x.pais, x.normalizado)):
            escritor.writerow(
                {
                    "pais": p.pais,
                    "nome_fonte": p.nome_fonte,
                    # Preenchido com a sugestão para facilitar; o Enzo confirma.
                    "nome_padrao": p.sugestao or p.nome_fonte,
                    "normalizado": p.normalizado,
                    "sugestao": p.sugestao or "",
                }
            )
    return caminho


def padronizar(
    pares: list[tuple[str, str]],
    mapa: MapaTimes,
    *,
    caminho_pendencias: Path | None = None,
) -> dict[tuple[str, str], str]:
    """Traduz ``(codigo_competicao, nome_fonte)`` em chaves ``PAIS:nome``.

    Args:
        pares: os pares encontrados nos dados.
        mapa: o mapa carregado do CSV versionado.
        caminho_pendencias: se informado e houver nomes desconhecidos, grava o
            arquivo de pendências antes de levantar o erro.

    Retorna:
        Dicionário ``(codigo, nome_fonte) -> "PAIS:nome_padrao"``.

    Levanta:
        NomeDesconhecido: se **qualquer** nome não estiver no mapa. É proposital
        que isso interrompa o pipeline: seguir em frente com um time não
        reconhecido significa perder jogos na junção sem aviso.
    """
    resolvidos: dict[tuple[str, str], str] = {}
    pendentes: list[Pendencia] = []
    vistos: set[tuple[str, str]] = set()

    for codigo, nome_fonte in pares:
        pais = pais_do_codigo(codigo)
        padrao = mapa.resolver(pais, nome_fonte)
        if padrao is not None:
            resolvidos[(codigo, nome_fonte)] = chave(pais, padrao)
            continue

        if (pais, nome_fonte) not in vistos:
            vistos.add((pais, nome_fonte))
            pendentes.append(
                Pendencia(
                    pais=pais,
                    nome_fonte=nome_fonte,
                    normalizado=normalizar(nome_fonte),
                    sugestao=mapa.sugerir(pais, nome_fonte),
                )
            )

    if pendentes:
        if caminho_pendencias is not None:
            salvar_pendencias(pendentes, caminho_pendencias)
        raise NomeDesconhecido(pendentes)

    return resolvidos
