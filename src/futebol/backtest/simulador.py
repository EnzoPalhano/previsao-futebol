"""O backtest: "teria dado lucro?" — respondido de um jeito que dá para acreditar.

O módulo recebe as previsões do walk-forward (que nunca viram o próprio jogo,
regra 6), junta com as odds reais e simula as apostas que teriam sido feitas.
Nada aqui escolhe modelo: a escolha é por log loss e já foi feita na Fase 4
(regra 9). O que se mede aqui é a **consequência** dela.

**As cinco travas que separam este backtest dos que dão lucro na internet.**

1. **Aposta-se na odd média pré-jogo** (``odd_pre_*``, que é a ``Avg*`` da
   fonte). Nunca na ``Max``. A ``Max`` é o maior valor entre umas vinte casas —
   quase sempre uma casa pequena, uma odd digitada errada ou uma aposta com
   limite de cinquenta reais. Backtest na ``Max`` dá lucro com quase qualquer
   modelo, e é o erro que invalida a maioria dos projetos de aposta que se
   encontram por aí (regra 8).
2. **A odd de fechamento só mede CLV**, nunca decide aposta. Ela é informação do
   futuro em relação ao momento da aposta; usá-la para escolher seria vazamento
   com outro nome.
3. **Só as ligas aprovadas na Fase 2.** As 18 que passaram no filtro de margem,
   cobertura e calibração. As do Grupo 2 estão fora por regra 12: elas só têm
   odd de fechamento, então nelas não existe nem aposta nem CLV.
4. **Jogo sem odd pré-jogo é pulado e contado.** Nunca descartado em silêncio —
   a Fase 1 já avisou que jogo sem odd não é uma amostra aleatória de jogos.
5. **Todo número sai com intervalo de confiança, número de apostas e o menor
   efeito que aquela amostra enxergaria** (regra 10). Um ROI sem essas três
   companhias não significa nada, para cima nem para baixo.

⚠️ **O que este módulo não pode fazer, e é bom saber antes de ler o resultado.**
Ele simula apostar na média do mercado **depois** de ela existir. Não há
simulação de limite de aposta, de conta limitada pela casa, de odd que sumiu
antes de você clicar, nem de comissão. Todas essas fricções puxam o resultado
real para **baixo** do simulado. Um backtest empatado aqui é, na vida real,
perdedor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from futebol.avaliacao import metricas
from futebol.backtest import estrategias
from futebol.config import Config
from futebol.odds import mercado

#: O método de remoção de margem do projeto, escolhido por medição na Fase 2.
METODO_MARGEM = "power"


@dataclass(frozen=True)
class Selecao:
    """Uma coisa em que dá para apostar.

    Atributos:
        chave: o nome da coluna de probabilidade na previsão e o sufixo da
            coluna de odd (``odd_pre_H``, ``odd_pre_over25``). Os dois são o
            mesmo texto de propósito: um único nome para uma única coisa.
        rotulo: como aparece no relatório, em português.
        mercado: a que grupo complementar ela pertence. Importa para tirar a
            margem, que é uma conta feita sobre o grupo inteiro, nunca sobre uma
            odd isolada.
    """

    chave: str
    rotulo: str
    mercado: str


#: As cinco seleções apostáveis do projeto. Todas saem da **mesma matriz de
#: placares** do modelo (decisão de 16/09/2026): não existe um caminho de conta
#: para o 1X2 e outro para o Over/Under. Com contas separadas, o projeto poderia
#: apostar ao mesmo tempo em "empate" e em "muitos gols" de forma incoerente, e
#: nenhum teste pegaria.
#:
#: "Ambos marcam" fica de fora porque a fonte não traz odd desse mercado — sem
#: odd não há aposta, e inventar uma seria inventar o resultado.
SELECOES: tuple[Selecao, ...] = (
    Selecao("H", "vitória do mandante", "1x2"),
    Selecao("D", "empate", "1x2"),
    Selecao("A", "vitória do visitante", "1x2"),
    Selecao("over25", "mais de 2,5 gols", "ou25"),
    Selecao("under25", "menos de 2,5 gols", "ou25"),
)

#: As colunas que a tabela de apostas carrega. Uma linha por aposta, com tudo o
#: que a especificação pede registrado: data, jogo, mercado, odd, probabilidade
#: do modelo, EV, resultado, lucro e CLV.
COLUNAS_DA_APOSTA: tuple[str, ...] = (
    "data",
    "liga",
    "temporada",
    "mandante",
    "visitante",
    "mercado",
    "selecao",
    "prob",
    "odd",
    "ev",
    "ganhou",
    "retorno_unitario",
    "prob_justa",
    "odd_fech",
    "prob_fech",
    "clv",
    "clv_bruto",
)


@dataclass(frozen=True)
class Amostra:
    """De onde as apostas candidatas saíram, e o que ficou de fora.

    Existe para a regra 13 e para a exigência da Fase 1d: jogo sem odd **não** é
    um jogo sorteado ao acaso (costuma ser time pequeno, jogo adiado, liga
    menor), então quantos foram e por quê tem de estar escrito.

    Atributos:
        candidatos: uma linha por (jogo, seleção) com odd pré-jogo disponível.
        ligas: as competições que entraram, já filtradas.
        jogos_na_janela: jogos previstos pelo walk-forward nessas ligas.
        jogos_com_odd: quantos tinham a odd pré-jogo de 1X2 completa.
        jogos_sem_odd: os pulados, e o motivo está no nome.
        jogos_sem_ou: quantos não tinham a dupla de Over/Under pré-jogo.
        jogos_sem_fechamento: quantos não permitem medir CLV.
        fora_por_grupo2: jogos das competições do Grupo 2, fora por regra 12.
        fora_por_liga_reprovada: jogos das ligas do Grupo 1 que o filtro da
            Fase 2 reprovou.
    """

    candidatos: pd.DataFrame
    ligas: list[str]
    jogos_na_janela: int
    jogos_com_odd: int
    jogos_sem_odd: int
    jogos_sem_ou: int
    jogos_sem_fechamento: int
    fora_por_grupo2: int
    fora_por_liga_reprovada: int

    def resumo(self) -> str:
        plural = "liga" if len(self.ligas) == 1 else "ligas"
        return (
            f"{len(self.candidatos)} apostas candidatas em {self.jogos_com_odd} jogos "
            f"de {len(self.ligas)} {plural}; {self.jogos_sem_odd} jogos pulados por "
            f"não ter odd média pré-jogo"
        )


def preparar(
    jogos: pd.DataFrame,
    previsoes: pd.DataFrame,
    cfg: Config,
    metodo: str = METODO_MARGEM,
) -> Amostra:
    """Junta previsões e odds e monta todas as apostas **possíveis**.

    Candidata é toda combinação (jogo, seleção) que tem previsão do modelo e odd
    média pré-jogo. Se ela vira aposta ou não é decisão de :func:`selecionar`,
    que olha o valor esperado — separar as duas coisas é o que permite dizer
    "de 100 mil oportunidades, 20 mil passaram no filtro".

    Args:
        jogos: a tabela de jogos, com as odds.
        previsoes: a saída do walk-forward, indexada como ``jogos``.
        cfg: a configuração, de onde saem as ligas aprovadas.
        metodo: como tirar a margem das odds de fechamento, para o CLV.

    Retorna:
        Uma :class:`Amostra`.
    """
    aprovadas = list(cfg.bruto["ligas_aprovadas_backtest"])
    do_modelo = jogos.loc[previsoes.index]

    fora_grupo2 = int((do_modelo["grupo"] == "grupo2").sum())
    do_grupo1 = do_modelo.loc[do_modelo["grupo"] == "grupo1"]
    fora_reprovada = int((~do_grupo1["liga"].isin(aprovadas)).sum())

    elegiveis = do_modelo.loc[do_modelo["liga"].isin(aprovadas)]
    if elegiveis.empty:
        raise ValueError(
            "Nenhum jogo elegível para backtest. Confira 'ligas_aprovadas_backtest' "
            f"no config.yaml ({', '.join(aprovadas) or 'vazia'}) e a camada ativa."
        )

    colunas_1x2 = [f"odd_pre_{s.chave}" for s in SELECOES if s.mercado == "1x2"]
    tem_odd = elegiveis[colunas_1x2].notna().all(axis=1)
    com_odd = elegiveis.loc[tem_odd]

    colunas_ou = [f"odd_pre_{s.chave}" for s in SELECOES if s.mercado == "ou25"]
    sem_ou = int((~com_odd[colunas_ou].notna().all(axis=1)).sum())
    colunas_fech = [f"odd_fech_{s.chave}" for s in SELECOES if s.mercado == "1x2"]
    sem_fechamento = int((~com_odd[colunas_fech].notna().all(axis=1)).sum())

    candidatos = _candidatos(com_odd, previsoes.loc[com_odd.index], metodo)
    return Amostra(
        candidatos=candidatos,
        ligas=sorted(com_odd["liga"].unique()),
        jogos_na_janela=len(elegiveis),
        jogos_com_odd=len(com_odd),
        jogos_sem_odd=int((~tem_odd).sum()),
        jogos_sem_ou=sem_ou,
        jogos_sem_fechamento=sem_fechamento,
        fora_por_grupo2=fora_grupo2,
        fora_por_liga_reprovada=fora_reprovada,
    )


def _candidatos(
    jogos: pd.DataFrame, previsoes: pd.DataFrame, metodo: str
) -> pd.DataFrame:
    """Uma linha por (jogo, seleção) apostável, com tudo já calculado."""
    aconteceu = _o_que_aconteceu(jogos)
    justas = {
        nome: _probabilidades_justas(jogos, nome, metodo) for nome in ("1x2", "ou25")
    }
    justas_pre = {
        nome: _probabilidades_justas(jogos, nome, metodo, momento="pre")
        for nome in ("1x2", "ou25")
    }

    partes = []
    for selecao in SELECOES:
        odd = jogos[f"odd_pre_{selecao.chave}"].to_numpy(float)
        odd_fech = jogos[f"odd_fech_{selecao.chave}"].to_numpy(float)
        prob = previsoes[selecao.chave].to_numpy(float)
        ganhou = aconteceu[selecao.chave]
        indice = _indice_da_selecao(selecao)
        prob_fech = justas[selecao.mercado][:, indice]
        prob_justa = justas_pre[selecao.mercado][:, indice]

        parte = pd.DataFrame(
            {
                "data": jogos["data"].to_numpy(),
                "liga": jogos["liga"].to_numpy(),
                "temporada": jogos["temporada"].to_numpy(),
                "mandante": jogos["mandante"].to_numpy(),
                "visitante": jogos["visitante"].to_numpy(),
                "mercado": selecao.mercado,
                "selecao": selecao.chave,
                "prob": prob,
                "odd": odd,
                # Valor esperado de apostar 1 unidade, segundo o modelo. É a
                # única coisa que decide aposta neste projeto.
                "ev": prob * odd - 1.0,
                "ganhou": ganhou,
                # O lucro de apostar 1 unidade: ganha odd−1, perde 1.
                "retorno_unitario": np.where(ganhou, odd - 1.0, -1.0),
                # A estimativa do mercado no momento da aposta, sem a comissão.
                # `1/odd - prob_justa` é o que a casa cobrou nesta seleção.
                "prob_justa": prob_justa,
                "odd_fech": odd_fech,
                "prob_fech": prob_fech,
                # CLV: o valor esperado da aposta medido com a probabilidade
                # JUSTA do fechamento. Ver `medir` para o porquê de ser este o
                # número principal.
                "clv": odd * prob_fech - 1.0,
                "clv_bruto": odd / odd_fech - 1.0,
            },
            index=jogos.index,
        )
        partes.append(parte.loc[np.isfinite(odd)])

    candidatos = pd.concat(partes)
    return candidatos.sort_values(["data", "liga", "mandante", "selecao"]).reset_index(
        drop=True
    )


def _indice_da_selecao(selecao: Selecao) -> int:
    """A posição da seleção dentro do grupo complementar dela."""
    do_mercado = [s.chave for s in SELECOES if s.mercado == selecao.mercado]
    return do_mercado.index(selecao.chave)


def _o_que_aconteceu(jogos: pd.DataFrame) -> dict[str, np.ndarray]:
    """Para cada seleção, um vetor de ``True``/``False``: ela pagou?"""
    resultado = jogos["resultado"].to_numpy()
    gols = (jogos["gols_mandante"] + jogos["gols_visitante"]).to_numpy()
    return {
        "H": resultado == "H",
        "D": resultado == "D",
        "A": resultado == "A",
        # 2,5 não é placar possível, então não existe empate técnico ("push"):
        # toda aposta de Over/Under 2,5 ou ganha tudo ou perde tudo.
        "over25": gols >= 3,
        "under25": gols < 3,
    }


def _probabilidades_justas(
    jogos: pd.DataFrame, nome_mercado: str, metodo: str, momento: str = "fech"
) -> np.ndarray:
    """As probabilidades do mercado, já sem a margem da casa.

    Elas não escolhem aposta nenhuma. Servem para duas medições:

    - ``momento="fech"`` — o **CLV**, que compara o preço pego com a estimativa
      final do mercado;
    - ``momento="pre"`` — a **margem** embutida no preço em que se apostou. É o
      que a Fase 7 precisa para mostrar a comissão acumulada de uma múltipla:
      dividir a probabilidade implícita (``1/odd``) pela justa dá exatamente o
      quanto a casa cobrou naquela seleção, e numa múltipla esses fatores se
      **multiplicam**.

    A remoção da margem é feita sobre o grupo inteiro (as três odds do 1X2
    juntas, as duas do Over/Under juntas), porque margem é uma propriedade do
    mercado, não de uma odd sozinha.
    """
    odds = mercado.odds_da_tabela(jogos, nome_mercado, momento)
    justas = np.full_like(odds, np.nan, dtype=float)
    completas = np.isfinite(odds).all(axis=1)
    if completas.any():
        justas[completas] = mercado.remover_margem(odds[completas], metodo)
    return justas


# ----------------------------------------------------------------------------
# Escolher as apostas
# ----------------------------------------------------------------------------
def selecionar(candidatos: pd.DataFrame, ev_minimo: float = 0.05) -> pd.DataFrame:
    """As apostas que o projeto teria feito: aquelas com ``EV > ev_minimo``.

    Args:
        candidatos: a saída de :func:`preparar`.
        ev_minimo: o corte. 0,05 quer dizer "só aposto quando acho que ganho
            mais de 5% do que arrisco, em média".

    ⚠️ **Por que um corte, e não "aposte em todo EV positivo".** Porque o EV é
    calculado com a probabilidade **do modelo**, que tem erro. Um EV medido de
    +1% pode ser um EV verdadeiro de −4%, e como as odds já vêm com a margem da
    casa embutida, um erro pequeno para cima já basta para transformar uma
    aposta ruim em oportunidade aparente. O corte é uma margem de segurança
    contra o erro do próprio modelo — e a Fase 6 mede o que acontece com vários
    valores dele, em vez de escolher um e torcer.
    """
    apostas = candidatos.loc[candidatos["ev"] > ev_minimo].copy()
    return apostas.sort_values(["data", "liga", "mandante", "selecao"]).reset_index(
        drop=True
    )


def aleatorias(
    candidatos: pd.DataFrame, quantas: int, seed: int = 42
) -> pd.DataFrame:
    """Sorteia ``quantas`` apostas entre as candidatas, sem olhar o EV.

    É a comparação obrigatória da regra 2.6d, e ela é mais informativa do que
    parece. A estratégia aleatória aposta nas mesmas ligas, nas mesmas odds e no
    mesmo período — só não usa o modelo. O ROI dela é, por construção, próximo
    de **menos a margem média** do mercado. Se a estratégia do modelo não ficar
    acima disso, o modelo não está acrescentando nada: está pagando a comissão
    da casa com passos extras.
    """
    if quantas <= 0 or candidatos.empty:
        return candidatos.iloc[:0].copy()
    quantas = min(quantas, len(candidatos))
    sorteadas = candidatos.sample(n=quantas, random_state=seed)
    return sorteadas.sort_values(["data", "liga", "mandante", "selecao"]).reset_index(
        drop=True
    )


# ----------------------------------------------------------------------------
# Medir
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Resultado:
    """As notas de um conjunto de apostas, com incerteza em tudo (regra 10).

    Atributos:
        nome: como a linha aparece na tabela.
        n: número de apostas.
        taxa_acerto: fração das apostas que pagaram.
        odd_media: a odd média em que se apostou.
        roi: lucro por unidade apostada, com stake constante.
        roi_erro_padrao: o erro-padrão desse ROI.
        roi_ic: intervalo de 95% por bootstrap.
        roi_detectavel: o menor ROI que **esta** amostra enxergaria.
        clv: valor esperado médio das apostas medido pela probabilidade justa do
            fechamento. Positivo = pegou preço melhor que o mercado fechou.
        clv_erro_padrao, clv_ic, clv_detectavel: o mesmo, para o CLV.
        clv_bruto: a variação média de odd, ``odd_pre / odd_fech − 1``.
        n_clv: em quantas apostas deu para medir CLV (exige odd de fechamento).
        n_para_roi: quantas apostas seriam necessárias para enxergar o ROI
            observado, com a volatilidade medida nesta amostra.
        n_para_clv: o mesmo, para o CLV.
    """

    nome: str
    n: int
    taxa_acerto: float
    odd_media: float
    roi: float
    roi_erro_padrao: float
    roi_ic: tuple[float, float]
    roi_detectavel: float
    clv: float
    clv_erro_padrao: float
    clv_ic: tuple[float, float]
    clv_detectavel: float
    clv_bruto: float
    n_clv: int
    n_para_roi: float
    n_para_clv: float
    lucro_unitario: float = 0.0

    @property
    def roi_significativo(self) -> bool:
        """O intervalo de 95% do ROI fica todo do mesmo lado do zero?"""
        baixo, alto = self.roi_ic
        return bool(baixo > 0 or alto < 0)

    @property
    def clv_significativo(self) -> bool:
        baixo, alto = self.clv_ic
        return bool(baixo > 0 or alto < 0)

    def como_linha(self) -> dict[str, object]:
        return {
            "quem": self.nome,
            "apostas": self.n,
            "taxa_acerto": self.taxa_acerto,
            "odd_media": self.odd_media,
            "roi": self.roi,
            "roi_baixo": self.roi_ic[0],
            "roi_alto": self.roi_ic[1],
            "roi_detectavel": self.roi_detectavel,
            "clv": self.clv,
            "clv_baixo": self.clv_ic[0],
            "clv_alto": self.clv_ic[1],
            "clv_detectavel": self.clv_detectavel,
            "n_clv": self.n_clv,
        }


def medir(
    apostas: pd.DataFrame,
    nome: str = "modelo",
    amostras_bootstrap: int = 10_000,
    seed: int = 42,
) -> Resultado:
    """Calcula ROI, CLV, poder estatístico e incerteza de um conjunto de apostas.

    **ROI** é o lucro por unidade apostada, com stake constante — ou seja, a
    média simples de ``retorno_unitario``. Com stake variável (Kelly) o ROI sai
    da :class:`futebol.backtest.estrategias.Evolucao`, e os dois números
    respondem coisas diferentes: este aqui mede o **acerto das escolhas**, aquele
    mede o resultado de uma política de dinheiro.

    **CLV** (*closing line value*) é o valor esperado da aposta calculado com a
    probabilidade justa do fechamento. Ele é o critério **primário** do projeto
    (seção 8.3) por uma razão estatística, não por gosto: o CLV de cada aposta
    não depende do resultado do jogo, só de dois preços. A volatilidade dele é
    uma ordem de grandeza menor que a do ROI, e por isso ele converge com
    centenas de apostas em vez de dezenas de milhares.

    ⚠️ Há duas formas de escrever CLV, e o projeto reporta as duas porque elas
    medem coisas diferentes:

    - ``clv`` (a principal) = ``odd_apostada × prob_justa_do_fechamento − 1``.
      Compara o preço pego com a **estimativa** do mercado no fim, já sem a
      comissão da casa. É a que responde "eu sabia algo que o mercado ainda não
      sabia?";
    - ``clv_bruto`` = ``odd_apostada / odd_fechamento − 1``. Compara dois preços
      de balcão. É mais fácil de explicar e mais otimista, porque a comissão da
      casa está dentro dos dois lados e não se cancela por completo.
    """
    if apostas.empty:
        vazio = (float("nan"), float("nan"))
        return Resultado(
            nome=nome, n=0, taxa_acerto=float("nan"), odd_media=float("nan"),
            roi=float("nan"), roi_erro_padrao=float("nan"), roi_ic=vazio,
            roi_detectavel=float("nan"), clv=float("nan"),
            clv_erro_padrao=float("nan"), clv_ic=vazio, clv_detectavel=float("nan"),
            clv_bruto=float("nan"), n_clv=0, n_para_roi=float("nan"),
            n_para_clv=float("nan"),
        )

    retornos = apostas["retorno_unitario"].to_numpy(float)
    clvs = apostas["clv"].to_numpy(float)
    clvs = clvs[np.isfinite(clvs)]

    roi = float(retornos.mean())
    # ddof=1: a amostra estima a variância da população, não a dela mesma.
    desvio_roi = float(retornos.std(ddof=1)) if len(retornos) > 1 else float("nan")
    erro_roi = desvio_roi / np.sqrt(len(retornos))

    if len(clvs) > 1:
        clv = float(clvs.mean())
        desvio_clv = float(clvs.std(ddof=1))
        erro_clv = desvio_clv / np.sqrt(len(clvs))
        ic_clv = metricas.bootstrap_ic(clvs, amostras=amostras_bootstrap, seed=seed)
        detectavel_clv = metricas.efeito_detectavel(len(clvs), desvio_clv)
        n_para_clv = metricas.tamanho_amostra(clv, desvio_clv)
    else:
        clv = desvio_clv = erro_clv = detectavel_clv = n_para_clv = float("nan")
        ic_clv = (float("nan"), float("nan"))

    brutos = apostas["clv_bruto"].to_numpy(float)
    brutos = brutos[np.isfinite(brutos)]

    return Resultado(
        nome=nome,
        n=len(apostas),
        taxa_acerto=float(apostas["ganhou"].to_numpy(bool).mean()),
        odd_media=float(apostas["odd"].to_numpy(float).mean()),
        roi=roi,
        roi_erro_padrao=erro_roi,
        roi_ic=metricas.bootstrap_ic(retornos, amostras=amostras_bootstrap, seed=seed),
        roi_detectavel=metricas.efeito_detectavel(len(retornos), desvio_roi),
        clv=clv,
        clv_erro_padrao=erro_clv,
        clv_ic=ic_clv,
        clv_detectavel=detectavel_clv,
        clv_bruto=float(brutos.mean()) if len(brutos) else float("nan"),
        n_clv=len(clvs),
        n_para_roi=metricas.tamanho_amostra(roi, desvio_roi),
        n_para_clv=n_para_clv,
        lucro_unitario=float(retornos.sum()),
    )


def por_liga(
    apostas: pd.DataFrame, minimo_de_apostas: int = 100, seed: int = 42
) -> pd.DataFrame:
    """Uma linha por liga — a tabela que a especificação exige (seção 4.3).

    ⚠️ **Por que ela é obrigatória.** Uma média geral pode esconder que o lucro
    veio de uma liga só, o que quase sempre é sorte: com 18 ligas, a melhor delas
    parece boa por acaso com facilidade. O critério de consistência da seção 8.4
    — "o CLV tem de ser positivo na maioria das ligas com amostra suficiente" —
    só pode ser conferido aqui.

    Args:
        apostas: a tabela de apostas.
        minimo_de_apostas: ligas com menos que isso ficam de fora, e o corte é
            dito no relatório.
    """
    linhas = []
    for liga, do_liga in apostas.groupby("liga", sort=True):
        if len(do_liga) < minimo_de_apostas:
            continue
        resultado = medir(do_liga, nome=str(liga), amostras_bootstrap=2000, seed=seed)
        linhas.append({"liga": str(liga), **resultado.como_linha()})
    return pd.DataFrame(linhas)


def por_mercado(apostas: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Uma linha por seleção (mandante, empate, visitante, over, under)."""
    rotulos = {s.chave: s.rotulo for s in SELECOES}
    linhas = []
    for chave in (s.chave for s in SELECOES):
        do_mercado = apostas.loc[apostas["selecao"] == chave]
        if do_mercado.empty:
            continue
        resultado = medir(
            do_mercado, nome=rotulos[chave], amostras_bootstrap=2000, seed=seed
        )
        linhas.append({"selecao": chave, **resultado.como_linha()})
    return pd.DataFrame(linhas)


