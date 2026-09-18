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
gravadas em ``data/processed/validacao/`` (fora do Git, regra 4), com a janela e
a assinatura dos parâmetros no nome do arquivo — nunca só o nome do candidato,
que muda de significado quando o ``config.yaml`` muda. Rodar de novo reaproveita o que já existe, e ``--forcar``
recalcula. Isso separa o que é caro (medir) do que é rápido (relatar e
desenhar), e é o que permite ajustar o texto do relatório sem esperar meia hora.
"""

from __future__ import annotations

import hashlib
import json
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

#: O ponto em torno do qual a grade oficial foi montada — os valores que a Fase 3
#: deixou no ``config.yaml`` marcados como ``PROVISORIO``.
#:
#: ⚠️ **Por que constantes, e não o ``config.yaml``.** A Fase 4 termina gravando
#: a escolha no config. Se a grade fosse lida de lá, a execução seguinte montaria
#: uma grade **diferente** da que foi medida: o encolhimento seria varrido em
#: torno do ``xi`` novo, e ``dixon-coles`` passaria a nomear outra configuração.
#: Seriam configurações novas disputando, e a contagem da regra 11 subiria sem
#: ninguém perceber — que é exatamente o sobreajuste da validação que a regra 11
#: existe para impedir. A grade de uma fase é um fato histórico: congela.
XI_DA_GRADE = 0.0018
M_DA_GRADE = 6.0


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
    xi_padrao = XI_DA_GRADE
    m_padrao = M_DA_GRADE

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
            construir=lambda: Poisson(cfg=cfg, jogos_equivalentes=m_padrao),
            parametros={"modelo": "poisson", "m": m_padrao},
        ),
        Candidato(
            nome="dixon-coles",
            descricao=f"Poisson + placares baixos + decaimento (xi={xi_padrao})",
            construir=lambda: DixonColes(
                cfg=cfg, xi=xi_padrao, jogos_equivalentes=m_padrao
            ),
            parametros={"modelo": "dixon-coles", "xi": xi_padrao, "m": m_padrao},
        ),
        Candidato(
            nome="dc-casa-unica",
            descricao=(
                f"Dixon-Coles com um fator casa só para as 38 competições "
                f"({fator_unico:.3f}), fixado antes da janela"
            ),
            construir=lambda: DixonColes(
                cfg=cfg,
                xi=xi_padrao,
                jogos_equivalentes=m_padrao,
                fator_casa="global",
                valor_fator_casa=fator_unico,
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
            construir=lambda xi=xi: DixonColes(
                cfg=cfg, xi=xi, jogos_equivalentes=m_padrao
            ),
            parametros={"modelo": "dixon-coles", "xi": xi, "m": m_padrao},
        )
        for xi in GRADE_XI
        if xi != xi_padrao
    ]
    lista += [
        Candidato(
            nome=f"dc-m-{m}",
            descricao=f"Dixon-Coles com encolhimento m={m}",
            construir=lambda m=m: DixonColes(cfg=cfg, xi=xi_padrao, jogos_equivalentes=m),
            parametros={"modelo": "dixon-coles", "xi": xi_padrao, "m": m},
        )
        for m in GRADE_ENCOLHIMENTO
        if m != m_padrao
    ]
    return lista


#: Quantas configurações a grade congelada da Fase 4 mede. A Fase 5 **soma** a
#: este número; ele nunca é substituído (regra 11).
N_CONFIGURACOES_FASE_4 = 13


def candidatos_fase5(
    cfg: Config, features: pd.DataFrame, jogos: pd.DataFrame | None = None
) -> list[Candidato]:
    """As configurações que a Fase 5 acrescenta à disputa.

    São **três**, e a conta de por que só três é a mesma da Fase 4: cada
    configuração testada é uma chance a mais de a melhor estar na frente por
    acaso (regra 11). Cada uma responde a uma pergunta diferente, e nenhuma
    existe para raspar decimal:

    - ``gbm`` — o modelo completo. *As features pagam?*
    - ``gbm-sem-dc`` — o mesmo, sem as quatro colunas do Dixon-Coles. *O GBM
      acrescenta alguma coisa, ou só está copiando o modelo de gols?* É a
      pergunta mais informativa da fase: se as duas variantes empatarem, o
      Dixon-Coles não estava ajudando; se a sem-DC despencar, o que o GBM sabe
      vem quase todo dele;
    - ``gbm-raso`` — árvores pequenas e folhas grandes. *Ele está decorando?*
      Resultado de futebol é quase todo ruído, e a variante regularizada é a
      forma de descobrir isso com número em vez de opinião.

    Args:
        cfg: configuração do projeto.
        features: a saída de
            :func:`futebol.features.construtor.carregar_ou_construir`, já
            calculada para a tabela inteira.
        jogos: opcional, só para permitir prever um jogo avulso pelo nome dos
            times. O walk-forward não precisa.
    """
    from futebol.features import construtor
    from futebol.modelos.gbm import FabricaGBM

    sem_dc = [c for c in features.columns if not c.startswith("dc_")]

    def fabrica(colunas: list[str], **hiper) -> FabricaGBM:
        return FabricaGBM(features[colunas], cfg=cfg, chaves=jogos, **hiper)

    completas = list(construtor.nomes_das_features())
    variantes = [
        ("gbm", "LightGBM de gols, com as 23 features", fabrica(completas), ),
        (
            "gbm-sem-dc",
            "o mesmo, sem as quatro colunas do Dixon-Coles",
            fabrica(sem_dc),
        ),
        (
            "gbm-raso",
            "LightGBM mais regularizado (folhas grandes, árvore rasa)",
            fabrica(completas, num_leaves=8, min_child_samples=200),
        ),
    ]
    return [
        Candidato(
            nome=nome,
            descricao=descricao,
            construir=fab.novo,
            # ⚠️ "tudo": o GBM é um modelo global, treinado com as 38
            # competições juntas. Com escopo "liga" ele veria só a competição
            # da vez, e um modelo de aprendizado com um trinta e oito avos dos
            # dados não é o modelo que se quer medir.
            escopo="tudo",
            parametros=fab.parametros,
        )
        for nome, descricao, fab in variantes
    ]


# ----------------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------------
def pasta_do_cache(cfg: Config) -> Path:
    """``data/processed/validacao/`` — fora do Git (regra 4)."""
    return cfg.raiz / "data" / "processed" / "validacao"


def marca_dos_parametros(parametros: dict[str, object]) -> str:
    """Uma assinatura curta e estável dos parâmetros de um candidato.

    ⚠️ **Por que isso existe.** O nome de um candidato depende do
    ``config.yaml``: o candidato chamado ``dixon-coles`` é *aquele com o ``xi``
    que estiver no config no momento*. Enquanto o cache era guardado só pelo
    nome, mudar o ``xi`` no config fazia a execução seguinte **ler previsões do
    ``xi`` antigo achando que eram do novo** — números errados, sem erro na tela.
    Foi o que aconteceu ao gravar a escolha da Fase 4 (``xi`` 0,0018 → 0,003).

    Guardando pelos parâmetros, duas configurações diferentes nunca disputam o
    mesmo arquivo, e a mesma configuração reaproveita o cache mesmo que o nome
    dela mude.
    """
    texto = json.dumps(parametros, sort_keys=True, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:10]


def caminho_do_cache(cfg: Config, candidato: Candidato, inicio, fim) -> Path:
    """Um arquivo por **parâmetros**, por janela.

    A janela entra no nome porque previsões de janelas diferentes não podem ser
    comparadas entre si. Guardá-las no mesmo arquivo seria a forma mais fácil de
    misturar duas medições e não perceber. Os parâmetros entram pelo mesmo
    motivo, e o nome do candidato fica junto só para o arquivo ser legível — quem
    decide qual arquivo é qual é a assinatura, nunca o nome.
    """
    marca = f"{pd.Timestamp(inicio).date()}_{pd.Timestamp(fim).date()}"
    assinatura = marca_dos_parametros(candidato.parametros)
    return pasta_do_cache(cfg) / f"{marca}__{candidato.nome}__{assinatura}.parquet"


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
    caminho = caminho_do_cache(cfg, candidato, inicio, fim)

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

    _gravar_no_cache(resultado.previsoes, caminho)
    return resultado.previsoes


def _gravar_no_cache(previsoes: pd.DataFrame, caminho: Path) -> None:
    """Grava o cache de um jeito que sobrevive a um desligamento no meio.

    A gravação vai primeiro para um arquivo ``.parcial`` ao lado do definitivo, e
    só depois ele é **renomeado** — e renomear, no mesmo disco, é uma operação
    que ou acontece inteira ou não acontece.

    ⚠️ Sem isso, fechar o terminal no meio de uma gravação deixaria um parquet
    truncado com o nome do arquivo bom. A execução seguinte o leria como "cache
    pronto" e mediria tudo em cima de previsões pela metade — um erro que não dá
    mensagem nenhuma, só números errados. É o mesmo cuidado que
    :mod:`futebol.dados.download` toma com os CSVs baixados.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".parcial")
    try:
        previsoes.to_parquet(temporario)
        temporario.replace(caminho)
    finally:
        temporario.unlink(missing_ok=True)


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


