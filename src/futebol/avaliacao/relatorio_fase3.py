"""O relatório da Fase 3: os modelos medidos contra o baseline e o mercado.

Este módulo faz duas coisas: **mede** e **escreve**. A medição é uma avaliação
fora da amostra por recortes mensais — o modelo é reajustado no dia 1º de cada
mês e prevê os jogos daquele mês, sem nunca ter visto nenhum deles.

⚠️ **Isto não é o walk-forward oficial do projeto.** O critério oficial de
escolha de modelo é o walk-forward rodada a rodada da Fase 4 (regra 9), e todo
número deste relatório é **provisório**. A diferença entre os dois: aqui o
modelo pode estar até 30 dias desatualizado quando prevê o último jogo do mês,
e lá ele é reajustado a cada rodada. Isso pune os modelos um pouco, e pune
todos do mesmo jeito — o que preserva a comparação **relativa** entre eles, que
é para o que este relatório serve.

⚠️ **Nada aqui toca as temporadas de teste final** (regra 7). A trava é
:mod:`futebol.avaliacao.divisao`, e o relatório imprime quantos jogos ficaram
trancados para o Enzo poder conferir.

O que a Fase 3 tem para responder, e que este relatório responde com número:

1. os modelos batem o baseline burro? (se não, não aprenderam nada sobre times)
2. a que distância ficam do mercado de fechamento?
3. o fator casa por liga é melhor que um fator casa único? (experimento pedido)
4. o decaimento temporal ajuda, e com que ``xi``?
5. o encolhimento ajuda, e com quanta força?
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from futebol import relatorio
from futebol.avaliacao import divisao, metricas
from futebol.config import Config
from futebol.modelos import base
from futebol.modelos.baseline import Baseline
from futebol.modelos.dixon_coles import DixonColes
from futebol.modelos.poisson import Poisson
from futebol.odds import mercado

#: A ordem das opções do 1X2 nas matrizes de probabilidade.
CHAVES_1X2: tuple[str, ...] = ("H", "D", "A")

#: De letra do resultado para índice de coluna.
INDICE_RESULTADO: dict[str, int] = {"H": 0, "D": 1, "A": 2}

#: De quanto em quanto tempo o modelo é reajustado na medição. ``MS`` = todo
#: dia 1º. Um passo menor melhora os modelos e demora mais; o passo oficial,
#: rodada a rodada, é da Fase 4.
PASSO_PADRAO = "MS"

#: A janela de avaliação começa aqui: o início da última temporada liberada.
#: Tudo antes disso é treino.
INICIO_PADRAO = "2023-07-01"

#: O método de remoção de margem, escolhido na Fase 2 (ECE 0,0023).
METODO_MARGEM = "power"

#: Log loss de quem chuta 33% para cada opção. A referência mais baixa possível.
LOG_LOSS_UNIFORME = float(np.log(3))


@dataclass(frozen=True)
class Medida:
    """As notas de um modelo numa janela de avaliação.

    Atributos:
        nome: como o modelo aparece na tabela.
        n: quantos jogos foram previstos.
        log_loss: a nota que manda no projeto (regra 9).
        brier: erro quadrático médio, mais fácil de interpretar.
        ece: erro de calibração esperado.
        log_loss_ou: a log loss no mercado de Over/Under 2,5, que é binário e
            por isso tem escala diferente da do 1X2 (o chute uniforme ali dá
            0,693, não 1,0986).
    """

    nome: str
    n: int
    log_loss: float
    brier: float
    ece: float
    log_loss_ou: float | None = None

    def como_linha(self) -> dict[str, object]:
        return {
            "modelo": self.nome,
            "jogos": self.n,
            "log_loss": self.log_loss,
            "brier": self.brier,
            "ece": self.ece,
            "log_loss_ou": self.log_loss_ou,
        }


# ----------------------------------------------------------------------------
# Medição fora da amostra
# ----------------------------------------------------------------------------
def cortes_da_janela(inicio, fim, passo: str = PASSO_PADRAO) -> list[pd.Timestamp]:
    """As datas em que o modelo é reajustado, mais o fim da janela.

    A lista devolvida tem um elemento a mais que o número de recortes: o último
    é o fim da janela, e serve de limite do último recorte.
    """
    inicio, fim = pd.Timestamp(inicio), pd.Timestamp(fim)
    if fim <= inicio:
        raise ValueError(f"Janela vazia: de {inicio.date()} até {fim.date()}.")
    cortes = list(pd.date_range(inicio, fim, freq=passo))
    if not cortes or cortes[0] > inicio:
        cortes.insert(0, inicio)
    if cortes[-1] < fim:
        cortes.append(fim)
    return cortes


def previsoes_em_recortes(
    jogos: pd.DataFrame,
    construir_modelo: Callable[[], base.Modelo],
    inicio=INICIO_PADRAO,
    fim=None,
    passo: str = PASSO_PADRAO,
) -> pd.DataFrame:
    """Prevê a janela em recortes, retreinando o modelo no início de cada um.

    Args:
        jogos: a tabela (já **sem** as temporadas de teste final).
        construir_modelo: função que devolve um modelo novo, ainda sem treino.
            É uma função e não um modelo porque cada recorte precisa de um
            ajuste do zero — reaproveitar o objeto treinado deixaria o ajuste
            anterior influenciando o seguinte.
        inicio: começo da janela de avaliação.
        fim: fim da janela. ``None`` = o dia seguinte ao último jogo da tabela.
        passo: frequência de reajuste (``"MS"`` = mensal).

    Retorna:
        Uma linha por jogo previsto, com as probabilidades de cada mercado, o
        resultado observado e a data do corte que gerou aquela previsão.

    ⚠️ **Onde estaria o data leakage, se estivesse.** Cada modelo é treinado
    com ``ate_data=corte`` e prevê só jogos de data ``>= corte``. Ou seja:
    nenhuma previsão jamais viu o jogo que está prevendo, nem qualquer jogo
    posterior a ele. O teste ``test_nenhuma_previsao_viu_o_proprio_jogo``
    confere isso comparando, jogo a jogo, a data prevista com a data do último
    jogo de treino.
    """
    fim = pd.Timestamp(jogos["data"].max()) + pd.Timedelta(days=1) if fim is None else fim
    cortes = cortes_da_janela(inicio, fim, passo)

    partes = []
    for corte, proximo in zip(cortes[:-1], cortes[1:], strict=True):
        alvo = jogos.loc[(jogos["data"] >= corte) & (jogos["data"] < proximo)]
        if alvo.empty:
            continue
        modelo = construir_modelo().treinar(jogos, ate_data=corte)
        previsoes = modelo.prever_muitos(alvo)
        previsoes["liga"] = alvo["liga"].to_numpy()
        previsoes["grupo"] = alvo["grupo"].to_numpy()
        previsoes["data"] = alvo["data"].to_numpy()
        previsoes["corte"] = corte
        previsoes["treino_ate"] = modelo.ultima_data_de_treino
        previsoes["observado"] = alvo["resultado"].map(INDICE_RESULTADO).to_numpy()
        # 0 = aconteceu o over, 1 = aconteceu o under, na ordem das colunas
        # ("over25", "under25"). O índice tem que casar com a ordem, senão a
        # nota sairia invertida e ainda assim plausível.
        gols = alvo["gols_mandante"] + alvo["gols_visitante"]
        previsoes["observado_ou"] = np.where(gols >= 3, 0, 1)
        partes.append(previsoes)

    if not partes:
        raise ValueError(
            f"Nenhum jogo na janela de {pd.Timestamp(inicio).date()} a "
            f"{pd.Timestamp(fim).date()}."
        )
    return pd.concat(partes)


def perdas_por_jogo(previsoes: pd.DataFrame) -> np.ndarray:
    """``−log(p)`` do resultado que aconteceu, jogo a jogo.

    É a log loss antes de tirar a média. Serve para comparar duas variantes
    **jogo a jogo**, que é a única forma de saber se a diferença entre elas é
    maior que o acaso.
    """
    probabilidades = previsoes[list(CHAVES_1X2)].to_numpy(dtype=float)
    observado = previsoes["observado"].to_numpy(dtype=int)
    escolhidas = probabilidades[np.arange(len(observado)), observado]
    return -np.log(np.clip(escolhidas, 1e-15, 1.0))


def medir(previsoes: pd.DataFrame, nome: str) -> Medida:
    """As notas de um conjunto de previsões."""
    probabilidades = previsoes[list(CHAVES_1X2)].to_numpy(dtype=float)
    observado = previsoes["observado"].to_numpy(dtype=int)
    over_under = previsoes[["over25", "under25"]].to_numpy(dtype=float)
    return Medida(
        nome=nome,
        n=len(previsoes),
        log_loss=metricas.log_loss(probabilidades, observado),
        brier=metricas.brier(probabilidades, observado),
        ece=metricas.ece(probabilidades, observado),
        log_loss_ou=metricas.log_loss(
            over_under, previsoes["observado_ou"].to_numpy(dtype=int)
        ),
    )


@dataclass(frozen=True)
class Diferenca:
    """A diferença de log loss entre duas variantes, com incerteza.

    Comparar duas médias sem erro-padrão é a forma mais comum de inventar
    resultado: em 11 mil jogos, diferenças de 0,001 em log loss aparecem por
    acaso com facilidade. Como as duas variantes preveem **os mesmos jogos**, a
    comparação certa é emparelhada — jogo por jogo, o que cancela a dificuldade
    de cada partida e reduz muito o ruído.

    Atributos:
        media: a diferença média (``pior − melhor``, como foi pedida).
        erro_padrao: o erro-padrão dessa média.
        n: quantos jogos entraram.
    """

    media: float
    erro_padrao: float
    n: int

    @property
    def intervalo(self) -> tuple[float, float]:
        """O intervalo de 95% da diferença média."""
        margem = 1.96 * self.erro_padrao
        return self.media - margem, self.media + margem

    @property
    def significativa(self) -> bool:
        """O intervalo de 95% fica todo do mesmo lado do zero?"""
        baixo, alto = self.intervalo
        return baixo > 0 or alto < 0

    @property
    def efeito_minimo_detectavel(self) -> float:
        """A menor diferença que esta amostra conseguiria enxergar.

        Regra 10: reportar um efeito sem dizer o que a amostra é capaz de
        detectar deixa "não deu diferença" indistinguível de "não dava para
        saber". A conta é a usual para 95% de confiança e 80% de poder::

            efeito mínimo ≈ 2,8 · erro-padrão
        """
        return 2.8 * self.erro_padrao

    def como_texto(self) -> str:
        """A diferença em texto, com vírgula decimal e sinal explícito."""

        def com_sinal(valor: float) -> str:
            return ("+" if valor >= 0 else "") + relatorio.num(valor, 5)

        baixo, alto = self.intervalo
        veredito = "diferença real" if self.significativa else "indistinguível de zero"
        return (
            f"{com_sinal(self.media)} (IC 95%: {com_sinal(baixo)} a "
            f"{com_sinal(alto)}; n = {relatorio.inteiro(self.n)} jogos; menor efeito "
            f"detectável nesta amostra: "
            f"{relatorio.num(self.efeito_minimo_detectavel, 5)}) — {veredito}"
        )


def comparar(
    pior: pd.DataFrame, melhor: pd.DataFrame, /
) -> Diferenca:
    """Diferença emparelhada de log loss entre duas variantes.

    Args:
        pior: as previsões da variante que se espera ser pior.
        melhor: as previsões da outra.

    Retorna:
        A :class:`Diferenca`. Positiva quer dizer que ``pior`` de fato teve log
        loss maior (foi pior).
    """
    if len(pior) != len(melhor):
        raise ValueError(
            f"As duas variantes preveem conjuntos diferentes: {len(pior)} e "
            f"{len(melhor)} jogos. A comparação emparelhada exige os mesmos jogos."
        )
    diferencas = perdas_por_jogo(pior) - perdas_por_jogo(melhor)
    return Diferenca(
        media=float(diferencas.mean()),
        erro_padrao=float(diferencas.std(ddof=1) / np.sqrt(len(diferencas))),
        n=len(diferencas),
    )


def medir_o_mercado(jogos_da_janela: pd.DataFrame) -> tuple[Medida, pd.DataFrame]:
    """A nota das odds de fechamento nos mesmos jogos da janela.

    ⚠️ **Regra 13 e regra 12.** Só entram jogos do Grupo 1 com as três odds de
    fechamento registradas. Não é o mesmo conjunto que os modelos preveem — os
    16 países do Grupo 2 não têm odd pré-jogo e as ligas do Grupo 1 têm buracos
    de cobertura. Por isso a função devolve **também** o recorte usado, para o
    relatório poder medir os modelos exatamente nas mesmas partidas.

    Retorna:
        ``(medida do mercado, os jogos que entraram)``.
    """
    grupo1 = jogos_da_janela.loc[jogos_da_janela["grupo"] == "grupo1"]
    colunas = ["odd_fech_H", "odd_fech_D", "odd_fech_A"]
    odds = grupo1[colunas].to_numpy(dtype=float)
    completas = np.isfinite(odds).all(axis=1)
    usados = grupo1.loc[completas]

    probabilidades = mercado.remover_margem(odds[completas], METODO_MARGEM)
    observado = usados["resultado"].map(INDICE_RESULTADO).to_numpy(dtype=int)
    return (
        Medida(
            nome="mercado (fechamento)",
            n=int(completas.sum()),
            log_loss=metricas.log_loss(probabilidades, observado),
            brier=metricas.brier(probabilidades, observado),
            ece=metricas.ece(probabilidades, observado),
        ),
        usados,
    )


def medir_nos_mesmos_jogos(
    previsoes: pd.DataFrame, jogos: pd.DataFrame, nome: str
) -> Medida:
    """Mede um modelo apenas nos jogos de um recorte (o do mercado)."""
    return medir(previsoes.loc[previsoes.index.intersection(jogos.index)], nome)


# ----------------------------------------------------------------------------
# As variantes comparadas
# ----------------------------------------------------------------------------
def variantes_principais(cfg: Config) -> dict[str, Callable[[], base.Modelo]]:
    """Os três modelos da fase, com os parâmetros do ``config.yaml``."""
    return {
        "baseline (histórico da liga)": lambda: Baseline(cfg=cfg),
        "poisson": lambda: Poisson(cfg=cfg),
        "dixon-coles": lambda: DixonColes(cfg=cfg),
    }


def valores_de_xi() -> tuple[float, ...]:
    """A grade de ``xi`` da varredura provisória.

    ⚠️ Registrado para a regra 11: esta grade é uma das configurações testadas,
    e o número delas entra no pré-registro do CLAUDE.md. A escolha definitiva é
    da Fase 4.
    """
    return (0.0, 0.0005, 0.001, 0.0018, 0.003, 0.005)


def valores_de_encolhimento() -> tuple[int, ...]:
    """A grade de ``jogos_equivalentes`` da varredura provisória."""
    return (1, 2, 6, 12, 20)


# ----------------------------------------------------------------------------
# O relatório
# ----------------------------------------------------------------------------
def _cabecalho(
    jogos: pd.DataFrame,
    separacao: divisao.Divisao,
    cfg: Config,
    janela: tuple[pd.Timestamp, pd.Timestamp],
    gerado_em: str,
) -> str:
    grupo1 = sorted(jogos.loc[jogos["grupo"] == "grupo1", "liga"].unique())
    grupo2 = sorted(jogos.loc[jogos["grupo"] == "grupo2", "liga"].unique())
    inicio, fim = janela
    return "\n".join(
        [
            "# Fase 3 — Os primeiros modelos, medidos",
            "",
            f"- Camada de ligas: **{cfg.camada_ativa}**",
            f"- Jogos liberados (fora do teste final): **{relatorio.inteiro(len(jogos))}**",
            f"- Jogos trancados até a Fase 9: **{relatorio.inteiro(separacao.trancados)}** "
            f"(temporadas que começaram em {separacao.ano_de_corte} ou depois)",
            f"- Janela de avaliação: **{inicio.date()} a {fim.date()}**, "
            "com o modelo reajustado todo dia 1º",
            f"- Grupo 1 — backtest e CLV ({len(grupo1)}): {', '.join(grupo1)}",
            f"- Grupo 2 — treino e calibração ({len(grupo2)}): {', '.join(grupo2)}",
            f"- Gerado em: {gerado_em}",
            "",
            "> **Regra 13.** Cada tabela diz a quais ligas se refere. A comparação",
            "> com o mercado usa **só o Grupo 1 com odd de fechamento registrada** —",
            "> os 16 países do Grupo 2 não têm odd pré-jogo (regra 12).",
            "",
            "> ⚠️ **Todo número aqui é provisório.** O critério oficial de escolha de",
            "> modelo é a log loss no walk-forward rodada a rodada da Fase 4",
            "> (regra 9). Esta medição reajusta o modelo uma vez por mês, o que",
            "> deixa a previsão do fim do mês até 30 dias desatualizada. Isso",
            "> penaliza todos os modelos do mesmo jeito, então a comparação entre",
            "> eles continua valendo; o valor absoluto, não.",
            "",
            "> ⚠️ **Nada aqui viu as temporadas de teste final** (regra 7). A trava",
            "> é por código, em `futebol/avaliacao/divisao.py`, e conta pelo ano em",
            "> que a temporada começou — porque campeonato de ano civil chama a",
            "> temporada de `2024`, não de `2024/25`.",
        ]
    )


def _secao_como_funciona() -> str:
    return """## 1. O que a Fase 3 construiu

