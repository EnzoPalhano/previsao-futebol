"""O relatório da Fase 5: o LightGBM valeu a pena?

Este módulo não mede nada — ele **conta** o que
:mod:`futebol.avaliacao.selecao` mediu, lendo o mesmo cache que
``scripts/validar.py`` gravou. Separar medir de relatar é o que permite ajustar
o texto sem esperar meia hora de walk-forward, e é o que garante que o número do
relatório e o número da escolha oficial são o mesmo número.

⚠️ Uma fase pode terminar em "não". A especificação pede "a tabela da Fase 4
atualizada com o LightGBM" — não pede que o LightGBM ganhe. Um resultado
negativo, medido direito, vale tanto quanto um positivo: ele impede o projeto de
carregar complexidade que não paga.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from futebol import relatorio
from futebol.avaliacao import selecao, validacao
from futebol.config import Config

#: O que cada feature quer dizer, em português de gente. A especificação pede
#: que a importância venha explicada — um gráfico com vinte e três nomes
#: técnicos é uma figura, não uma explicação.
O_QUE_CADA_FEATURE_SIGNIFICA: dict[str, str] = {
    "dc_H": "chance de vitória do mandante, segundo o Dixon-Coles",
    "dc_D": "chance de empate, segundo o Dixon-Coles",
    "dc_A": "chance de vitória do visitante, segundo o Dixon-Coles",
    "dc_over25": "chance de sair mais de 2,5 gols, segundo o Dixon-Coles",
    "elo_mandante": "rating Elo do mandante antes do jogo",
    "elo_visitante": "rating Elo do visitante antes do jogo",
    "elo_diferenca": "quanto o mandante é melhor que o visitante, em pontos de Elo",
    "pontos5_mandante": "pontos que o mandante somou nos últimos 5 jogos dele",
    "pontos5_visitante": "pontos que o visitante somou nos últimos 5 jogos dele",
    "historico_mandante": "quantos jogos o mandante já tem de história",
    "historico_visitante": "quantos jogos o visitante já tem de história",
    "gols_feitos5_mandante": "gols que o mandante fez, por jogo, nos últimos 5 EM CASA",
    "gols_feitos10_mandante": "o mesmo, nos últimos 10 em casa",
    "gols_sofridos5_mandante": "gols que o mandante tomou, por jogo, nos últimos 5 em casa",
    "gols_sofridos10_mandante": "o mesmo, nos últimos 10 em casa",
    "gols_feitos5_visitante": "gols que o visitante fez, por jogo, nos últimos 5 FORA",
    "gols_feitos10_visitante": "o mesmo, nos últimos 10 fora",
    "gols_sofridos5_visitante": "gols que o visitante tomou, por jogo, nos últimos 5 fora",
    "gols_sofridos10_visitante": "o mesmo, nos últimos 10 fora",
    "descanso_mandante": "dias desde o jogo anterior do mandante",
    "descanso_visitante": "dias desde o jogo anterior do visitante",
    "descanso_diferenca": "quantos dias de descanso o mandante teve a mais",
    "estadio_vazio": "o jogo foi no período de portões fechados pela pandemia",
}

#: Os nomes dos candidatos da Fase 5, na ordem em que o relatório fala deles.
DA_FASE_5: tuple[str, ...] = ("gbm", "gbm-raso", "gbm-sem-dc")

#: Nome do mercado nas tabelas, igual ao da Fase 4.
NOME_MERCADO = "mercado (fechamento)"


def montar(
    cfg: Config,
    liberados: pd.DataFrame,
    previsoes: dict[str, pd.DataFrame],
    importancia: pd.DataFrame,
    caminho_importancia: Path,
    janela: tuple[pd.Timestamp, pd.Timestamp],
    gerado_em: str,
) -> str:
    """O relatório inteiro, em Markdown."""
    do_mercado = validacao.previsoes_do_mercado(
        liberados.loc[
            (liberados["data"] >= janela[0]) & (liberados["data"] < janela[1])
        ]
    )
    medidas, alinhados = validacao.medir_nos_mesmos_jogos(
        {**previsoes, NOME_MERCADO: do_mercado}
    )
    por_nome = {m.nome: m for m in medidas}
    campeao_fase4 = min(
        (m for m in medidas if m.nome not in DA_FASE_5 and m.nome != NOME_MERCADO),
        key=lambda m: m.log_loss,
    )
    melhor_gbm = min(
        (por_nome[nome] for nome in DA_FASE_5 if nome in por_nome),
        key=lambda m: m.log_loss,
    )
    return "\n\n".join(
        [
            _cabecalho(cfg, liberados, janela, medidas, gerado_em),
            _resposta(campeao_fase4, melhor_gbm, alinhados),
            _tabela(medidas),
            _comparacoes(alinhados, por_nome),
            _importancia(importancia, caminho_importancia),
            _veredito(campeao_fase4, melhor_gbm),
            _pre_registro(previsoes, gerado_em),
        ]
    )


def _cabecalho(cfg, liberados, janela, medidas, gerado_em) -> str:
    grupo1 = sorted(liberados.loc[liberados["grupo"] == "grupo1", "liga"].unique())
    grupo2 = sorted(liberados.loc[liberados["grupo"] == "grupo2", "liga"].unique())
    n = medidas[0].n
    return f"""# Fase 5 — Features e machine learning

