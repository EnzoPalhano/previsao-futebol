"""Força de ataque, força de defesa e o fator casa — o primeiro modelo de verdade.

A ideia, que é de 1982 (Maher) e continua sendo a base de quase tudo em futebol:

1. cada time tem uma **força de ataque** (faz mais ou menos gol que a média da
   liga) e uma **força de defesa** (sofre mais ou menos gol que a média);
2. jogar em casa vale um bônus, o **fator casa**;
3. o número de gols de cada lado é sorteado de uma **Poisson** com média
   ``λ`` (mandante) e ``μ`` (visitante)::

       λ = exp(intercepto + ataque_mandante − defesa_visitante + fator_casa)
       μ = exp(intercepto + ataque_visitante − defesa_mandante)

O ``exp`` está aí para as forças serem multiplicativas e os números não poderem
ficar negativos: ``ataque = +0,30`` quer dizer "faz ``exp(0,30)`` = 1,35 vez a
média da liga", e ``defesa = +0,20`` quer dizer "sofre ``exp(−0,20)`` = 0,82 da
média" — defesa positiva é defesa **boa**. O ``intercepto`` carrega o nível de
gols da liga, e por isso as forças são sempre lidas *em relação à média da
própria liga*.

**Por que a Poisson?** Gol é evento raro, independente-ish, espalhado pelos 90
minutos: é o caso de livro da distribuição de Poisson. O caderno da Fase 2 já
mostrou que ela descreve bem a contagem de gols observada — com uma exceção
conhecida, os placares baixos (0x0, 1x0, 1x1), que é exatamente o que o
Dixon-Coles corrige em :mod:`futebol.modelos.dixon_coles`.

Três decisões deste módulo que mudam o resultado:

**1. Um ajuste por liga, não um ajuste global.** ``ENG:Arsenal`` e
``BRA:Palmeiras`` nunca se enfrentam; forças estimadas juntas seriam
incomparáveis. Cada competição ganha seu próprio intercepto, seu próprio fator
casa e suas próprias forças, e a leitura "ataque acima da média" passa a ter um
significado preciso: acima da média **daquela** competição.

⚠️ A consequência incômoda: um time promovido chega sem histórico *naquela
divisão* — os jogos dele na divisão de baixo estão em outro ajuste. É para esse
caso que existe o encolhimento, logo abaixo.

**2. Encolhimento (*shrinkage*) para a média da liga, por penalização.** As
forças não são estimadas soltas: a verossimilhança é penalizada por um termo
que puxa todo mundo para zero (= a média da liga)::

    penalidade = (m · γ / 2) · Σ (ataque² + defesa²)

com ``γ`` = média de gols por time por jogo da liga e ``m`` =
``jogos_equivalentes`` do ``config.yaml``. O efeito, aproximado mas fiel, é um
peso do tipo::

    força estimada ≈ (n / (n + m)) · força que os jogos do time pediriam

onde ``n`` são os jogos do time (somados **pelos pesos**, quando há decaimento
temporal). Ou seja: ``m`` é quantos jogos de história a média da liga vale. Com
``m = 6``, um time com 6 jogos fica na metade do caminho entre "média da liga"
e "o que os 6 jogos dele dizem"; com uma temporada inteira, quase toda a força
é dele. Um time recém-promovido, sem jogo nenhum, é previsto como um time médio
da divisão — que é a resposta honesta quando não se sabe nada.

A penalização também resolve um problema técnico de graça: sem ela o modelo é
**indeterminado** (somar 1 a todos os ataques e 1 ao intercepto dá exatamente
as mesmas previsões). Com ela, a solução é única e as forças saem com média
exatamente zero, o que é o que torna a frase "ataque acima da média" legível.

**3. Máxima verossimilhança, com gradiente escrito à mão.** O ajuste procura os
parâmetros que tornam os placares observados os mais prováveis possíveis. O
gradiente analítico (:func:`_nll_e_gradiente`) existe por um motivo prático: a
Fase 4 vai reajustar o modelo centenas de vezes por liga no walk-forward, e a
diferença entre gradiente analítico e numérico ali é de horas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson as poisson_scipy

from futebol.config import Config
from futebol.modelos import base

#: Tamanho da matriz de placares (0 a 10 gols de cada lado), se nada disser
#: outra coisa. 10 gols é folgado: 11x0 nunca aconteceu na fonte, e a cauda que
#: sobra de fora é redistribuída na normalização.
MAX_GOLS_PADRAO = 10

#: Quantos jogos de história a média da liga vale, no encolhimento. Ver a
#: fórmula no topo do módulo. Provisório na Fase 3 — a escolha por validação é
#: da Fase 4, junto com o ``xi`` do Dixon-Coles.
JOGOS_EQUIVALENTES_PADRAO = 6

#: Teto de iterações do otimizador. Ajustes de liga convergem em muito menos;
#: o teto existe para um caso patológico não travar um walk-forward inteiro.
MAX_ITERACOES = 500

#: Limites dos parâmetros. Servem de cinto de segurança: uma liga com dados
#: estranhos não pode produzir um ataque de ``exp(20)``.
LIMITE_FORCA = 3.0
LIMITE_INTERCEPTO = 5.0
LIMITE_FATOR_CASA = 1.5


# ----------------------------------------------------------------------------
# O gancho do Dixon-Coles
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class ContribuicaoDaCorrecao:
    """O que uma correção de placares acrescenta à verossimilhança.

    Todas as derivadas são **em relação ao logaritmo** das médias (``log λ`` e
    ``log μ``), porque é assim que os parâmetros entram no modelo: somando
    dentro do ``exp``. Isso deixa a regra da cadeia do ajuste trivial.

    Atributos:
        log_ajuste: ``log τ`` de cada jogo — o quanto a correção aumenta (ou
            diminui) a probabilidade daquele placar.
        derivada_log_lambda: ``∂ log τ / ∂ log λ``, por jogo.
        derivada_log_mu: ``∂ log τ / ∂ log μ``, por jogo.
        derivada_parametros: matriz ``(parâmetros, jogos)`` com
            ``∂ log τ / ∂ parâmetro``.
    """

    log_ajuste: np.ndarray
    derivada_log_lambda: np.ndarray
    derivada_log_mu: np.ndarray
    derivada_parametros: np.ndarray


class CorrecaoDePlacares(Protocol):
    """Gancho para quem quiser mexer na probabilidade de certos placares.

    Existe para o Dixon-Coles poder acrescentar a correção de placares baixos
    **sem** que este módulo saiba o que é essa correção. Quem implementa é
    :class:`futebol.modelos.dixon_coles.CorrecaoPlacaresBaixos`; aqui só está a
    forma do encaixe.

    A inversão é de propósito: o motor de ajuste é a parte difícil e testada, e
    ela não deveria mudar para um modelo novo aparecer.
    """

    #: Nomes dos parâmetros extras, na ordem em que entram no vetor.
    nomes: tuple[str, ...]

    def iniciais(self) -> np.ndarray:
        """Valor inicial de cada parâmetro extra."""
        ...

    def limites(self) -> list[tuple[float, float]]:
        """``(mínimo, máximo)`` de cada parâmetro extra."""
        ...

    def avaliar(
        self,
        gols_mandante: np.ndarray,
        gols_visitante: np.ndarray,
        media_mandante: np.ndarray,
        media_visitante: np.ndarray,
        parametros: np.ndarray,
    ) -> ContribuicaoDaCorrecao:
        """A contribuição da correção e suas derivadas, jogo a jogo."""
        ...


# ----------------------------------------------------------------------------
# O resultado de um ajuste
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class ForcaDoTime:
    """A força de um time, do jeito que o modelo a enxerga.

    Atributos:
        ataque: em log. ``+0,30`` = faz ``exp(0,30)`` = 1,35 vez a média da liga.
        defesa: em log, com sinal invertido — **positivo é defesa boa**.
            ``+0,20`` = sofre ``exp(−0,20)`` = 0,82 da média da liga.
        jogos: quantos jogos do time entraram no ajuste.
        peso: os mesmos jogos somados pelos pesos do decaimento temporal.
            Sem decaimento, é igual a ``jogos``. É este número que manda no
            encolhimento.
    """

    ataque: float
    defesa: float
    jogos: int
    peso: float


@dataclass(frozen=True)
class AjusteLiga:
    """Os parâmetros ajustados de uma liga.

    Atributos:
        liga: o código da liga.
        intercepto: o nível de gols da liga, em log.
        fator_casa: o bônus de jogar em casa, em log. ``0,25`` quer dizer que o
            mandante faz ``exp(0,25)`` = 1,28 vez o que faria fora.
        forcas: ``{time: ForcaDoTime}``.
        extras: parâmetros da correção de placares (vazio no Poisson puro).
        jogos: quantos jogos entraram.
        peso_total: a soma dos pesos (com decaimento, menor que ``jogos``).
        jogos_equivalentes: o ``m`` do encolhimento usado neste ajuste.
        convergiu: se o otimizador terminou satisfeito.
        mensagem: o que o otimizador disse.
        log_verossimilhanca: a verossimilhança no ótimo, sem a penalização.
    """

    liga: str
    intercepto: float
    fator_casa: float
    forcas: dict[str, ForcaDoTime]
    extras: dict[str, float]
    jogos: int
    peso_total: float
    jogos_equivalentes: float
    convergiu: bool
    mensagem: str
    log_verossimilhanca: float

    def forca(self, time: str) -> ForcaDoTime:
        """A força de um time; time desconhecido vira um time médio da liga.

        Devolver a média em vez de levantar erro é decisão de projeto: no app,
        pedir um time que acabou de subir é normal, e "um time médio desta
        divisão" é a resposta honesta para quem não tem histórico ali.
        """
        return self.forcas.get(time, ForcaDoTime(0.0, 0.0, 0, 0.0))

    def medias(self, mandante: str, visitante: str) -> tuple[float, float]:
        """``(λ, μ)``: os gols esperados de cada lado."""
        casa = self.forca(mandante)
        fora = self.forca(visitante)
        lam = np.exp(self.intercepto + casa.ataque - fora.defesa + self.fator_casa)
        mu = np.exp(self.intercepto + fora.ataque - casa.defesa)
        return float(lam), float(mu)

    def tabela_de_forcas(self) -> pd.DataFrame:
        """Uma linha por time, ordenada da melhor para a pior força total.

        A coluna ``forca_total`` (ataque + defesa) é só para ordenar e conversar:
        o modelo nunca a usa, porque ataque e defesa entram em contas diferentes.
        """
        linhas = [
            {
                "time": time,
                "ataque": forca.ataque,
                "defesa": forca.defesa,
                "forca_total": forca.ataque + forca.defesa,
                "jogos": forca.jogos,
                "peso": forca.peso,
                "peso_proprio": forca.peso / (forca.peso + self.jogos_equivalentes),
            }
            for time, forca in self.forcas.items()
        ]
        tabela = pd.DataFrame(linhas)
        return tabela.sort_values("forca_total", ascending=False).reset_index(drop=True)


# ----------------------------------------------------------------------------
# A matriz de placares
# ----------------------------------------------------------------------------
def matriz_poisson(lam: float, mu: float, max_gols: int = MAX_GOLS_PADRAO) -> np.ndarray:
    """A matriz de placares de duas Poisson independentes.

    ``matriz[i, j] = P(mandante faz i) · P(visitante faz j)``.

    A independência entre os dois lados é a hipótese mais frágil do modelo — na
    prática, um time que está perdendo se expõe mais e o jogo abre. É justamente
    essa falha que o Dixon-Coles remenda nos placares baixos.
    """
    if not (np.isfinite(lam) and np.isfinite(mu)) or lam <= 0 or mu <= 0:
        raise base.ErroDeModelo(
            f"Médias de gols inválidas para a matriz de placares: λ={lam}, μ={mu}."
        )
    gols = np.arange(max_gols + 1)
    do_mandante = poisson_scipy.pmf(gols, lam)
    do_visitante = poisson_scipy.pmf(gols, mu)
    return base.normalizar_matriz(np.outer(do_mandante, do_visitante))


# ----------------------------------------------------------------------------
# O fator casa medido no conjunto todo
# ----------------------------------------------------------------------------
def fator_casa_global(jogos: pd.DataFrame) -> float:
    """O fator casa de todas as ligas juntas, em uma conta fechada.

    ``log(média de gols do mandante / média de gols do visitante)``.

    Esta é a versão "fator casa constante" do experimento pedido na Fase 3: um
    número só, o mesmo para as 38 competições. Ele é usado como valor fixo para
    comparar com a versão em que cada liga estima o seu — e a comparação está em
    ``docs/relatorios/fase3.md``.

    A conta é o que o próprio modelo diria se todos os times fossem iguais:
    com ataque e defesa zerados, ``λ/μ = exp(fator casa)``.
    """
    media_mandante = float(jogos["gols_mandante"].mean())
    media_visitante = float(jogos["gols_visitante"].mean())
    if media_mandante <= 0 or media_visitante <= 0:
        raise base.ErroDeModelo(
            "Não dá para medir o fator casa: um dos lados não fez nenhum gol "
            "em toda a amostra."
        )
    return float(np.log(media_mandante / media_visitante))


# ----------------------------------------------------------------------------
# O ajuste de uma liga
# ----------------------------------------------------------------------------
def _indices_dos_times(jogos: pd.DataFrame) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Numera os times da liga e traduz cada jogo para esses números."""
    times = pd.Index(
        sorted(set(jogos["mandante"]).union(jogos["visitante"])), name="time"
    )
    mandante = times.get_indexer(jogos["mandante"])
    visitante = times.get_indexer(jogos["visitante"])
    return list(times), mandante, visitante


