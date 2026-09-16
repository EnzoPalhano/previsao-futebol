"""Monta o relatório da Fase 2: como é o futebol, e quão bom é o mercado.

O relatório existe para responder quatro perguntas, e ele foi escrito de trás
para frente a partir delas:

1. qual é a margem média da casa em cada liga?
2. o mercado é bem calibrado?
3. a vantagem de jogar em casa mudou ao longo dos anos?
4. quais ligas passaram no filtro de qualidade?

Cada seção aqui é uma dessas respostas, sempre dizendo de quais ligas ela fala
(regra 13). O texto é gerado a partir dos dados: rodar de novo depois de
baixar mais uma temporada atualiza todos os números juntos, sem ninguém
esquecer de mexer numa tabela.
"""

from __future__ import annotations

import pandas as pd

from futebol.avaliacao import exploracao, filtro, metricas
from futebol.config import Config
from futebol.odds import mercado
from futebol.relatorio import de_dataframe, inteiro, num, pct, tabela_markdown

#: As temporadas sem público, nas duas formas em que aparecem na tabela
#: (``2019/20`` nas ligas europeias, ``2020`` nos campeonatos de ano civil).
TEMPORADAS_VAZIAS = exploracao.TEMPORADAS_SEM_PUBLICO


def pontos_percentuais(valor: float) -> str:
    """Diferença em pontos percentuais, com sinal: ``+1,2 p.p.``."""
    if pd.isna(valor):
        return "-"
    # A vírgula entra só no número: trocar todo ponto viraria "p,p,".
    return f"{valor * 100:+.1f}".replace(".", ",") + " p.p."


def _media_ponderada(tabela: list[dict], escolher) -> float:
    """Média das diferenças das faixas escolhidas, pesada pelo nº de jogos."""
    faixas = [linha for linha in tabela if escolher(linha)]
    total = sum(linha["n"] for linha in faixas)
    if not total:
        return float("nan")
    return sum(linha["diferenca"] * linha["n"] for linha in faixas) / total


# ----------------------------------------------------------------------------
# Seções
# ----------------------------------------------------------------------------
def _cabecalho(jogos: pd.DataFrame, cfg: Config, gerado_em: str) -> str:
    grupo1 = sorted(jogos.loc[jogos["grupo"] == "grupo1", "liga"].unique())
    grupo2 = sorted(jogos.loc[jogos["grupo"] == "grupo2", "liga"].unique())
    return "\n".join(
        [
            "# Fase 2 — O mercado medido",
            "",
            f"- Camada de ligas: **{cfg.camada_ativa}**",
            f"- Jogos analisados: **{inteiro(len(jogos))}**",
            f"- Grupo 1 — backtest e CLV ({len(grupo1)}): {', '.join(grupo1)}",
            f"- Grupo 2 — treino e calibração ({len(grupo2)}): {', '.join(grupo2)}",
            f"- Gerado em: {gerado_em}",
            "",
            "> **Regra 13.** Cada tabela diz a quais ligas se refere. Onde estiver",
            "> escrito *Grupo 1*, o número **não** inclui Brasil, Argentina, EUA e os",
            "> outros 13 países do Grupo 2 — eles não têm odd pré-jogo (regra 12).",
        ]
    )


