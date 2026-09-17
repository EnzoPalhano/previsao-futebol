"""O walk-forward: a avaliação que o projeto tem coragem de acreditar.

Toda nota de modelo que vale algo responde a mesma pergunta: **se eu tivesse
usado este modelo naquele dia, com o que eu sabia naquele dia, o que teria
acontecido?** É só isso que walk-forward significa. Para cada rodada:

1. treinar **só** com os jogos anteriores a ela;
2. prever a rodada;
3. guardar a previsão ao lado do que aconteceu;
4. andar para a rodada seguinte e repetir.

Rodada aqui é literal: **cada data em que uma competição jogou**. Numa liga com
120 datas por temporada, são 120 ajustes por temporada — o modelo é reestimado
antes de cada uma delas. Isso é mais rigoroso que o recorte mensal que a Fase 3
usou para experimentar: lá a previsão do fim do mês podia estar 30 dias
desatualizada, e aqui nunca passa de zero.

⚠️ **É esta medição que escolhe o modelo do projeto** (regra 9). Não o ROI, não
a acurácia, não a calibração: a **log loss** medida aqui, na janela de
validação, com as temporadas de teste final trancadas (regra 7).

**Por que isto não é "só rodar um `for`".** Três armadilhas moram aqui, e cada
uma produz um resultado bom e falso:

- **treinar com o próprio jogo.** Um ``<=`` onde devia haver ``<`` e o modelo
  prevê partidas que já viu. A trava está em
  :func:`futebol.modelos.base.jogos_ate` e é conferida jogo a jogo por
  :func:`conferir_sem_vazamento`;
- **treinar com o futuro distante.** Ajustar uma vez com a tabela inteira e
  "prever" o passado. É por isso que o modelo é construído **de novo** em cada
  rodada, por uma função fábrica, e nunca reaproveitado;
- **comparar em conjuntos diferentes.** O mercado só existe onde há odd
  registrada; medir o modelo em 11 mil jogos e o mercado em 8 mil e pôr os dois
  na mesma tabela é comparar coisas diferentes. Daí
  :func:`medir_nos_mesmos_jogos`.

O módulo mede **um ajuste por liga**, e não um ajuste global por rodada. Isso é
possível porque os modelos do projeto estimam cada competição separadamente
(ver :mod:`futebol.modelos.poisson`), e é o que torna o walk-forward estrito
viável: são ~11 mil ajustes numa janela de três temporadas, a 11 ms cada.
⚠️ Variante que estime algo **global** — o fator casa único, por exemplo —
precisa de ``escopo="tudo"``, senão o "global" dela seria calculado só com a
liga da vez.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd

from futebol.avaliacao import metricas
from futebol.modelos import base
from futebol.odds import mercado

#: A ordem das opções do 1X2 em toda matriz de probabilidade do projeto.
CHAVES_1X2: tuple[str, ...] = ("H", "D", "A")

#: De letra do resultado para índice de coluna.
INDICE_RESULTADO: dict[str, int] = {"H": 0, "D": 1, "A": 2}

#: Jogos de história que uma liga precisa ter antes de uma rodada para ela
#: entrar na avaliação. Prever com 20 jogos de histórico não mede o modelo,
#: mede o acaso — e as rodadas puladas são contadas e reportadas, nunca
#: descartadas em silêncio.
MINIMO_DE_TREINO = 100

#: O método de remoção de margem, escolhido por medição na Fase 2 (ECE 0,0023).
METODO_MARGEM = "power"


@dataclass(frozen=True)
class Medida:
    """As notas de um conjunto de previsões.

    Atributos:
        nome: como aparece na tabela do relatório.
        n: quantos jogos.
        log_loss: a nota que decide (regra 9). Menor é melhor.
        brier: erro quadrático médio das probabilidades.
        acuracia: fração de acertos da opção mais provável. Reportada, não usada
            para decidir — ver :func:`futebol.avaliacao.metricas.acuracia`.
        ece: erro de calibração esperado.
        log_loss_ou: log loss no mercado de Over/Under 2,5. Escala diferente da
            do 1X2: por ser binário, o chute uniforme ali dá 0,693.
    """

    nome: str
    n: int
    log_loss: float
    brier: float
    acuracia: float
    ece: float
    log_loss_ou: float | None = None

    def como_linha(self) -> dict[str, object]:
        return {
            "modelo": self.nome,
            "jogos": self.n,
            "log_loss": self.log_loss,
            "brier": self.brier,
            "acuracia": self.acuracia,
            "ece": self.ece,
            "log_loss_ou": self.log_loss_ou,
        }


@dataclass(frozen=True)
class Diferenca:
    """A diferença de log loss entre duas variantes, com incerteza.

    Comparar duas médias sem erro-padrão é a forma mais comum de inventar
    resultado: em dezenas de milhares de jogos, diferenças de 0,001 em log loss
    aparecem por acaso com facilidade. Como as duas variantes preveem **os
    mesmos jogos**, a comparação certa é emparelhada — jogo por jogo, o que
    cancela a dificuldade de cada partida e derruba muito o ruído.

    Atributos:
        media: a diferença média, na ordem em que foi pedida (``pior − melhor``).
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
        from futebol import relatorio

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