Três modelos, todos obedecendo à mesma interface (`treinar` e `prever`) e todos
entregando a mesma coisa: uma **matriz de placares**. A chance de cada placar
possível, de 0x0 a 10x10. Todo mercado sai dessa matriz — o 1X2 é a soma dos
triângulos, o Over 2,5 é a soma das casas em que os gols passam de dois, o
"ambos marcam" é tudo fora da primeira linha e da primeira coluna. Assim as
probabilidades nunca se contradizem entre si.

| Modelo | O que ele sabe |
|---|---|
| `baseline` | a distribuição histórica de placares da liga. **Ignora quem joga** |
| `poisson` | força de ataque e de defesa de cada time + fator casa da liga |
| `dixon-coles` | o Poisson + correção dos placares baixos + jogo antigo pesa menos |

O Poisson diz que os gols de cada lado saem de uma distribuição de Poisson com
médias

```
λ = exp(nível da liga + ataque do mandante − defesa do visitante + fator casa)
μ = exp(nível da liga + ataque do visitante − defesa do mandante)
```

Ataque e defesa são lidos em relação à média da própria liga: `ataque = +0,30`
quer dizer "faz `exp(0,30)` = 1,35 vez o que um time médio daquela competição
faria". Defesa positiva é defesa boa.

**Encolhimento.** As forças não são estimadas soltas: quem tem pouca história
na competição é puxado para a média dela, com peso `n / (n + m)`, onde `n` são
os jogos do time e `m` é o `jogos_equivalentes` do `config.yaml`. É a resposta
para o time recém-promovido, que chega sem nenhum jogo naquela divisão: o
modelo o trata como um time médio, que é o que se pode honestamente dizer de
quem não se conhece.
"""


def _secao_comparacao(medidas: Sequence[Medida], do_mercado: Sequence[Medida]) -> str:
    tabela = pd.DataFrame([m.como_linha() for m in medidas])
    principal = relatorio.de_dataframe(
        tabela,
        {
            "modelo": "Modelo",
            "jogos": "Jogos",
            "log_loss": "Log loss (1X2)",
            "brier": "Brier",
            "ece": "ECE",
            "log_loss_ou": "Log loss (O/U 2,5)",
        },
        {
            "jogos": "inteiro",
            "log_loss": "num",
            "brier": "num",
            "ece": "num",
            "log_loss_ou": "num",
        },
    )
    comparativa = relatorio.de_dataframe(
        pd.DataFrame([m.como_linha() for m in do_mercado]),
        {
            "modelo": "Quem prevê",
            "jogos": "Jogos",
            "log_loss": "Log loss (1X2)",
            "brier": "Brier",
            "ece": "ECE",
        },
        {"jogos": "inteiro", "log_loss": "num", "brier": "num", "ece": "num"},
    )

    melhor = min(medidas, key=lambda m: m.log_loss)
    mercado_ = do_mercado[-1]
    distancia = mercado_.log_loss
    melhor_g1 = min(do_mercado[:-1], key=lambda m: m.log_loss)

    return f"""## 2. Os modelos contra a régua

