"""Múltiplas: juntar várias apostas num bilhete só, e medir o que isso custa.

Uma múltipla (ou *acumulada*) paga o **produto** das odds: três seleções de odd
2,00 viram odd 8,00, e dez reais viram oitenta. É por isso que elas são
irresistíveis, e é por isso que a casa as adora.

Este módulo mede duas coisas, e as duas são más notícias que **se somam**:

1. **A comissão se multiplica.** Se cada seleção carrega 6% de margem, três
   seleções não carregam 6% — carregam ``1,06³ − 1 ≈ 19%``. O preço de um
   bilhete de dez jogos é quase o dobro do valor justo dele. Isso é aritmética,
   não opinião, e :func:`medir_por_tamanho` mostra a curva subindo;
2. **A chance de ganhar mostrada é otimista demais**, e o quanto ela é
   otimista é a pergunta que a especificação chama de o coração da fase (7.1).

⚠️ **O problema da independência, que é o ponto conceitual desta fase.**

A chance de uma múltipla acertar é calculada como o **produto** das chances de
cada seleção. Isso supõe que os jogos são independentes — que o resultado de um
não diz nada sobre o outro. Duas objeções, e o projeto trata cada uma de um
jeito:

- **dentro do mesmo jogo** a correlação é enorme (se o mandante goleia, é bem
  mais provável que tenham saído mais de 2,5 gols). → **Resolvido** pela
  restrição de no máximo **uma seleção por jogo**, que este módulo impõe em
  :func:`melhor_selecao_por_jogo` e não é opcional;
- **entre jogos diferentes** sobra uma correlação menor e real: rodadas com
  muitos gols, efeitos de calendário, e principalmente o **erro compartilhado do
  próprio modelo** — se ele está subestimando gols naquele mês, erra na mesma
  direção em todos os jogos daquela rodada. → **Não resolvido**, e o produto
  simples **superestima** a chance de acertar múltiplas grandes.

⚠️ **O que NÃO conserta isso:** sortear os jogos por Monte Carlo a partir das
matrizes de placar, de forma independente. Se o sorteio é independente, ele
apenas reproduz o produto das probabilidades com ruído amostral a mais — o mesmo
número por um caminho mais caro. (O Monte Carlo continua útil para outra coisa:
a **distribuição do número de acertos**, que o :mod:`futebol.backtest.cash_out`
precisa.)

**O que o projeto faz então: mede o tamanho do erro.** Roda milhares de múltiplas
nas rodadas passadas e compara, por tamanho, a **taxa de acerto real** com a
**taxa prevista**. Se o desvio crescer com o número de seleções, é a correlação
aparecendo — e com um controle que separa as duas explicações possíveis: a mesma
conta é feita com as probabilidades **justas do mercado**, que a Fase 2 mediu
serem bem calibradas jogo a jogo. Se o produto do mercado também errar para
cima, o problema não é do nosso modelo: é da suposição de independência.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from futebol.avaliacao import metricas
from futebol.config import Config

#: As colunas que identificam uma partida. A restrição de "uma seleção por jogo"
#: é aplicada sobre esta chave — e ela inclui a liga porque há clubes homônimos
#: em países diferentes (regra 14).
CHAVE_DO_JOGO: tuple[str, ...] = ("data", "liga", "mandante", "visitante")

#: Uma linha por múltipla montada.
COLUNAS_DA_MULTIPLA: tuple[str, ...] = (
    "data",
    "tamanho",
    "bloco",
    "odd_total",
    "prob_modelo",
    "prob_mercado",
    "prob_implicita",
    "margem_acumulada",
    "ganhou",
    "acertos",
    "retorno_unitario",
)


def limites(cfg: Config) -> dict[str, object]:
    """Os limites da seção ``multiplas`` do ``config.yaml``."""
    secao = cfg.secao("multiplas")
    return {
        "min_selecoes": int(secao.get("min_selecoes", 1)),
        "max_selecoes": int(secao.get("max_selecoes", 10)),
        "odd_minima": float(secao.get("odd_minima_selecao", 1.0)),
        "odd_maxima": float(secao.get("odd_maxima_selecao", 100.0)),
        "uma_por_jogo": bool(secao.get("uma_selecao_por_jogo", True)),
        "beam_width": int(secao.get("beam_width", 50)),
    }


def elegiveis(candidatos: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Descarta as seleções fora da faixa de odd permitida.

    ⚠️ **Por que existe uma faixa.** Nos dois extremos a múltipla deixa de fazer
    sentido:

    - **odd baixa demais** (abaixo de 1,20) quase não move a odd total, e ainda
      assim acrescenta uma chance a mais de o bilhete inteiro morrer. É
      conveniência da casa, não do apostador;
    - **odd alta demais** (acima de 5,00) é onde a comissão explode — a Fase 6
      mediu mais de 21% de margem acima de odd 10. Uma seleção dessas sozinha já
      envenena o bilhete.

    Os dois valores vêm do ``config.yaml`` e nunca foram ajustados olhando
    resultado.
    """
    valores = limites(cfg)
    dentro = (candidatos["odd"] >= valores["odd_minima"]) & (
        candidatos["odd"] <= valores["odd_maxima"]
    )
    return candidatos.loc[dentro].copy()


