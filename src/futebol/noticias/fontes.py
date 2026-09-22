"""De onde vêm os desfalques, e o que impede a conta de estourar.

**Duas implementações, uma interface.** :class:`ApiFutebol` fala com a
API-Football de verdade; :class:`FonteFalsa` devolve o que você mandar ela
devolver. Os testes usam a segunda — a especificação exige testes com respostas
**falsas**, e o motivo é duplo: teste que depende de rede falha por motivo
errado, e teste que gasta chamada de API custa dinheiro a cada execução.

⚠️ **O plano gratuito dá 100 chamadas por dia**, e a cota zera às 00:00 UTC sem
acumular o que sobrou. Isso não é um detalhe de configuração: é o que decide o
desenho do pipeline. Buscar a escalação de cada time de cada jogo dos próximos 7
dias, em 18 ligas, passa de 100 fácil. Por isso:

1. **a busca é por liga, não por jogo.** ``/injuries?league=X&season=Y&date=Z``
   devolve a liga inteira num pedido. Dezoito ligas = dezoito chamadas;
2. **tudo passa pelo cache**, e o cache é em disco, com validade. Rodar o script
   duas vezes no mesmo dia não gasta duas cotas;
3. **o orçamento é contado e trava**. Quando acaba, :class:`SemCota` é levantada
   em vez de a chamada ser feita — estourar a cota de graça derruba a conta do
   Enzo pelo resto do dia.

**Sobre o que foi confirmado e o que não foi.** A especificação manda conferir
endpoints e limites antes de implementar. Confirmado na documentação pública:
a base ``https://v3.football.api-sports.io``, o header ``x-apisports-key``, o
limite de 100/dia do plano gratuito, e que ``/injuries`` aceita
``league``+``season``, ``fixture``, ``team`` e ``date``, devolvendo ``type``
(Injury/Suspension) e ``reason``.

**Confirmado contra a API rodando em 21/09/2026**, com a chave do Enzo: os 18
ids de liga (lidos de ``/leagues``, não deduzidos), o formato do registro de
``/injuries`` e as duas restrições do plano gratuito.

⚠️ **E as duas restrições do plano gratuito se contradizem**, o que decide o
desenho da busca: ``season`` tem de estar em 2022–2024, e ``date`` tem de estar
em hoje ±1 dia. Pedir ``season=2023&date=2024-06-02`` é recusado pela regra da
data; pedir a temporada corrente é recusado pela regra da temporada. Só
``league``+``season`` **sem** ``date`` passa — e é assim que
:meth:`ApiFutebol.desfalques` pergunta, filtrando as datas localmente.

**Consequência prática, e ela é grande:** no plano gratuito **não há como
operar a fase na temporada corrente.** Dá para demonstrá-la com dados reais de
2022 a 2024 (``--historico``), o que é bem melhor que dados inventados, mas não
é medição — ver a nota sobre backtest em :mod:`futebol.noticias.registro`.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from futebol.config import Config
from futebol.noticias import importancia
from futebol.noticias.tipos import Desfalque, JogoAlvo

#: A base da API, confirmada na documentação pública.
BASE = "https://v3.football.api-sports.io"

#: O header de autenticação. A chave **nunca** vai na URL: URL entra em log de
#: servidor, em histórico de shell e em mensagem de erro.
HEADER_CHAVE = "x-apisports-key"

#: Como o ``type`` da API vira o vocabulário do projeto.
TIPOS: dict[str, str] = {
    "injury": "fora",
    "suspended": "fora",
    "missing fixture": "fora",
    "questionable": "duvida",
    "doubtful": "duvida",
}

#: Confiança de um desfalque vindo da API oficial. Não é 1,0 porque a API
#: também erra e porque "questionable" é, por definição, incerto — mas é alta,
#: e bem acima do que uma notícia de jornal merece.
CONFIANCA_DA_API = 0.95

#: O código da liga no projeto → o ``id`` dela na API-Football.
#:
#: ⚠️ **Estes números foram LIDOS da API, não deduzidos.** Uma chamada a
#: ``/leagues`` em 21/09/2026 devolveu 1.246 competições; estes 18 são os que
#: correspondem às ligas aprovadas do projeto, casados por país e nome. Chutar
#: ID de liga seria buscar os jogos de uma competição errada e não perceber —
#: o erro voltaria como "nenhum desfalque", não como erro.
LIGAS_NA_API: dict[str, int] = {
    "E0": 39,    # England / Premier League
    "E1": 40,    # England / Championship
    "E2": 41,    # England / League One
    "E3": 42,    # England / League Two
    "SC0": 179,  # Scotland / Premiership
    "D1": 78,    # Germany / Bundesliga
    "D2": 79,    # Germany / 2. Bundesliga
    "I1": 135,   # Italy / Serie A
    "I2": 136,   # Italy / Serie B
    "SP1": 140,  # Spain / La Liga
    "SP2": 141,  # Spain / Segunda División
    "F1": 61,    # France / Ligue 1
    "F2": 62,    # France / Ligue 2
    "N1": 88,    # Netherlands / Eredivisie
    "P1": 94,    # Portugal / Primeira Liga
    "B1": 144,   # Belgium / Jupiler Pro League
    "T1": 203,   # Turkey / Süper Lig
    "G1": 197,   # Greece / Super League 1
}

#: As temporadas que o **plano gratuito** libera. Medido, não suposto: pedir
#: 2026 devolve ``{'plan': 'Free plans do not have access to this season, try
#: from 2022 to 2024.'}`` com zero resultados.
#:
#: ⚠️ **É a limitação que decide o que esta fase consegue fazer de verdade.** A
#: temporada atual é paga, então no plano gratuito não há como buscar as lesões
#: de hoje — só as de 2022 a 2024. Ver :class:`TemporadaPaga`.
TEMPORADAS_GRATUITAS = (2022, 2023, 2024)


class TemporadaPaga(Exception):
    """A temporada pedida exige plano pago.

    Levantada com a explicação inteira porque a mensagem crua da API ("Free
    plans do not have access to this season") não diz o que fazer, e o que
    fazer aqui tem três opções legítimas.
    """


class SemCota(Exception):
    """O orçamento diário de chamadas acabou.

    Levantada **antes** da chamada, nunca depois: estourar a cota de graça
    derruba a conta pelo resto do dia, e a cota só volta às 00:00 UTC.
    """


class SemChave(Exception):
    """Falta ``API_FUTEBOL_CHAVE`` no ``.env``.

    Não é um erro de programação: é a configuração que o Enzo ainda não fez, e
    a mensagem diz como fazer.
    """


class FonteDeDesfalques(Protocol):
    """O que qualquer fonte precisa saber responder."""

    def desfalques(self, jogos: Iterable[JogoAlvo]) -> list[Desfalque]:
        """Os desfalques dos times desses jogos, e de mais ninguém."""
        ...


# ----------------------------------------------------------------------------
# O orçamento
# ----------------------------------------------------------------------------
@dataclass
class Orcamento:
    """Conta as chamadas do dia e trava quando acabam.

    ⚠️ O contador é **persistido em disco** e chaveado pela data UTC. Guardá-lo
    só em memória faria cada execução do script começar do zero, e três
    execuções de 40 chamadas passariam de 100 sem ninguém perceber — que é
    exatamente o acidente que o limite existe para evitar.
    """

    limite: int
    caminho: Path
    usadas: int = field(init=False, default=0)
    dia: str = field(init=False, default="")

    def __post_init__(self) -> None:
        self.dia = datetime.now(UTC).strftime("%Y-%m-%d")
        self.usadas = self._ler()

    def _ler(self) -> int:
        if not self.caminho.is_file():
            return 0
        try:
            dados = json.loads(self.caminho.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0
        # Contador de outro dia é contador zerado: a cota reseta às 00:00 UTC.
        return int(dados.get("usadas", 0)) if dados.get("dia") == self.dia else 0

    def _gravar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(
            json.dumps({"dia": self.dia, "usadas": self.usadas}), encoding="utf-8"
        )

    @property
    def restam(self) -> int:
        return max(0, self.limite - self.usadas)

    def gastar(self, quantas: int = 1) -> None:
        """Registra o gasto, ou recusa se não couber."""
        if self.usadas + quantas > self.limite:
            raise SemCota(
                f"O orçamento de {self.limite} chamadas/dia acabou "
                f"({self.usadas} usadas hoje). A cota da API-Football zera às "
                "00:00 UTC e o que sobra não acumula. Rode de novo amanhã, ou "
                "reduza `noticias.dias_a_frente` no config.yaml."
            )
        self.usadas += quantas
        self._gravar()


# ----------------------------------------------------------------------------
# O cache
# ----------------------------------------------------------------------------
@dataclass
class Cache:
    """Respostas guardadas em disco, com validade.

    ⚠️ Exigido pela especificação ("cache local das respostas, não repetir
    requisições"), e é o que torna o limite de 100/dia viável: rodar o script
    duas vezes no mesmo dia custa uma cota, não duas.
    """

    pasta: Path
    validade_horas: float = 4.0

    def _caminho(self, chave: str) -> Path:
        seguro = "".join(c if c.isalnum() or c in "-_" else "_" for c in chave)
        return self.pasta / f"{seguro}.json"

    def ler(self, chave: str):
        caminho = self._caminho(chave)
        if not caminho.is_file():
            return None
        idade = (time.time() - caminho.stat().st_mtime) / 3600
        if idade > self.validade_horas:
            return None
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def gravar(self, chave: str, dados) -> None:
        caminho = self._caminho(chave)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(dados), encoding="utf-8")


# ----------------------------------------------------------------------------
# A fonte falsa
# ----------------------------------------------------------------------------
@dataclass
class FonteFalsa:
    """Devolve o que você mandar. É com ela que os testes rodam.

    Também é o que faz a fase inteira ser demonstrável **sem conta em lugar
    nenhum**: o script aceita ``--falso`` e o app mostra o pipeline funcionando
    com desfalques de mentira, claramente rotulados como tal.
    """

    respostas: list[Desfalque] = field(default_factory=list)
    chamadas: int = field(init=False, default=0)

    def desfalques(self, jogos: Iterable[JogoAlvo]) -> list[Desfalque]:
        self.chamadas += 1
        times = {time for jogo in jogos for time in jogo.times}
        # Filtra igual à fonte de verdade: nada fora dos times alvo.
        return [d for d in self.respostas if d.jogador.time in times]


# ----------------------------------------------------------------------------
# A API de verdade
# ----------------------------------------------------------------------------
@dataclass
class ApiFutebol:
    """A API-Football. Precisa de ``API_FUTEBOL_CHAVE`` no ``.env``.

    ⚠️ **Nunca executou contra o serviço real** — não há chave neste ambiente.
    O código segue o formato documentado e tolera campo faltando, mas a primeira
    execução de verdade é a primeira prova de que funciona.
    """

    chave: str
    orcamento: Orcamento
    cache: Cache
    timeout: float = 20.0

    @classmethod
    def do_ambiente(cls, cfg: Config) -> ApiFutebol:
        """Monta a partir do ``.env`` e do ``config.yaml``.

        Levanta:
            SemChave: com a instrução de como resolver.
        """
        chave = os.environ.get("API_FUTEBOL_CHAVE", "").strip()
        if not chave:
            raise SemChave(
                "Falta API_FUTEBOL_CHAVE. Crie uma conta gratuita em "
                "dashboard.api-football.com, copie a chave e:\n\n"
                "    Copy-Item .env.exemplo .env\n"
                "    # abra o .env e preencha API_FUTEBOL_CHAVE=...\n\n"
                "Enquanto isso, `python scripts/desfalques.py --falso` mostra o "
                "pipeline rodando com dados de mentira."
            )
        secao = cfg.secao("noticias")
        pasta = cfg.raiz / "data" / "noticias"
        return cls(
            chave=chave,
            orcamento=Orcamento(
                limite=int(secao["limite_chamadas_dia"]),
                caminho=pasta / "orcamento.json",
            ),
            cache=Cache(
                pasta=pasta / "cache",
                validade_horas=float(secao.get("cache_horas", 4.0)),
            ),
        )

    def _pedir(self, caminho: str, parametros: dict) -> dict:
        """Uma chamada, com cache e orçamento pela frente."""
        chave_cache = caminho + "_" + "_".join(
            f"{k}-{v}" for k, v in sorted(parametros.items())
        )
        guardado = self.cache.ler(chave_cache)
        if guardado is not None:
            return guardado

        self.orcamento.gastar(1)

        import requests

        resposta = requests.get(
            f"{BASE}/{caminho}",
            params=parametros,
            headers={HEADER_CHAVE: self.chave},
            timeout=self.timeout,
        )
        resposta.raise_for_status()
        dados = resposta.json()

        # A API devolve 200 com a lista de erros dentro do corpo. Tratar isso
        # como sucesso faria o pipeline seguir com zero desfalques e parecer
        # que simplesmente não há lesão nenhuma.
        erros = dados.get("errors") or {}
        if erros:
            # A recusa por plano é a mais comum e a menos óbvia: ela volta com
            # HTTP 200 e zero resultados, então sem este ramo o pipeline
            # concluiria "não há lesão nenhuma" e seguiria em frente.
            if "plan" in erros:
                raise TemporadaPaga(
                    f"A API-Football recusou por limite de plano: {erros['plan']}\n\n"
                    "O plano gratuito cobre as temporadas "
                    f"{', '.join(str(t) for t in TEMPORADAS_GRATUITAS)} — a "
                    "temporada atual é paga. Três saídas legítimas:\n\n"
                    "  1. `--historico 2023`: roda o pipeline com lesões REAIS "
                    "de uma temporada liberada. Serve de demonstração, nunca de "
                    "medição (ver a nota sobre backtest no guia da Fase 10);\n"
                    "  2. assinar um plano pago, se você quiser operar a fase de "
                    "verdade na temporada corrente;\n"
                    "  3. `--falso`, que não chama a API nenhuma."
                )
            raise RuntimeError(f"A API-Football recusou o pedido: {erros}")

        self.cache.gravar(chave_cache, dados)
        return dados

    def desfalques(self, jogos: Iterable[JogoAlvo]) -> list[Desfalque]:
        """Os desfalques das ligas desses jogos, filtrados pelos times deles.

        ⚠️ A busca é **por liga**, não por jogo: ``/injuries`` devolve a
        competição inteira num pedido, e com 100 chamadas por dia essa
        diferença é a viabilidade do pipeline.
        """
        jogos = list(jogos)
        times_alvo = {time for jogo in jogos for time in jogo.times}
        por_liga: dict[tuple[str, int], set[date]] = {}
        for jogo in jogos:
            chave = (jogo.liga, jogo.temporada_da_api)
            por_liga.setdefault(chave, set()).add(jogo.data)

        achados: list[Desfalque] = []
        for (liga, temporada), datas in sorted(por_liga.items()):
            # ⚠️ `league` é o **id da API**, não o código do projeto. Mandar
            # "E0" onde a API espera 39 não dá erro: devolve zero resultados, e
            # o pipeline conclui que não há lesão nenhuma. Liga que o projeto
            # conhece e a API não é pulada, não chutada.
            id_da_liga = LIGAS_NA_API.get(liga)
            if id_da_liga is None:
                continue

            # ⚠️ **Sem o parâmetro `date`, e o filtro por data é feito aqui.**
            # O plano gratuito tem DUAS restrições, e elas se contradizem:
            # `season` precisa estar em 2022–2024, e `date` precisa estar em
            # hoje ±1 dia. Pedir season=2023 com date=2024-06-02 é recusado
            # pela regra da data; pedir a temporada corrente é recusado pela
            # regra da temporada. Já `league`+`season` sem `date` passa.
            #
            # Ganho colateral que valeria a escolha de qualquer forma: uma
            # chamada por (liga, temporada) em vez de uma por (liga, dia). Para
            # 7 dias em 18 ligas, 18 chamadas em vez de 126 — dentro da cota de
            # 100/dia em vez de muito acima dela.
            dados = self._pedir(
                "injuries", {"league": id_da_liga, "season": temporada}
            )
            achados.extend(
                self._converter_da_temporada(
                    dados.get("response") or [], times_alvo, datas, liga
                )
            )
        return achados

    def pesar(
        self,
        desfalques: list[Desfalque],
        contexto: dict[str, tuple[int, int]],
        teto_de_chamadas: int = 30,
    ) -> list[Desfalque]:
        """Busca as estatísticas de cada jogador e devolve os desfalques pesados.

        ⚠️ **Sem isto, todo desfalque tem peso zero e nada move a previsão.** O
        projeto não tem dado de jogador — a fonte dele traz placar e odds e nada
        mais —, então minutos, gols e titularidade só podem vir da API. É a
        peça que separa "o artilheiro está fora" de "o terceiro goleiro está
        fora".

        Args:
            desfalques: os encontrados, com peso zero.
            teto_de_chamadas: quantas chamadas esta etapa pode gastar. Uma
                rodada cheia tem dezenas de lesionados, e uma chamada por
                jogador estouraria a cota de 100/dia sozinha. Passado o teto, o
                resto fica com peso zero — que já significa "não sei" e é a
                resposta certa quando não se sabe.

        Retorna:
            Novos desfalques, com o peso calculado. Quem não pôde ser pesado sai
            **inalterado**, e não descartado: a pessoa precisa ver a notícia
            mesmo que o modelo a ignore.
        """
        from dataclasses import replace

        gastas = 0
        pesados: list[Desfalque] = []
        for desfalque in desfalques:
            id_jogador = desfalque.jogador.identificador
            temporada = desfalque.temporada_api
            if not id_jogador or temporada is None or gastas >= teto_de_chamadas:
                pesados.append(desfalque)
                continue

            try:
                dados = self._pedir(
                    "players", {"id": id_jogador, "season": temporada}
                )
            except (TemporadaPaga, SemCota):
                # Sem estatística, peso zero — que é "não sei", não "não
                # importa". Derrubar o pipeline aqui perderia os desfalques já
                # encontrados, que valem ser mostrados de todo jeito.
                pesados.append(desfalque)
                continue
            gastas += 1

            partidas, gols_do_time = contexto.get(desfalque.jogador.time, (0, 0))
            stats = self._estatisticas(
                dados.get("response") or [],
                partidas,
                gols_do_time,
                LIGAS_NA_API.get(desfalque.liga),
            )
            if stats is None:
                pesados.append(desfalque)
                continue
            pesados.append(
                replace(
                    desfalque,
                    jogador=importancia.montar_jogador(
                        desfalque.jogador.nome,
                        desfalque.jogador.time,
                        stats,
                        identificador=id_jogador,
                    ),
                )
            )
        return pesados

    @staticmethod
    def _estatisticas(
        resposta: list,
        jogos_do_time: int,
        gols_do_time: int,
        id_da_liga: int | None = None,
    ) -> importancia.Estatisticas | None:
        """Do JSON de ``/players`` para :class:`~.importancia.Estatisticas`.

        A API devolve uma entrada por competição que o jogador disputou na
        temporada. Os minutos e gols de todas são somados; a posição vem da
        primeira — jogador não muda de posição entre a liga e a copa.

        ⚠️ ``jogos_do_time`` e ``gols_do_time`` vêm **de fora**, da tabela do
        projeto (:func:`~.importancia.contexto_dos_times`). A API não os
        fornece, e a aproximação óbvia — usar as aparições do próprio jogador —
        daria peso 1,0 a um reserva com uma aparição de 90 minutos.
        """
        if not resposta:
            return None
        linhas = resposta[0].get("statistics") or []
        if not linhas:
            return None

        # ⚠️ **Só os blocos da liga que interessa.** A API devolve um bloco por
        # competição disputada -- liga, copa nacional, europa. Somar os minutos
        # de todas e dividir pelos 38 jogos da LIGA faz quem joga copa estourar
        # o teto: Kolasinac saiu com peso 1,000 exatamente assim, e 1,000
        # significa "este jogador e o time inteiro". O erro nao aparece como
        # erro -- aparece como um ajuste grande demais.
        if id_da_liga is not None:
            da_liga = [
                linha
                for linha in linhas
                if (linha.get("league") or {}).get("id") == id_da_liga
            ]
            if da_liga:
                linhas = da_liga

        def soma(grupo: str, campo: str) -> int:
            total = 0
            for linha in linhas:
                valor = (linha.get(grupo) or {}).get(campo)
                if isinstance(valor, (int, float)):
                    total += int(valor)
            return total

        return importancia.Estatisticas(
            minutos=soma("games", "minutes"),
            gols=soma("goals", "total"),
            assistencias=soma("goals", "assists"),
            titular=soma("games", "lineups"),
            jogos_do_time=jogos_do_time,
            gols_do_time=gols_do_time,
            posicao=str((linhas[0].get("games") or {}).get("position") or ""),
        )

    def _converter_da_temporada(
        self, itens: list, times_alvo: set[str], datas: set[date], liga: str = ""
    ) -> list[Desfalque]:
        """Fica só com os desfalques das datas pedidas.

        A API devolve a temporada inteira; quem recorta é isto. O recorte é por
        **data do jogo** (``fixture.date``), que é o que interessa: um jogador
        fora do jogo de agosto não está fora do jogo de maio.
        """
        saida: list[Desfalque] = []
        for item in itens:
            bruto = ((item.get("fixture") or {}).get("date") or "")[:10]
            try:
                dia = date.fromisoformat(bruto)
            except ValueError:
                continue
            if dia not in datas:
                continue
            saida.extend(self._converter([item], times_alvo, dia, liga))
        return saida

    def _converter(
        self, itens: list, times_alvo: set[str], dia: date, liga: str = ""
    ) -> list[Desfalque]:
        """Do JSON da API para :class:`Desfalque`.

        Tolerante a campo faltando de propósito: a alternativa seria o pipeline
        inteiro morrer porque um jogador veio sem posição.
        """
        saida = []
        for item in itens:
            jogador = item.get("player") or {}
            time_api = (item.get("team") or {}).get("name", "")
            nome = jogador.get("name") or ""
            if not nome:
                continue

            time = self._casar_time(time_api, times_alvo)
            if time is None:
                continue

            tipo = str(jogador.get("type") or "").strip().lower()
            status = TIPOS.get(tipo, "duvida")
            saida.append(
                Desfalque(
                    # Peso zero: quem dá peso é `importancia`, com as
                    # estatísticas do jogador. Chutar aqui seria inventar.
                    jogador=replace(
                        importancia.sem_estatisticas(
                            nome, time, jogador.get("position") or ""
                        ),
                        # O id e nao o nome: nome de jogador e ambiguo entre
                        # fontes, e buscar estatistica por nome traria a de
                        # outra pessoa sem avisar.
                        identificador=jogador.get("id"),
                    ),
                    status=status,
                    motivo=str(jogador.get("reason") or tipo or "").strip(),
                    confianca=CONFIANCA_DA_API,
                    fonte=f"{BASE}/injuries (API-Football)",
                    data=dia,
                    liga=liga,
                    temporada_api=(item.get("league") or {}).get("season"),
                )
            )
        return saida

    @staticmethod
    def _casar_time(nome_da_api: str, times_alvo: set[str]) -> str | None:
        """Casa o nome da API com a chave ``PAIS:nome`` do projeto.

        ⚠️ **Casamento frouxo, e o motivo é honesto: os dois vocabulários são
        diferentes e ninguém mapeou um no outro.** O projeto levou a Fase 1
        inteira para mapear ~1.500 nomes de times de UMA fonte; a API é uma
        segunda fonte, com as suas próprias grafias. Aqui a comparação é pelo
        nome sem o prefixo, ignorando caixa e pontuação.

        Quem não casa é **descartado**, não chutado — associar o desfalque ao
        time errado é o pior erro possível aqui (é a regra 14 outra vez). O
        script conta quantos caíram, para o número aparecer em vez de sumir.
        """
        def limpar(texto: str) -> str:
            return "".join(c for c in texto.lower() if c.isalnum())

        alvo = limpar(nome_da_api)
        if not alvo:
            return None
        # `chave_do_time` e nao `time`: o modulo `time` esta importado aqui em
        # cima, e a variavel o sombrearia. Nao quebra nada hoje porque este
        # metodo nao usa o modulo — quebraria no dia em que alguem usasse.
        for chave_do_time in times_alvo:
            _, _, nome = chave_do_time.partition(":")
            if limpar(nome) == alvo:
                return chave_do_time
        return None