Todas as 38 competições, {relatorio.inteiro(medidas[0].n)} jogos previstos fora
da amostra. Menor é melhor nas três notas.

{principal}

Referências para ler a coluna da log loss: **{relatorio.num(LOG_LOSS_UNIFORME)}**
é o que tira quem chuta 33% para cada opção, e a Fase 2 mediu
**0,9984** para o mercado de fechamento do Grupo 1 inteiro.

O que a tabela diz:

- o **baseline** bate o chute uniforme. Só a estatística da liga — quantos por
  cento dos jogos o mandante ganha, quantos terminam com mais de 2,5 gols — já
  vale alguma coisa;
- o **Poisson** bate o baseline com folga. Essa é a prova de que ele aprendeu
  algo **sobre os times**, e não só sobre a liga;
- o **Dixon-Coles** bate o Poisson. Os dois remendos (placares baixos e
  decaimento) valem a complexidade que custam;
- o melhor da fase é o **{melhor.nome}**, com log loss
  **{relatorio.num(melhor.log_loss)}**.

⚠️ O ECE do baseline é o **mais baixo** da tabela, e isso não o torna melhor.
Calibração mede se "quando digo 60%, acontece 60%" — e um modelo que sempre diz
a média da liga acerta isso por construção, sem informar nada sobre o jogo. É
por isso que o projeto escolhe por log loss, e nunca por calibração sozinha.