- Camada de ligas: **{cfg.camada_ativa}**
- Janela de validação: **{janela[0].date()} a {janela[1].date()}** — a mesma da Fase 4
- Jogos avaliados: **{relatorio.inteiro(n)}**, os mesmos para todos os modelos
- Grupo 1 — backtest e CLV ({len(grupo1)}): {", ".join(grupo1)}
- Grupo 2 — treino e calibração ({len(grupo2)}): {", ".join(grupo2)}
- Gerado em: {gerado_em}

> **Regra 13.** Onde não estiver escrito o contrário, o número é das
> **{len(grupo1) + len(grupo2)} competições**. Aposta é outra história: ali
> valem só as 18 ligas aprovadas na Fase 2 (regra 12).

> **Regra 9.** A escolha continua sendo por **log loss** no walk-forward de
> validação. Um modelo novo não entra por ser novo, nem por ser sofisticado.

> **Regra 11.** As três configurações desta fase **somam** às 26 anteriores.
> Toda configuração testada é uma chance a mais de a melhor estar na frente por
> acaso, e é por isso que elas são contadas."""


def _resposta(campeao_fase4, melhor_gbm, alinhados) -> str:
    diferenca = validacao.comparar(
        alinhados[melhor_gbm.nome], alinhados[campeao_fase4.nome]
    )
    return f"""## A resposta, primeiro

A pergunta da fase era: **dar ao modelo vinte e três informações em vez de só os
placares faz ele prever melhor?**

A resposta medida é **não** — e, mais exatamente, *não deu para distinguir*. O
melhor LightGBM (`{melhor_gbm.nome}`, log loss
{relatorio.num(melhor_gbm.log_loss)}) ficou atrás do campeão da Fase 4
(`{campeao_fase4.nome}`, {relatorio.num(campeao_fase4.log_loss)}), e a diferença
entre os dois, medida jogo a jogo:

**{diferenca.como_texto()}**

Então o modelo do projeto **não muda**: `xi`, `jogos_equivalentes` e o fator casa
continuam exatamente como a Fase 4 os deixou. O único acréscimo ao `config.yaml`
nesta fase foi a `vantagem_casa` do Elo (50 pontos), que é parâmetro de
**feature** e não entra em nenhuma previsão oficial. O LightGBM fica no
repositório como o que ele é: uma hipótese que foi testada direito e não se
sustentou.

⚠️ **Isso não é um fracasso da fase; é o produto dela.** Uma fase que só
pudesse terminar em "sim" não seria uma medição, seria uma encenação. O que se
comprou aqui foi a informação de que a complexidade não paga — e o direito de
não carregá-la nas Fases 6 a 9."""


def _tabela(medidas) -> str:
    tabela = pd.DataFrame(
        [
            {
                "quem": m.nome,
                "fase": "5" if m.nome in DA_FASE_5 else ("—" if m.nome == NOME_MERCADO else "4"),
                "jogos": m.n,
                "log_loss": m.log_loss,
                "brier": m.brier,
                "acuracia": m.acuracia,
                "ece": m.ece,
            }
            for m in sorted(medidas, key=lambda m: m.log_loss)
        ]
    )
    corpo = relatorio.de_dataframe(
        tabela,
        {
            "quem": "Quem prevê",
            "fase": "Fase",
            "jogos": "Jogos",
            "log_loss": "Log loss (1X2)",
            "brier": "Brier",
            "acuracia": "Acurácia",
            "ece": "ECE",
        },
        {
            "jogos": "inteiro",
            "log_loss": "num",
            "brier": "num",
            "acuracia": "pct",
            "ece": "num",
        },
    )
    return f"""## A tabela da Fase 4, atualizada