# ----------------------------------------------------------------------------
# O modelo oficial, para quem só quer usá-lo
# ----------------------------------------------------------------------------
def candidato_oficial(
    cfg: Config, jogos: pd.DataFrame, inicio=INICIO_VALIDACAO
) -> Candidato:
    """O candidato que corresponde ao que está gravado no ``config.yaml``.

    A Fase 6 em diante não disputa modelo: usa o escolhido. Esta função é a ponte
    entre "o que o config diz" e "qual arquivo de cache é esse".

    ⚠️ **Por que ela procura na grade em vez de montar um candidato novo.** O
    cache é um arquivo por (janela, nome, assinatura dos parâmetros). Montar aqui
    um candidato chamado ``oficial`` com os mesmos parâmetros daria a **mesma**
    assinatura e um **nome** diferente — ou seja, um arquivo novo, e uma hora de
    walk-forward para recalcular previsões idênticas às que já estão no disco.
    Procurando pelos parâmetros, o modelo oficial é reconhecido como o candidato
    da grade que ele de fato é, e o cache da Fase 4 é reaproveitado.

    Se algum dia o ``config.yaml`` apontar para uma configuração fora da grade
    congelada, o candidato é construído na hora — com o nome carregando os dois
    parâmetros, para nunca colidir com um da grade.
    """
    xi = float(cfg.bruto["modelos"]["dixon_coles"]["xi"])
    m = float(cfg.bruto["modelos"]["shrinkage"]["jogos_equivalentes"])
    procurado = {"modelo": "dixon-coles", "xi": xi, "m": m}

    for candidato in candidatos(cfg, jogos, inicio):
        if candidato.parametros == procurado:
            return candidato

    return Candidato(
        nome=f"dc-xi-{xi}-m-{m:g}",
        descricao=f"Dixon-Coles oficial do config.yaml (xi={xi}, m={m:g})",
        construir=lambda: DixonColes(cfg=cfg, xi=xi, jogos_equivalentes=m),
        parametros=procurado,
    )