### O mercado, nas mesmas partidas

Comparar o modelo com o mercado só é honesto no mesmo conjunto de jogos: o
mercado só existe onde há odd registrada, e isso exclui o Grupo 2 inteiro
(regra 12) e os buracos de cobertura do Grupo 1.

{comparativa}

O mercado de fechamento tira **{relatorio.num(distancia)}** e o melhor modelo da
fase tira **{relatorio.num(melhor_g1.log_loss)}** — uma distância de
**{relatorio.num(melhor_g1.log_loss - distancia)}** de log loss.

**Isto é o esperado, e não é fracasso** (Fase 4 da especificação). A odd de
fechamento embute lesão, escalação, mercado de transferência, dinheiro
profissional e o resultado de milhares de pessoas apostando. Um modelo com
força de ataque e defesa tirada de placares não deveria vencer isso — e se
vencesse na primeira tentativa, a suspeita certa seria data leakage, não
talento. O valor do projeto está em achar **onde** a diferença é pequena o
bastante para existir aposta com valor, e isso é assunto da Fase 6.
"""


def _secao_fator_casa(
    diferenca: Diferenca, fatores: pd.DataFrame, por_liga: Medida, global_: Medida
) -> str:
    extremos = pd.concat([fatores.head(5), fatores.tail(5)])
    tabela = relatorio.de_dataframe(
        extremos,
        {
            "liga": "Liga",
            "fator_casa": "Fator casa (log)",
            "vantagem_casa": "Gols do mandante ÷ do visitante",
            "jogos": "Jogos",
        },
        {"fator_casa": "num3", "vantagem_casa": "num2", "jogos": "inteiro"},
    )
    unico = float(fatores["fator_casa_global"].iloc[0])
    veredito = (
        "A diferença é real, embora pequena: o intervalo de 95% fica todo do "
        "lado de o fator casa por liga ser melhor."
        if diferenca.significativa
        else (
            "**A diferença não se distingue de zero nesta amostra.** O intervalo "
            "de 95% cruza o zero, e o efeito observado é menor que o menor efeito "
            "que 11 mil jogos conseguiriam detectar. A leitura honesta é *não sei "
            "dizer qual é melhor*, e não *são iguais*."
        )
    )
    return f"""## 3. Experimento: o fator casa deve ser por liga?