Todos medidos nas mesmas partidas. Menor é melhor em log loss, Brier e ECE.

{corpo}

Duas coisas que a tabela mostra e que vale dizer em voz alta:

**1. O LightGBM entrou no meio do pelotão do Dixon-Coles, não acima dele.** As
variantes `gbm` e `gbm-raso` caíram exatamente na faixa em que já estavam as
variações de `xi` do modelo de gols — ou seja, onde nada é distinguível de nada.

**2. A calibração do LightGBM é pior.** O ECE dele é cerca do dobro do
Dixon-Coles. Faz sentido: uma árvore prevê por médias de grupos de jogos
parecidos, e nas pontas ela extrapola mal. Isso importaria muito se ele fosse o
escolhido, porque o valor esperado de uma aposta é calculado **com a
probabilidade do modelo** — probabilidade inflada vira aposta que não existe. A
especificação previa calibrar (isotônica ou Platt) "se necessário"; como o
modelo não entrou, calibrá-lo seria trabalho para melhorar algo que não vai ser
usado, e **cada** variante calibrada custaria mais uma configuração na regra 11."""


def _comparacoes(alinhados, por_nome) -> str:
    perguntas = [
        (
            "O LightGBM completo bate o Dixon-Coles com o mesmo `xi`?",
            "gbm",
            "dixon-coles",
        ),
        ("E a variante regularizada, contra o campeão?", "gbm-raso", "dc-xi-0.003"),
        (
            "Quanto vale entregar o Dixon-Coles de bandeja ao LightGBM?",
            "gbm-sem-dc",
            "gbm",
        ),
        (
            "As dezenove features, sozinhas, valem mais que um Poisson?",
            "poisson",
            "gbm-sem-dc",
        ),
    ]
    blocos = []
    for pergunta, pior, melhor in perguntas:
        if pior not in alinhados or melhor not in alinhados:
            continue
        diferenca = validacao.comparar(alinhados[pior], alinhados[melhor])
        blocos.append(
            f"**{pergunta}**\n\n`{melhor}` contra `{pior}`:\n\n"
            f"> {diferenca.como_texto()}"
        )
    corpo = "\n\n".join(blocos)
    return f"""## As quatro perguntas, com incerteza

Ordenar uma tabela não responde nada: com 36 mil jogos, diferença de log loss
abaixo de ~0,0015 não é mensurável. Cada linha abaixo é a diferença **emparelhada
jogo a jogo**, com intervalo de confiança e o menor efeito que a amostra
conseguiria detectar (regra 10).

{corpo}

**A leitura conjunta.** As duas primeiras perguntas dão empate técnico: o
LightGBM não é melhor nem pior que o modelo de gols, e a amostra não consegue
separá-los. As duas últimas, sim, dão diferença real — e é nelas que está o
aprendizado da fase:

- tirar o Dixon-Coles das features **piora muito** o LightGBM. Quase todo o
  conhecimento dele vem de lá;
- mas as outras features não são inúteis: sozinhas, elas batem o Poisson. Elas
  têm sinal — só não têm sinal **além** do que o Dixon-Coles já capturou.

⚠️ **A quarta comparação pede uma ressalva, e ela ensina uma coisa de
estatística que vale carregar para as próximas fases.** Repare que ali o efeito
medido é **menor** que o "menor efeito detectável", e mesmo assim o intervalo de
confiança não cruza o zero. Os dois números não se contradizem porque respondem a
perguntas diferentes: o intervalo usa 1,96 erros-padrão e pergunta *este efeito
apareceu?*; o menor efeito detectável usa 2,8 e pergunta *esta amostra teria 80%
de chance de enxergar um efeito deste tamanho, se ele existisse?*. Aqui a
resposta é "apareceu, mas a amostra teria boa chance de não ter visto". É um
achado **frágil**: sustenta dizer que as features têm algum sinal, e não sustenta
nenhuma afirmação sobre o tamanho desse sinal.

