"""O LightGBM da Fase 5: aprende **gols**, entrega matriz de placares.

O Dixon-Coles estima a força de cada time a partir de uma coisa só: os placares
anteriores. O LightGBM pode olhar vinte e três coisas ao mesmo tempo — forma
recente, descanso, Elo, estádio vazio, e a própria leitura do Dixon-Coles — e
descobrir sozinho onde cada uma importa. Esta é a pergunta da fase: **isso paga?**

**O que ele prevê, e por que não é o que a especificação escreveu.** A seção da
Fase 5 pede um multiclasse de 1X2 e um binário de Over 2,5 — dois modelos, duas
contas separadas. Isso colide de frente com a decisão de 16/09/2026, que manda
todo mercado sair da **mesma matriz de placares**, para o projeto nunca apostar
ao mesmo tempo em "empate" e em "muitos gols" de forma incoerente. Escolhido, com
o Enzo, resolver a colisão a favor da coerência: o GBM prevê os **gols esperados
de cada lado** (dois regressores de objetivo Poisson) e a matriz sai deles::

    lambda_casa = GBM_casa(features do jogo)
    lambda_fora = GBM_fora(features do jogo)
    matriz[i, j] = P(Poisson(lambda_casa) = i) · P(Poisson(lambda_fora) = j)

Assim o GBM obedece ao mesmo contrato de :mod:`futebol.modelos.base` que os
outros três modelos, entra no walk-forward da Fase 4 sem nenhuma exceção, e é
comparável com eles pela mesma log loss. O preço é conhecido e está declarado: o
alvo de treino é gol, não resultado, e um modelo que aprendesse 1X2 diretamente
poderia ir melhor **no 1X2**.

**Por que a liga não é feature.** Um modelo global precisa saber que a Bundesliga
faz mais gols que a Grécia. Essa informação já chega, e numa forma melhor que um
código de liga: as quatro colunas do Dixon-Coles são a expectativa **daquele
jogo, naquela liga**, estimada por um modelo que ajusta cada competição
separadamente. Um código categórico daria ao GBM a média da liga; o Dixon-Coles
dá a média do confronto.

⚠️ **O retreino é a cada 30 dias, e o cache dele mora na fábrica.** Reajustar um
LightGBM antes de cada uma das 1.026 datas da janela levaria horas por
configuração. Em vez disso, :class:`FabricaGBM` treina nos **marcos** de 30 em
30 dias e reaproveita o ajuste do último marco. Isso continua honesto — o ajuste
do marco ``M`` só viu jogos anteriores a ``M``, e ``M`` é anterior ou igual à
data prevista, então nada de futuro entra — e o viés que cria é **contra** o GBM,
que joga com uma leitura até 30 dias velha.

⚠️ E o cache é **de instância**, nunca de módulo. Um cache global chaveado por
nome foi exatamente o defeito que a Fase 4 destravou: o nome de um modelo depende
da configuração, e quando a configuração muda o nome passa a apontar para outra
coisa **em silêncio**. Aqui cada fábrica carrega as próprias features, os
próprios hiperparâmetros e o próprio cache; duas configurações diferentes são
dois objetos diferentes e não têm como se confundir.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from futebol.config import Config
from futebol.modelos import base
from futebol.modelos.poisson import MAX_GOLS_PADRAO, matriz_poisson

#: De quantos em quantos dias o LightGBM é reajustado. Ver o aviso no topo.
PASSO_DE_RETREINO = 30

#: Jogos que precisam existir antes de um marco para o ajuste acontecer. Um GBM
#: com poucas centenas de linhas e vinte e três colunas decora em vez de
#: aprender, e um modelo que decorou tem log loss ótima no treino e péssima
#: adiante.
MINIMO_DE_TREINO = 500

#: Hiperparâmetros de partida. Conservadores de propósito: resultado de futebol
#: é quase todo ruído, e árvore funda em dado ruidoso decora o ruído.
#:
#: ⚠️ Cada variação destes números que for medida na validação **conta para a
#: regra 11** e entra no pré-registro. Por isso a grade da Fase 5 é pequena e
#: fica em :mod:`futebol.avaliacao.selecao`, não aqui.
HIPERPARAMETROS: dict[str, object] = {
    "objective": "poisson",
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "verbose": -1,
}

#: As colunas que identificam um jogo quando só se tem um :class:`base.Jogo`.
CHAVE_DO_JOGO: tuple[str, ...] = ("data", "mandante", "visitante")


class ErroDeGBM(base.ErroDeModelo):
    """Features ausentes, treino insuficiente ou jogo que não está na tabela."""


@dataclass(frozen=True)
class Ajuste:
    """Um par de regressores treinados num marco, e a trilha do que eles viram.

    Atributos:
        gols_mandante: o regressor dos gols do mandante.
        gols_visitante: o regressor dos gols do visitante.
        jogos: quantas linhas entraram no treino.
        ultima_data: a data do jogo mais recente que entrou. É o que o modelo
            reporta como ``ultima_data_de_treino`` — e é a verdade, não o corte
            que foi pedido. A diferença entre as duas importa: o corte pedido
            pode ser 29 dias mais novo que o marco em que o ajuste aconteceu, e
            declarar o corte seria declarar um treino que não houve.
    """

    gols_mandante: object
    gols_visitante: object
    jogos: int
    ultima_data: pd.Timestamp


class FabricaGBM:
    """Produz modelos :class:`GBM` que compartilham features e ajustes.

    O walk-forward exige uma **fábrica** de modelos, e não um modelo, para que
    cada rodada receba um ajuste do zero e nada da rodada anterior sobre.
    Para o LightGBM isso seria caro demais ao pé da letra, então o que se
    compartilha aqui é só o que é legítimo compartilhar: um ajuste feito num
    marco, que toda rodada dentro daquele marco pode usar sem ver o futuro.

    Args:
        features: a saída de :func:`futebol.features.construtor.construir`,
            calculada uma vez para a tabela inteira. Toda coluna dela já é
            causal — é lá que a regra 6 foi garantida, e não aqui.
        cfg: usado só para ``max_gols``.
        passo_dias: distância entre marcos de retreino.
        minimo_de_treino: linhas necessárias antes de um marco.
        max_gols: tamanho da matriz de placares.
        hiperparametros: sobrepõem :data:`HIPERPARAMETROS`.
    """

    def __init__(
        self,
        features: pd.DataFrame,
        cfg: Config | None = None,
        passo_dias: int = PASSO_DE_RETREINO,
        minimo_de_treino: int = MINIMO_DE_TREINO,
        max_gols: int | None = None,
        chaves: pd.DataFrame | None = None,
        **hiperparametros: object,
    ) -> None:
        if features.empty:
            raise ErroDeGBM("A tabela de features está vazia.")
        self.features = features
        self.colunas = list(features.columns)
        #: ``{(data, mandante, visitante): índice}``, só para prever um jogo
        #: avulso pelo nome dos times. O walk-forward não precisa dele: lá os
        #: jogos chegam com o índice, que é a chave mais segura que existe.
        self._por_chave: dict[tuple, object] | None = None
        if chaves is not None:
            faltando = [c for c in CHAVE_DO_JOGO if c not in chaves.columns]
            if faltando:
                raise ErroDeGBM(
                    f"A tabela de chaves não tem: {', '.join(faltando)}."
                )
            self._por_chave = {
                (pd.Timestamp(linha[0]), linha[1], linha[2]): indice
                for indice, linha in zip(
                    chaves.index,
                    chaves[list(CHAVE_DO_JOGO)].to_numpy(),
                    strict=True,
                )
            }
        self.passo_dias = int(passo_dias)
        self.minimo_de_treino = int(minimo_de_treino)
        do_config = cfg.secao("modelos").get("poisson", {}) if cfg is not None else {}
        self.max_gols = int(
            max_gols
            if max_gols is not None
            else do_config.get("max_gols", MAX_GOLS_PADRAO)
        )
        self.hiperparametros = {**HIPERPARAMETROS, **hiperparametros}
        #: ``{marco: Ajuste}``. Cache **desta** fábrica e de mais ninguém.
        self._ajustes: dict[pd.Timestamp | None, Ajuste] = {}

    # -- os marcos ---------------------------------------------------------
    def marco_de(self, corte: pd.Timestamp | None) -> pd.Timestamp | None:
        """O último marco de retreino anterior ou igual a ``corte``.

        Os marcos são contados a partir de uma âncora fixa, e não do primeiro
        jogo da tabela: assim duas execuções com janelas diferentes caem nos
        **mesmos** marcos, e o cache de uma serve à outra sem nunca misturar
        ajustes de recortes distintos.
        """
        if corte is None:
            return None
        corte = pd.Timestamp(corte)
        dias = (corte - _ANCORA).days
        return _ANCORA + pd.Timedelta(days=(dias // self.passo_dias) * self.passo_dias)

    def ajuste_em(self, marco: pd.Timestamp | None, jogos: pd.DataFrame) -> Ajuste:
        """O ajuste daquele marco, treinando-o se ainda não existir."""
        if marco in self._ajustes:
            return self._ajustes[marco]
        ajuste = self._treinar(marco, jogos)
        self._ajustes[marco] = ajuste
        return ajuste

    def _treinar(self, marco: pd.Timestamp | None, jogos: pd.DataFrame) -> Ajuste:
        from lightgbm import LGBMRegressor

        usados = base.jogos_ate(jogos, marco).dropna(
            subset=["gols_mandante", "gols_visitante"]
        )
        if len(usados) < self.minimo_de_treino:
            quando = f" antes de {marco.date()}" if marco is not None else ""
            raise ErroDeGBM(
                f"Só há {len(usados)} jogo(s) para treinar o LightGBM{quando}; o "
                f"mínimo é {self.minimo_de_treino}. Com menos que isso ele decora "
                "em vez de aprender."
            )
        entradas = self.features.reindex(usados.index)[self.colunas]
        regressores = []
        for alvo in ("gols_mandante", "gols_visitante"):
            modelo = LGBMRegressor(**self.hiperparametros)
            modelo.fit(entradas, usados[alvo].astype(float))
            regressores.append(modelo)
        return Ajuste(
            gols_mandante=regressores[0],
            gols_visitante=regressores[1],
            jogos=len(usados),
            ultima_data=pd.Timestamp(usados["data"].max()),
        )

    # -- a fábrica ---------------------------------------------------------
    def novo(self) -> GBM:
        """Um modelo novo ligado a esta fábrica. É o que o walk-forward chama."""
        return GBM(self)

    def chave_para(self, jogo: base.Jogo):
        """O índice da linha de features daquele jogo, ou ``None`` se não houver."""
        if self._por_chave is None:
            raise ErroDeGBM(
                "Esta fábrica foi construída sem a tabela de chaves, então só "
                "sabe prever em lote (`prever_muitos`), onde o jogo chega pelo "
                "índice. Passe `chaves=jogos` para prever um jogo pelo nome."
            )
        return self._por_chave.get(
            (pd.Timestamp(jogo.data), jogo.mandante, jogo.visitante)
        )

    @property
    def parametros(self) -> dict[str, object]:
        """O que identifica esta configuração, para o pré-registro (regra 11)."""
        return {
            "modelo": "gbm",
            "passo_retreino": self.passo_dias,
            "features": len(self.colunas),
            # Distingue a variante que recebe a leitura do Dixon-Coles da que
            # tem de se virar sozinha — é a comparação que responde se o GBM
            # acrescenta algo ou só copia o modelo de gols.
            "com_dixon_coles": any(
                coluna.startswith("dc_") for coluna in self.colunas
            ),
            **{
                chave: valor
                for chave, valor in self.hiperparametros.items()
                if chave not in ("verbose", "objective")
            },
        }


#: Âncora dos marcos de retreino. Data fixa e arbitrária, anterior a todo jogo da
#: fonte — o que importa é ela nunca mudar, para dois recortes diferentes caírem
#: nos mesmos marcos.
_ANCORA = pd.Timestamp("2000-01-03")


class GBM(base.Modelo):
    """O LightGBM como modelo do projeto: treina, prevê, entrega matriz.

    Não se constrói este objeto diretamente; ele vem de :meth:`FabricaGBM.novo`,
    porque sozinho ele não teria as features nem o cache de ajustes.
    """

    nome = "gbm"

    def __init__(self, fabrica: FabricaGBM) -> None:
        super().__init__()
        self.fabrica = fabrica
        self._ajuste: Ajuste | None = None

    # -- treino ------------------------------------------------------------
    def treinar(self, jogos: pd.DataFrame, ate_data=None) -> GBM:
        """Como o da classe base, mas a trilha de auditoria diz a verdade.

        ⚠️ A classe base registra em ``ultima_data_de_treino`` o último jogo
        **anterior ao corte pedido**. Para o GBM isso seria mentira: o ajuste
        vem do marco, que pode estar até 29 dias atrás. A trilha é corrigida
        aqui para a data que realmente entrou no treino — sempre mais antiga,
        nunca mais nova, então a conferência de vazamento continua valendo.
        """
        super().treinar(jogos, ate_data=ate_data)
        if self._ajuste is not None:
            self.ultima_data_de_treino = self._ajuste.ultima_data
        return self

    def _ajustar(self, jogos: pd.DataFrame) -> None:
        marco = self.fabrica.marco_de(self.corte_de_treino)
        self._ajuste = self.fabrica.ajuste_em(marco, jogos)

    # -- previsão ----------------------------------------------------------
    def medias(self, entradas: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Os gols esperados dos dois lados, uma linha por jogo.

        O objetivo ``poisson`` do LightGBM prevê uma média de contagem, que é
        sempre positiva. O piso é só uma rede de segurança: uma média zero faria
        a matriz de placares inteira ser zero, e o erro apareceria longe daqui.
        """
        ajuste = self._exigir_ajuste()
        lam = np.asarray(ajuste.gols_mandante.predict(entradas), dtype=float)
        mu = np.asarray(ajuste.gols_visitante.predict(entradas), dtype=float)
        return np.clip(lam, 1e-6, None), np.clip(mu, 1e-6, None)

    def matriz_de_placares(self, jogo: base.Jogo) -> np.ndarray:
        """A matriz de um jogo. Ver :meth:`prever_muitos` para o caminho em lote."""
        entradas = self._features_do_jogo(jogo)
        lam, mu = self.medias(entradas)
        return matriz_poisson(float(lam[0]), float(mu[0]), self.fabrica.max_gols)

    def prever_muitos(self, jogos: pd.DataFrame) -> pd.DataFrame:
        """Previsão de uma tabela inteira, em uma só passada pelo LightGBM.

        É este o caminho que o walk-forward usa. As features vêm pelo **índice**
        da tabela, que é o mesmo da tabela de features — e não por uma busca por
        nome de time, que seria mais lenta e mais fácil de desalinhar.
        """
        self._exigir_treinado()
        faltando = jogos.index.difference(self.fabrica.features.index)
        if len(faltando):
            raise ErroDeGBM(
                f"{len(faltando)} jogo(s) da tabela não têm features calculadas. "
                "A tabela de features tem de cobrir todos os jogos que se quer "
                "prever, e ser construída uma vez sobre a tabela inteira."
            )
        entradas = self.fabrica.features.loc[jogos.index, self.fabrica.colunas]
        lam, mu = self.medias(entradas)
        previsoes = [
            base.mercados_da_matriz(
                matriz_poisson(float(um), float(outro), self.fabrica.max_gols)
            )
            for um, outro in zip(lam, mu, strict=True)
        ]
        return pd.DataFrame(
            previsoes, index=jogos.index, columns=list(base.CHAVES_PREVISAO)
        )

    # -- apoio -------------------------------------------------------------
    def _features_do_jogo(self, jogo: base.Jogo) -> pd.DataFrame:
        """Localiza a linha de features de um jogo avulso, pela chave dele."""
        features = self.fabrica.features
        if jogo.data is None:
            raise ErroDeGBM(
                f"Para prever {jogo.mandante} x {jogo.visitante} com o GBM é "
                "preciso a data do jogo: as features são todas datadas."
            )
        # A tabela de jogos não vem junto das features, então a chave é
        # reconstruída a partir do índice compartilhado por ambas.
        chave = self.fabrica.chave_para(jogo)
        if chave is None:
            raise ErroDeGBM(
                f"O jogo {jogo.mandante} x {jogo.visitante} em "
                f"{pd.Timestamp(jogo.data).date()} não está na tabela de "
                "features. O GBM só prevê jogos cujas features foram calculadas."
            )
        return features.loc[[chave], self.fabrica.colunas]

    def _exigir_ajuste(self) -> Ajuste:
        self._exigir_treinado()
        if self._ajuste is None:  # pragma: no cover - treinar sempre preenche
            raise ErroDeGBM("O GBM foi treinado sem produzir ajuste.")
        return self._ajuste