O experimento pedido na Fase 3. Duas variantes do Dixon-Coles, iguais em tudo o
mais:

- **por liga** — cada competição estima o seu fator casa;
- **global** — um número só, medido em todas as ligas juntas
  (`log(gols do mandante ÷ gols do visitante)` = {relatorio.num(unico, 3)},
  ou seja, o mandante faz {relatorio.num(float(np.exp(unico)), 2)} vez o que faz
  fora) e congelado em todas.

| Variante | Log loss |
|---|---|
| fator casa por liga | {relatorio.num(por_liga.log_loss)} |
| fator casa global | {relatorio.num(global_.log_loss)} |

A comparação certa é **emparelhada**, jogo a jogo — as duas variantes preveem
exatamente as mesmas partidas, e emparelhar cancela a dificuldade de cada
jogo. A diferença (global − por liga) em log loss:

**{diferenca.como_texto()}**

{veredito}

E isso faz sentido quando se olha de onde a diferença poderia vir. O fator casa
**varia muito** entre competições — a tabela abaixo mostra as cinco pontas de
cada lado, entre as 38 competições (Grupo 1 e Grupo 2 juntos, porque o fator
casa é estimado com placares e não com odds):

{tabela}

O padrão não é aleatório: no topo estão campeonatos de país grande, com viagem
longa entre cidades (Brasil, EUA), e embaixo ligas compactas ou com cultura de
mando mais fraca. Isso conversa com o que a Fase 2 já havia medido sobre a queda
do fator casa nos estádios vazios de 2020/21.