@dataclass(frozen=True)
class ResultadoWalkForward:
    """As previsões e a contabilidade de como elas foram feitas.

    A contabilidade não é enfeite: sem ela não há como saber se uma comparação
    entre dois modelos foi feita no mesmo conjunto de jogos.

    Atributos:
        previsoes: uma linha por jogo previsto.
        ajustes: quantas vezes um modelo foi treinado.
        rodadas_puladas: rodadas deixadas de fora por falta de histórico.
        jogos_pulados: quantos jogos havia nessas rodadas.
        ligas: quantas competições entraram.
    """

    previsoes: pd.DataFrame
    ajustes: int
    rodadas_puladas: int
    jogos_pulados: int
    ligas: int

    def resumo(self) -> str:
        return (
            f"{len(self.previsoes)} jogos previstos em {self.ligas} competições, "
            f"com {self.ajustes} ajustes de modelo; {self.jogos_pulados} jogos em "
            f"{self.rodadas_puladas} rodadas ficaram de fora por histórico curto"
        )


# ----------------------------------------------------------------------------
# As rodadas
# ----------------------------------------------------------------------------
def rodadas(
    jogos: pd.DataFrame, inicio=None, fim=None
) -> Iterator[tuple[str, pd.DataFrame, list[pd.Timestamp]]]:
    """Percorre ``(liga, jogos da liga, datas a avaliar)``, liga por liga.

    Uma "rodada" é uma data em que a competição jogou. Duas partidas no mesmo
    dia entram juntas, e é assim que tem de ser: na vida real, a aposta do jogo
    das 18h foi feita antes de o jogo das 16h terminar, e usar o resultado das
    16h para prever as 18h seria vazamento (ver
    :func:`futebol.modelos.base.jogos_ate`).

    A tabela da liga vem **inteira**, e não só a janela: ela é o histórico de
    treino. As datas são só as da janela pedida.

    ⚠️ O recorte por liga é feito **uma vez** por competição, de propósito.
    Filtrar a tabela dentro do laço de datas custaria uma varredura dos 116 mil
    jogos a cada rodada — onze mil varreduras, e o walk-forward deixaria de ser
    viável. É o tipo de detalhe que não muda nenhum número e muda se a fase
    existe ou não.

    Args:
        jogos: a tabela.
        inicio: primeira data avaliada. ``None`` = desde o começo da tabela.
        fim: limite superior, **exclusivo**. ``None`` = até o fim da tabela.
    """
    for liga, do_liga in jogos.groupby("liga", sort=True):
        na_janela = do_liga["data"]
        if inicio is not None:
            na_janela = na_janela.loc[na_janela >= pd.Timestamp(inicio)]
        if fim is not None:
            na_janela = na_janela.loc[na_janela < pd.Timestamp(fim)]
        datas = [pd.Timestamp(data) for data in sorted(na_janela.unique())]
        if datas:
            yield str(liga), do_liga, datas