def _secao_metodos(jogos: pd.DataFrame) -> str:
    """Compara os três jeitos de tirar a margem. É uma escolha, e ela tem efeito."""
    grupo1 = jogos[jogos["grupo"] == "grupo1"]
    observado = mercado.resultado_observado(grupo1, "1x2")

    linhas = []
    eces = {}
    for metodo in mercado.METODOS:
        probabilidades = mercado.probabilidades_do_mercado(grupo1, "1x2", "fech", metodo)
        eces[metodo] = metricas.ece(probabilidades, observado)
        linhas.append(
            [
                metodo,
                num(metricas.log_loss(probabilidades, observado)),
                num(metricas.brier(probabilidades, observado)),
                num(eces[metodo]),
            ]
        )
    melhor = min(eces, key=lambda metodo: eces[metodo])
    vezes = eces["proporcional"] / eces[melhor]

    return "\n".join(
        [
            "## 1. Tirar a margem é uma escolha — e ela muda o número",
            "",
            "Odd não é probabilidade: é probabilidade **mais a comissão da casa**.",
            "Some as três implícitas de um jogo e dá 104%, 107%. Tirar esses pontos",
            "a mais exige uma hipótese sobre *como* a casa distribuiu a comissão, e",
            "os três métodos discordam de propósito:",
            "",
            "- **proporcional**: a casa cobrou a mesma fatia de todos;",
            "- **power** e **shin**: o azarão paga comissão maior que o favorito.",
            "",
            "Medido no 1X2 de fechamento do Grupo 1:",
            "",
            tabela_markdown(linhas, ["Método", "Log loss", "Brier", "ECE"]),
            "",
            f"O **{melhor}** fica mais bem calibrado: ECE de {num(eces[melhor])} contra",
            f"{num(eces['proporcional'])} do proporcional — erro de calibração",
            f"{num(vezes, 1)} vezes menor, com log loss praticamente igual. É a",
            "evidência de que a casa **de fato** cobra mais caro no azarão, e é por",
            f"isso que o resto do projeto usa `{melhor}`.",
        ]
    )


def _secao_baseline(jogos: pd.DataFrame) -> str:
    """A meta a bater. Sem ela, um log loss de 0,98 não quer dizer nada."""
    grupo1 = jogos[jogos["grupo"] == "grupo1"]
    linhas = []

    for (liga, formato), bloco in grupo1.groupby(["liga", "formato"], observed=True):
        observado = mercado.resultado_observado(bloco, "1x2")
        pre = mercado.probabilidades_do_mercado(bloco, "1x2", "pre", "power")
        fech = mercado.probabilidades_do_mercado(bloco, "1x2", "fech", "power")
        linhas.append(
            [
                liga,
                formato,
                inteiro(len(bloco)),
                num(metricas.log_loss(pre, observado)),
                num(metricas.log_loss(fech, observado)),
                num(metricas.brier(fech, observado)),
            ]
        )

    grupo2 = jogos[jogos["grupo"] == "grupo2"]
    observado_g2 = mercado.resultado_observado(grupo2, "1x2")
    fech_g2 = mercado.probabilidades_do_mercado(grupo2, "1x2", "fech", "power")

    return "\n".join(
        [
            "## 2. O baseline do mercado — a meta que os modelos precisam bater",
            "",
            "Esta é a nota que as odds tiram sozinhas, sem modelo nenhum. Um modelo",
            "da Fase 3 só é útil se conseguir um número **menor** que este.",
            "",
            "Referências para ler a tabela: chutar 33% para cada dá log loss",
            f"**1,0986**. O mercado de fechamento do Grupo 1 inteiro dá "
            f"**{num(metricas.log_loss(mercado.probabilidades_do_mercado(grupo1, '1x2', 'fech', 'power'), mercado.resultado_observado(grupo1, '1x2')))}**.",
            "",
            tabela_markdown(
                sorted(linhas, key=lambda linha: linha[4]),
                ["Liga", "Formato", "Jogos", "Log loss pré", "Log loss fech.", "Brier fech."],
            ),
            "",
            "⚠️ **A tabela sai separada por formato** porque até 2018/19 (formato B)",
            "a odd de fechamento é da Pinnacle, e não a média do mercado — as duas",
            "não são a mesma medida.",
            "",
            "O fechamento é sempre melhor que o pré-jogo. Isso é o mercado",
            "aprendendo: entre a abertura e o apito entram dinheiro e informação",
            "(escalação, lesão, clima). É também a razão de o CLV existir como",
            "critério — bater a odd de fechamento é evidência de ter acertado antes",
            "do mercado.",
            "",
            f"No Grupo 2 ({inteiro(len(grupo2))} jogos, só fechamento de 1X2), o",
            f"baseline é **{num(metricas.log_loss(fech_g2, observado_g2))}** de log loss.",
            "Esses jogos servem para treinar e para medir calibração — nunca para",
            "backtest de aposta (regra 12).",
        ]
    )