def _nll_e_gradiente(
    parametros: np.ndarray,
    gols_mandante: np.ndarray,
    gols_visitante: np.ndarray,
    indice_mandante: np.ndarray,
    indice_visitante: np.ndarray,
    pesos: np.ndarray,
    n_times: int,
    penalidade: float,
    correcao: CorrecaoDePlacares | None,
) -> tuple[float, np.ndarray]:
    """A verossimilhança negativa penalizada e o gradiente dela.

    O vetor de parâmetros é sempre ``[intercepto, fator_casa, ataque(n_times),
    defesa(n_times), extras...]``.

    O gradiente é analítico. A conta toda se reduz a duas quantidades por jogo —
    quanto de gol o modelo previu a mais do que aconteceu, de cada lado::

        resto_mandante = peso · (λ − gols do mandante)
        resto_visitante = peso · (μ − gols do visitante)

    e a derivada em relação à força de um time é só a soma dos restos dos jogos
    em que ele apareceu naquele papel. ``np.bincount`` faz essas somas de uma
    vez. Nada aqui é esperto; é só a conta escrita com cuidado.
    """
    intercepto = parametros[0]
    casa = parametros[1]
    ataque = parametros[2 : 2 + n_times]
    defesa = parametros[2 + n_times : 2 + 2 * n_times]
    extras = parametros[2 + 2 * n_times :]

    log_lambda = intercepto + ataque[indice_mandante] - defesa[indice_visitante] + casa
    log_mu = intercepto + ataque[indice_visitante] - defesa[indice_mandante]
    lam = np.exp(log_lambda)
    mu = np.exp(log_mu)

    # Verossimilhança de Poisson sem o log(k!), que é constante e não muda o
    # ótimo. Por isso este número serve para comparar ajustes do MESMO conjunto
    # de jogos, e não para comparar conjuntos diferentes.
    log_verossimilhanca = np.sum(
        pesos * (gols_mandante * log_lambda - lam + gols_visitante * log_mu - mu)
    )

    resto_mandante = pesos * (lam - gols_mandante)
    resto_visitante = pesos * (mu - gols_visitante)
    gradiente_extras = np.zeros_like(extras)

    if correcao is not None:
        contribuicao = correcao.avaliar(
            gols_mandante, gols_visitante, lam, mu, extras
        )
        log_verossimilhanca += np.sum(pesos * contribuicao.log_ajuste)
        resto_mandante = resto_mandante - pesos * contribuicao.derivada_log_lambda
        resto_visitante = resto_visitante - pesos * contribuicao.derivada_log_mu
        gradiente_extras = -(contribuicao.derivada_parametros * pesos).sum(axis=1)

    nll = -log_verossimilhanca + 0.5 * penalidade * float(
        np.sum(ataque**2) + np.sum(defesa**2)
    )

    como_mandante = np.bincount(indice_mandante, resto_mandante, minlength=n_times)
    como_visitante = np.bincount(indice_visitante, resto_visitante, minlength=n_times)
    sofridos_em_casa = np.bincount(indice_mandante, resto_visitante, minlength=n_times)
    sofridos_fora = np.bincount(indice_visitante, resto_mandante, minlength=n_times)

    gradiente = np.concatenate(
        [
            [resto_mandante.sum() + resto_visitante.sum()],  # intercepto
            [resto_mandante.sum()],  # fator casa: só o lado do mandante
            como_mandante + como_visitante + penalidade * ataque,
            -(sofridos_fora + sofridos_em_casa) + penalidade * defesa,
            gradiente_extras,
        ]
    )
    return float(nll), gradiente