# ----------------------------------------------------------------------------
# O walk-forward
# ----------------------------------------------------------------------------
def walk_forward(
    jogos: pd.DataFrame,
    construir_modelo: Callable[[], base.Modelo],
    inicio=None,
    fim=None,
    minimo_de_treino: int = MINIMO_DE_TREINO,
    escopo: str = "liga",
    aviso: Callable[[str], None] | None = None,
) -> ResultadoWalkForward:
    """Treina antes de cada rodada e prevê a rodada. O coração da Fase 4.

    Args:
        jogos: a tabela, **já sem** as temporadas de teste final
            (:func:`futebol.avaliacao.divisao.separar`).
        construir_modelo: função que devolve um modelo **novo**, sem treino. É
            uma função e não um modelo porque cada rodada precisa de um ajuste
            do zero; reaproveitar o objeto treinado deixaria o ajuste da rodada
            anterior influenciando a seguinte.
        inicio: primeira data avaliada.
        fim: limite superior, exclusivo.
        minimo_de_treino: jogos de história que a liga precisa ter antes da
            rodada. Abaixo disso a rodada é pulada e contada.
        escopo: ``"liga"`` treina com os jogos daquela competição (rápido, e
            idêntico ao global nos modelos do projeto, que ajustam liga por
            liga); ``"tudo"`` treina com a tabela inteira, necessário para
            variantes que estimam algo global.
        aviso: por onde reportar progresso.

    Retorna:
        Um :class:`ResultadoWalkForward`.
    """
    if escopo not in ("liga", "tudo"):
        raise ValueError(f"escopo deve ser 'liga' ou 'tudo'; veio {escopo!r}.")

    partes: list[pd.DataFrame] = []
    ajustes = rodadas_puladas = jogos_pulados = 0
    ligas_vistas: set[str] = set()

    for liga, do_liga, datas in rodadas(jogos, inicio, fim):
        # O treino do escopo "liga" vê só a competição da vez. Como os modelos do
        # projeto ajustam cada liga separadamente, o resultado é idêntico ao do
        # escopo "tudo" — por uma fração do custo.
        historico = jogos if escopo == "tudo" else do_liga
        ajustes_da_liga = 0

        for data in datas:
            da_rodada = do_liga.loc[do_liga["data"] == data]
            if int((do_liga["data"] < data).sum()) < minimo_de_treino:
                rodadas_puladas += 1
                jogos_pulados += len(da_rodada)
                continue

            modelo = construir_modelo().treinar(historico, ate_data=data)
            ajustes_da_liga += 1
            partes.append(_linhas_de_previsao(modelo, da_rodada, data, liga))

        if ajustes_da_liga:
            ligas_vistas.add(liga)
            ajustes += ajustes_da_liga
            if aviso is not None:
                aviso(f"    {liga}: {ajustes_da_liga} rodadas")

    if not partes:
        raise ValueError(
            "Nenhuma rodada avaliada. Confira a janela pedida e o "
            f"minimo_de_treino ({minimo_de_treino})."
        )

    return ResultadoWalkForward(
        previsoes=pd.concat(partes),
        ajustes=ajustes,
        rodadas_puladas=rodadas_puladas,
        jogos_pulados=jogos_pulados,
        ligas=len(ligas_vistas),
    )


def _linhas_de_previsao(
    modelo: base.Modelo, da_rodada: pd.DataFrame, data: pd.Timestamp, liga: str
) -> pd.DataFrame:
    """As previsões de uma rodada, com o observado e a trilha de auditoria."""
    previsoes = modelo.prever_muitos(da_rodada)
    previsoes["liga"] = liga
    previsoes["grupo"] = da_rodada["grupo"].to_numpy() if "grupo" in da_rodada else "?"
    previsoes["temporada"] = (
        da_rodada["temporada"].to_numpy() if "temporada" in da_rodada else "?"
    )
    previsoes["data"] = data
    # A trilha que o teste de vazamento confere: até onde o treino foi.
    previsoes["treino_ate"] = modelo.ultima_data_de_treino
    previsoes["observado"] = da_rodada["resultado"].map(INDICE_RESULTADO).to_numpy()
    # 0 = over, 1 = under, na ordem das colunas ("over25", "under25"). Se este
    # índice trocar de lado, a nota sai plausível e errada.
    gols = da_rodada["gols_mandante"] + da_rodada["gols_visitante"]
    previsoes["observado_ou"] = np.where(gols >= 3, 0, 1)
    return previsoes