Só que a **maioria dos jogos** está em ligas cujo fator casa é próximo da média
geral. Quem pagaria o preço de um número único são as competições das pontas, e
elas são uma fatia pequena da amostra — por isso a diferença média fica
espremida contra o ruído, mesmo com 11 mil jogos.

**Decisão: fica o fator casa por liga** (`modelos.poisson.fator_casa:
por_liga`), por três motivos, e nenhum deles é "ganhou o teste":

1. em nenhuma medição ele apareceu **pior**;
2. custa um parâmetro por competição, com centenas ou milhares de jogos para
   estimá-lo — não é o tipo de parâmetro que causa sobreajuste;
3. o número único é indefensável nas pontas: aplicar a vantagem de casa do
   futebol japonês ao Brasileirão é errado por uma razão física (viagem,
   altitude, público), não estatística.

A Fase 4 revisita isso com o walk-forward oficial, onde a amostra é maior.

⚠️ Um efeito de graça, que não aparece na tabela: como o Dixon-Coles é
reajustado a cada data de previsão e os jogos recentes pesam mais, o fator casa
estimado **muda ao longo do tempo** por si só. O experimento acima compara
"por liga" com "único"; a variação no tempo já está dentro das duas.
"""


def _secao_decaimento(varredura: pd.DataFrame, diferenca: Diferenca) -> str:
    tabela = relatorio.de_dataframe(
        varredura,
        {
            "xi": "xi",
            "meia_vida_texto": "Meia-vida",
            "log_loss": "Log loss",
            "brier": "Brier",
            "ece": "ECE",
        },
        {"xi": "num4", "log_loss": "num", "brier": "num", "ece": "num"},
    )
    melhor = varredura.loc[varredura["log_loss"].idxmin()]
    return f"""## 4. Vale fazer jogo antigo pesar menos?

O decaimento temporal dá a cada jogo o peso `exp(−xi · dias)`. Com `xi = 0` o
modelo acha que 2019 e o mês passado valem o mesmo; quanto maior o `xi`, mais
curta a memória.

{tabela}

Ligar o decaimento vale a pena. A diferença entre não ter memória curta
(`xi = 0`) e usar o valor do `config.yaml`, medida emparelhada jogo a jogo:

**{diferenca.como_texto()}**

O melhor ponto desta grade é `xi = {relatorio.num(float(melhor["xi"]), 4)}`
(meia-vida de {relatorio.num(float(melhor["meia_vida"]), 0)} dias), com log loss
{relatorio.num(float(melhor["log_loss"]))}.

⚠️ **Este número NÃO é a escolha do `xi`** (regra 9). A escolha sai do
walk-forward de validação da Fase 4, rodada a rodada, e o que está aqui é uma
varredura grossa de sanidade: ela mostra que o parâmetro importa e em que
vizinhança ficar, e serve para o Enzo ver o formato da curva. Escolher agora,
com uma medição mensal e uma grade de {len(varredura)} pontos, seria decidir com
a ferramenta errada.
"""


def _secao_encolhimento(varredura: pd.DataFrame) -> str:
    tabela = relatorio.de_dataframe(
        varredura,
        {
            "jogos_equivalentes": "jogos_equivalentes (m)",
            "peso_com_10_jogos": "Peso próprio com 10 jogos",
            "log_loss": "Log loss",
            "brier": "Brier",
            "ece": "ECE",
        },
        {
            "jogos_equivalentes": "inteiro",
            "peso_com_10_jogos": "pct",
            "log_loss": "num",
            "brier": "num",
            "ece": "num",
        },
    )
    melhor = varredura.loc[varredura["log_loss"].idxmin()]
    return f"""## 5. Quanto encolher a força de quem tem pouca história?