# ----------------------------------------------------------------------------
# A grade de configurações (regra 11)
# ----------------------------------------------------------------------------
#: Os limites de EV que a Fase 6 varre. Quatro, e explicados no relatório:
#: 0% ("aposte em tudo que parecer positivo") até 10% ("só quando a discordância
#: com o mercado for grande").
GRADE_EV: tuple[float, ...] = (0.0, 0.02, 0.05, 0.10)


@dataclass(frozen=True)
class Configuracao:
    """Uma combinação de (limite de EV × estratégia × tipo de banca).

    A regra 11 manda **contar** essas combinações. Com quatro limites, duas
    estratégias e dois tipos de banca são dezesseis, e é assim que se escreve no
    relatório — não "testamos algumas variações".
    """

    ev_minimo: float
    estrategia: str
    tipo_banca: str

    @property
    def rotulo(self) -> str:
        return f"EV>{self.ev_minimo:.0%} · {self.estrategia} · banca {self.tipo_banca}"


def grade(
    ev: tuple[float, ...] = GRADE_EV,
    estrategias: tuple[str, ...] = ("stake_fixa", "kelly_fracionado"),
    bancas: tuple[str, ...] = ("fixa", "composta"),
) -> list[Configuracao]:
    """Todas as combinações da grade, na ordem em que o relatório as mostra."""
    return [
        Configuracao(ev_minimo=limite, estrategia=nome, tipo_banca=banca)
        for limite in ev
        for nome in estrategias
        for banca in bancas
    ]