def conferir_sem_vazamento(previsoes: pd.DataFrame) -> None:
    """Confere, linha por linha, que nenhuma previsão viu o próprio jogo.

    Levanta:
        AssertionError: se alguma previsão tiver sido feita por um modelo cujo
            treino alcançou a data da partida.

    Esta função é chamada pelos testes **e** pelo gerador de relatório. A
    duplicação é de propósito: a regra 6 é a única do projeto cuja violação não
    aparece como erro, e sim como um resultado bom demais.
    """
    alcancou = previsoes["treino_ate"] >= previsoes["data"]
    if bool(alcancou.any()):
        exemplo = previsoes.loc[alcancou].iloc[0]
        raise AssertionError(
            f"Vazamento de futuro (regra 6): {int(alcancou.sum())} previsão(ões) "
            f"feitas por modelo treinado até {exemplo['treino_ate']} para jogo de "
            f"{exemplo['data']} na liga {exemplo['liga']}."
        )


# ----------------------------------------------------------------------------
# O mercado, na mesma forma das previsões
# ----------------------------------------------------------------------------
def previsoes_do_mercado(
    jogos: pd.DataFrame, momento: str = "fech", metodo: str = METODO_MARGEM
) -> pd.DataFrame:
    """As odds viram previsões, no mesmo formato das dos modelos.

    Pôr o mercado na mesma forma dos modelos é o que permite medi-lo com o mesmo
    código — e um mercado medido por um caminho diferente do dos modelos seria
    uma comparação sem valor.

    Args:
        jogos: a tabela (a função filtra o que serve).
        momento: ``"fech"`` (fechamento) ou ``"pre"`` (pré-jogo).
        metodo: como tirar a margem. ``power`` é o do projeto (Fase 2).

    Retorna:
        Uma linha por jogo **com as três odds de 1X2 registradas**, índice igual
        ao da tabela de entrada. A coluna de ambos-marcam vem vazia: a fonte não
        traz esse mercado (⚠️ e por isso o mercado nunca aparece na comparação
        de "ambos marcam").

    ⚠️ **Regra 12.** Liga do Grupo 2 só tem odd de fechamento; pedir
    ``momento="pre"`` nelas devolve linha nenhuma, e é assim que tem de ser.
    """
    colunas_1x2 = [f"odd_{momento}_{opcao}" for opcao in CHAVES_1X2]
    colunas_ou = [f"odd_{momento}_over25", f"odd_{momento}_under25"]
    faltando = [c for c in colunas_1x2 + colunas_ou if c not in jogos.columns]
    if faltando:
        raise ValueError(f"A tabela não tem as colunas de odd: {', '.join(faltando)}.")

    odds = jogos[colunas_1x2].to_numpy(dtype=float)
    completas = np.isfinite(odds).all(axis=1)
    usados = jogos.loc[completas]
    if usados.empty:
        return pd.DataFrame(columns=[*base.CHAVES_PREVISAO, "liga", "observado"])

    probabilidades = mercado.remover_margem(odds[completas], metodo)
    previsoes = pd.DataFrame(
        probabilidades, index=usados.index, columns=list(CHAVES_1X2)
    )

    # O Over/Under tem cobertura própria, menor que a do 1X2: onde faltar, a
    # linha fica vazia e a log loss de O/U simplesmente a ignora.
    odds_ou = usados[colunas_ou].to_numpy(dtype=float)
    tem_ou = np.isfinite(odds_ou).all(axis=1)
    previsoes["over25"] = np.nan
    previsoes["under25"] = np.nan
    if tem_ou.any():
        sem_margem = mercado.remover_margem(odds_ou[tem_ou], metodo)
        previsoes.loc[tem_ou, ["over25", "under25"]] = sem_margem

    previsoes["ambos_marcam"] = np.nan
    previsoes["ambos_nao_marcam"] = np.nan
    previsoes["liga"] = usados["liga"].to_numpy()
    previsoes["grupo"] = usados["grupo"].to_numpy()
    previsoes["temporada"] = usados["temporada"].to_numpy()
    previsoes["data"] = usados["data"].to_numpy()
    previsoes["observado"] = usados["resultado"].map(INDICE_RESULTADO).to_numpy()
    gols = usados["gols_mandante"] + usados["gols_visitante"]
    previsoes["observado_ou"] = np.where(gols >= 3, 0, 1)
    return previsoes


