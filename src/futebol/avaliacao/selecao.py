"""A escolha oficial do modelo e dos parâmetros (regra 9).

Aqui a Fase 3 deixa de ter valores "provisórios". Este módulo define a lista de
configurações candidatas, roda o walk-forward de
:mod:`futebol.avaliacao.validacao` em cada uma e escolhe a de **menor log loss**.

Três regras do projeto se encontram neste arquivo:

- **regra 9** — a escolha é por log loss no walk-forward de validação. Não por
  ROI, não por acurácia, não por calibração;
- **regra 7** — nada aqui vê as temporadas de teste final. A tabela chega já
  filtrada por :mod:`futebol.avaliacao.divisao`;
- **regra 11** — a lista de candidatos é **explícita e contável**. Quem testa
  vinte configurações e reporta a melhor está reportando, em parte, sorte; o
  número de candidatos entra no pré-registro e cresce com o projeto.

⚠️ **Por que uma lista fixa em código, e não uma busca automática.** Uma busca
grande (dezenas de valores, várias dimensões) encontraria um mínimo melhor na
validação e pior na vida real — é sobreajuste da própria validação. A grade aqui
é pequena de propósito, em torno do que a literatura e a Fase 3 indicaram, e
serve para responder "o parâmetro importa? em que vizinhança?", não para raspar
a terceira casa decimal.

**O cache.** Cada candidato custa alguns minutos de walk-forward, e a janela
inteira dá mais de dez mil ajustes por candidato. As previsões de cada um são
gravadas em ``data/processed/validacao/`` (fora do Git, regra 4), com a janela no
nome do arquivo. Rodar de novo reaproveita o que já existe, e ``--forcar``
recalcula. Isso separa o que é caro (medir) do que é rápido (relatar e
desenhar), e é o que permite ajustar o texto do relatório sem esperar meia hora.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from futebol.avaliacao import validacao
from futebol.config import Config
from futebol.modelos import base
from futebol.modelos.baseline import Baseline
from futebol.modelos.dixon_coles import DixonColes
from futebol.modelos.poisson import Poisson, fator_casa_global

#: Início da janela oficial de validação. Antes disso é histórico de treino: as
#: 22 ligas do Grupo 1 começam em 2019/20, então sobram duas temporadas inteiras
#: de aquecimento antes da primeira rodada avaliada.
INICIO_VALIDACAO = "2021-07-01"

#: Valores de ``xi`` (decaimento temporal) na grade oficial. Em meia-vida:
#: infinito, 1386, 693, 385, 231 e 139 dias.
GRADE_XI: tuple[float, ...] = (0.0, 0.0005, 0.001, 0.0018, 0.003, 0.005)

#: Valores de ``jogos_equivalentes`` (encolhimento) na grade oficial.
GRADE_ENCOLHIMENTO: tuple[int, ...] = (1, 2, 6, 12, 20)


@dataclass(frozen=True)
class Candidato:
    """Uma configuração que disputa a escolha oficial.

    Atributos:
        nome: identificador curto, usado na tabela e no nome do arquivo de cache.
        descricao: uma linha em português, para o relatório.
        construir: fábrica que devolve um modelo novo, sem treino.
        escopo: ``"liga"`` ou ``"tudo"``, repassado ao walk-forward.
        parametros: os valores que definem a configuração. É o que vai para o
            pré-registro — "dixon-coles" não identifica nada; ``xi`` e ``m`` sim.
    """

    nome: str
    descricao: str
    construir: Callable[[], base.Modelo]
    escopo: str = "liga"
    parametros: dict[str, object] = field(default_factory=dict)


def candidatos(
    cfg: Config, jogos: pd.DataFrame, inicio=INICIO_VALIDACAO
) -> list[Candidato]:
    """A lista oficial de configurações da Fase 4.

    Args:
        cfg: configuração do projeto (fonte dos valores padrão).
        jogos: a tabela liberada, usada para medir o fator casa único **antes**
            do início da janela.
        inicio: começo da janela de validação.

    São 13 configurações: os três modelos, a grade de ``xi``, a grade de
    encolhimento e a variante de fator casa único. As repetições entre as grades
    e o padrão do ``config.yaml`` não são contadas duas vezes.
    """
    modelos = cfg.secao("modelos")
    xi_padrao = float(modelos["dixon_coles"]["xi"])
    m_padrao = float(modelos["shrinkage"]["jogos_equivalentes"])

    # O "fator casa único" é medido uma vez, com o que se sabia no começo da
    # janela, e congelado. Medi-lo de novo a cada rodada exigiria reajustar as 38
    # ligas em cada uma delas — quarenta vezes mais trabalho para responder a
    # mesma pergunta. O valor sai só de jogos anteriores à janela: nada de
    # futuro entra nele.
    antes_da_janela = base.jogos_ate(jogos, inicio)
    fator_unico = fator_casa_global(antes_da_janela)

    lista = [
        Candidato(
            nome="baseline",
            descricao="histórico de placares da liga; ignora quem joga",
            construir=lambda: Baseline(cfg=cfg),
            parametros={"modelo": "baseline"},
        ),
        Candidato(
            nome="poisson",
            descricao="ataque, defesa e fator casa por liga, sem decaimento",
            construir=lambda: Poisson(cfg=cfg),
            parametros={"modelo": "poisson", "m": m_padrao},
        ),
        Candidato(
            nome="dixon-coles",
            descricao=f"Poisson + placares baixos + decaimento (xi={xi_padrao})",
            construir=lambda: DixonColes(cfg=cfg),
            parametros={"modelo": "dixon-coles", "xi": xi_padrao, "m": m_padrao},
        ),
        Candidato(
            nome="dc-casa-unica",
            descricao=(
                f"Dixon-Coles com um fator casa só para as 38 competições "
                f"({fator_unico:.3f}), fixado antes da janela"
            ),
            construir=lambda: DixonColes(
                cfg=cfg, fator_casa="global", valor_fator_casa=fator_unico
            ),
            parametros={
                "modelo": "dixon-coles",
                "fator_casa": "global",
                "valor_fator_casa": round(fator_unico, 6),
            },
        ),
    ]

    lista += [
        Candidato(
            nome=f"dc-xi-{xi}",
            descricao=f"Dixon-Coles com xi={xi}",
            construir=lambda xi=xi: DixonColes(cfg=cfg, xi=xi),
            parametros={"modelo": "dixon-coles", "xi": xi, "m": m_padrao},
        )
        for xi in GRADE_XI
        if xi != xi_padrao
    ]
    lista += [
        Candidato(
            nome=f"dc-m-{m}",
            descricao=f"Dixon-Coles com encolhimento m={m}",
            construir=lambda m=m: DixonColes(cfg=cfg, jogos_equivalentes=m),
            parametros={"modelo": "dixon-coles", "xi": xi_padrao, "m": m},
        )
        for m in GRADE_ENCOLHIMENTO
        if m != m_padrao
    ]
    return lista


# ----------------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------------
def pasta_do_cache(cfg: Config) -> Path:
    """``data/processed/validacao/`` — fora do Git (regra 4)."""
    return cfg.raiz / "data" / "processed" / "validacao"


def caminho_do_cache(cfg: Config, nome: str, inicio, fim) -> Path:
    """Um arquivo por candidato **e por janela**.

    A janela entra no nome porque previsões de janelas diferentes não podem ser
    comparadas entre si. Guardá-las no mesmo arquivo seria a forma mais fácil de
    misturar duas medições e não perceber.
    """
    marca = f"{pd.Timestamp(inicio).date()}_{pd.Timestamp(fim).date()}"
    return pasta_do_cache(cfg) / f"{marca}__{nome}.parquet"


def rodar_candidato(
    jogos: pd.DataFrame,
    candidato: Candidato,
    cfg: Config,
    inicio=INICIO_VALIDACAO,
    fim=None,
    forcar: bool = False,
    aviso: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """Roda (ou lê do cache) o walk-forward de um candidato.

    Retorna:
        As previsões, uma linha por jogo avaliado.
    """
    fim = pd.Timestamp(jogos["data"].max()) + pd.Timedelta(days=1) if fim is None else fim
    caminho = caminho_do_cache(cfg, candidato.nome, inicio, fim)

    if caminho.is_file() and not forcar:
        if aviso is not None:
            aviso(f"  {candidato.nome}: lido do cache")
        return pd.read_parquet(caminho)

    if aviso is not None:
        aviso(f"  {candidato.nome}: medindo (walk-forward, alguns minutos)...")
    resultado = validacao.walk_forward(
        jogos,
        candidato.construir,
        inicio=inicio,
        fim=fim,
        escopo=candidato.escopo,
    )
    # A conferência roda sempre, e não só nos testes: é a regra 6, e ela não
    # pode depender de alguém lembrar de rodar o pytest.
    validacao.conferir_sem_vazamento(resultado.previsoes)
    if aviso is not None:
        aviso(f"    {resultado.resumo()}")

    caminho.parent.mkdir(parents=True, exist_ok=True)
    resultado.previsoes.to_parquet(caminho)
    return resultado.previsoes


def rodar(
    jogos: pd.DataFrame,
    cfg: Config,
    inicio=INICIO_VALIDACAO,
    fim=None,
    forcar: bool = False,
    aviso: Callable[[str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """Roda todos os candidatos e devolve ``{nome: previsões}``."""
    lista = candidatos(cfg, jogos, inicio)
    return {
        candidato.nome: rodar_candidato(
            jogos, candidato, cfg, inicio, fim, forcar, aviso
        )
        for candidato in lista
    }


# ----------------------------------------------------------------------------
# A escolha
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Escolha:
    """O resultado da seleção oficial.

    Atributos:
        vencedor: a medida do candidato de menor log loss.
        medidas: todas as medidas, da melhor para a pior.
        parametros: os parâmetros do vencedor, para o pré-registro.
        n_configuracoes: quantas configurações disputaram (regra 11).
        margem: quanto o vencedor ficou à frente do segundo colocado, em log
            loss. Serve para dizer se a escolha foi clara ou apertada.
    """

    vencedor: validacao.Medida
    medidas: list[validacao.Medida]
    parametros: dict[str, object]
    n_configuracoes: int
    margem: float


def escolher(
    previsoes: dict[str, pd.DataFrame], lista: list[Candidato]
) -> Escolha:
    """Escolhe a configuração de menor log loss (regra 9).

    ⚠️ Todos os candidatos são medidos **nos mesmos jogos** — a interseção das
    previsões de todos. Sem isso, um candidato que tenha pulado rodadas por
    histórico curto apareceria com vantagem ou desvantagem que não é dele.
    """
    medidas, _ = validacao.medir_nos_mesmos_jogos(previsoes)
    ordenadas = sorted(medidas, key=lambda m: m.log_loss)
    vencedor = ordenadas[0]
    parametros = next(c.parametros for c in lista if c.nome == vencedor.nome)
    return Escolha(
        vencedor=vencedor,
        medidas=ordenadas,
        parametros=parametros,
        n_configuracoes=len(medidas),
        margem=(
            ordenadas[1].log_loss - vencedor.log_loss if len(ordenadas) > 1 else float("nan")
        ),
    )
