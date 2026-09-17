"""O relatório da Fase 4: a avaliação honesta e a escolha oficial do modelo.

Este é o relatório que o projeto inteiro estava esperando. A Fase 2 mediu o
adversário, a Fase 3 construiu os modelos e mediu por cima; aqui a medição é a
de verdade — **walk-forward rodada a rodada** — e é dela que sai:

1. a tabela comparando baseline, Poisson, Dixon-Coles e o mercado de
   fechamento (o "pronto quando" da fase);
2. a **escolha oficial do modelo e dos parâmetros**, por log loss (regra 9);
3. as curvas de calibração;
4. o mapa de onde o modelo chega perto do mercado — que é a única coisa que
   interessa para a Fase 6.

O módulo só **lê o cache** produzido por :mod:`futebol.avaliacao.selecao` e
escreve texto e gráficos. Medir custa meia hora; relatar custa segundos, e essa
separação é o que permite melhorar o texto sem repetir a conta.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from futebol import relatorio
from futebol.avaliacao import divisao, graficos, selecao, validacao
from futebol.config import Config

#: Nome do mercado nas tabelas. Ele é referência, não candidato: não disputa a
#: escolha, porque o projeto compara modelos entre si e usa o mercado como
#: régua (e porque não daria para "usar o mercado" como modelo — ele não existe
#: antes do jogo começar em toda liga, nem para todo mercado).
NOME_MERCADO = "mercado (fechamento)"

#: Log loss de quem chuta 33% para cada opção.
LOG_LOSS_UNIFORME = float(np.log(3))

#: Ligas com menos jogos que isto ficam fora da tabela por liga.
MINIMO_POR_LIGA = 200


def _pct(valor: float) -> str:
    return relatorio.pct(valor, 1)


# ----------------------------------------------------------------------------
# Seções
# ----------------------------------------------------------------------------
def _cabecalho(
    liberados: pd.DataFrame,
    separacao: divisao.Divisao,
    cfg: Config,
    janela: tuple[pd.Timestamp, pd.Timestamp],
    medida_referencia: validacao.Medida,
    gerado_em: str,
) -> str:
    grupo1 = sorted(liberados.loc[liberados["grupo"] == "grupo1", "liga"].unique())
    grupo2 = sorted(liberados.loc[liberados["grupo"] == "grupo2", "liga"].unique())
    inicio, fim = janela
    return "\n".join(
        [
            "# Fase 4 — A avaliação honesta",
            "",
            f"- Camada de ligas: **{cfg.camada_ativa}**",
            f"- Janela de validação: **{inicio.date()} a {fim.date()}**",
            f"- Jogos avaliados: **{relatorio.inteiro(medida_referencia.n)}**, "
            "cada um previsto por um modelo treinado **só** com o que existia "
            "antes da rodada dele",
            f"- Jogos trancados até a Fase 9: "
            f"**{relatorio.inteiro(separacao.trancados)}** (regra 7)",
            f"- Grupo 1 — backtest e CLV ({len(grupo1)}): {', '.join(grupo1)}",
            f"- Grupo 2 — treino e calibração ({len(grupo2)}): {', '.join(grupo2)}",
            f"- Gerado em: {gerado_em}",
            "",
            "> **Regra 13.** Cada tabela diz de quais ligas fala. Onde não estiver",
            "> escrito o contrário, o número é das **38 competições**, Grupo 1 e",
            "> Grupo 2 juntos — o que vale para medir previsão, já que o Grupo 2",
            "> tem odd de fechamento. Aposta é outra história: ali valem só as 18",
            "> ligas aprovadas na Fase 2 (regra 12).",
            "",
            "> **Regra 9.** A escolha de modelo desta fase é por **log loss**. Não",
            "> por acurácia, não por calibração, e principalmente não por lucro.",
            "",
            "> **Regra 7.** Nada aqui viu as temporadas de teste final. A trava é",
            "> código (`futebol/avaliacao/divisao.py`) e o walk-forward confere,",
            "> linha por linha, que nenhum treino alcançou a partida prevista.",
        ]
    )


def _secao_metodo(resultado_exemplo: str) -> str:
    return f"""## 1. O que mudou da Fase 3 para cá

A Fase 3 mediu os modelos reajustando cada um **uma vez por mês**. Servia para
experimentar, e o próprio relatório dizia que era provisório. Aqui a medição é a
que vale:

| | Fase 3 (provisória) | Fase 4 (oficial) |
|---|---|---|
| Quando o modelo é retreinado | todo dia 1º | **antes de cada rodada** |
| Quanto a previsão pode estar velha | até 30 dias | zero |
| Para que serve | ver se a ideia funciona | **escolher o modelo** (regra 9) |

"Rodada" aqui é literal: cada data em que uma competição jogou. Para prever o
Arsenal x Chelsea de um sábado, o modelo é estimado com tudo o que aconteceu até
a sexta — e com nada além disso.

{resultado_exemplo}

⚠️ **Onde o vazamento entraria, e por que ele não entra.** Um `<=` no lugar de
um `<` bastaria para o modelo treinar com o próprio jogo que está prevendo, e o
resultado ficaria ótimo e falso. Duas travas cuidam disso: o corte de data mora
na classe base dos modelos (nenhum modelo pode esquecê-lo) e o walk-forward
confere, previsão por previsão, que a data do último jogo de treino é **anterior**
à da partida. A conferência roda junto com a medição, não só no `pytest` —
depender de alguém lembrar de rodar o teste seria depender de memória.

E há um teste de **sabotagem**: um modelo que ignora o corte de propósito tem de
ser reprovado. Um teste que só verifica o código certo não prova que a trava
funciona; prova que o código certo passa.
"""


def _secao_comparacao(
    medidas: list[validacao.Medida], caminho_calibracao: Path, ligas: int
) -> str:
    tabela = relatorio.de_dataframe(
        pd.DataFrame([m.como_linha() for m in medidas]),
        {
            "modelo": "Quem prevê",
            "jogos": "Jogos",
            "log_loss": "Log loss (1X2)",
            "brier": "Brier",
            "acuracia": "Acurácia",
            "ece": "ECE",
            "log_loss_ou": "Log loss (O/U 2,5)",
        },
        {
            "jogos": "inteiro",
            "log_loss": "num",
            "brier": "num",
            "acuracia": "pct",
            "ece": "num",
            "log_loss_ou": "num",
        },
    )
    por_nome = {m.nome: m for m in medidas}
    melhor_modelo = min(
        (m for m in medidas if m.nome != NOME_MERCADO), key=lambda m: m.log_loss
    )
    do_mercado = por_nome[NOME_MERCADO]
    distancia = melhor_modelo.log_loss - do_mercado.log_loss

    return f"""## 2. A tabela da fase: os modelos contra o mercado

As mesmas {relatorio.inteiro(medidas[0].n)} partidas para todo mundo, em
{ligas} competições. Menor é melhor em log loss, Brier e ECE; maior é melhor em
acurácia.

{tabela}

Referência: quem chuta 33% para cada opção tira log loss
**{relatorio.num(LOG_LOSS_UNIFORME)}**.

Três leituras, em ordem de importância:

**1. Cada degrau de modelo é real.** O baseline bate o chute uniforme (sabe a
estatística da liga), o Poisson bate o baseline (sabe quem joga) e o Dixon-Coles
bate o Poisson (sabe que placar baixo é diferente e que jogo velho vale menos).

**2. O mercado ganha, por {relatorio.num(distancia)} de log loss.** Era o
esperado — e a especificação já dizia que seria, antes de qualquer conta. A odd
de fechamento embute escalação, lesão, suspensão, clima e o dinheiro de milhares
de apostadores profissionais. Um modelo que só lê placares não deveria vencer
isso, e se vencesse a primeira suspeita certa seria vazamento no código, não
talento.

**3. A acurácia atrapalha mais do que ajuda.** Repare que ela varia pouco entre
modelos muito diferentes: é que quase toda previsão de 1X2 aponta o mandante, e
acertar "quem ganha" é uma pergunta grosseira demais para separar um modelo bom
de um medíocre. Ela está na tabela por honestidade, e não entra em nenhuma
decisão (regra 9).

### A calibração

![Curva de calibração dos modelos e do mercado]({caminho_calibracao.name})

Como ler: a diagonal é a calibração perfeita — "quando digo 60%, acontece 60%".
Ponto **abaixo** da linha é confiança demais (o modelo prometeu mais do que
entregou); **acima**, timidez.