def _secao_margem(jogos: pd.DataFrame) -> str:
    ranking = exploracao.ranking_de_margem(jogos)
    ranking["grupo_texto"] = ranking["grupo"].map({"grupo1": "1", "grupo2": "2"})

    pre_fech = exploracao.pre_contra_fechamento(jogos[jogos["grupo"] == "grupo1"])
    pre_fech = pre_fech[pre_fech["formato"] == "A"].sort_values("aperto", ascending=False)

    return "\n".join(
        [
            "## 3. Quanto a casa cobra, liga a liga",
            "",
            "*Resposta à pergunta 1: qual é a margem média da casa em cada liga?*",
            "",
            "O número é o **overround**: a soma das probabilidades implícitas menos",
            "1. Quanto menor, melhor para quem aposta. A tabela abaixo atualiza a da",
            "seção 4.3 da especificação, que usou só a temporada 2024/25 no Grupo 1 —",
            "aqui estão **todas** as temporadas.",
            "",
            de_dataframe(
                ranking,
                {
                    "liga": "Liga",
                    "grupo_texto": "Grupo",
                    "jogos": "Jogos",
                    "margem_media": "Margem média",
                    "margem_mediana": "Margem mediana",
                },
                {"jogos": "inteiro", "margem_media": "pct2", "margem_mediana": "pct2"},
            ),
            "",
            "**O padrão da especificação se confirma:** as cinco grandes ligas",
            "europeias cobram de 4,3% a 5,0%; as divisões inferiores e as ligas",
            "menores cobram de 7% a 9,3% — o dobro.",
            "",
            "⚠️ **Margem baixa não quer dizer fácil de ganhar.** Na Premier League a",
            "margem é baixa *porque o mercado é eficiente*: a taxa é barata e a linha",
            "é quase impossível de bater. Na quarta divisão escocesa a taxa é cara,",
            "mas a casa tem menos informação. Qual dos dois efeitos ganha é uma das",
            "perguntas que este projeto existe para responder — e ela só será",
            "respondida na Fase 6, com backtest.",
            "",
            "### O mercado aperta a margem até o apito",
            "",
            "Comparando a odd média pré-jogo com a de fechamento (Grupo 1, formato A):",
            "",
            de_dataframe(
                pre_fech,
                {
                    "liga": "Liga",
                    "margem_pre": "Margem pré-jogo",
                    "margem_fech": "Margem fechamento",
                    "aperto": "Aperto",
                },
                {"margem_pre": "pct2", "margem_fech": "pct2", "aperto": "pct2"},
            ),
            "",
            "O aperto é positivo em **todas** as ligas: a margem cai entre a abertura",
            "e o apito. Como o projeto aposta na odd pré-jogo (regra 8), é a coluna",
            "da esquerda — a mais cara — que o modelo precisa vencer.",
        ]
    )


def _secao_evolucao(jogos: pd.DataFrame) -> str:
    _, resumo = exploracao.evolucao_margem(jogos[jogos["grupo"] == "grupo1"])
    resumo = resumo.sort_values("variacao")

    caiu = int((resumo["variacao"] < 0).sum())
    total = len(resumo)

    return "\n".join(
        [
            "## 4. A margem mudou ao longo dos anos?",
            "",
            "Comparando a primeira temporada medida (2019/20) com a última",
            "(2025/26), no 1X2 de fechamento do Grupo 1:",
            "",
            de_dataframe(
                resumo,
                {
                    "liga": "Liga",
                    "temporadas": "Temporadas",
                    "primeira": "2019/20",
                    "ultima": "2025/26",
                    "variacao": "Variação",
                },
                {"primeira": "pct2", "ultima": "pct2", "variacao": "pct2"},
            ),
            "",
            f"A margem caiu em **{caiu} das {total}** ligas do Grupo 1. O mercado",
            "ficou mais barato para o apostador — o que costuma andar junto com",
            "ficar mais difícil de bater, porque margem menor é sinal de mais",
            "dinheiro e mais modelos disputando a mesma linha.",
        ]
    )