def ajustar_liga(
    jogos: pd.DataFrame,
    liga: str = "?",
    *,
    pesos: np.ndarray | None = None,
    jogos_equivalentes: float = JOGOS_EQUIVALENTES_PADRAO,
    fator_casa_fixo: float | None = None,
    correcao: CorrecaoDePlacares | None = None,
    max_iteracoes: int = MAX_ITERACOES,
) -> AjusteLiga:
    """Estima intercepto, fator casa e as forças de todos os times de uma liga.

    Args:
        jogos: os jogos **de uma liga só**, já filtrados por data.
        liga: o código da liga, só para o resultado se identificar.
        pesos: peso de cada jogo (decaimento temporal). ``None`` = todos valem 1.
        jogos_equivalentes: o ``m`` do encolhimento. Quanto maior, mais as
            forças ficam coladas na média da liga.
        fator_casa_fixo: se dado, o fator casa não é estimado, e sim mantido
            neste valor. É como se roda a versão "fator casa constante" do
            experimento da Fase 3.
        correcao: gancho do Dixon-Coles. ``None`` = Poisson puro.
        max_iteracoes: teto do otimizador.

    Retorna:
        Um :class:`AjusteLiga`.
    """
    if jogos.empty:
        raise base.ErroDeModelo(f"Liga {liga!r} não tem jogo nenhum para ajustar.")

    times, indice_mandante, indice_visitante = _indices_dos_times(jogos)
    n_times = len(times)
    gols_mandante = jogos["gols_mandante"].to_numpy(dtype=float)
    gols_visitante = jogos["gols_visitante"].to_numpy(dtype=float)
    pesos = (
        np.ones(len(jogos))
        if pesos is None
        else np.asarray(pesos, dtype=float)
    )
    if len(pesos) != len(jogos):
        raise base.ErroDeModelo(
            f"{len(pesos)} peso(s) para {len(jogos)} jogo(s) na liga {liga!r}."
        )

    # γ: gols por time por jogo. Entra na força da penalização para que o
    # encolhimento signifique "m jogos", e não "m unidades de log-gol".
    media_de_gols = float(
        np.average(
            np.concatenate([gols_mandante, gols_visitante]),
            weights=np.concatenate([pesos, pesos]),
        )
    )
    penalidade = float(jogos_equivalentes) * max(media_de_gols, 1e-6)

    # Chute inicial: liga sem nenhuma diferença entre times. O intercepto sai
    # da média de gols do visitante, e o fator casa da razão casa/fora — já
    # perto do ótimo, o que economiza iterações.
    media_visitante = float(np.average(gols_visitante, weights=pesos))
    media_mandante = float(np.average(gols_mandante, weights=pesos))
    intercepto_inicial = float(np.log(max(media_visitante, 1e-3)))
    casa_inicial = (
        float(fator_casa_fixo)
        if fator_casa_fixo is not None
        else float(np.log(max(media_mandante, 1e-3) / max(media_visitante, 1e-3)))
    )

    iniciais = [intercepto_inicial, casa_inicial]
    limites: list[tuple[float, float]] = [
        (-LIMITE_INTERCEPTO, LIMITE_INTERCEPTO),
        # Limite inferior igual ao superior é como o L-BFGS-B congela um
        # parâmetro: mais simples e menos sujeito a erro que montar dois
        # vetores de parâmetros diferentes.
        (casa_inicial, casa_inicial)
        if fator_casa_fixo is not None
        else (-LIMITE_FATOR_CASA, LIMITE_FATOR_CASA),
    ]
    iniciais += [0.0] * (2 * n_times)
    limites += [(-LIMITE_FORCA, LIMITE_FORCA)] * (2 * n_times)
    if correcao is not None:
        iniciais += list(correcao.iniciais())
        limites += list(correcao.limites())

    resultado = minimize(
        _nll_e_gradiente,
        x0=np.array(iniciais, dtype=float),
        args=(
            gols_mandante,
            gols_visitante,
            indice_mandante,
            indice_visitante,
            pesos,
            n_times,
            penalidade,
            correcao,
        ),
        jac=True,
        method="L-BFGS-B",
        bounds=limites,
        options={"maxiter": max_iteracoes},
    )

    ajustados = resultado.x
    ataque = ajustados[2 : 2 + n_times]
    defesa = ajustados[2 + n_times : 2 + 2 * n_times]
    extras = ajustados[2 + 2 * n_times :]

    jogos_por_time = np.bincount(indice_mandante, minlength=n_times) + np.bincount(
        indice_visitante, minlength=n_times
    )
    peso_por_time = np.bincount(
        indice_mandante, pesos, minlength=n_times
    ) + np.bincount(indice_visitante, pesos, minlength=n_times)

    nomes_extras = correcao.nomes if correcao is not None else ()
    return AjusteLiga(
        liga=liga,
        intercepto=float(ajustados[0]),
        fator_casa=float(ajustados[1]),
        forcas={
            time: ForcaDoTime(
                ataque=float(ataque[i]),
                defesa=float(defesa[i]),
                jogos=int(jogos_por_time[i]),
                peso=float(peso_por_time[i]),
            )
            for i, time in enumerate(times)
        },
        extras=dict(zip(nomes_extras, (float(v) for v in extras), strict=True)),
        jogos=len(jogos),
        peso_total=float(pesos.sum()),
        jogos_equivalentes=float(jogos_equivalentes),
        convergiu=bool(resultado.success),
        mensagem=str(resultado.message),
        # O sinal volta ao natural, e a penalização sai: o número reportado é a
        # verossimilhança dos dados, não o valor da função que foi minimizada.
        log_verossimilhanca=-float(resultado.fun)
        + 0.5 * penalidade * float(np.sum(ataque**2) + np.sum(defesa**2)),
    )