# ----------------------------------------------------------------------------
# Medir e comparar
# ----------------------------------------------------------------------------
def perdas_por_jogo(previsoes: pd.DataFrame) -> np.ndarray:
    """``−log(p)`` do resultado que aconteceu, jogo a jogo.

    É a log loss antes de tirar a média, e é o que permite comparar duas
    variantes **emparelhadas**.
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
        acuracia=metricas.acuracia(probabilidades, observado),
        ece=metricas.ece(probabilidades, observado),
        log_loss_ou=metricas.log_loss(
            over_under, previsoes["observado_ou"].to_numpy(dtype=int)
        ),
    )


def comparar(pior: pd.DataFrame, melhor: pd.DataFrame, /) -> Diferenca:
    """Diferença emparelhada de log loss entre duas variantes.

    Args:
        pior: previsões da variante que se espera ser pior.
        melhor: previsões da outra.

    Retorna:
        A :class:`Diferenca`. Positiva quer dizer que ``pior`` de fato teve log
        loss maior.
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


def mesmos_jogos(*conjuntos: pd.DataFrame) -> list[pd.DataFrame]:
    """Recorta todos os conjuntos para os jogos que aparecem em **todos**.

    É a forma honesta de pôr modelo e mercado na mesma tabela: o mercado só
    existe onde há odd, e o modelo pode ter pulado rodadas por histórico curto.
    A interseção é o único conjunto em que a comparação significa algo.
    """
    if not conjuntos:
        return []
    comum = conjuntos[0].index
    for conjunto in conjuntos[1:]:
        comum = comum.intersection(conjunto.index)
    return [conjunto.loc[comum] for conjunto in conjuntos]


def medir_nos_mesmos_jogos(
    previsoes: dict[str, pd.DataFrame],
) -> tuple[list[Medida], dict[str, pd.DataFrame]]:
    """Mede vários conjuntos de previsões na interseção deles.

    Args:
        previsoes: ``{nome: previsões}``.

    Retorna:
        ``(medidas, previsões já recortadas)`` — as previsões voltam para quem
        precisa comparar emparelhado depois.
    """
    nomes = list(previsoes)
    recortados = mesmos_jogos(*(previsoes[nome] for nome in nomes))
    alinhados = dict(zip(nomes, recortados, strict=True))
    return [medir(alinhados[nome], nome) for nome in nomes], alinhados


def por_liga(
    previsoes: dict[str, pd.DataFrame], minimo_de_jogos: int = 100
) -> pd.DataFrame:
    """Uma linha por liga, com a log loss de cada conjunto de previsões.

    Serve à regra 13 (toda tabela diz de quais ligas fala) e à Fase 6: é aqui
    que se vê **onde** o modelo chega perto do mercado, que é o único lugar onde
    pode existir aposta com valor.

    Args:
        previsoes: ``{nome: previsões}``, já recortadas para os mesmos jogos.
        minimo_de_jogos: ligas com menos que isso ficam de fora da tabela, por
            ruído — e o corte é dito no relatório.
    """
    nomes = list(previsoes)
    referencia = previsoes[nomes[0]]
    linhas = []
    for liga, do_liga in referencia.groupby("liga", sort=True):
        if len(do_liga) < minimo_de_jogos:
            continue
        linha: dict[str, object] = {"liga": str(liga), "jogos": len(do_liga)}
        for nome in nomes:
            recorte = previsoes[nome].loc[do_liga.index]
            linha[nome] = medir(recorte, nome).log_loss
        linhas.append(linha)
    return pd.DataFrame(linhas)