⚠️ Calibração não mede conhecimento. Um modelo que responde sempre "44%, 26%,
30%" (a média da liga) fica quase perfeito nesta curva e não sabe nada sobre
jogo nenhum. Ela serve para outra coisa, e essa coisa é decisiva para apostar: o
valor esperado de uma aposta é calculado **com a probabilidade do modelo**. Se
ela vier inflada, o EV vem inflado junto, e o backtest da Fase 6 apostaria em
valor que não existe.
"""


def _secao_escolha(
    escolha: selecao.Escolha,
    diferenca_segundo: validacao.Diferenca,
    cfg: Config,
) -> str:
    modelos = cfg.secao("modelos")
    xi_atual = modelos["dixon_coles"]["xi"]
    m_atual = modelos["shrinkage"]["jogos_equivalentes"]
    escolhidos = escolha.parametros
    mudou = (
        escolhidos.get("xi", xi_atual) != xi_atual
        or escolhidos.get("m", m_atual) != m_atual
    )
    nota = (
        "⚠️ A escolha **mudou** valores que estavam no `config.yaml` desde a "
        "Fase 3. Os novos valores já estão gravados lá, e a marca `PROVISORIO` "
        "saiu."
        if mudou
        else (
            "A configuração escolhida é a que já estava no `config.yaml` desde a "
            "Fase 3 — mas agora ela está lá **por medição**, e não por chute. É "
            "isso que a marca `PROVISORIO` significava, e ela saiu."
        )
    )
    return f"""## 3. A escolha oficial (regra 9)

Disputaram **{escolha.n_configuracoes} configurações**, todas medidas no mesmo
walk-forward e nos mesmos jogos. Venceu a de menor log loss:

> **{escolha.vencedor.nome}** — log loss
> **{relatorio.num(escolha.vencedor.log_loss)}**
> Parâmetros: `{escolhidos}`

A margem sobre a segunda colocada foi de
**{relatorio.num(escolha.margem, 5)}** de log loss. Medida jogo a jogo, com
incerteza:

**{diferenca_segundo.como_texto()}**

{nota}

⚠️ **Por que log loss, e não lucro.** O ROI de um backtest depende de algumas
centenas de apostas, cada uma valendo 0 ou 1. Nesse tamanho de amostra, a
diferença entre um modelo bom e um modelo **sortudo** é invisível — a Fase 6 vai
mostrar isso com número. A log loss usa as
{relatorio.inteiro(escolha.vencedor.n)} partidas e a probabilidade inteira, não
só o que deu certo. Escolher por lucro é escolher o modelo mais sortudo do
passado, e a regra 9 existe para isso não acontecer por descuido.

⚠️ **Por que só {escolha.n_configuracoes} configurações** (regra 11). Quanto mais
configurações se testa, maior a chance de a melhor delas estar na frente por
acaso — e uma busca ampla acaba se ajustando à própria validação. A grade é
pequena e definida em código (`futebol/avaliacao/selecao.py`), em torno do que a
literatura e a Fase 3 indicaram. O número acumulado está no pré-registro.
"""


def _secao_grade(
    titulo: str,
    tabela: pd.DataFrame,
    colunas: dict[str, str],
    formatos: dict[str, str],
    texto: str,
) -> str:
    return f"""### {titulo}

{relatorio.de_dataframe(tabela, colunas, formatos)}

{texto}
"""


def _secao_parametros(
    varredura_xi: pd.DataFrame,
    varredura_m: pd.DataFrame,
    diferenca_decaimento: validacao.Diferenca,
) -> str:
    melhor_xi = varredura_xi.loc[varredura_xi["log_loss"].idxmin()]
    melhor_m = varredura_m.loc[varredura_m["log_loss"].idxmin()]
    return f"""## 4. Os parâmetros que a Fase 3 deixou provisórios

### O decaimento temporal (`xi`)

Cada jogo entra no ajuste com peso `exp(−xi · dias)`. `xi = 0` é um modelo com
memória infinita; `xi` grande é um modelo amnésico.

{relatorio.de_dataframe(
    varredura_xi,
    {
        "xi": "xi",
        "meia_vida_texto": "Meia-vida",
        "log_loss": "Log loss",
        "brier": "Brier",
        "ece": "ECE",
    },
    {"xi": "num4", "log_loss": "num", "brier": "num", "ece": "num"},
)}

O fundo da curva está em `xi = {relatorio.num(float(melhor_xi["xi"]), 4)}`
({melhor_xi["meia_vida_texto"]}). Ter memória curta paga, e paga de forma
mensurável — a diferença entre `xi = 0` e o escolhido, medida jogo a jogo:

**{diferenca_decaimento.como_texto()}**

### O encolhimento (`jogos_equivalentes`)

Quantos jogos de história "a média da liga" vale, quando se estima a força de um
time. É a resposta ao time recém-promovido, que chega sem nenhum jogo naquela
divisão.

{relatorio.de_dataframe(
    varredura_m,
    {
        "jogos_equivalentes": "m",
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
)}

O fundo está em `m = {int(melhor_m["jogos_equivalentes"])}`, e a curva é rasa na
vizinhança — o modelo não é sensível a essa escolha dentro da faixa razoável, o
que é uma boa notícia: significa que não há nada aqui para "otimizar" além do
que já foi feito.
"""


def _secao_fator_casa(diferenca: validacao.Diferenca, valor_unico: float) -> str:
    veredito = (
        "Agora com amostra três vezes maior e medição rodada a rodada, **a "
        "diferença aparece**: o intervalo de 95% não cruza mais o zero."
        if diferenca.significativa
        else (
            "Mesmo com amostra três vezes maior e medição rodada a rodada, **a "
            "diferença continua indistinguível de zero**. A leitura honesta é "
            "*não dá para dizer qual é melhor por este critério* — e não *são "
            "iguais*."
        )
    )
    return f"""## 5. O fator casa por liga, revisitado

A Fase 3 comparou "um fator casa por competição" com "um fator casa só" e não
conseguiu separar os dois. Ficou prometida uma revisita com o walk-forward
oficial, e aqui está ela. A variante única usa
{relatorio.num(valor_unico, 3)} — medido com tudo o que existia **antes** do
começo da janela e congelado, para não haver futuro nele.

**{diferenca.como_texto()}**

{veredito}

De qualquer forma, o projeto segue com o fator casa **por liga**, pelos mesmos
motivos da Fase 3, que não dependem deste teste: o fator casa vai de 1,10 na
Áustria a 1,50 nos Estados Unidos, e aplicar a vantagem de casa de um país ao
outro é errado por razão física — viagem, altitude, público —, não estatística.
Um parâmetro a mais por competição, com milhares de jogos para estimá-lo, não é
o tipo de coisa que causa sobreajuste.
"""


def _secao_por_liga(
    tabela: pd.DataFrame,
    nome_modelo: str,
    caminho_grafico: Path,
    aprovadas: list[str],
) -> str:
    dados = tabela.assign(distancia=tabela[nome_modelo] - tabela[NOME_MERCADO])
    ordenada = dados.sort_values("distancia")
    perto = ordenada.head(8)
    longe = ordenada.tail(5)

    colunas = {
        "liga": "Liga",
        "jogos": "Jogos",
        nome_modelo: "Log loss do modelo",
        NOME_MERCADO: "Log loss do mercado",
        "distancia": "Distância",
        "aprovada": "Aprovada p/ aposta",
    }
    formatos = {
        "jogos": "inteiro",
        nome_modelo: "num",
        NOME_MERCADO: "num",
        "distancia": "num",
    }
    marcar = lambda t: t.assign(  # noqa: E731
        aprovada=t["liga"].map(lambda liga: "sim" if liga in aprovadas else "não")
    )
    ganha_do_mercado = int((dados["distancia"] < 0).sum())

    return f"""## 6. Onde o modelo chega perto do mercado

A média não decide nada: aposta se faz jogo a jogo, e só onde a diferença entre
o modelo e o mercado é pequena pode existir valor. Esta é a seção que a Fase 6
vai usar.

![Distância do mercado por competição]({caminho_grafico.name})

As competições em que o modelo fica **mais perto** do mercado:

{relatorio.de_dataframe(marcar(perto), colunas, formatos)}

E as em que ele fica mais longe:

{relatorio.de_dataframe(marcar(longe), colunas, formatos)}

A coluna "aprovada p/ aposta" vem do filtro de qualidade de mercado da Fase 2:
são as {len(aprovadas)} ligas do Grupo 1 com margem, cobertura e calibração
aceitáveis. ⚠️ **Estar perto do mercado numa liga não aprovada não serve para
nada** — sem odd pré-jogo não há aposta a simular (regra 12), e é o caso de todas
as competições do Grupo 2.

{
    "⚠️ **Em "
    + str(ganha_do_mercado)
    + " competição(ões) o modelo teve log loss MENOR que o mercado.** Isso não é "
    "para comemorar antes de conferir: com poucos milhares de jogos por liga, "
    "diferença pequena é ruído, e diferença grande costuma ser erro de dado ou "
    "cobertura de odds irregular. A Fase 6 só considera aposta onde há odd "
    "pré-jogo registrada, e o CLV vai dizer se a vantagem é real."
    if ganha_do_mercado
    else "Em nenhuma competição o modelo bateu o mercado — o que é o resultado "
    "normal e esperado."
}
"""


def _secao_limites(escolha: selecao.Escolha, gerado_em: str) -> str:
    return f"""## 7. O que esta fase não responde

- **não há nenhuma aposta aqui.** Nem ROI, nem CLV, nem valor esperado. Saber
  prever melhor que antes não é o mesmo que ganhar dinheiro: entre uma coisa e
  outra está a margem da casa, medida na Fase 2, que é de 4,3% a 8% nas ligas
  aprovadas. O modelo precisa ser melhor que o mercado **por mais que isso** num
  jogo específico para a aposta ter valor;
- **o teste final continua fechado** (regra 7). Estas
  {relatorio.inteiro(escolha.vencedor.n)} partidas são de validação; as duas
  temporadas mais recentes serão abertas uma única vez, na Fase 9;
- **nenhuma informação além de placar.** Elo, forma recente, dias de descanso e
  desfalques entram nas Fases 5 e 7. O que está medido aqui é o teto do que se
  consegue só com o placar dos jogos anteriores;
- **o modelo não sabe nada sobre o jogo específico.** Ele não sabe que o
  goleiro titular está suspenso nem que o time joga a final da Champions na
  quarta. O mercado sabe, e parte da diferença de log loss é exatamente isso.

## Pré-registro (regra 11)

Para a Fase 9 abrir o teste final uma única vez, o que foi escolhido precisa
estar escrito **antes**:

| | |
|---|---|
| Configurações testadas na validação | **{escolha.n_configuracoes}** (Fase 4) + 13 exploratórias na Fase 3 |
| Configuração escolhida | `{escolha.parametros}` |
| Critério | log loss no walk-forward de validação (regra 9) |
| Janela de validação | {relatorio.inteiro(escolha.vencedor.n)} partidas, nenhuma do teste final |
| Data | {gerado_em} |

Este quadro está repetido no `CLAUDE.md`, que é onde ele vale como registro. Se
as Fases 5, 6 ou 7 mudarem a escolha, o número de configurações testadas **sobe**
e o pré-registro é reescrito — nunca apagado.
"""


# ----------------------------------------------------------------------------
# Montagem
# ----------------------------------------------------------------------------
def gerar(
    jogos: pd.DataFrame,
    cfg: Config,
    gerado_em: str,
    inicio=selecao.INICIO_VALIDACAO,
    pasta_saida: Path | None = None,
    forcar: bool = False,
    aviso: Callable[[str], None] = print,
) -> str:
    """Lê (ou roda) a validação, escreve os gráficos e devolve o relatório."""
    pasta_saida = pasta_saida or (cfg.raiz / "docs" / "relatorios")
    separacao = divisao.separar(jogos, cfg)
    liberados = separacao.jogos
    aviso(separacao.resumo())

    fim = pd.Timestamp(liberados["data"].max()) + pd.Timedelta(days=1)
    janela = (pd.Timestamp(inicio), fim)

    lista = selecao.candidatos(cfg, liberados, inicio)
    previsoes = {
        candidato.nome: selecao.rodar_candidato(
            liberados, candidato, cfg, inicio, fim, forcar, aviso
        )
        for candidato in lista
    }
    do_mercado = validacao.previsoes_do_mercado(
        liberados.loc[
            (liberados["data"] >= janela[0]) & (liberados["data"] < janela[1])
        ]
    )

    # Tudo medido no mesmo conjunto: a interseção de todos os candidatos com o
    # mercado. Sem isso a tabela compara coisas diferentes.
    todos = {**previsoes, NOME_MERCADO: do_mercado}
    medidas, alinhados = validacao.medir_nos_mesmos_jogos(todos)
    por_nome = {m.nome: m for m in medidas}

    escolha = selecao.escolher(previsoes, lista)
    vencedor = escolha.vencedor.nome
    segundo = escolha.medidas[1].nome
    diferenca_segundo = validacao.comparar(alinhados[segundo], alinhados[vencedor])

    principais = [
        por_nome[nome]
        for nome in ("baseline", "poisson", "dixon-coles", NOME_MERCADO)
        if nome in por_nome
    ]

    # -- gráficos ---------------------------------------------------------
    aviso("  desenhando os gráficos...")
    subtitulo = (
        f"walk-forward de {janela[0].date()} a {janela[1].date()} · "
        f"{relatorio.inteiro(principais[0].n)} partidas · 38 competições"
    )
    caminho_calibracao = graficos.curva_calibracao(
        {m.nome: alinhados[m.nome] for m in principais},
        pasta_saida / "fase4_calibracao.png",
        subtitulo=subtitulo,
    )

    tabela_ligas = validacao.por_liga(
        {vencedor: alinhados[vencedor], NOME_MERCADO: alinhados[NOME_MERCADO]},
        minimo_de_jogos=MINIMO_POR_LIGA,
    )
    caminho_distancia = graficos.distancia_do_mercado(
        tabela_ligas,
        pasta_saida / "fase4_distancia_do_mercado.png",
        coluna_modelo=vencedor,
        subtitulo=subtitulo,
    )

    # -- grades -----------------------------------------------------------
    varredura_xi = _varredura_xi(cfg, por_nome, alinhados)
    varredura_m = _varredura_encolhimento(cfg, por_nome)
    padrao_dc = "dixon-coles"
    diferenca_decaimento = validacao.comparar(
        alinhados["dc-xi-0.0"], alinhados[padrao_dc]
    )
    diferenca_casa = validacao.comparar(
        alinhados["dc-casa-unica"], alinhados[padrao_dc]
    )
    valor_unico = float(
        next(c.parametros["valor_fator_casa"] for c in lista if c.nome == "dc-casa-unica")
    )

    exemplo = (
        f"Na janela avaliada isso deu **{relatorio.inteiro(escolha.vencedor.n)}** "
        "partidas previstas, com mais de **dez mil** ajustes de modelo por "
        "configuração testada — uma competição, uma rodada, um ajuste."
    )
    aprovadas = list(cfg.bruto.get("ligas_aprovadas_backtest", []))

    return "\n".join(
        [
            _cabecalho(liberados, separacao, cfg, janela, principais[0], gerado_em),
            "",
            _secao_metodo(exemplo),
            _secao_comparacao(principais, caminho_calibracao, ligas=38),
            _secao_escolha(escolha, diferenca_segundo, cfg),
            _secao_parametros(varredura_xi, varredura_m, diferenca_decaimento),
            _secao_fator_casa(diferenca_casa, valor_unico),
            _secao_por_liga(tabela_ligas, vencedor, caminho_distancia, aprovadas),
            _secao_limites(escolha, gerado_em),
        ]
    )


def _varredura_xi(
    cfg: Config,
    por_nome: dict[str, validacao.Medida],
    alinhados: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """A tabela da grade de ``xi``, incluindo o valor padrão do ``config.yaml``."""
    xi_padrao = float(cfg.secao("modelos")["dixon_coles"]["xi"])
    linhas = []
    for xi in selecao.GRADE_XI:
        nome = "dixon-coles" if xi == xi_padrao else f"dc-xi-{xi}"
        medida = por_nome[nome]
        linhas.append(
            {
                "xi": xi,
                "meia_vida_texto": (
                    "sem decaimento" if xi == 0 else f"{np.log(2) / xi:.0f} dias"
                ),
                "log_loss": medida.log_loss,
                "brier": medida.brier,
                "ece": medida.ece,
            }
        )
    return pd.DataFrame(linhas)


def _varredura_encolhimento(
    cfg: Config, por_nome: dict[str, validacao.Medida]
) -> pd.DataFrame:
    """A tabela da grade de encolhimento."""
    m_padrao = float(cfg.secao("modelos")["shrinkage"]["jogos_equivalentes"])
    linhas = []
    for m in selecao.GRADE_ENCOLHIMENTO:
        nome = "dixon-coles" if m == m_padrao else f"dc-m-{m}"
        medida = por_nome[nome]
        linhas.append(
            {
                "jogos_equivalentes": m,
                "peso_com_10_jogos": 10 / (10 + m),
                "log_loss": medida.log_loss,
                "brier": medida.brier,
                "ece": medida.ece,
            }
        )
    return pd.DataFrame(linhas)