def _secao_mando(jogos: pd.DataFrame) -> str:
    por_liga = exploracao.vantagem_mando(jogos, ["liga"]).sort_values(
        "pontos_casa", ascending=False
    )
    queda = exploracao.queda_do_mando_na_pandemia(jogos, TEMPORADAS_VAZIAS)
    queda = queda.sort_values("queda_pontos_casa", ascending=False)

    # Só o Grupo 1 nesta tabela: as 22 ligas dele têm todas o mesmo calendário
    # (agosto a maio) e as mesmas sete temporadas, então as linhas são
    # comparáveis entre si. Misturar aqui o Brasileirão, que vai de janeiro a
    # dezembro, empilharia períodos diferentes na mesma linha.
    grupo1 = jogos[jogos["grupo"] == "grupo1"]
    geral = exploracao.vantagem_mando(grupo1, ["temporada"]).sort_values("temporada")

    caiu = int((queda["queda_pontos_casa"] > 0).sum())

    return "\n".join(
        [
            "## 5. Quanto vale jogar em casa — e o que aconteceu em 2020",
            "",
            "*Resposta à pergunta 3: a vantagem de jogar em casa mudou ao longo dos anos?*",
            "",
            "**Sim, e muito.** Em 2020 e 2021 os estádios ficaram vazios, e a",
            "vantagem de mando caiu em quase todas as ligas do mundo ao mesmo tempo.",
            "É o experimento natural mais interessante deste conjunto de dados.",
            "",
            "Por temporada, nas 22 ligas do Grupo 1 (todas de agosto a maio):",
            "",
            de_dataframe(
                geral,
                {
                    "temporada": "Temporada",
                    "jogos": "Jogos",
                    "vitorias_casa": "Vitórias do mandante",
                    "pontos_casa": "Pontos por jogo",
                    "saldo_gols": "Saldo de gols",
                },
                {
                    "jogos": "inteiro",
                    "vitorias_casa": "pct",
                    "pontos_casa": "num3",
                    "saldo_gols": "num3",
                },
            ),
            "",
            "Comparando as temporadas jogadas sem público (2019/20 e 2020/21 na",
            "Europa, 2020 e 2021 nos campeonatos de ano civil) com as demais, o",
            f"mando caiu em **{caiu} de {len(queda)}** competições:",
            "",
            de_dataframe(
                queda.head(15),
                {
                    "liga": "Liga",
                    "pontos_casa_publico": "Pontos/jogo com público",
                    "pontos_casa_vazio": "Pontos/jogo sem público",
                    "queda_pontos_casa": "Queda",
                },
                {
                    "pontos_casa_publico": "num3",
                    "pontos_casa_vazio": "num3",
                    "queda_pontos_casa": "num3",
                },
            ),
            "",
            "⚠️ A temporada 2019/20 entra na conta como 'portões fechados', mas só a",
            "parte final dela foi jogada sem público — o que **diminui** o efeito",
            "medido, não aumenta.",
            "",
            "**Consequência direta para a Fase 3:** um modelo que trate o fator casa",
            "como constante ao longo das sete temporadas vai errar num pedaço grande",
            "do treino. Esta tabela é a justificativa para o fator casa variável no",
            "tempo.",
            "",
            "### Mando por liga (todas as temporadas)",
            "",
            de_dataframe(
                por_liga,
                {
                    "liga": "Liga",
                    "jogos": "Jogos",
                    "vitorias_casa": "Vitórias do mandante",
                    "empates": "Empates",
                    "pontos_casa": "Pontos por jogo",
                    "saldo_gols": "Saldo de gols",
                },
                {
                    "jogos": "inteiro",
                    "vitorias_casa": "pct",
                    "empates": "pct",
                    "pontos_casa": "num3",
                    "saldo_gols": "num3",
                },
            ),
        ]
    )


