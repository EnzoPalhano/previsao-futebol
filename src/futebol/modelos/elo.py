"""O rating Elo: uma nota por clube, atualizada jogo a jogo.

O Elo responde a uma pergunta que o Dixon-Coles responde de outro jeito: **quão
forte é este time agora?** A diferença está em *como* a resposta é construída.

- O Dixon-Coles reestima as forças **do zero** a cada rodada, olhando uma janela
  inteira de história com decaimento temporal;
- o Elo carrega um número por clube e o **corrige um pouco a cada jogo**, na
  direção da surpresa: quem ganha de quem não devia ganhar sobe muito; quem
  ganha de quem devia perder sobe pouco.

Nenhum dos dois é "o certo". Eles erram de formas diferentes, e é exatamente por
isso que o Elo entra na Fase 5 como **feature** do LightGBM, e não como um
modelo rival: dar ao GBM duas leituras independentes da mesma realidade é o que
pode fazê-lo enxergar o que nenhuma das duas vê sozinha.

**A conta, inteira.** Antes do jogo, a expectativa de pontuação do mandante é::

    esperado = 1 / (1 + 10 ** (-(elo_mandante + vantagem_casa - elo_visitante) / 400))

Depois do jogo, com ``real`` valendo 1 (vitória), 0,5 (empate) ou 0::

    elo_mandante += k * (real - esperado)
    elo_visitante -= k * (real - esperado)

Os 400 são a escala: 400 pontos de vantagem significam 10 vezes mais chance de
vencer. O ``k`` é o tamanho do passo — quanto do que acabou de acontecer entra
na nota. O que um lado ganha o outro perde, então a soma dos ratings de um país
**nunca muda**, e isso é conferido por teste.

⚠️ **A chave do clube é a coluna ``mandante``/``visitante``**, que é
``PAIS:nome`` (regra 14). Isso resolve de graça o caso mais importante do Elo
num projeto com cinco divisões inglesas: ``ENG:Luton`` é a **mesma** chave na E0
e na E1. Um time rebaixado leva o rating dele junto, como tem de ser — se a
chave fosse por competição, todo promovido e todo rebaixado renasceria com 1500,
e o Elo viraria ruído justamente nos times sobre os quais há mais a dizer.
Conferido na tabela: 140 clubes aparecem em duas ou mais divisões do mesmo país
e **nenhum** aparece em duas na mesma temporada — ou seja, são todos casos de
promoção e rebaixamento, nenhum é homônimo. Há teste que refaz essa conferência,
porque o dia em que ela deixar de valer o Elo se corrompe **em silêncio** (a
seção 4.1 da especificação avisa exatamente isso).

⚠️ **Times de países diferentes nunca se enfrentam**, então o Elo de cada país é
um universo isolado: ``ENG:Liverpool`` 1750 e ``BRA:Palmeiras`` 1750 não querem
dizer "igualmente fortes", querem dizer "igualmente acima da média **do próprio
país**". Comparar os dois números não significa nada, e nenhuma feature do
projeto faz isso.

**A trava contra vazamento (regra 6): a atualização é por bloco de data.** Todos
os jogos de um mesmo dia são previstos com o rating do **fim do dia anterior**, e
só depois o dia inteiro é incorporado. Sem isso, o jogo das 16h de sábado
entraria no Elo usado para prever o das 18h — informação que não existia na hora
de apostar. É a mesma regra do ``<`` estrito de
:func:`futebol.modelos.base.jogos_ate`, aplicada a um cálculo sequencial.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from futebol.config import Config

#: Rating de quem nunca jogou. O valor não tem significado próprio — o que
#: importa são as diferenças. 1500 é a convenção herdada do xadrez.
RATING_INICIAL = 1500.0

#: Tamanho do passo. Com k = 20, um azarão completo que vence ganha ~15 pontos;
#: um favorito que vence ganha ~3. Valor do ``config.yaml``.
K_PADRAO = 20.0

#: Vantagem de jogar em casa, em pontos de Elo, somada ao mandante no cálculo da
#: expectativa (não ao rating dele: é uma vantagem da situação, não do time).
#:
#: **Medida, não chutada.** Nos 53.009 jogos anteriores ao início da janela de
#: validação, o mandante somou 0,5719 ponto por jogo; a diferença de Elo que
#: produz essa pontuação entre dois times iguais é ``-400·log10(1/0,5719 - 1)``,
#: ou seja 50,3. Congelada a partir daí, como o fator casa único da Fase 4 —
#: nenhum jogo da janela avaliada entrou nesta conta.
#:
#: ⚠️ O valor varia MUITO por país: 20 no Japão, 32 na Inglaterra, 90 no Brasil,
#: 99 nos Estados Unidos. Um número só é uma simplificação consciente: quem
#: carrega a vantagem de casa por competição no projeto é o Dixon-Coles
#: (``fator_casa: por_liga``), e ele também é feature do LightGBM.
VANTAGEM_CASA_PADRAO = 50.0

#: As colunas que :meth:`Elo.ratings_antes` devolve.
COLUNAS_ELO: tuple[str, ...] = ("elo_mandante", "elo_visitante", "elo_diferenca")

#: Colunas que a tabela precisa ter para o Elo rodar.
COLUNAS_EXIGIDAS: tuple[str, ...] = (
    "data",
    "mandante",
    "visitante",
    "gols_mandante",
    "gols_visitante",
)


class ErroDeElo(Exception):
    """Tabela sem as colunas que o Elo precisa."""


class Elo:
    """Ratings Elo de todos os clubes, percorridos em ordem cronológica.

    Uso típico (é assim que a Fase 5 monta a feature)::

        elo = Elo(cfg=cfg)
        colunas = elo.ratings_antes(jogos)   # o rating ANTES de cada jogo
        jogos = jogos.join(colunas)

    Args:
        cfg: de onde vêm ``k`` e ``rating_inicial`` (seção ``modelos.elo``).
        k: tamanho do passo. Sobrepõe o ``config.yaml``.
        rating_inicial: nota de quem nunca jogou.
        vantagem_casa: pontos somados ao mandante no cálculo da expectativa.
    """

    def __init__(
        self,
        cfg: Config | None = None,
        k: float | None = None,
        rating_inicial: float | None = None,
        vantagem_casa: float | None = None,
    ) -> None:
        do_config = cfg.secao("modelos").get("elo", {}) if cfg is not None else {}
        self.k = float(k if k is not None else do_config.get("k", K_PADRAO))
        self.rating_inicial = float(
            rating_inicial
            if rating_inicial is not None
            else do_config.get("rating_inicial", RATING_INICIAL)
        )
        self.vantagem_casa = float(
            vantagem_casa
            if vantagem_casa is not None
            else do_config.get("vantagem_casa", VANTAGEM_CASA_PADRAO)
        )
        if self.k <= 0:
            raise ErroDeElo(f"k tem de ser positivo; veio {self.k}.")
        #: ``{clube: rating}``. Só contém quem já jogou.
        self.ratings: dict[str, float] = {}

    # -- a conta -----------------------------------------------------------
    def rating(self, clube: str) -> float:
        """O rating atual do clube; o inicial, se ele ainda não jogou."""
        return self.ratings.get(clube, self.rating_inicial)

    def esperado(self, do_mandante: float, do_visitante: float) -> float:
        """Pontuação esperada do mandante, entre 0 e 1, já com a vantagem de casa.

        É uma expectativa de *pontuação*, não de vitória: 0,57 quer dizer
        "espera-se 0,57 ponto por jogo", o que num esporte com empate não é o
        mesmo que "57% de chance de ganhar". O 1X2 de verdade sai da matriz de
        placares dos modelos, nunca daqui.
        """
        diferenca = do_mandante + self.vantagem_casa - do_visitante
        return 1.0 / (1.0 + 10.0 ** (-diferenca / 400.0))

    def ratings_antes(self, jogos: pd.DataFrame) -> pd.DataFrame:
        """Para cada jogo, o rating dos dois times **antes** de ele acontecer.

        Args:
            jogos: tabela com :data:`COLUNAS_EXIGIDAS`. Não precisa estar
                ordenada — a ordenação é feita aqui.

        Retorna:
            ``DataFrame`` com :data:`COLUNAS_ELO`, no **mesmo índice** da
            entrada, para dar para colar ao lado sem risco de desalinhar linhas.

        ⚠️ Este método **altera** o estado do objeto: ao terminar, ``ratings``
        guarda a situação depois do último jogo da tabela. Chamá-lo duas vezes na
        mesma tabela processaria a história duas vezes. Para recomeçar, crie
        outro :class:`Elo`.
        """
        self._conferir(jogos)
        ordenados = jogos.sort_values("data", kind="stable")

        antes_mandante = np.empty(len(ordenados), dtype=float)
        antes_visitante = np.empty(len(ordenados), dtype=float)
        posicao = 0

        for _, do_dia in ordenados.groupby("data", sort=True):
            # 1ª passada: lê o rating de todo mundo como ele estava ANTES de o
            # dia começar. Nenhum jogo deste dia influencia a previsão de outro
            # jogo do mesmo dia — é a regra 6 aplicada a um cálculo sequencial.
            deltas: dict[str, float] = {}
            for _, jogo in do_dia.iterrows():
                mandante = jogo["mandante"]
                visitante = jogo["visitante"]
                do_casa = self.rating(mandante)
                do_fora = self.rating(visitante)
                antes_mandante[posicao] = do_casa
                antes_visitante[posicao] = do_fora
                posicao += 1

                real = self._pontuacao(jogo)
                if real is None:  # jogo sem placar não ensina nada
                    continue
                ajuste = self.k * (real - self.esperado(do_casa, do_fora))
                # Acumulado: se um clube jogar duas vezes no mesmo dia (raro, mas
                # acontece em calendário remarcado), as duas correções valem.
                deltas[mandante] = deltas.get(mandante, 0.0) + ajuste
                deltas[visitante] = deltas.get(visitante, 0.0) - ajuste

            # 2ª passada: só agora o dia entra na história.
            for clube, delta in deltas.items():
                self.ratings[clube] = self.rating(clube) + delta

        saida = pd.DataFrame(
            {
                "elo_mandante": antes_mandante,
                "elo_visitante": antes_visitante,
                "elo_diferenca": antes_mandante - antes_visitante,
            },
            index=ordenados.index,
        )
        return saida.reindex(jogos.index)

    # -- apoio -------------------------------------------------------------
    def _pontuacao(self, jogo) -> float | None:
        """O que o mandante somou: 1, 0,5, 0 — ou ``None`` se não há placar.

        Sai sempre do **placar**, nunca da coluna ``resultado`` da fonte: é a
        mesma decisão de 16/09/2026 que vale no resto do projeto, e aqui ela
        importa porque um resultado divergente entraria no rating em silêncio.
        """
        gols_casa = jogo["gols_mandante"]
        gols_fora = jogo["gols_visitante"]
        if pd.isna(gols_casa) or pd.isna(gols_fora):
            return None
        if gols_casa > gols_fora:
            return 1.0
        return 0.5 if gols_casa == gols_fora else 0.0

    @staticmethod
    def _conferir(jogos: pd.DataFrame) -> None:
        faltando = [c for c in COLUNAS_EXIGIDAS if c not in jogos.columns]
        if faltando:
            raise ErroDeElo(
                f"A tabela não tem as colunas: {', '.join(faltando)}. "
                "Ela deve vir de `futebol.dados.limpeza.carregar`."
            )


def clubes_em_duas_divisoes_na_mesma_temporada(jogos: pd.DataFrame) -> pd.DataFrame:
    """Os clubes que aparecem em duas competições **na mesma temporada**.

    Serve à conferência descrita no topo do módulo. Como a chave do Elo é
    ``PAIS:nome``, um clube que sobe ou desce de divisão **continua sendo o
    mesmo** — que é o comportamento desejado, e é por isso que aparecer em duas
    competições ao longo dos anos não é problema nenhum. O que não pode existir é
    um clube em duas divisões na **mesma temporada**: isso não seria promoção,
    seria homônimo, e fundiria dois times diferentes num rating só.

    Retorna:
        Uma linha por ``(time, temporada)`` problemático. Tabela vazia é o
        resultado saudável, e é o que a tabela de hoje devolve.
    """
    lados = [
        jogos[["liga", "temporada", lado]].rename(columns={lado: "time"})
        for lado in ("mandante", "visitante")
    ]
    todos = pd.concat(lados).drop_duplicates()
    contagem = todos.groupby(["time", "temporada"])["liga"].nunique()
    return contagem[contagem > 1].reset_index(name="competicoes")