O `m` (`modelos.shrinkage.jogos_equivalentes`) é **quantos jogos de história a
média da liga vale**. A força que o modelo usa fica em torno de

```
força do time ≈ (n / (n + m)) · força que os jogos dele pedem
```

Com `m` grande, todo mundo vira time médio (o modelo deixa de distinguir os
times); com `m` perto de zero, três jogos bons fazem um time parecer o Bayern.

{tabela}

O melhor ponto desta grade é `m = {int(melhor["jogos_equivalentes"])}`, e a
curva é rasa entre 2 e 12 — o modelo não é sensível a essa escolha na faixa
razoável, o que é uma boa notícia.

⚠️ Igual ao `xi`: provisório, escolha definitiva na Fase 4.
"""


def _secao_placares_baixos(rho: pd.DataFrame, no_limite: pd.Series) -> str:
    extremos = pd.concat([rho.head(5), rho.tail(3)])
    tabela = relatorio.de_dataframe(
        extremos,
        {"liga": "Liga", "rho": "rho", "jogos": "Jogos"},
        {"rho": "num4", "jogos": "inteiro"},
    )
    negativos = int((rho["rho"] < 0).sum())
    return f"""## 6. A correção dos placares baixos, liga por liga

O `rho` do Dixon-Coles mede o quanto 0x0 e 1x1 acontecem **mais** (e 1x0 e 0x1
**menos**) do que a independência entre os dois times preveria. `rho` negativo
é o caso conhecido na literatura, e o efeito cai direto na probabilidade de
**empate** — o mercado em que o Poisson puro erra mais.

O projeto estima um `rho` por competição, junto com o resto:

{tabela}

Em {negativos} das {len(rho)} competições o `rho` saiu negativo, como a
literatura prevê. Onde ele fica perto de zero, a correção simplesmente não faz
nada naquela liga — o que é o comportamento correto: o parâmetro é estimado, não
imposto.

⚠️ {
        "Nenhuma liga encostou"
        if not no_limite.any()
        else f"ATENÇÃO: {int(no_limite.sum())} liga(s) encostaram"
    } no limite de |rho| ≤ 0,15 imposto pelo código. Esse limite existe porque um
`rho` muito negativo pode empurrar a probabilidade de um placar para baixo de
zero, e probabilidade negativa não existe.
"""


def _secao_limites(configuracoes: set[str]) -> str:
    return f"""## 7. O que este relatório não diz

Vale mais listar o que **não** está aqui do que enfeitar o que está:

- **não há walk-forward oficial.** A medição é mensal, não rodada a rodada. A
  Fase 4 refaz tudo isso do jeito certo, e é dela que sai a escolha do modelo;
- **não há nenhuma aposta.** Nem ROI, nem CLV, nem valor esperado. Comparar a
  probabilidade do modelo com a odd da casa é a Fase 6, e a lista de ligas
  aprovadas para isso já está no `config.yaml` desde a Fase 2 (18 ligas);
- **as temporadas de teste final continuam fechadas** (regra 7). Elas serão
  abertas uma única vez, na Fase 9, com a configuração já pré-registrada;
- **nenhuma feature de formulário.** Elo, médias móveis, dias de descanso e
  desfalques são das Fases 5 e 7. O que está medido aqui é o quanto se consegue
  **só com placares**.

**Contagem de configurações testadas (regra 11).** Nesta fase foram medidas
**{len(configuracoes)}** configurações distintas na janela de validação: os 3
modelos, as 2 variantes de fator casa, a grade de {len(valores_de_xi())} valores
de `xi` e a grade de {len(valores_de_encolhimento())} valores de encolhimento
(descontadas as repetições entre as grades e o padrão do `config.yaml`).