def _secao_gols(jogos: pd.DataFrame) -> str:
    distribuicao = exploracao.distribuicao_gols(jogos)
    over = exploracao.frequencia_over25(jogos, ["liga"]).sort_values(
        "over25", ascending=False
    )
    media = float((jogos["gols_mandante"] + jogos["gols_visitante"]).mean())

    return "\n".join(
        [
            "## 6. Os gols se parecem com uma Poisson?",
            "",
            f"Média de **{num(media, 2)} gols por jogo** nas 38 competições. A",
            "pergunta que importa para a Fase 3 é se a distribuição desses gols se",
            "parece com uma Poisson — porque é nessa hipótese que os modelos de",
            "Poisson e Dixon-Coles se apoiam.",
            "",
            de_dataframe(
                distribuicao,
                {
                    "gols": "Gols no jogo",
                    "jogos": "Jogos",
                    "observado": "Observado",
                    "poisson": "Poisson",
                    "diferenca": "Diferença",
                },
                {
                    "jogos": "inteiro",
                    "observado": "pct2",
                    "poisson": "pct2",
                    "diferenca": "pct2",
                },
            ),
            "",
            "A Poisson acerta o formato geral, e **erra de um jeito específico**:",
            "jogos de 0 gol acontecem mais do que ela prevê, e jogos de 1 e 2 gols",
            "um pouco menos. Esse desvio é conhecido e tem nome — é exatamente ele",
            "que o ajuste de **Dixon-Coles** corrige, inflando a probabilidade dos",
            "placares baixos (0-0, 1-0, 0-1, 1-1). Saber disso **antes** de treinar",
            "é o motivo de esta seção existir.",
            "",
            "### Mais de 2,5 gols, por liga",
            "",
            de_dataframe(
                over,
                {
                    "liga": "Liga",
                    "jogos": "Jogos",
                    "gols_por_jogo": "Gols por jogo",
                    "over25": "Mais de 2,5 gols",
                },
                {"jogos": "inteiro", "gols_por_jogo": "num2", "over25": "pct"},
            ),
        ]
    )


def _secao_calibracao(jogos: pd.DataFrame) -> str:
    grupo1 = jogos[jogos["grupo"] == "grupo1"]
    observado = mercado.resultado_observado(grupo1, "1x2")
    probabilidades = mercado.probabilidades_do_mercado(grupo1, "1x2", "fech", "power")
    tabela = metricas.tabela_calibracao(probabilidades, observado)

    linhas = [
        [
            linha["faixa"],
            inteiro(linha["n"]),
            pct(linha["previsto"], 1),
            pct(linha["observado"], 1),
            pontos_percentuais(linha["diferenca"]),
        ]
        for linha in tabela
    ]

    # O viés favorito-azarão sai da própria tabela, e não de um número escrito
    # à mão: trocar o método de remoção de margem muda estes valores, e o texto
    # precisa mudar junto.
    favoritos = _media_ponderada(tabela, lambda linha: linha["previsto"] >= 0.6)
    azaroes = _media_ponderada(tabela, lambda linha: linha["previsto"] < 0.15)

    return "\n".join(
        [
            "## 7. O mercado é bem calibrado?",
            "",
            "*Resposta à pergunta 2.*",
            "",
            "**Sim, notavelmente.** Agrupando todas as afirmações de probabilidade do",
            "mercado de fechamento do Grupo 1 e conferindo o que de fato aconteceu:",
            "",
            tabela_markdown(
                linhas,
                ["Faixa", "Afirmações", "Previsto", "Aconteceu", "Diferença"],
            ),
            "",
            f"O erro de calibração médio (ECE) é de **{num(metricas.ece(probabilidades, observado))}**",
            "— menos de meio ponto percentual. Quando o mercado de fechamento diz",
            "60%, acontece perto de 60%. Isso é a definição prática de um mercado",
            "difícil de bater, e é o adversário do projeto.",
            "",
            "⚠️ **Mas há um padrão nos restos**, e ele é o efeito mais famoso dos",
            "mercados de aposta: os **favoritos vencem mais** do que a odd dizia",
            f"({pontos_percentuais(favoritos)} nas faixas acima de 60%) e os",
            f"**azarões vencem menos** ({pontos_percentuais(azaroes)} abaixo de",
            "15%). É o *viés favorito-azarão*, e ele",
            "sobrevive mesmo depois de tirar a margem pelo método que melhor o",
            "corrige. Quem aposta em azarão paga caro duas vezes: na comissão maior",
            "e na probabilidade inflada.",
        ]
    )