def melhor_selecao_por_jogo(candidatos: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por partida: a seleção em que o modelo tem mais confiança.

    ⚠️ **Esta função é a restrição de "uma seleção por jogo", e ela não é uma
    preferência de estilo — é o que torna o produto das probabilidades
    defensável.** Os mercados de um mesmo jogo são fortemente correlacionados:
    "mandante vence" e "mais de 2,5 gols" acontecem juntos muito mais do que o
    produto das duas chances sugeriria. Multiplicá-las daria um número errado
    para **mais**, e nenhum teste de probabilidade individual pegaria isso.

    O critério é a probabilidade do modelo, não o valor esperado. São coisas
    diferentes e a Fase 6 mostrou por que a diferença importa: escolher por EV
    empurra a carteira para os azarões, que é onde a casa cobra mais caro. Numa
    múltipla isso seria fatal — cada azarão a mais multiplica a chance de o
    bilhete inteiro morrer.
    """
    ordenados = candidatos.sort_values("prob", ascending=False)
    return ordenados.drop_duplicates(subset=list(CHAVE_DO_JOGO), keep="first")


def montar_da_rodada(da_rodada: pd.DataFrame, tamanho: int) -> list[pd.DataFrame]:
    """Reparte as seleções de uma data em múltiplas **disjuntas** de ``tamanho``.

    As seleções entram ordenadas da mais provável para a menos provável e são
    cortadas em blocos: o primeiro bilhete leva os maiores favoritos da rodada, o
    segundo os seguintes, e assim por diante. A sobra é descartada.

    ⚠️ **Por que blocos disjuntos, e não uma múltipla só por rodada.** Duas
    razões, e as duas são sobre honestidade estatística:

    - **amostra.** Uma múltipla por data daria mil bilhetes por tamanho, e com
      uma chance de acerto de 1% num bilhete de dez jogos isso não mede nada.
      Os blocos dão milhares;
    - **independência entre os bilhetes de uma mesma rodada.** Se dois bilhetes
      do mesmo sábado compartilhassem partidas, o acerto de um estaria amarrado
      ao do outro, e o intervalo de confiança sairia mais estreito do que a
      realidade — o erro clássico de contar a mesma informação duas vezes.

    O que **não** é resolvido por isso é a correlação entre jogos diferentes da
    mesma rodada. Essa é a limitação do módulo inteiro, e é ela que a fase mede
    em vez de esconder.
    """
    ordenadas = da_rodada.sort_values("prob", ascending=False)
    quantos = len(ordenadas) // tamanho
    return [ordenadas.iloc[i * tamanho : (i + 1) * tamanho] for i in range(quantos)]


def resumir(pernas: pd.DataFrame, tamanho: int, bloco: int) -> dict[str, object]:
    """As contas de uma múltipla, a partir das seleções que a compõem.

    O que cada probabilidade quer dizer:

    - ``prob_modelo`` — o produto das chances **segundo o modelo**. É o número
      que um app de apostas mostraria como "sua chance de ganhar", e é ele que a
      validação histórica põe à prova;
    - ``prob_mercado`` — o mesmo produto, com as chances **justas do mercado**
      (sem a comissão). Serve de controle: o mercado é bem calibrado jogo a jogo
      (medido na Fase 2), então se este produto também errar para cima, o
      problema é a suposição de independência, não o modelo;
    - ``prob_implicita`` — o produto de ``1/odd``, ou seja, a chance que o
      **preço** sugere. Ela já inclui a comissão, e por isso é sempre menor que
      a justa;
    - ``margem_acumulada`` — quanto a casa cobra no bilhete inteiro:
      ``prob_implícita / prob_justa − 1``. Numa múltipla os fatores de comissão
      se multiplicam, e é esta linha que mostra isso acontecendo.
    """
    odds = pernas["odd"].to_numpy(float)
    prob_modelo = float(np.prod(pernas["prob"].to_numpy(float)))
    justas = pernas["prob_justa"].to_numpy(float)
    prob_mercado = float(np.prod(justas)) if np.isfinite(justas).all() else float("nan")
    prob_implicita = float(np.prod(1.0 / odds))
    odd_total = float(np.prod(odds))
    acertos = int(pernas["ganhou"].to_numpy(bool).sum())
    ganhou = acertos == tamanho
    return {
        "data": pernas["data"].iloc[0],
        "tamanho": tamanho,
        "bloco": bloco,
        "odd_total": odd_total,
        "prob_modelo": prob_modelo,
        "prob_mercado": prob_mercado,
        "prob_implicita": prob_implicita,
        "margem_acumulada": (
            prob_implicita / prob_mercado - 1.0 if prob_mercado > 0 else float("nan")
        ),
        "ganhou": ganhou,
        "acertos": acertos,
        "retorno_unitario": odd_total - 1.0 if ganhou else -1.0,
    }


@dataclass(frozen=True)
class Historico:
    """As múltiplas montadas nas rodadas passadas, e as seleções de cada uma.

    Atributos:
        multiplas: uma linha por bilhete, com as colunas de
            :data:`COLUNAS_DA_MULTIPLA` mais um ``id``.
        pernas: uma linha por seleção, com o ``id`` do bilhete a que ela
            pertence e a ``ordem`` dela dentro dele.

    As duas tabelas existem porque respondem coisas diferentes: a medição por
    tamanho só precisa do resumo, e o cash out precisa saber **quais** seleções
    já se resolveram e quais faltam.
    """

    multiplas: pd.DataFrame
    pernas: pd.DataFrame


def montar_historico(
    candidatos: pd.DataFrame,
    cfg: Config,
    tamanhos: range | tuple[int, ...] | None = None,
) -> Historico:
    """Monta milhares de múltiplas nas rodadas passadas, de cada tamanho.

    Args:
        candidatos: a saída de :func:`futebol.backtest.simulador.preparar`.
        cfg: a configuração, de onde saem os limites de odd e de tamanho.
        tamanhos: quais tamanhos montar. ``None`` usa de 2 até ``max_selecoes``
            (bilhete de uma seleção só não é múltipla — é uma aposta simples, e
            a Fase 6 já mediu essas).

    Retorna:
        Um :class:`Historico`.
    """
    valores = limites(cfg)
    if tamanhos is None:
        tamanhos = range(2, valores["max_selecoes"] + 1)

    por_jogo = melhor_selecao_por_jogo(elegiveis(candidatos, cfg))
    linhas: list[dict[str, object]] = []
    partes: list[pd.DataFrame] = []
    for _, da_rodada in por_jogo.groupby("data", sort=True):
        for tamanho in tamanhos:
            for bloco, pernas in enumerate(montar_da_rodada(da_rodada, tamanho)):
                identificador = len(linhas)
                linhas.append({"id": identificador, **resumir(pernas, tamanho, bloco)})
                partes.append(
                    pernas.assign(id=identificador, ordem=np.arange(len(pernas)))
                )

    if not linhas:
        raise ValueError(
            "Nenhuma múltipla montada. Confira a faixa de odd em 'multiplas' no "
            "config.yaml e se a tabela de candidatos tem jogos."
        )
    return Historico(
        multiplas=pd.DataFrame(linhas, columns=["id", *COLUNAS_DA_MULTIPLA]),
        pernas=pd.concat(partes, ignore_index=True),
    )


# ----------------------------------------------------------------------------
# A medição — o coração da fase (7.4)
# ----------------------------------------------------------------------------
def medir_por_tamanho(
    multiplas: pd.DataFrame, amostras_bootstrap: int = 2000, seed: int = 42
) -> pd.DataFrame:
    """Taxa real × taxa prevista, ROI e margem, tamanho a tamanho.

    É a tabela que a especificação chama de obrigatória, e cada coluna responde
    uma pergunta diferente:

    - ``prevista_modelo`` contra ``real`` — a múltipla acerta tanto quanto o
      modelo promete? O ``desvio`` é a diferença, e o intervalo de confiança dele
      sai por bootstrap **emparelhado**: para cada bilhete, ``ganhou − prevista``.
      Emparelhar importa porque os bilhetes têm probabilidades muito diferentes
      entre si, e comparar duas médias soltas jogaria essa variação toda no erro;
    - ``prevista_mercado`` — o mesmo produto, feito com as probabilidades justas
      do mercado. É o controle que separa "o modelo está errado" de "a suposição
      de independência está errada";
    - ``margem`` — a comissão acumulada. Deve crescer com o tamanho, e cresce;
    - ``roi`` — o resultado em dinheiro de apostar 1 unidade em cada bilhete.

    ⚠️ **Como ler o desvio.** Se ele for negativo (real abaixo da prevista) e
    **crescer em módulo** com o tamanho da múltipla, é a correlação entre jogos
    aparecendo: o produto simples supõe independência, e a falta dela sempre
    empurra a chance real para baixo em bilhetes grandes.
    """
    linhas = []
    for tamanho, do_tamanho in multiplas.groupby("tamanho", sort=True):
        ganhou = do_tamanho["ganhou"].to_numpy(bool).astype(float)
        prevista = do_tamanho["prob_modelo"].to_numpy(float)
        do_mercado = do_tamanho["prob_mercado"].to_numpy(float)
        retornos = do_tamanho["retorno_unitario"].to_numpy(float)

        desvios = ganhou - prevista
        desvios_mercado = ganhou - do_mercado
        ic_desvio = metricas.bootstrap_ic(desvios, amostras=amostras_bootstrap, seed=seed)
        ic_mercado = metricas.bootstrap_ic(
            desvios_mercado, amostras=amostras_bootstrap, seed=seed
        )
        ic_roi = metricas.bootstrap_ic(retornos, amostras=amostras_bootstrap, seed=seed)

        media_prevista = float(prevista.mean())
        media_mercado = float(np.nanmean(do_mercado))
        linhas.append(
            {
                "tamanho": int(tamanho),
                "multiplas": len(do_tamanho),
                "odd_total": float(do_tamanho["odd_total"].mean()),
                "prevista_modelo": media_prevista,
                "prevista_mercado": media_mercado,
                "real": float(ganhou.mean()),
                "acertos": int(ganhou.sum()),
                "desvio": float(desvios.mean()),
                "desvio_baixo": ic_desvio[0],
                "desvio_alto": ic_desvio[1],
                # O desvio em porcentagem da própria previsão. Sem ele, a tabela
                # engana: -0,026 num bilhete que promete 36% e -0,0001 num que
                # promete 0,96% parecem "o erro encolheu", quando o primeiro é
                # 7% de exagero e o segundo é 1%.
                "desvio_relativo": (
                    float(desvios.mean()) / media_prevista if media_prevista else np.nan
                ),
                "desvio_mercado": float(desvios_mercado.mean()),
                "desvio_mercado_baixo": ic_mercado[0],
                "desvio_mercado_alto": ic_mercado[1],
                "desvio_mercado_relativo": (
                    float(desvios_mercado.mean()) / media_mercado
                    if media_mercado
                    else np.nan
                ),
                # Regra 10: "não deu diferença" só quer dizer algo ao lado de
                # "esta amostra enxergaria uma diferença de tanto". Num bilhete
                # de dez jogos que acerta 0,6% das vezes, o ruído é enorme em
                # termos relativos, e sem esta coluna o "não detectei correlação"
                # soaria muito mais forte do que ele é.
                "detectavel_relativo": (
                    metricas.efeito_detectavel(
                        len(desvios_mercado), float(desvios_mercado.std(ddof=1))
                    )
                    / media_mercado
                    if media_mercado
                    else np.nan
                ),
                # ⚠️ A coluna que separa as duas explicações possíveis para o
                # desvio. Se o modelo exagera a chance de **cada** seleção por um
                # fator fixo `r`, então num bilhete de `k` pernas o exagero é
                # `r^k` — e esta razão, que é a k-ésima raiz dele, sai constante
                # em todos os tamanhos. Se ela **cair** conforme o bilhete
                # cresce, aí sim há algo além do erro por perna: correlação.
                "razao_por_selecao": (
                    (media_mercado / media_prevista) ** (1.0 / tamanho)
                    if media_prevista > 0
                    else np.nan
                ),
                "margem": float(do_tamanho["margem_acumulada"].mean()),
                "margem_por_selecao": float(
                    (1.0 + do_tamanho["margem_acumulada"].mean()) ** (1.0 / tamanho)
                    - 1.0
                ),
                "roi": float(retornos.mean()),
                "roi_baixo": ic_roi[0],
                "roi_alto": ic_roi[1],
            }
        )
    return pd.DataFrame(linhas)


def margem_teorica(margem_por_selecao: float, tamanho: int) -> float:
    """A comissão acumulada que a aritmética prevê: ``(1 + m)ⁿ − 1``.

    Serve para o relatório poder dizer "o medido bate com a conta". Com 6% por
    seleção, uma dupla custa 12,4%, um bilhete de cinco custa 33,8% e um de dez
    custa 79,1% — e nada disso depende de modelo nenhum.
    """
    return float((1.0 + margem_por_selecao) ** tamanho - 1.0)
