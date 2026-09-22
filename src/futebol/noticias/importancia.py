"""Quanto um jogador vale para o time dele.

⚠️ **Esta é a peça que separa "o reserva do lateral está fora" de "o artilheiro
está fora", e sem ela a fase inteira não faz sentido.** Um ajuste que tratasse
os dois igual moveria a previsão pelo número de desfalques, não pelo tamanho
deles — e o número de desfalques é quase ruído: todo time sempre tem alguém no
departamento médico.

**De onde vêm os dados.** Não do projeto. A fonte do projeto
(football-data.co.uk) traz placar e odds e **nenhuma** informação de elenco.
Minutos, gols e titularidade vêm da API de futebol, e por isso as funções aqui
recebem os números prontos: elas são puras, não sabem que existe internet, e são
as que os testes exercitam.

**A fórmula, e por que ela é essa.** O peso é a média de três frações, cada uma
em [0, 1]:

1. **minutos** — quanto do tempo de jogo do time ele ocupou;
2. **participação em gols** — gols mais assistências dele sobre os do time;
3. **titularidade** — quantas vezes começou jogando, sobre os jogos do time.

As três dizem coisas diferentes e nenhuma basta sozinha. Só minutos promove o
zagueiro que joga sempre e nunca decide. Só gols promove o centroavante que
entrou seis vezes e fez três. Só titularidade ignora quem saiu machucado no
primeiro tempo de metade dos jogos. A média das três é grosseira — e é
deliberadamente grosseira, porque a alternativa seria inventar pesos para as
componentes sem ter como medi-los.

⚠️ **Participação em gols entra só para o ataque.** Um goleiro com zero gols não
pode ser descontado por isso: para quem defende, o peso sai de minutos e
titularidade, e o terceiro componente não existe. Usar a média dos três para
todo mundo faria todo defensor parecer irrelevante.
"""

from __future__ import annotations

from dataclasses import dataclass

from futebol.noticias.tipos import Jogador

#: Posições que contam como ataque, defesa ou os dois. A API entrega a posição
#: em inglês; o mapa traduz para o vocabulário do projeto.
#:
#: ⚠️ O meio-campo é ``"ambos"`` de propósito, e não uma terceira categoria: o
#: modelo tem dois parâmetros por time, então um setor a mais não teria onde ser
#: aplicado. Um volante fora derruba os dois lados um pouco.
POSICOES: dict[str, str] = {
    "attacker": "ataque",
    "forward": "ataque",
    "atacante": "ataque",
    "midfielder": "ambos",
    "meio-campo": "ambos",
    "defender": "defesa",
    "zagueiro": "defesa",
    "lateral": "defesa",
    "goalkeeper": "defesa",
    "goleiro": "defesa",
}

#: Para quem não tem posição conhecida. ``"ambos"`` é o palpite menos errado:
#: ele espalha o efeito em vez de concentrá-lo no lado errado.
SETOR_PADRAO = "ambos"

#: Quantos jogadores um time põe em campo.
#:
#: ⚠️ **Sem dividir por isto, o peso mede a coisa errada, e o erro é grande.**
#: "Jogou 76% dos minutos disponíveis" e "é 76% do time" são afirmações
#: completamente diferentes: um titular absoluto é ``1/11`` do time em campo,
#: não a metade dele.
#:
#: O primeiro teste com dados reais deixou isso na cara. De Roon saiu com peso
#: **0,531** — o que significaria que perder um volante equivale a perder
#: metade do Atalanta. Com dois desfalques por time, os dois batiam no teto de
#: 0,25 e ficavam **idênticos**; e como o modelo só enxerga
#: ``ataque_casa − defesa_fora``, dois ajustes iguais **se cancelam
#: exatamente**. A previsão saía 50,1% → 50,1% e parecia que o ajuste não
#: estava ligado. Estava — e estava saturado.
#:
#: Dividindo, um titular absoluto vale ~0,09, perder um titular derruba o
#: ataque para ``exp(−0,09)`` = 91% do que era, e o teto de 0,25 volta a
#: significar "perdi uns três titulares" em vez de ser atingido sempre.
JOGADORES_EM_CAMPO = 11


@dataclass(frozen=True)
class Estatisticas:
    """O que a API entrega sobre um jogador numa temporada.

    Atributos:
        minutos: minutos que ele jogou.
        gols: gols dele.
        assistencias: assistências dele.
        titular: em quantos jogos começou.
        jogos_do_time: quantas partidas o time fez.
        gols_do_time: quantos gols o time fez.
        posicao: como a fonte a chama. Traduzida por :data:`POSICOES`.
    """

    minutos: int = 0
    gols: int = 0
    assistencias: int = 0
    titular: int = 0
    jogos_do_time: int = 0
    gols_do_time: int = 0
    posicao: str = ""