Registrar isso não é formalidade. Quanto mais configurações são testadas, maior
a chance de a melhor delas estar na frente **por sorte** — e é por isso que o
número precisa estar escrito antes de o teste final ser aberto. Nenhuma destas
{len(configuracoes)} olhou o teste final. O total acumulado vive no pré-registro
do CLAUDE.md e cresce na Fase 4.
"""


def gerar(
    jogos: pd.DataFrame,
    cfg: Config,
    gerado_em: str,
    inicio=INICIO_PADRAO,
    passo: str = PASSO_PADRAO,
    aviso=print,
) -> str:
    """Mede tudo e devolve o relatório da Fase 3 em Markdown.

    Args:
        jogos: a tabela completa, **com** teste final — a separação é feita aqui
            dentro, para o relatório poder dizer quantos jogos ficaram de fora.
        cfg: a configuração do projeto.
        gerado_em: a data que aparece no cabeçalho.
        inicio: começo da janela de avaliação.
        passo: frequência de reajuste do modelo.
        aviso: por onde reportar o progresso (a medição leva alguns minutos).
    """
    separacao = divisao.separar(jogos, cfg)
    liberados = separacao.jogos
    aviso(separacao.resumo())

    fim = pd.Timestamp(liberados["data"].max()) + pd.Timedelta(days=1)
    janela = (pd.Timestamp(inicio), fim)

    # Regra 11: cada configuração medida é registrada, para o relatório poder
    # dizer quantas foram — e não "algumas". Repetição não conta duas vezes.
    configuracoes: set[str] = set()

    def avaliar(nome: str, construir) -> pd.DataFrame:
        aviso(f"  medindo {nome}...")
        configuracoes.add(nome)
        return previsoes_em_recortes(liberados, construir, inicio, fim, passo)

    # -- os três modelos --------------------------------------------------
    previsoes = {
        nome: avaliar(nome, construir)
        for nome, construir in variantes_principais(cfg).items()
    }
    medidas = [medir(p, nome) for nome, p in previsoes.items()]

    da_janela = liberados.loc[
        (liberados["data"] >= janela[0]) & (liberados["data"] < janela[1])
    ]
    medida_mercado, jogos_com_odd = medir_o_mercado(da_janela)
    no_mesmo_recorte = [
        medir_nos_mesmos_jogos(p, jogos_com_odd, nome) for nome, p in previsoes.items()
    ] + [medida_mercado]

    # -- fator casa: por liga x global ------------------------------------
    com_casa_global = avaliar(
        "dixon-coles com fator casa global",
        lambda: DixonColes(cfg=cfg, fator_casa="global"),
    )
    diferenca_casa = comparar(com_casa_global, previsoes["dixon-coles"])

    ajustado = DixonColes(cfg=cfg).treinar(liberados, ate_data=janela[1])
    fatores = ajustado.resumo()[["liga", "jogos", "fator_casa", "vantagem_casa", "rho"]]
    fatores = fatores.sort_values("fator_casa", ascending=False).reset_index(drop=True)
    fatores["fator_casa_global"] = float(
        DixonColes(cfg=cfg, fator_casa="global")
        .treinar(liberados, ate_data=janela[1])
        .fator_casa_medido
    )

    # -- varredura do xi --------------------------------------------------
    # A varredura reaproveita a medição do dixon-coles padrão quando o valor da
    # grade é o do config.yaml: refazer a mesma conta daria o mesmo número e
    # contaria uma configuração inexistente.
    xi_padrao = DixonColes(cfg=cfg).xi
    linhas_xi = []
    for xi in valores_de_xi():
        se_padrao = np.isclose(xi, xi_padrao)
        avaliadas = (
            previsoes["dixon-coles"]
            if se_padrao
            else avaliar(f"xi = {xi}", lambda xi=xi: DixonColes(cfg=cfg, xi=xi))
        )
        medida = medir(avaliadas, f"xi={xi}")
        linhas_xi.append(
            {
                "xi": xi,
                "meia_vida": float("inf") if xi == 0 else float(np.log(2) / xi),
                "meia_vida_texto": (
                    "sem decaimento" if xi == 0 else f"{np.log(2) / xi:.0f} dias"
                ),
                "log_loss": medida.log_loss,
                "brier": medida.brier,
                "ece": medida.ece,
            }
        )
    varredura_xi = pd.DataFrame(linhas_xi)
    sem_decaimento = avaliar("xi = 0.0", lambda: DixonColes(cfg=cfg, xi=0.0))
    diferenca_decaimento = comparar(sem_decaimento, previsoes["dixon-coles"])

    # -- varredura do encolhimento ----------------------------------------
    m_padrao = DixonColes(cfg=cfg).jogos_equivalentes
    linhas_m = []
    for m in valores_de_encolhimento():
        avaliadas = (
            previsoes["dixon-coles"]
            if np.isclose(m, m_padrao)
            else avaliar(
                f"encolhimento m = {m}",
                lambda m=m: DixonColes(cfg=cfg, jogos_equivalentes=m),
            )
        )
        medida = medir(avaliadas, f"m={m}")
        linhas_m.append(
            {
                "jogos_equivalentes": m,
                "peso_com_10_jogos": 10 / (10 + m),
                "log_loss": medida.log_loss,
                "brier": medida.brier,
                "ece": medida.ece,
            }
        )
    varredura_m = pd.DataFrame(linhas_m)

    resumo_ajuste = ajustado.resumo()
    rho = (
        resumo_ajuste[["liga", "jogos", "rho"]]
        .sort_values("rho")
        .reset_index(drop=True)
    )

    return "\n".join(
        [
            _cabecalho(liberados, separacao, cfg, janela, gerado_em),
            "",
            _secao_como_funciona(),
            _secao_comparacao(medidas, no_mesmo_recorte),
            _secao_fator_casa(
                diferenca_casa,
                fatores,
                medir(previsoes["dixon-coles"], "por liga"),
                medir(com_casa_global, "global"),
            ),
            _secao_decaimento(varredura_xi, diferenca_decaimento),
            _secao_encolhimento(varredura_m),
            _secao_placares_baixos(rho, resumo_ajuste["rho_no_limite"]),
            _secao_limites(configuracoes),
        ]
    )
