"""O cofre sendo aberto: a configuração pré-registrada e o teste final.

⚠️ **Este módulo roda uma única vez no projeto inteiro, e o motivo é o que dá
sentido a tudo o que veio antes.**

Desde a Fase 1, as temporadas que começaram em 2024 estão trancadas por
:mod:`futebol.avaliacao.divisao`. Nenhum modelo as viu, nenhum parâmetro foi
escolhido olhando para elas, nenhum backtest as usou. Elas existem para
responder **uma** pergunta, **uma** vez: o que o projeto afirma se sustenta em
dados que ele nunca tocou?

Se fosse permitido rodar, não gostar do resultado, mexer num parâmetro e rodar
de novo, as temporadas trancadas deixariam de ser teste e virariam mais um
conjunto de validação — e o número final não significaria nada. O valor delas
está inteiro na promessa de não repetir.

**Por que a configuração está congelada aqui, em código.**

A seção 2.6e da especificação manda pré-registrar a configuração no
``CLAUDE.md``. Só que o ``CLAUDE.md`` deste projeto **não é versionado** (é uma
decisão do Enzo, registrada lá): ele é local, ignorado via
``.git/info/exclude``. Ou seja, o pré-registro mais importante do projeto morava
num arquivo que o histórico do Git não pode testemunhar, e que pode ser editado
depois sem deixar rastro.

Então ele é duplicado aqui, como constante congelada, exatamente como a Fase 4
fez com ``selecao.XI_DA_GRADE``: o commit que introduz este arquivo é datado
pelo Git e **antecede** o commit que traz o resultado. E há um teste
(:func:`conferir_config`, chamada no ``pytest`` e pelo script) que compara estas
constantes com o ``config.yaml`` de hoje — se alguém mexer no config depois do
pré-registro, o ``pytest`` fica vermelho em vez de o teste final rodar com uma
configuração diferente da registrada.

⚠️ Nada aqui é escolha nova. É a transcrição do que o ``config.yaml`` já dizia
desde a Fase 6 e do que aquela fase mediu.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from futebol.avaliacao import divisao, selecao, validacao
from futebol.backtest import simulador
from futebol.config import Config
from futebol.dados import limpeza

# ----------------------------------------------------------------------------
# O pré-registro, congelado
# ----------------------------------------------------------------------------
#: A configuração de aposta levada ao teste final, fechada em 21/09/2026 antes
#: de qualquer jogo trancado ser lido.
#:
#: ⚠️ **O limite de EV é 5%, e o projeto já sabia que era o pior dos quatro.** A
#: Fase 6 mediu que o filtro de EV é anti-seletivo e piora monotonicamente com o
#: aperto (−11,36% em EV > 0%, −12,92% em 5%, −15,25% em 10%). Registrar 5% do
#: mesmo jeito é justamente o ponto: a alternativa seria escolher o limite
#: **depois** de ver qual saiu melhor no cofre, que é seleção por ROI — o que a
#: regra 9 proíbe. Escolher o critério depois de ver o resultado é como o
#: projeto se enganaria, e é contra isso que existe pré-registro.
CONFIGURACAO: dict[str, object] = {
    "modelo": "dixon-coles",
    "xi": 0.003,
    "jogos_equivalentes": 6.0,
    "fator_casa": "por_liga",
    "mercados": ("1x2", "ou25"),
    "odd_da_aposta": "odd_pre",
    "odd_do_clv": "odd_fech",
    "metodo_margem": "power",
    "ev_minimo": 0.05,
    "estrategia": "stake_fixa",
    "stake_fixa_pct": 0.01,
    "tipo_banca": "fixa",
    "bootstrap_amostras": 10_000,
}

#: Os anos em que começam as temporadas do teste final.
#:
#: São as duas registradas em ``avaliacao.temporadas_teste_final`` (``2425`` e
#: ``2526``). Ficam de dentro as quatro formas em que elas aparecem na tabela:
#: ``2024/25`` e ``2025/26`` nas ligas de temporada cruzada, ``2024`` e ``2025``
#: nas de ano civil (Brasil, EUA, Noruega, Japão) — a armadilha registrada no
#: CLAUDE.md, em que um filtro que só conhece a forma europeia descarta metade
#: das competições em silêncio.
#:
#: ⚠️ ``2026`` e ``2026/27`` ficam **de fora**: estão em andamento, e temporada
#: incompleta não é amostra de temporada. O cofre é mais largo que isto de
#: propósito (tranca tudo a partir de 2024) e essa folga **continua trancada**.
ANOS_DO_TESTE_FINAL: tuple[int, ...] = (2024, 2025)

#: Quantas configurações o projeto testou antes de abrir o cofre (regra 11).
#: 29 de modelo (Fases 3 a 5) + 16 de aposta (Fase 6) + 63 (Fase 7) + 0 (Fase 8).
CONFIGURACOES_TESTADAS = 108


class PreRegistroViolado(Exception):
    """O ``config.yaml`` não bate com o que foi pré-registrado.

    Isto não é um aviso: é uma parada. Rodar o teste final com uma configuração
    diferente da registrada produziria um número que não responde à pergunta
    que o pré-registro fez.
    """


def conferir_config(cfg: Config) -> None:
    """O ``config.yaml`` de hoje ainda é o que foi pré-registrado?

    Levanta:
        PreRegistroViolado: com a lista do que divergiu.

    ⚠️ Esta função é a razão de o pré-registro estar em código e não só no
    ``CLAUDE.md``. Ela roda no ``pytest`` **e** no script, antes de abrir o
    cofre: um `config.yaml` editado depois de 21/09/2026 derruba os dois, em vez
    de mudar o teste final em silêncio.
    """
    backtest = cfg.secao("backtest")
    esperado = {
        "modelos.dixon_coles.xi": (
            float(cfg.bruto["modelos"]["dixon_coles"]["xi"]),
            CONFIGURACAO["xi"],
        ),
        "modelos.shrinkage.jogos_equivalentes": (
            float(cfg.bruto["modelos"]["shrinkage"]["jogos_equivalentes"]),
            CONFIGURACAO["jogos_equivalentes"],
        ),
        "modelos.poisson.fator_casa": (
            cfg.bruto["modelos"]["poisson"]["fator_casa"],
            CONFIGURACAO["fator_casa"],
        ),
        "backtest.coluna_odd_aposta": (
            backtest["coluna_odd_aposta"],
            CONFIGURACAO["odd_da_aposta"],
        ),
        "backtest.coluna_odd_clv": (
            backtest["coluna_odd_clv"],
            CONFIGURACAO["odd_do_clv"],
        ),
        "backtest.ev_minimo": (
            float(backtest["ev_minimo"]),
            CONFIGURACAO["ev_minimo"],
        ),
        "backtest.estrategia": (backtest["estrategia"], CONFIGURACAO["estrategia"]),
        "backtest.stake_fixa_pct": (
            float(backtest["stake_fixa_pct"]),
            CONFIGURACAO["stake_fixa_pct"],
        ),
        "backtest.tipo_banca": (backtest["tipo_banca"], CONFIGURACAO["tipo_banca"]),
        "backtest.bootstrap_amostras": (
            int(backtest["bootstrap_amostras"]),
            CONFIGURACAO["bootstrap_amostras"],
        ),
    }
    divergiram = [
        f"  {chave}: config.yaml diz {atual!r}, o pré-registro diz {registrado!r}"
        for chave, (atual, registrado) in esperado.items()
        if atual != registrado
    ]
    if divergiram:
        raise PreRegistroViolado(
            "O config.yaml mudou depois do pré-registro de 21/09/2026:\n"
            + "\n".join(divergiram)
            + "\n\nO teste final só vale com a configuração registrada. Reverta o "
            "config.yaml — o pré-registro NÃO pode ser reescrito para bater com "
            "ele, que seria escolher depois de ver."
        )


# ----------------------------------------------------------------------------
# A janela trancada
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Janela:
    """Os jogos do teste final, e o que ficou de fora dele.

    Atributos:
        jogos: a tabela **inteira**, até o fim do teste final. O walk-forward
            precisa dela completa: prever um jogo de 2025 exige o histórico até
            2025, e isso é legítimo — a regra 6 proíbe usar o futuro, não o
            passado.
        inicio: primeira data avaliada.
        fim: limite superior, exclusivo.
        avaliados: quantos jogos caem dentro da janela.
        temporadas: as temporadas que entraram.
        ainda_trancados: jogos que continuam no cofre (temporada em andamento).
    """

    jogos: pd.DataFrame
    inicio: pd.Timestamp
    fim: pd.Timestamp
    avaliados: int
    temporadas: tuple[str, ...]
    ainda_trancados: int

    def resumo(self) -> str:
        return (
            f"{self.avaliados} jogos entre {self.inicio.date()} e "
            f"{self.fim.date()} ({', '.join(self.temporadas)}); "
            f"{self.ainda_trancados} seguem trancados (temporada em andamento)"
        )


def do_teste_final(temporada: str) -> bool:
    """A temporada é uma das duas pré-registradas?

    Vale para as duas formas: ``2024/25`` e ``2024`` são o mesmo período.
    """
    return limpeza.ano_inicial(temporada) in ANOS_DO_TESTE_FINAL


def abrir_cofre(jogos: pd.DataFrame, cfg: Config) -> Janela:
    """Recorta a janela do teste final da tabela completa.

    ⚠️ É a única função do projeto que olha de propósito para temporada
    trancada. Toda a Fase 3 à 8 chamou :func:`divisao.separar` para **não** ver
    o que esta aqui vê.

    Args:
        jogos: a tabela completa, ainda sem nenhum recorte.
        cfg: a configuração, para conferir que o cofre é o que se pensa.

    Levanta:
        ValueError: se a janela sair vazia — o que significaria que a tabela não
            tem as temporadas de teste, e um teste final sobre nada é pior que
            nenhum teste final.
    """
    do_teste = jogos["temporada"].map(do_teste_final)
    dentro = jogos.loc[do_teste]
    if dentro.empty:
        raise ValueError(
            "Nenhum jogo das temporadas de teste final na tabela. Rode "
            "`python scripts/preparar_dados.py` e confira "
            "avaliacao.temporadas_teste_final no config.yaml."
        )

    ano_do_cofre = divisao.ano_de_corte(cfg)
    ainda = jogos["temporada"].map(
        lambda t: divisao.e_teste_final(t, ano_do_cofre) and not do_teste_final(t)
    )
    inicio = pd.Timestamp(dentro["data"].min())
    fim = pd.Timestamp(dentro["data"].max()) + pd.Timedelta(days=1)
    return Janela(
        # A tabela vai inteira, menos o que continua trancado: prever a rodada
        # de agosto de 2024 precisa do histórico até julho de 2024, e ele está
        # na parte liberada. O que não pode entrar é o que vem DEPOIS da janela.
        jogos=jogos.loc[~ainda].copy(),
        inicio=inicio,
        fim=fim,
        avaliados=int(do_teste.sum()),
        temporadas=tuple(sorted(dentro["temporada"].unique())),
        ainda_trancados=int(ainda.sum()),
    )


# ----------------------------------------------------------------------------
# A rodada única
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Resultado:
    """Tudo o que o teste final produziu, numa peça só.

    Atributos:
        previsoes: o walk-forward do modelo oficial na janela trancada.
        medida_modelo: log loss e companhia, do modelo.
        medida_mercado: o mesmo, das odds de fechamento.
        amostra: a saída de :func:`simulador.preparar`.
        aposta: o resultado da configuração pré-registrada (EV > 5%).
        regua: apostar em **todas** as candidatas — a referência sem a qual o
            número acima não se lê (Fase 6).
        janela: de onde tudo saiu.
    """

    previsoes: pd.DataFrame
    medida_modelo: validacao.Medida
    medida_mercado: validacao.Medida
    amostra: simulador.Amostra
    aposta: simulador.Resultado
    regua: simulador.Resultado
    janela: Janela


def rodar(
    jogos: pd.DataFrame,
    cfg: Config,
    aviso: Callable[[str], None] | None = None,
    forcar: bool = False,
) -> Resultado:
    """Abre o cofre e mede, uma vez.

    ⚠️ A ordem importa: :func:`conferir_config` roda **antes** de qualquer
    leitura de temporada trancada. Se o pré-registro foi violado, o cofre nem
    chega a ser aberto.
    """
    conferir_config(cfg)

    janela = abrir_cofre(jogos, cfg)
    if aviso is not None:
        aviso(f"  cofre: {janela.resumo()}")

    # O candidato é procurado pelos PARÂMETROS na grade congelada da Fase 4, e
    # não montado aqui: é o mesmo cuidado da Fase 6 (ver CLAUDE.md). O cache é
    # um arquivo por (janela, nome, assinatura), então esta janela ganha o
    # arquivo dela sem encostar no da validação.
    candidato = selecao.candidato_oficial(cfg, janela.jogos, inicio=janela.inicio)
    previsoes = selecao.rodar_candidato(
        janela.jogos,
        candidato,
        cfg,
        inicio=janela.inicio,
        fim=janela.fim,
        forcar=forcar,
        aviso=aviso,
    )

    do_mercado = validacao.previsoes_do_mercado(janela.jogos.loc[previsoes.index])
    modelo, mercado = validacao.mesmos_jogos(previsoes, do_mercado)

    amostra = simulador.preparar(
        janela.jogos, previsoes, cfg, metodo=str(CONFIGURACAO["metodo_margem"])
    )
    apostas = simulador.selecionar(
        amostra.candidatos, float(CONFIGURACAO["ev_minimo"])
    )
    if apostas.empty:
        raise ValueError(
            "Nenhuma aposta passou no filtro de EV no teste final. Isso não é um "
            "resultado: é sinal de que a janela ou as odds não chegaram."
        )

    bootstrap = int(CONFIGURACAO["bootstrap_amostras"])
    return Resultado(
        previsoes=previsoes,
        medida_modelo=validacao.medir(modelo, candidato.nome),
        medida_mercado=validacao.medir(mercado, "mercado (fechamento)"),
        amostra=amostra,
        aposta=simulador.medir(
            apostas, "modelo", amostras_bootstrap=bootstrap, seed=cfg.seed
        ),
        regua=simulador.medir(
            amostra.candidatos,
            "todas as candidatas",
            amostras_bootstrap=bootstrap,
            seed=cfg.seed,
        ),
        janela=janela,
    )
