"""Dixon-Coles: dois remendos no Poisson, e os dois importam para apostar.

O Poisson de :mod:`futebol.modelos.poisson` tem duas falhas conhecidas, e o
artigo de Dixon e Coles (1997) conserta exatamente essas duas.

**Falha 1 — os placares baixos não são independentes.**

O Poisson trata os gols dos dois lados como sorteios separados. Não são: 0x0,
1x0, 0x1 e 1x1 acontecem com frequência diferente da que a independência prevê.
0x0 e 1x1 acontecem **mais**; 1x0 e 0x1, **menos**. Faz sentido de assistir
futebol: num jogo travado os dois times seguem travados, e num 1x1 tardio ambos
param de arriscar. A correção multiplica só essas quatro casas da matriz::

    τ(0,0) = 1 − λ·μ·ρ        τ(0,1) = 1 + λ·ρ
    τ(1,0) = 1 + μ·ρ          τ(1,1) = 1 − ρ

com ``ρ`` estimado junto com o resto. ``ρ`` negativo (o caso real, algo entre
−0,02 e −0,12) empurra probabilidade **para** 0x0 e 1x1 e **tira** de 1x0 e 0x1.

O detalhe elegante do artigo: as quatro correções se cancelam exatamente, então
a matriz continua somando 1 sem precisar de conserto. Isso dá um teste bonito e
forte — se a soma mudar, a fórmula está errada.

⚠️ E isso mexe justamente no mercado que o projeto aposta: 0x0 e 1x1 são
empates, e 1x0/0x1 não. A correção mexe direto na probabilidade de empate, que
é onde o Poisson puro erra mais e onde as odds de empate são mais gordas.

**Falha 2 — o Poisson acha que 2019 e o mês passado valem o mesmo.**

O Chelsea de cinco anos atrás não diz quase nada sobre o Chelsea de hoje, e
mesmo assim o ajuste do Poisson dá a ele o mesmo peso. O Dixon-Coles resolve
com **decaimento exponencial**: cada jogo entra na verossimilhança com peso::

    peso = exp(−ξ · dias desde o jogo)

``ξ`` (xi) controla a memória do modelo. É mais fácil pensar em **meia-vida**,
que é ``ln(2)/ξ``: com ``ξ = 0,0018``, um jogo de 385 dias atrás vale metade de
um jogo de hoje, e um de três anos atrás vale 14%.

⚠️ **O ``ξ`` é escolhido por validação, nunca chutado (regra 9).** O valor que
está no ``config.yaml`` é um ponto de partida da Fase 3; quem escolhe é o
walk-forward da Fase 4, por log loss, e nunca olhando o teste final. ``ξ`` alto
demais é um modelo amnésico (joga história fora e fica ruidoso); baixo demais é
um modelo que acha que o time ainda tem o técnico de 2019.

**Efeito de graça: o fator casa deixa de ser constante.** Como o ajuste é
refeito a cada data de previsão e os jogos recentes pesam mais, o fator casa
estimado acompanha o tempo — foi assim que a temporada de estádios vazios de
2020/21 apareceu nos dados da Fase 2. O experimento que compara fator casa por
liga com fator casa único está em ``docs/relatorios/fase3.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from futebol.config import Config
from futebol.modelos import base
from futebol.modelos import poisson as modelo_poisson

#: Decaimento por dia, se nada disser outra coisa. Meia-vida de ~385 dias.
#: PROVISÓRIO: a escolha é do walk-forward da Fase 4 (regra 9).
XI_PADRAO = 0.0018

#: Chute inicial do ``rho``. Perto do que a literatura encontra, para o
#: otimizador partir de um lugar razoável.
RHO_INICIAL = -0.03

#: Limite de ``|rho|``. Não é estético: a correção pode empurrar τ para baixo
#: de zero — com λ = 5 gols esperados, ``1 + λρ`` já seria negativo em
#: ρ = −0,20, e probabilidade negativa não existe. 0,15 deixa folga sobre todo
#: valor que a literatura reporta (−0,02 a −0,13); se alguma liga encostar no
#: limite, isso aparece no relatório em vez de virar erro silencioso.
LIMITE_RHO = 0.15

#: Piso de τ na verossimilhança, para o logaritmo nunca ver zero.
PISO_TAU = 1e-10


# ----------------------------------------------------------------------------
# A correção de placares baixos
# ----------------------------------------------------------------------------
def tau(
    gols_mandante: np.ndarray,
    gols_visitante: np.ndarray,
    media_mandante: np.ndarray,
    media_visitante: np.ndarray,
    rho: float,
) -> np.ndarray:
    """O fator que multiplica a probabilidade de cada placar.

    Vale 1 em todo placar que não seja 0x0, 1x0, 0x1 ou 1x1 — ou seja, o
    Dixon-Coles não mexe em nada além dos placares baixos.
    """
    gols_mandante = np.asarray(gols_mandante)
    gols_visitante = np.asarray(gols_visitante)
    fator = np.ones(np.broadcast(gols_mandante, gols_visitante).shape, dtype=float)

    zero_zero = (gols_mandante == 0) & (gols_visitante == 0)
    zero_um = (gols_mandante == 0) & (gols_visitante == 1)
    um_zero = (gols_mandante == 1) & (gols_visitante == 0)
    um_um = (gols_mandante == 1) & (gols_visitante == 1)

    lam, mu = np.broadcast_arrays(
        np.asarray(media_mandante, dtype=float),
        np.asarray(media_visitante, dtype=float),
    )
    fator = np.where(zero_zero, 1.0 - lam * mu * rho, fator)
    fator = np.where(zero_um, 1.0 + lam * rho, fator)
    fator = np.where(um_zero, 1.0 + mu * rho, fator)
    fator = np.where(um_um, 1.0 - rho, fator)
    return fator


def aplicar_na_matriz(matriz: np.ndarray, lam: float, mu: float, rho: float) -> np.ndarray:
    """Aplica a correção nas quatro casas de placar baixo da matriz.

    A matriz devolvida ainda soma 1 (a menos da cauda cortada em 10 gols),
    porque as quatro correções se cancelam entre si — é o que o teste
    ``test_a_correcao_nao_muda_a_soma`` confere.
    """
    corrigida = np.array(matriz, dtype=float, copy=True)
    corrigida[0, 0] *= 1.0 - lam * mu * rho
    corrigida[0, 1] *= 1.0 + lam * rho
    corrigida[1, 0] *= 1.0 + mu * rho
    corrigida[1, 1] *= 1.0 - rho
    return corrigida


@dataclass(frozen=True)
class CorrecaoPlacaresBaixos:
    """A correção de placares baixos, no formato que o ajuste do Poisson aceita.

    Implementa o protocolo
    :class:`futebol.modelos.poisson.CorrecaoDePlacares`: o motor de máxima
    verossimilhança não sabe o que é Dixon-Coles, só sabe pedir "o quanto você
    acrescenta à verossimilhança e quais são as suas derivadas".

    O único parâmetro extra é o ``rho``.
    """

    nomes: tuple[str, ...] = ("rho",)
    rho_inicial: float = RHO_INICIAL
    limite: float = LIMITE_RHO

    def iniciais(self) -> np.ndarray:
        return np.array([self.rho_inicial], dtype=float)

    def limites(self) -> list[tuple[float, float]]:
        return [(-self.limite, self.limite)]

    def avaliar(
        self,
        gols_mandante: np.ndarray,
        gols_visitante: np.ndarray,
        media_mandante: np.ndarray,
        media_visitante: np.ndarray,
        parametros: np.ndarray,
    ) -> modelo_poisson.ContribuicaoDaCorrecao:
        """``log τ`` e suas derivadas, jogo a jogo.

        As derivadas em relação a ``log λ`` e ``log μ`` saem da regra da cadeia
        com ``∂λ/∂(log λ) = λ``, que é o motivo de o modelo todo viver no
        logaritmo: a derivada de cada parâmetro é a mesma conta, sem fatores
        extras espalhados.
        """
        rho = float(parametros[0])
        lam = np.asarray(media_mandante, dtype=float)
        mu = np.asarray(media_visitante, dtype=float)

        fator = np.clip(
            tau(gols_mandante, gols_visitante, lam, mu, rho), PISO_TAU, None
        )

        zero_zero = (gols_mandante == 0) & (gols_visitante == 0)
        zero_um = (gols_mandante == 0) & (gols_visitante == 1)
        um_zero = (gols_mandante == 1) & (gols_visitante == 0)
        um_um = (gols_mandante == 1) & (gols_visitante == 1)

        # ∂τ/∂λ · λ, casa por casa (zero onde τ não depende de λ).
        derivada_lambda = np.zeros_like(fator)
        derivada_lambda = np.where(zero_zero, -lam * mu * rho, derivada_lambda)
        derivada_lambda = np.where(zero_um, lam * rho, derivada_lambda)

        derivada_mu = np.zeros_like(fator)
        derivada_mu = np.where(zero_zero, -lam * mu * rho, derivada_mu)
        derivada_mu = np.where(um_zero, mu * rho, derivada_mu)

        derivada_rho = np.zeros_like(fator)
        derivada_rho = np.where(zero_zero, -lam * mu, derivada_rho)
        derivada_rho = np.where(zero_um, lam, derivada_rho)
        derivada_rho = np.where(um_zero, mu, derivada_rho)
        derivada_rho = np.where(um_um, -1.0, derivada_rho)

        return modelo_poisson.ContribuicaoDaCorrecao(
            log_ajuste=np.log(fator),
            derivada_log_lambda=derivada_lambda / fator,
            derivada_log_mu=derivada_mu / fator,
            derivada_parametros=(derivada_rho / fator)[None, :],
        )


# ----------------------------------------------------------------------------
# O decaimento temporal
# ----------------------------------------------------------------------------
def pesos_por_decaimento(
    datas: pd.Series, referencia: pd.Timestamp, xi: float
) -> np.ndarray:
    """``exp(−ξ · dias)``: quanto cada jogo ainda conta.

    Args:
        datas: a data de cada jogo.
        referencia: a "data de hoje" do modelo. Jogo nela vale 1.
        xi: decaimento por dia. ``0`` devolve peso 1 para tudo — o que torna o
            Dixon-Coles um Poisson com correção de placares baixos, e é assim
            que o teste separa um efeito do outro.

    Jogo com data **posterior** à referência receberia peso maior que 1, o que
    seria o sintoma de um vazamento de futuro. Isso não deveria acontecer (o
    corte de :func:`futebol.modelos.base.jogos_ate` vem antes), e por isso aqui
    é erro, não aviso.
    """
    if xi < 0:
        raise base.ErroDeModelo(f"O decaimento xi não pode ser negativo (veio {xi}).")
    dias = (pd.Timestamp(referencia) - pd.to_datetime(datas)).dt.days.to_numpy(
        dtype=float
    )
    if (dias < 0).any():
        raise base.ErroDeModelo(
            "Há jogo com data posterior à data de referência do decaimento. "
            "Isso é vazamento de futuro (regra 6) — confira o corte de treino."
        )
    return np.exp(-float(xi) * dias)


def meia_vida(xi: float) -> float:
    """Em quantos dias um jogo passa a valer metade. ``ln(2)/ξ``.

    É a forma legível do ``ξ``: "meia-vida de 385 dias" diz algo; "ξ = 0,0018"
    não diz nada para ninguém.
    """
    if xi <= 0:
        return float("inf")
    return float(np.log(2.0) / xi)


# ----------------------------------------------------------------------------
# O modelo
# ----------------------------------------------------------------------------
class DixonColes(modelo_poisson.Poisson):
    """Poisson + correção de placares baixos + decaimento temporal.

    Herda todo o ajuste do :class:`~futebol.modelos.poisson.Poisson` e troca
    exatamente dois ganchos: o peso de cada jogo e a correção de placares. Essa
    é a razão de os dois ganchos existirem — a diferença entre os dois modelos
    fica em quinze linhas, e o que é comum é literalmente o mesmo código.

    Args:
        cfg: configuração do projeto (seção ``modelos.dixon_coles``).
        max_gols: tamanho da matriz de placares.
        xi: decaimento por dia. ``0`` desliga o decaimento.
        jogos_equivalentes: o ``m`` do encolhimento.
        fator_casa: ``"por_liga"`` ou ``"global"``.
    """

    nome = "dixon_coles"

    def __init__(
        self,
        cfg: Config | None = None,
        max_gols: int | None = None,
        xi: float | None = None,
        jogos_equivalentes: float | None = None,
        fator_casa: str | None = None,
    ) -> None:
        secao = cfg.secao("modelos") if cfg is not None else {}
        do_config = secao.get("dixon_coles", {})
        super().__init__(
            cfg=cfg,
            max_gols=max_gols if max_gols is not None else do_config.get("max_gols"),
            jogos_equivalentes=jogos_equivalentes,
            fator_casa=fator_casa,
        )
        self.xi = float(xi if xi is not None else do_config.get("xi", XI_PADRAO))
        if self.xi < 0:
            raise base.ErroDeModelo(f"O decaimento xi não pode ser negativo: {self.xi}.")
        #: A data de onde o decaimento conta para trás, definida no treino.
        self.referencia_do_decaimento: pd.Timestamp | None = None

    @property
    def meia_vida_em_dias(self) -> float:
        """Em quantos dias um jogo passa a valer metade."""
        return meia_vida(self.xi)

    # -- os dois ganchos ---------------------------------------------------
    def _ajustar(self, jogos: pd.DataFrame) -> None:
        # A referência é a data da previsão (o `ate_data` do treino), e não a
        # do último jogo da liga. A diferença aparece em liga fora de
        # temporada: os jogos dela têm que envelhecer junto com o calendário,
        # e não ficar congelados com peso 1 no último jogo disputado.
        self.referencia_do_decaimento = self.corte_de_treino or pd.Timestamp(
            jogos["data"].max()
        )
        super()._ajustar(jogos)

    def _pesos(self, jogos: pd.DataFrame) -> np.ndarray | None:
        assert self.referencia_do_decaimento is not None  # posto por `_ajustar`
        return pesos_por_decaimento(
            jogos["data"], self.referencia_do_decaimento, self.xi
        )

    def _correcao(self) -> modelo_poisson.CorrecaoDePlacares:
        return CorrecaoPlacaresBaixos()

    # -- previsão ----------------------------------------------------------
    def rho_da_liga(self, liga: str) -> float:
        """O ``rho`` estimado para uma liga."""
        return self.ajuste_da_liga(liga).extras["rho"]

    def matriz_de_placares(self, jogo: base.Jogo) -> np.ndarray:
        lam, mu = self.medias(jogo)
        matriz = modelo_poisson.matriz_poisson(lam, mu, self.max_gols)
        corrigida = aplicar_na_matriz(matriz, lam, mu, self.rho_da_liga(jogo.liga))
        return base.normalizar_matriz(corrigida)

    # -- para relatório ----------------------------------------------------
    def resumo(self) -> pd.DataFrame:
        """O resumo do Poisson, mais o ``rho`` e se ele encostou no limite."""
        tabela = super().resumo()
        tabela = tabela.rename(columns={"extra_rho": "rho"})
        tabela["rho_no_limite"] = np.isclose(
            tabela["rho"].abs(), LIMITE_RHO, atol=1e-4
        )
        tabela["meia_vida_dias"] = self.meia_vida_em_dias
        return tabela