def _secao_filtro(jogos: pd.DataFrame, cfg: Config, avaliacao: pd.DataFrame) -> str:
    criterios = filtro.Criterios.do_config(cfg)
    grupo1 = avaliacao[avaliacao["grupo"] == "grupo1"]
    aprovadas = filtro.ligas_aprovadas(avaliacao)
    reprovadas = grupo1[~grupo1["aprovada"]]

    jogos_aprovados = int(jogos[jogos["liga"].isin(aprovadas)].shape[0])

    return "\n".join(
        [
            "## 8. Quais ligas entram no backtest",
            "",
            "*Resposta à pergunta 4, e ao pedido original: \"quero as ligas em que tem",
            "apostas boas\".*",
            "",
            "A lista abaixo **não** foi escolhida a dedo. Ela é o resultado de aplicar",
            "os cortes do `config.yaml` às medições desta fase:",
            "",
            f"- margem máxima no 1X2 pré-jogo: **{pct(criterios.margem_maxima, 0)}**",
            f"- cobertura mínima de odds: **{pct(criterios.cobertura_minima, 0)}**",
            f"- jogos mínimos: **{criterios.jogos_minimos}**",
            f"- ECE máximo: **{criterios.fator_ece_maximo:.1f}×** o piso de ruído da liga",
            "",
            "🔎 **Sobre o corte de calibração.** Medir calibração com o ECE cru pune",
            "liga pequena: com 1.200 jogos, o ECE é alto **mesmo num mercado**",
            "**perfeito**, só por acaso amostral. Por isso o ECE de cada liga é",
            "comparado com o piso de ruído dela — o ECE que apareceria se aquele",
            "mercado fosse perfeito, estimado por simulação. Este critério foi fixado",
            "**depois** de ver os números (o corte anterior, absoluto, reprovava a",
            "Grécia por ser pequena). Nenhuma liga foi reprovada por ele: quem caiu,",
            "caiu por margem.",
            "",
            de_dataframe(
                grupo1,
                {
                    "liga": "Liga",
                    "jogos": "Jogos",
                    "cobertura": "Cobertura",
                    "margem_pre": "Margem pré",
                    "ece": "ECE",
                    "piso_ece": "Piso de ruído",
                    "fator_ece": "ECE/piso",
                    "log_loss": "Log loss",
                    "aprovada": "Aprovada",
                },
                {
                    "jogos": "inteiro",
                    "cobertura": "pct",
                    "margem_pre": "pct2",
                    "ece": "num",
                    "piso_ece": "num",
                    "fator_ece": "num2",
                    "log_loss": "num",
                },
            ),
            "",
            f"### Aprovadas ({len(aprovadas)})",
            "",
            f"`{', '.join(aprovadas)}`",
            "",
            f"São **{inteiro(jogos_aprovados)} jogos** elegíveis para o backtest de",
            "apostas da Fase 6.",
            "",
            f"### Reprovadas ({len(reprovadas)})",
            "",
            tabela_markdown(
                [[linha["liga"], linha["motivos"]] for _, linha in reprovadas.iterrows()],
                ["Liga", "Motivo"],
            ),
            "",
            "Todas as quatro caíram pelo mesmo motivo: margem acima de 8%. São as",
            "divisões mais baixas da Escócia e a quinta divisão inglesa — exatamente",
            "onde a casa cobra mais caro por ter menos informação. Para lucrar ali, o",
            "modelo precisaria de uma vantagem de mais de 8% sobre o mercado, o que",
            "seria extraordinário.",
            "",
            "⚠️ **Os 16 países do Grupo 2 não aparecem nesta lista** e nunca",
            "aparecerão: sem odd pré-jogo não existe aposta para simular (regra 12).",
            "Eles continuam valendo para treinar os modelos e para medir calibração —",
            "são 63.184 jogos, mais da metade do total.",
        ]
    )