Ou seja: o LightGBM não descobriu nada sobre futebol que o modelo de gols não
soubesse. Ele redescobriu o modelo de gols, com mais peças móveis."""


def _importancia(importancia: pd.DataFrame, caminho: Path) -> str:
    por_familia = (
        importancia.groupby("familia")["pct"].sum().sort_values(ascending=False)
    )
    linhas_familia = "\n".join(
        f"| {familia} | {relatorio.pct(valor / 100)} |"
        for familia, valor in por_familia.items()
    )
    topo = importancia.head(8)
    linhas_topo = "\n".join(
        f"| `{linha['feature']}` | {relatorio.pct(linha['pct'] / 100)} | "
        f"{O_QUE_CADA_FEATURE_SIGNIFICA.get(linha['feature'], '—')} |"
        for _, linha in topo.iterrows()
    )
    return f"""## De onde o LightGBM tira o que ele sabe

![Importância das features]({caminho.name})

Somando por família de feature:

| Família | Participação no ganho |
|---|---|
{linhas_familia}

E as oito colunas mais usadas, com o que cada uma quer dizer:

| Feature | Ganho | O que é |
|---|---|---|
{linhas_topo}

⚠️ **Importância não é utilidade, e a confusão entre as duas é a armadilha mais
comum quando se olha um gráfico desses.** O "ganho" mede quanto as divisões
naquela coluna reduziram o erro **dentro do treino**. Uma coluna contínua e cheia
de valores distintos dá à árvore muitos lugares onde cortar e aparece alto por
isso; e duas colunas que dizem a mesma coisa dividem o crédito, de modo que
importância baixa pode significar "redundante", não "inútil".

O que responde de verdade "esta feature paga?" é **tirá-la e medir de novo** — e
foi exatamente isso que a variante `gbm-sem-dc` fez. As duas leituras concordam,
e é essa concordância que dá confiança na conclusão: o gráfico diz que as quatro
colunas do Dixon-Coles respondem por
{relatorio.pct(por_familia.get("Dixon-Coles", 0.0) / 100)} do ganho, e a medição
independente diz que tirá-las custa log loss de verdade."""


def _veredito(campeao_fase4, melhor_gbm) -> str:
    return f"""## O que muda no projeto

**Nada nos parâmetros do modelo.** O modelo oficial continua sendo
`{campeao_fase4.nome}` — Dixon-Coles com `xi = 0,003` e `m = 6`, escolhido na
Fase 4 pela regra 9 e confirmado aqui contra três adversários novos.

O que a fase deixa no repositório, e que segue valendo:

- **o Elo** (`futebol/modelos/elo.py`), com a atualização por bloco de data;
- **as features** (`futebol/features/construtor.py`), 23 colunas causais, com o
  teste que prova que apagar o futuro não muda o passado;
- **o LightGBM** (`futebol/modelos/gbm.py`), que continua medível a qualquer
  momento com `validar.py --com-gbm`.

Nenhuma dessas peças é desperdício mesmo com o veredito negativo. As features e
o Elo são exatamente o que a **Fase 7** vai precisar quando entrar informação
que o placar não tem — desfalque, escalação, notícia — e é aí que um modelo de
árvore tem chance real de saber algo que o modelo de gols não sabe. O que a
Fase 5 mostrou é que, **com o que existe hoje na tabela**, esse algo não existe.

⚠️ **O limite honesto desta conclusão.** Ela vale para o que foi testado: um GBM
de gols, com estas 23 features, retreinado a cada 30 dias, medido em log loss de
1X2. Um GBM que aprendesse 1X2 diretamente poderia ir melhor **no 1X2** — foi
uma troca consciente, feita para manter todo mercado saindo da mesma matriz de
placares. Não se testou isso, e o relatório não afirma o que não mediu."""


def _pre_registro(previsoes: dict, gerado_em: str) -> str:
    return f"""## Pré-registro (regra 11)

| | |
|---|---|
| Configurações testadas até aqui | **{13 + selecao.N_CONFIGURACOES_FASE_4 + len(DA_FASE_5)}** — 13 exploratórias (Fase 3) + {selecao.N_CONFIGURACOES_FASE_4} oficiais (Fase 4) + {len(DA_FASE_5)} (Fase 5) |
| Configuração escolhida | `{{'modelo': 'dixon-coles', 'xi': 0.003, 'm': 6.0}}` — **inalterada** |
| Critério | log loss no walk-forward de validação (regra 9) |
| Disputaram nesta fase | {len(previsoes)} configurações, todas nos mesmos jogos |
| Data | {gerado_em} |

O número sobe e **nunca** é reescrito para baixo. Ele existe para que a Fase 9,
ao abrir o teste final uma única vez, saiba quantas chances o projeto deu a si
mesmo de encontrar um vencedor por acaso."""