def setor(posicao: str) -> str:
    """Traduz a posição da fonte para ``ataque``/``defesa``/``ambos``."""
    return POSICOES.get(posicao.strip().lower(), SETOR_PADRAO)


def _fracao(parte: float, total: float) -> float:
    """Uma razão segura, presa em [0, 1].

    ⚠️ O teto em 1 não é paranoia: a API às vezes reporta minutos de um jogador
    que passou pelo time no meio da temporada com o total de jogos do time novo,
    e a razão passa de 1. Sem o teto, o peso sairia acima de 100% e o ajuste
    estouraria o time inteiro por causa de um jogador.
    """
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, parte / total))


def peso(stats: Estatisticas) -> float:
    """Quanto do time este jogador é, em [0, 1].

    A média das componentes que **fazem sentido para a posição dele**: minutos e
    titularidade sempre; participação em gols só para quem ataca.

    Retorna:
        0.0 quando não há dados suficientes — e zero aqui significa "não sei",
        que é o valor certo: sem dados, o ajuste correto é não mexer em nada.
    """
    if stats.jogos_do_time <= 0:
        return 0.0

    # Os dois primeiros são **frações do time**, não do próprio jogador: o
    # denominador conta os 11 em campo. Ver `JOGADORES_EM_CAMPO`.
    componentes = [
        _fracao(stats.minutos, stats.jogos_do_time * 90 * JOGADORES_EM_CAMPO),
        _fracao(stats.titular, stats.jogos_do_time * JOGADORES_EM_CAMPO),
    ]
    # ⚠️ A participação em gols entra só quando dá para calculá-la: para quem
    # ataca **e** com os gols do time conhecidos. Incluí-la com
    # ``gols_do_time == 0`` daria fração zero, e zero aqui seria lido como "ele
    # não participa de gol nenhum" quando o certo é "não sei quantos gols o
    # time fez" — uma componente desconhecida puxaria o peso do artilheiro
    # para baixo em vez de ficar de fora.
    if setor(stats.posicao) in ("ataque", "ambos") and stats.gols_do_time > 0:
        componentes.append(
            _fracao(stats.gols + stats.assistencias, stats.gols_do_time)
        )
    return sum(componentes) / len(componentes)


def montar_jogador(
    nome: str, time: str, stats: Estatisticas, identificador: int | None = None
) -> Jogador:
    """Um :class:`Jogador` com peso e setor já calculados."""
    return Jogador(
        nome=nome,
        time=time,
        setor=setor(stats.posicao),
        peso=peso(stats),
        identificador=identificador,
    )


def contexto_dos_times(jogos, temporada: str | None = None) -> dict[str, tuple[int, int]]:
    """``{time: (jogos do time, gols do time)}``, da tabela do projeto.

    ⚠️ **Estes dois números NÃO vêm da API, e isso é de propósito.** O
    ``/players`` devolve as estatísticas *do jogador* e nada do time; para ter
    os totais do time seria mais uma chamada por time, dentro de uma cota de
    100 por dia. Só que o projeto **já tem** esses números, exatos, na própria
    tabela de jogos — de graça e sem chamada nenhuma.

    A alternativa que eu quase usei era aproximar ``jogos_do_time`` pelas
    aparições do próprio jogador. Ela é pior do que parece: um reserva com uma
    aparição de 90 minutos daria ``minutos / (1 × 90) = 1,0`` e viraria o
    jogador mais importante do elenco. A aproximação não teria dado erro —
    teria dado o peso errado.

    Args:
        jogos: a tabela de jogos do projeto.
        temporada: se dada, conta só essa temporada.
    """
    tabela = jogos if temporada is None else jogos.loc[
        jogos["temporada"].astype(str) == str(temporada)
    ]
    contexto: dict[str, tuple[int, int]] = {}
    for coluna, gols in (("mandante", "gols_mandante"), ("visitante", "gols_visitante")):
        agrupado = tabela.groupby(coluna).agg(
            partidas=(coluna, "size"), feitos=(gols, "sum")
        )
        for time, linha in agrupado.iterrows():
            partidas, feitos = contexto.get(str(time), (0, 0))
            contexto[str(time)] = (
                partidas + int(linha["partidas"]),
                feitos + int(linha["feitos"]),
            )
    return contexto


def sem_estatisticas(nome: str, time: str, posicao: str = "") -> Jogador:
    """Um jogador de quem não se sabe nada.

    ⚠️ Peso **zero**, e não um palpite médio. Um desfalque de quem não se tem
    dado não pode mover a previsão: mover seria inventar a informação que está
    faltando. Ele ainda aparece na tela, listado como "sem dados" — porque a
    pessoa precisa saber que a notícia existe, mesmo que o modelo a ignore.
    """
    return Jogador(nome=nome, time=time, setor=setor(posicao), peso=0.0)