# ----------------------------------------------------------------------------
# O modelo
# ----------------------------------------------------------------------------
class Poisson(base.Modelo):
    """Poisson com força de ataque, força de defesa e fator casa por liga.

    Uso::

        modelo = Poisson(cfg=cfg).treinar(jogos, ate_data="2024-08-01")
        modelo.prever(Jogo("E0", "ENG:Arsenal", "ENG:Chelsea"))

    Args:
        cfg: configuração do projeto, de onde saem ``max_gols`` e
            ``jogos_equivalentes``. Pode ser omitida nos testes.
        max_gols: tamanho da matriz de placares.
        jogos_equivalentes: o ``m`` do encolhimento.
        fator_casa: ``"por_liga"`` (cada liga estima o seu) ou ``"global"``
            (um número só, medido em todas as ligas juntas e congelado). É o
            experimento pedido na Fase 3. Omitido, vem do ``config.yaml``.
    """

    nome = "poisson"

    def __init__(
        self,
        cfg: Config | None = None,
        max_gols: int | None = None,
        jogos_equivalentes: float | None = None,
        fator_casa: str | None = None,
    ) -> None:
        super().__init__()
        secao = cfg.secao("modelos") if cfg is not None else {}
        self.max_gols = int(
            max_gols
            if max_gols is not None
            else secao.get("poisson", {}).get("max_gols", MAX_GOLS_PADRAO)
        )
        self.jogos_equivalentes = float(
            jogos_equivalentes
            if jogos_equivalentes is not None
            else secao.get("shrinkage", {}).get(
                "jogos_equivalentes", JOGOS_EQUIVALENTES_PADRAO
            )
        )
        fator_casa = (
            fator_casa
            if fator_casa is not None
            else secao.get("poisson", {}).get("fator_casa", "por_liga")
        )
        if fator_casa not in ("por_liga", "global"):
            raise base.ErroDeModelo(
                f"fator_casa deve ser 'por_liga' ou 'global'; veio {fator_casa!r}."
            )
        self.modo_fator_casa = fator_casa
        #: Um ajuste por liga, preenchido no treino.
        self.ajustes: dict[str, AjusteLiga] = {}
        #: O fator casa medido no conjunto todo (só no modo ``"global"``).
        self.fator_casa_medido: float | None = None

    # -- treino ------------------------------------------------------------
    def _ajustar(self, jogos: pd.DataFrame) -> None:
        self.fator_casa_medido = (
            fator_casa_global(jogos) if self.modo_fator_casa == "global" else None
        )
        self.ajustes = {
            str(liga): ajustar_liga(
                da_liga,
                liga=str(liga),
                pesos=self._pesos(da_liga),
                jogos_equivalentes=self.jogos_equivalentes,
                fator_casa_fixo=self.fator_casa_medido,
                correcao=self._correcao(),
            )
            for liga, da_liga in jogos.groupby("liga", sort=True)
        }

    def _pesos(self, jogos: pd.DataFrame) -> np.ndarray | None:
        """Peso de cada jogo. No Poisson puro, todos valem igual.

        O Dixon-Coles sobrescreve este método para fazer jogo antigo pesar
        menos — é o único ponto em que os dois modelos diferem no treino.
        """
        return None

    def _correcao(self) -> CorrecaoDePlacares | None:
        """Correção de placares baixos. ``None`` aqui; o Dixon-Coles troca."""
        return None

    # -- previsão ----------------------------------------------------------
    def ajuste_da_liga(self, liga: str) -> AjusteLiga:
        """O ajuste de uma liga, ou um erro que diz quais ligas existem."""
        self._exigir_treinado()
        if liga not in self.ajustes:
            disponiveis = ", ".join(sorted(self.ajustes))
            raise base.ErroDeModelo(
                f"A liga {liga!r} não estava no treino. Ligas ajustadas: {disponiveis}."
            )
        return self.ajustes[liga]

    def medias(self, jogo: base.Jogo) -> tuple[float, float]:
        """``(λ, μ)`` do jogo: os gols esperados de cada lado."""
        return self.ajuste_da_liga(jogo.liga).medias(jogo.mandante, jogo.visitante)

    def matriz_de_placares(self, jogo: base.Jogo) -> np.ndarray:
        lam, mu = self.medias(jogo)
        return matriz_poisson(lam, mu, self.max_gols)

    # -- para relatório ----------------------------------------------------
    def resumo(self) -> pd.DataFrame:
        """Uma linha por liga: gols esperados, fator casa e se convergiu."""
        self._exigir_treinado()
        linhas = [
            {
                "liga": ajuste.liga,
                "jogos": ajuste.jogos,
                "times": len(ajuste.forcas),
                "gols_medios": float(np.exp(ajuste.intercepto)),
                "fator_casa": ajuste.fator_casa,
                "vantagem_casa": float(np.exp(ajuste.fator_casa)),
                "convergiu": ajuste.convergiu,
                **{f"extra_{k}": v for k, v in ajuste.extras.items()},
            }
            for ajuste in self.ajustes.values()
        ]
        return pd.DataFrame(linhas)
