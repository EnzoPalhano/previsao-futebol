"""De "Arsenal x Chelsea" para um jogo que o modelo entende.

O modelo não conhece "Arsenal". Ele conhece ``ENG:Arsenal``, e só sabe prever
dentro de uma liga (regra 14 e :mod:`futebol.modelos.poisson`). Este módulo é a
ponte entre o jeito humano de pedir uma previsão e o jeito do modelo: recebe
dois nomes soltos, descobre de quem se trata, descobre em que competição eles
se encontram e devolve um :class:`futebol.modelos.base.Jogo`.

Ele existe separado do script de linha de comando porque a mesma tradução vai
ser usada pelo aplicativo da Fase 8 — e porque o caso perigoso aqui merece
teste automatizado:

⚠️ **Homônimo.** Existe Everton na Inglaterra e no Chile, River Plate na
Argentina e no Uruguai, Nacional em Portugal e no Uruguai. Se o projeto
escolhesse um deles por conta própria — o primeiro da lista, o mais antigo, o
que tem mais jogos — a previsão sairia bonita e sobre o time errado. Por isso,
nome ambíguo é **erro**, com a lista de opções na mensagem, e nunca um chute.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from futebol.dados import nomes_times
from futebol.modelos import base


class ErroDeConsulta(Exception):
    """Nome de time que não existe, ambíguo, ou confronto impossível de situar."""


@dataclass(frozen=True)
class Resolucao:
    """O jogo pronto para o modelo, mais o que foi preciso supor no caminho.

    Atributos:
        jogo: o :class:`~futebol.modelos.base.Jogo` resolvido.
        explicacao_liga: como a competição foi escolhida. Vai para a tela: o
            usuário precisa saber se a liga foi a que ele pediu, a do último
            encontro entre os dois, ou um palpite baseado no mandante.
        jogos_do_mandante: quantos jogos o mandante tem naquela liga.
        jogos_do_visitante: idem para o visitante. Zero é legítimo (time
            recém-promovido) e significa que o modelo vai tratá-lo como um time
            médio da divisão, por encolhimento.
    """

    jogo: base.Jogo
    explicacao_liga: str
    jogos_do_mandante: int
    jogos_do_visitante: int


# ----------------------------------------------------------------------------
# Achar o time
# ----------------------------------------------------------------------------
def chaves_dos_times(jogos: pd.DataFrame, liga: str | None = None) -> list[str]:
    """Todas as chaves de time da tabela, ou só as de uma liga."""
    recorte = jogos if liga is None else jogos.loc[jogos["liga"] == liga]
    return sorted(set(recorte["mandante"]).union(recorte["visitante"]))


def candidatos(jogos: pd.DataFrame, nome: str, liga: str | None = None) -> list[str]:
    """Quais chaves de time podem ser o nome pedido, da mais para a menos certa.

    A busca vai afunilando, e para no primeiro nível que encontrar alguém:

    1. a chave exata (``ENG:Arsenal``);
    2. o nome normalizado igual (``arsenal`` acha ``ENG:Arsenal``, e
       ``atletico madrid`` acha ``ESP:Atletico Madrid`` com ou sem acento);
    3. o nome normalizado contido no do time (``nottm`` acha
       ``ENG:Nott'm Forest``).

    O nível 3 é o que salva quem digita meio nome, e é também o que mais produz
    empate — ``united`` acha oito times. Empate não é resolvido aqui: quem
    chamou recebe a lista inteira e decide (no caso do projeto, reclama).
    """
    chaves = chaves_dos_times(jogos, liga)
    procurado = nomes_times.normalizar(nome)
    if not procurado:
        raise ErroDeConsulta("Nome de time vazio.")

    exatas = [chave for chave in chaves if chave == nome]
    if exatas:
        return exatas

    def sem_pais(chave: str) -> str:
        return chave.split(":", 1)[1] if ":" in chave else chave

    iguais = [
        chave for chave in chaves if nomes_times.normalizar(sem_pais(chave)) == procurado
    ]
    if iguais:
        return iguais

    return [
        chave
        for chave in chaves
        if procurado in nomes_times.normalizar(sem_pais(chave))
    ]


def resolver_time(jogos: pd.DataFrame, nome: str, liga: str | None = None) -> str:
    """A chave ``PAIS:nome`` de um time, ou um erro que explica o problema.

    Levanta:
        ErroDeConsulta: se nenhum time corresponder, ou se mais de um
            corresponder. No segundo caso, a mensagem lista as opções — é o
            caso do homônimo, e escolher por conta própria seria pior que falhar.
    """
    achados = candidatos(jogos, nome, liga)

    if not achados:
        onde = f" na liga {liga}" if liga else ""
        raise ErroDeConsulta(
            f"Não achei nenhum time parecido com {nome!r}{onde}. "
            "Os nomes são os da fonte (football-data.co.uk) — tente um pedaço "
            "do nome, como 'nottm' para o Nottingham Forest."
        )
    if len(achados) > 1:
        lista = ", ".join(achados)
        raise ErroDeConsulta(
            f"{nome!r} pode ser mais de um time: {lista}. "
            "Escreva a chave inteira (ex.: 'ENG:Everton') ou restrinja a liga "
            "com --liga. Há clubes de mesmo nome em países diferentes, e "
            "escolher um deles no chute daria uma previsão sobre o time errado."
        )
    return achados[0]


# ----------------------------------------------------------------------------
# Achar a competição
# ----------------------------------------------------------------------------
def ligas_do_time(jogos: pd.DataFrame, chave: str) -> pd.DataFrame:
    """Em que competições o time jogou, com a data do último jogo em cada uma.

    Ordenado da mais recente para a mais antiga. Um time inglês aparece na
    ``E0`` e na ``E1`` quando caiu e voltou — e é por isso que a liga do
    confronto precisa ser escolhida, não adivinhada de um jogo só.
    """
    dele = jogos.loc[(jogos["mandante"] == chave) | (jogos["visitante"] == chave)]
    if dele.empty:
        return pd.DataFrame(columns=["liga", "ultimo_jogo", "jogos"])
    resumo = (
        dele.groupby("liga")
        .agg(ultimo_jogo=("data", "max"), jogos=("data", "size"))
        .reset_index()
    )
    return resumo.sort_values("ultimo_jogo", ascending=False).reset_index(drop=True)


def escolher_liga(jogos: pd.DataFrame, mandante: str, visitante: str) -> tuple[str, str]:
    """Em que competição este confronto acontece.

    A regra, em ordem:

    1. a competição em que os **dois** jogaram mais recentemente — é onde o
       confronto de fato pode acontecer;
    2. se eles nunca coincidiram, a competição mais recente do **mandante**,
       porque é a casa dele que decide onde o jogo seria. O visitante entra
       nessa liga como time sem histórico, e o encolhimento cuida do resto.

    Retorna:
        ``(liga, explicação)``. A explicação é para a tela: o usuário precisa
        saber quando o projeto supôs algo.
    """
    do_mandante = ligas_do_time(jogos, mandante)
    do_visitante = ligas_do_time(jogos, visitante)
    if do_mandante.empty:
        raise ErroDeConsulta(f"O time {mandante!r} não tem jogo nenhum na tabela.")

    comuns = do_mandante.merge(
        do_visitante[["liga", "ultimo_jogo"]], on="liga", suffixes=("_m", "_v")
    )
    if not comuns.empty:
        # O último encontro possível: a liga em que o mais recente dos dois
        # últimos jogos é o maior.
        comuns = comuns.assign(
            encontro=comuns[["ultimo_jogo_m", "ultimo_jogo_v"]].min(axis=1)
        ).sort_values("encontro", ascending=False)
        escolhida = comuns.iloc[0]
        return str(escolhida["liga"]), (
            f"liga {escolhida['liga']}: a mais recente em que os dois jogaram "
            f"(até {pd.Timestamp(escolhida['encontro']).date()})"
        )

    escolhida = do_mandante.iloc[0]
    return str(escolhida["liga"]), (
        f"liga {escolhida['liga']}: os dois nunca se cruzaram na tabela, então "
        f"vale a competição mais recente do mandante. ATENÇÃO: o visitante "
        f"entra sem histórico nela e será tratado como um time médio da liga"
    )


# ----------------------------------------------------------------------------
# A resolução completa
# ----------------------------------------------------------------------------
def montar(
    jogos: pd.DataFrame,
    mandante: str,
    visitante: str,
    liga: str | None = None,
    data=None,
) -> Resolucao:
    """Traduz o pedido humano em um :class:`~futebol.modelos.base.Jogo`.

    Args:
        jogos: a tabela de jogos.
        mandante: nome ou chave do time da casa.
        visitante: nome ou chave do visitante.
        liga: a competição, se o usuário quiser fixá-la. Omitida, é escolhida
            por :func:`escolher_liga`.
        data: a data do jogo. É ela que define o corte de treino do modelo.
    """
    if liga is not None and liga not in set(jogos["liga"]):
        disponiveis = ", ".join(sorted(set(jogos["liga"])))
        raise ErroDeConsulta(
            f"A liga {liga!r} não está na tabela. Ligas presentes: {disponiveis}."
        )

    chave_mandante = resolver_time(jogos, mandante, liga)
    chave_visitante = resolver_time(jogos, visitante, liga)
    if chave_mandante == chave_visitante:
        raise ErroDeConsulta(
            f"Mandante e visitante são o mesmo time ({chave_mandante})."
        )

    if liga is None:
        liga, explicacao = escolher_liga(jogos, chave_mandante, chave_visitante)
    else:
        explicacao = f"liga {liga}: escolhida por você"

    da_liga = jogos.loc[jogos["liga"] == liga]
    conta = lambda chave: int(  # noqa: E731 - a expressão é menor que a função
        ((da_liga["mandante"] == chave) | (da_liga["visitante"] == chave)).sum()
    )

    return Resolucao(
        jogo=base.Jogo(
            liga=liga,
            mandante=chave_mandante,
            visitante=chave_visitante,
            data=pd.Timestamp(data) if data is not None else None,
        ),
        explicacao_liga=explicacao,
        jogos_do_mandante=conta(chave_mandante),
        jogos_do_visitante=conta(chave_visitante),
    )