#: Quantas configurações de **aposta** a Fase 6 mede. Soma às 29 configurações
#: de modelo das Fases 3 a 5 (regra 11) e nunca é reescrita para baixo.
N_CONFIGURACOES_FASE_6 = len(grade())


@dataclass(frozen=True)
class Backtest:
    """Tudo o que uma execução do backtest produziu, pronto para o relatório.

    Atributos:
        amostra: de onde as apostas saíram e o que ficou de fora.
        ev_minimo: o corte usado nesta execução.
        apostas: o registro de cada aposta feita.
        resultado: as notas da estratégia do modelo.
        aleatorio: as notas da estratégia aleatória de mesmo tamanho.
        evolucoes: ``{(estratégia, tipo de banca): Evolucao}`` — as quatro
            combinações de dinheiro, sempre as quatro, nunca só a mais bonita.
    """

    amostra: Amostra
    ev_minimo: float
    apostas: pd.DataFrame
    resultado: Resultado
    aleatorio: Resultado
    evolucoes: dict[tuple[str, str], estrategias.Evolucao] = field(
        default_factory=dict
    )


def rodar(
    jogos: pd.DataFrame,
    previsoes: pd.DataFrame,
    cfg: Config,
    ev_minimo: float | None = None,
    banca_inicial: float | None = None,
    amostra: Amostra | None = None,
) -> Backtest:
    """O backtest inteiro de um limite de EV: escolher, medir e simular a banca.

    É a função que o ``scripts/backtest.py`` e o relatório da fase chamam, e ela
    existe para os dois verem **exatamente** o mesmo número. Duas rotas
    diferentes para o mesmo resultado é como um relatório passa a discordar de si
    mesmo sem ninguém perceber.

    Args:
        jogos: a tabela de jogos com odds.
        previsoes: as previsões do walk-forward do modelo oficial.
        cfg: a configuração do projeto.
        ev_minimo: o corte de valor esperado. ``None`` usa o do ``config.yaml``.
        banca_inicial: ``None`` usa a do ``config.yaml``.
        amostra: uma :func:`preparar` já pronta, para varrer vários limites de EV
            sem refazer a parte cara.
    """
    secao = cfg.secao("backtest")
    ev_minimo = float(secao["ev_minimo"]) if ev_minimo is None else float(ev_minimo)
    banca_inicial = (
        float(secao["banca_inicial"]) if banca_inicial is None else float(banca_inicial)
    )
    bootstrap = int(secao.get("bootstrap_amostras", 10_000))

    amostra = preparar(jogos, previsoes, cfg) if amostra is None else amostra
    apostas = selecionar(amostra.candidatos, ev_minimo)

    evolucoes: dict[tuple[str, str], estrategias.Evolucao] = {}
    for nome in ("stake_fixa", "kelly_fracionado"):
        estrategia = estrategias.criar(nome, secao)
        for tipo in estrategias.TIPOS_DE_BANCA:
            evolucoes[(nome, tipo)] = estrategias.simular_banca(
                apostas, estrategia, banca_inicial, tipo
            )

    return Backtest(
        amostra=amostra,
        ev_minimo=ev_minimo,
        apostas=apostas,
        resultado=medir(
            apostas, "modelo", amostras_bootstrap=bootstrap, seed=cfg.seed
        ),
        aleatorio=medir(
            aleatorias(amostra.candidatos, len(apostas), seed=cfg.seed),
            "aleatória",
            amostras_bootstrap=bootstrap,
            seed=cfg.seed,
        ),
        evolucoes=evolucoes,
    )