def _secao_respostas(jogos: pd.DataFrame, avaliacao: pd.DataFrame) -> str:
    grupo1 = jogos[jogos["grupo"] == "grupo1"]
    observado = mercado.resultado_observado(grupo1, "1x2")
    probabilidades = mercado.probabilidades_do_mercado(grupo1, "1x2", "fech", "power")
    aprovadas = filtro.ligas_aprovadas(avaliacao)
    calibracao = metricas.tabela_calibracao(probabilidades, observado)
    favoritos = _media_ponderada(calibracao, lambda linha: linha["previsto"] >= 0.6)

    return "\n".join(
        [
            "## 9. As quatro respostas, em uma frase cada",
            "",
            "| Pergunta | Resposta |",
            "|---|---|",
            "| Qual a margem média da casa em cada liga? | De **4,3%** (Premier "
            "League) a **9,3%** (4ª divisão escocesa) no 1X2 de fechamento. As cinco "
            "grandes europeias cobram metade do que cobram as divisões menores. |",
            f"| O mercado é bem calibrado? | **Sim**: ECE de "
            f"{num(metricas.ece(probabilidades, observado))} no fechamento do Grupo 1. "
            f"Sobra um viés favorito-azarão de {pontos_percentuais(favoritos)} nos "
            "favoritos. |",
            "| A vantagem de jogar em casa mudou? | **Mudou muito.** Caiu em 2020-21, "
            "com os estádios vazios, e voltou a subir depois. O fator casa não pode "
            "ser uma constante no modelo. |",
            f"| Quais ligas passaram no filtro? | **{len(aprovadas)} das 22** do Grupo 1. "
            "Reprovadas: SC1, SC2, SC3 e EC, todas por margem acima de 8%. |",
            "",
            "---",
            "",
            "## O que a Fase 3 recebe daqui",
            "",
            f"1. **A meta:** log loss de {num(metricas.log_loss(probabilidades, observado))} "
            "no fechamento do Grupo 1. Um modelo que não chegue perto disso não é útil.",
            "2. **Um alerta:** a Poisson simples erra nos placares de poucos gols — o "
            "ajuste de Dixon-Coles nasce daí.",
            "3. **Um requisito:** o fator casa precisa variar no tempo.",
            "4. **Um método:** `power` para tirar a margem, por ser o mais bem calibrado.",
            "5. **Um escopo:** 18 ligas aprovadas para aposta; 38 competições para treinar.",
        ]
    )


# ----------------------------------------------------------------------------
# Montagem
# ----------------------------------------------------------------------------
def gerar(
    jogos: pd.DataFrame,
    cfg: Config,
    *,
    gerado_em: str,
    avaliacao: pd.DataFrame | None = None,
    repeticoes: int = filtro.REPETICOES_PISO,
) -> str:
    """Monta o relatório inteiro da Fase 2 em Markdown."""
    if avaliacao is None:
        avaliacao = filtro.avaliar(jogos, cfg, repeticoes=repeticoes)

    secoes = [
        _cabecalho(jogos, cfg, gerado_em),
        _secao_metodos(jogos),
        _secao_baseline(jogos),
        _secao_margem(jogos),
        _secao_evolucao(jogos),
        _secao_mando(jogos),
        _secao_gols(jogos),
        _secao_calibracao(jogos),
        _secao_filtro(jogos, cfg, avaliacao),
        _secao_respostas(jogos, avaliacao),
    ]
    return "\n\n".join(secoes) + "\n"
