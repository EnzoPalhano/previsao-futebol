"""As peças de informação que esta fase manipula, e o vocabulário delas.

Um módulo de tipos existe aqui por um motivo específico: a informação desta fase
vem de **três fontes que não se parecem** — uma API de futebol, notícias em
texto corrido e um LLM que lê as notícias. Sem um formato comum, cada uma
entregaria um dicionário com chaves diferentes, e o ajuste do modelo teria de
conhecer as três.

⚠️ **O campo ``confianca`` não é enfeite.** Um desfalque confirmado pela API vale
1,0; um extraído de uma notícia vale o que o LLM disse que vale. Tratar os dois
igual seria deixar um boato mexer na previsão com a mesma força de uma
escalação oficial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

#: Os estados possíveis de um jogador, na ordem em que pesam.
#:
#: ``fora`` é lesão, suspensão ou corte confirmado; ``duvida`` é o que a
#: imprensa chama de "questionável"; ``volta`` é quem estava fora e voltou — e
#: ele existe porque uma notícia de volta **cancela** um desfalque anterior, que
#: é informação tão útil quanto a de saída.
STATUS = ("fora", "duvida", "volta")

#: Em que parte do jogo o jogador pesa. Vem da posição.
#:
#: A divisão é grosseira de propósito: o modelo tem **dois** parâmetros por time
#: (ataque e defesa), então dividir o elenco em mais que isso produziria um peso
#: que não teria onde ser aplicado.
SETORES = ("ataque", "defesa", "ambos")


@dataclass(frozen=True)
class Jogador:
    """Um jogador e o quanto ele significa para o time dele.

    Atributos:
        nome: como a fonte o chama.
        time: a chave do projeto, ``PAIS:nome`` (regra 14).
        setor: ``"ataque"``, ``"defesa"`` ou ``"ambos"``.
        peso: quanto do time ele é, em [0, 1]. Sai de
            :func:`futebol.noticias.importancia.peso`, nunca à mão.
    """

    nome: str
    time: str
    setor: str = "ambos"
    peso: float = 0.0
    #: O ``id`` do jogador na API, quando ele veio de lá. É por ele que as
    #: estatísticas são buscadas — nome de jogador é ambíguo entre fontes, e
    #: buscar por nome traria as estatísticas de outra pessoa sem avisar.
    identificador: int | None = None

    def __post_init__(self) -> None:
        if self.setor not in SETORES:
            raise ValueError(f"setor {self.setor!r} não é um de {SETORES}")
        if not 0.0 <= self.peso <= 1.0:
            raise ValueError(f"peso {self.peso} fora de [0, 1]")


@dataclass(frozen=True)
class Desfalque:
    """Um jogador fora (ou em dúvida), e de onde essa informação veio.

    Atributos:
        jogador: quem.
        status: ``"fora"``, ``"duvida"`` ou ``"volta"``.
        motivo: lesão, suspensão, convocação… texto livre, para a tela.
        confianca: quanto acreditar, em [0, 1]. A API oficial entrega 1,0;
            uma notícia entrega o que o LLM estimou.
        fonte: URL ou nome da fonte. **Obrigatório** — desfalque sem fonte é
            indistinguível de desfalque inventado, e a tela mostra o link.
        data: quando a informação foi publicada.
    """

    jogador: Jogador
    status: str
    motivo: str = ""
    confianca: float = 1.0
    fonte: str = ""
    data: date | None = None
    #: A competição em que o desfalque foi encontrado, no código do projeto.
    #: Serve para filtrar as estatísticas do jogador: somar os minutos de todas
    #: as competições e dividir pelos jogos de uma faria quem joga copa saturar
    #: no teto.
    liga: str = ""
    #: A temporada no vocabulário da API (o ano em que ela começou), quando
    #: conhecida. Guardada aqui porque é ela que a busca de estatísticas do
    #: jogador precisa, e deduzi-la da data levaria ao erro que
    #: :attr:`JogoAlvo.temporada_da_api` documenta.
    temporada_api: int | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUS:
            raise ValueError(f"status {self.status!r} não é um de {STATUS}")
        if not 0.0 <= self.confianca <= 1.0:
            raise ValueError(f"confianca {self.confianca} fora de [0, 1]")
        if not self.fonte:
            raise ValueError(
                "desfalque sem fonte. Um desfalque sem origem é indistinguível "
                "de um desfalque inventado, e a tela precisa mostrar o link."
            )


@dataclass(frozen=True)
class JogoAlvo:
    """Um jogo dos próximos dias, que é o único motivo para buscar qualquer coisa.

    ⚠️ **O pipeline inteiro filtra antes de buscar**, e esta classe é o filtro.
    Nenhuma consulta à API, nenhuma busca de notícia e nenhuma chamada ao LLM
    acontece fora da lista de times que sai daqui — é o que segura o custo e o
    limite diário de chamadas.
    """

    liga: str
    mandante: str
    visitante: str
    data: date
    #: A temporada como a tabela do projeto a escreve (``2023/24`` ou ``2023``).
    #: Opcional: os próximos jogos vêm de um arquivo que não diz a temporada.
    temporada: str = ""

    @property
    def times(self) -> tuple[str, str]:
        return (self.mandante, self.visitante)

    @property
    def temporada_da_api(self) -> int:
        """O ano que a API-Football usa para identificar a temporada.

        ⚠️ **Não é ``self.data.year``, e essa confusão já custou uma execução.**
        A API identifica a temporada pelo ano em que ela **começou**: a
        Premier League 2023/24 é ``season=2023``, inclusive para um jogo de
        **junho de 2024**. Mandando 2024, a API responde com sucesso e zero
        resultados — e o pipeline conclui "nenhum desfalque" em vez de "pedi a
        temporada errada".

        É a terceira encarnação da mesma armadilha no projeto: temporada e
        intervalo de datas não são a mesma coisa (ver as anotações das Fases 9 e
        10 no CLAUDE.md).

        Quando :attr:`temporada` é conhecida, a conta é exata. Quando não é —
        caso dos próximos jogos, que vêm de um arquivo sem essa coluna —, cai
        numa **heurística**: julho em diante pertence à temporada que começa no
        próprio ano; antes disso, à que começou no ano anterior. Ela acerta as
        ligas europeias e **erra as de ano civil** (Brasil, EUA, Noruega,
        Japão), que por regra 12 não entram nesta fase de todo jeito.
        """
        if self.temporada:
            from futebol.dados import limpeza

            return limpeza.ano_inicial(self.temporada)
        return self.data.year if self.data.month >= 7 else self.data.year - 1

    def __str__(self) -> str:
        return f"{self.mandante} × {self.visitante} ({self.liga}, {self.data})"


@dataclass(frozen=True)
class Ajuste:
    """Quanto a força de um time muda por causa dos desfalques.

    Atributos:
        time: a chave do time.
        ataque: quanto **subtrair** do ataque, em log. Sempre ≥ 0.
        defesa: quanto **subtrair** da defesa, em log. Sempre ≥ 0.
        desfalques: os que produziram este ajuste, para a tela poder listar.
        truncado: o teto do ``config.yaml`` chegou a agir? Serve para o
            relatório dizer "o time perdeu meio time e o ajuste parou no limite"
            em vez de esconder isso.

    ⚠️ **Os dois são subtrações, e os dois derrubam o time.** No modelo,
    ``λ = exp(intercepto + ataque_mandante − defesa_visitante + fator_casa)``, e
    a defesa entra com **sinal invertido** (positivo é defesa boa). Então tirar
    um zagueiro é subtrair de ``defesa``, o que **aumenta** os gols que o time
    sofre. Somar em vez de subtrair faria o time melhorar ao perder jogador — um
    erro que não daria erro nenhum.
    """

    time: str
    ataque: float = 0.0
    defesa: float = 0.0
    desfalques: tuple[Desfalque, ...] = field(default_factory=tuple)
    truncado: bool = False

    @property
    def mexeu(self) -> bool:
        return self.ataque > 0.0 or self.defesa > 0.0

    def resumo(self) -> str:
        """Uma linha em português, para a tela e para o log."""
        if not self.mexeu:
            return f"{self.time}: sem desfalques relevantes"
        partes = []
        if self.ataque > 0:
            partes.append(f"ataque −{self.ataque:.3f}")
        if self.defesa > 0:
            partes.append(f"defesa −{self.defesa:.3f}")
        teto = " (no teto)" if self.truncado else ""
        return f"{self.time}: {', '.join(partes)}{teto}"
