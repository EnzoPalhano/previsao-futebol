"""Os jogos dos próximos dias — o filtro que vem antes de qualquer busca.

⚠️ **A ordem do pipeline é "filtrar antes de buscar", e este módulo é o
filtro.** Nenhuma consulta à API, nenhuma busca de notícia e nenhuma chamada ao
LLM acontece fora da lista de times que sai daqui. Com 100 chamadas por dia de
cota e um LLM que cobra por chamada, buscar primeiro e filtrar depois seria
caro e lento — e o custo apareceria como uma conta no fim do mês, não como um
erro na tela.

**De onde vêm os jogos futuros.** O projeto **não tem**: a fonte dele
(football-data.co.uk) é um histórico de partidas já jogadas. O mesmo site
publica um arquivo separado de próximos jogos (``fixtures.csv``), e é ele que
:func:`baixar` lê. A API de futebol também serve, e a Fase 9 registrou isso
como item opcional que não foi feito.

⚠️ **Só entram as 18 ligas aprovadas.** Não é economia de chamada: é a regra 12.
Um desfalque do Brasileirão pode até ajustar a previsão, mas nada do Grupo 2
pode virar aposta nem CLV, e deixar esses jogos entrarem aqui faria a avaliação
da fase misturar o que pode e o que não pode ser medido.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from futebol.config import Config
from futebol.noticias.tipos import JogoAlvo

#: Onde o football-data publica os jogos das próximas semanas.
URL_FIXTURES = "https://www.football-data.co.uk/fixtures.csv"

#: As colunas que interessam. O arquivo segue o formato A das ligas do Grupo 1.
COLUNAS = ("Div", "Date", "HomeTeam", "AwayTeam")


def ligas_permitidas(cfg: Config) -> set[str]:
    """As 18 aprovadas pelo filtro da Fase 2 (regra 12)."""
    return set(cfg.bruto["ligas_aprovadas_backtest"])


def _data(texto: str) -> date | None:
    """O football-data escreve ``dd/mm/yyyy`` e às vezes ``dd/mm/yy``."""
    for formato in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            continue
    return None


def ler(
    texto_csv: str,
    cfg: Config,
    hoje: date | None = None,
    dias: int | None = None,
) -> list[JogoAlvo]:
    """Interpreta o CSV de próximos jogos.

    Função pura: recebe texto, devolve jogos. É ela que os testes exercitam —
    :func:`baixar` só acrescenta a rede.

    Args:
        texto_csv: o conteúdo do ``fixtures.csv``.
        cfg: de onde saem as ligas permitidas e ``dias_a_frente``.
        hoje: a data de referência. Explícita para o teste não depender do
            relógio — teste que depende de hoje quebra sozinho amanhã.
        dias: quantos dias à frente olhar. O padrão vem do ``config.yaml``.
    """
    hoje = hoje or date.today()
    dias = int(cfg.secao("noticias")["dias_a_frente"]) if dias is None else dias
    limite = hoje + timedelta(days=dias)
    permitidas = ligas_permitidas(cfg)
    pais = _mapa_de_pais(cfg)

    jogos: list[JogoAlvo] = []
    for linha in csv.DictReader(io.StringIO(texto_csv)):
        liga = (linha.get("Div") or "").strip()
        if liga not in permitidas:
            continue
        quando = _data(linha.get("Date") or "")
        if quando is None or not (hoje <= quando <= limite):
            continue
        mandante = (linha.get("HomeTeam") or "").strip()
        visitante = (linha.get("AwayTeam") or "").strip()
        if not mandante or not visitante:
            continue
        prefixo = pais.get(liga, liga)
        jogos.append(
            JogoAlvo(
                liga=liga,
                # Regra 14: a chave do time é sempre PAIS:nome. Guardar o nome
                # solto aqui faria o ajuste procurar um time que o modelo não
                # conhece, e não achar nada — em silêncio.
                mandante=f"{prefixo}:{mandante}",
                visitante=f"{prefixo}:{visitante}",
                data=quando,
            )
        )
    return sorted(jogos, key=lambda j: (j.data, j.liga, j.mandante))


def _mapa_de_pais(cfg: Config) -> dict[str, str]:
    """``{código da liga: prefixo do país}``, como a tabela de jogos usa.

    Lido da própria tabela quando ela existe, para não haver um segundo mapa
    que possa discordar do primeiro.
    """
    caminho = cfg.raiz / "data" / "processed" / "jogos.parquet"
    if not caminho.is_file():
        caminho = cfg.raiz / "data" / "app" / "jogos.parquet"
    if not caminho.is_file():
        return {}

    import pandas as pd

    tabela = pd.read_parquet(caminho, columns=["liga", "mandante"])
    mapa: dict[str, str] = {}
    for liga, grupo in tabela.groupby("liga", sort=False):
        primeiro = str(grupo["mandante"].iloc[0])
        prefixo, _, _ = primeiro.partition(":")
        if prefixo:
            mapa[str(liga)] = prefixo
    return mapa


def baixar(cfg: Config, hoje: date | None = None) -> list[JogoAlvo]:
    """Lê os próximos jogos do football-data.

    ⚠️ O site responde **HTTP 302** e exige ``User-Agent`` — é a mesma
    armadilha do download do histórico, registrada no CLAUDE.md desde a Fase 1.
    Sem seguir o redirecionamento, o arquivo volta vazio e o pipeline conclui
    que não há jogo nenhum nos próximos dias.
    """
    import requests

    fontes = cfg.secao("fontes")
    resposta = requests.get(
        URL_FIXTURES,
        headers={"User-Agent": fontes["user_agent"]},
        timeout=float(fontes["timeout_segundos"]),
        allow_redirects=True,
    )
    resposta.raise_for_status()
    return ler(resposta.text, cfg, hoje=hoje)


def times(jogos: Iterable[JogoAlvo]) -> set[str]:
    """Os times alvo. Nenhuma busca acontece fora desta lista."""
    return {time for jogo in jogos for time in jogo.times}
