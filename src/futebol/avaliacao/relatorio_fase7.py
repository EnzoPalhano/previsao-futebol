"""O relatório da Fase 7: múltiplas e cash out, medidos.

Como nas fases anteriores, este módulo **não mede nada** — ele conta o que
:mod:`futebol.backtest.multiplas` e :mod:`futebol.backtest.cash_out` mediram.

A fase tinha três perguntas, e as três têm resposta numérica:

1. **quanto a casa cobra a mais numa múltipla?** Muito, e de forma previsível: a
   comissão de cada perna se multiplica;
2. **a chance de ganhar mostrada é otimista demais?** Sim — mas **não** pelo
   motivo que a especificação esperava. O erro é do modelo, perna a perna, e ele
   se acumula. A suposição de independência, medida com um controle, não produz
   erro detectável;
3. **alguma regra de cash out muda o resultado?** Não. O botão cobra a taxa dele
   independentemente de quando é apertado, e isso sai como identidade da conta,
   não como coincidência dos dados.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from futebol import relatorio
from futebol.backtest import cash_out, montador, multiplas
from futebol.config import Config

#: Os tamanhos de múltipla que a seção de cash out detalha. Três chegam: um
#: bilhete pequeno, um médio e um grande. Mostrar os nove encheria o relatório
#: de linhas que repetem a mesma conclusão.
TAMANHOS_DO_CASH_OUT: tuple[int, ...] = (2, 6, 10)

#: Quantas configurações de aposta a Fase 7 acrescenta à contagem da regra 11:
#: os 9 tamanhos de múltipla × (nunca sacar + sacar quando compensa), mais as
#: regras de "sacar após N acertos", que somam 45 pontos de decisão nos 9
#: tamanhos. O número é grande e é por isso que ele é contado.
N_CONFIGURACOES_FASE_7 = 9 * 2 + 45

#: O ROI de uma aposta simples medido na Fase 6, para o relatório poder
#: comparar múltipla com aposta simples sem que o leitor precise abrir o
#: outro arquivo. Fica aqui como constante nomeada, e não solto no texto,
#: para ser fácil de achar e conferir contra `docs/relatorios/fase6.md`.
ROI_DA_FASE_6 = -0.1292


def _extremos(por_tamanho: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """O menor bilhete medido, um do meio e o maior.

    ⚠️ Escolhidos da tabela, e não escritos à mão. O relatório ilustra a
    conclusão com exemplos concretos ("num bilhete de dois jogos…"), e um
    exemplo fixo em código quebra em silêncio se algum dia a grade de tamanhos
    mudar no ``config.yaml`` — ou pior, continua funcionando e passa a citar um
    tamanho que não foi medido.
    """
    ordenada = por_tamanho.sort_values("tamanho")
    return (
        ordenada.iloc[0],
        ordenada.iloc[len(ordenada) * 2 // 3],
        ordenada.iloc[-1],
    )


def _com_sinal(valor: float, casas: int = 2) -> str:
    if valor is None or pd.isna(valor):
        return "-"
    return ("+" if valor >= 0 else "") + relatorio.pct(valor, casas)


def _intervalo(baixo: float, alto: float, casas: int = 2) -> str:
    return f"{_com_sinal(baixo, casas)} a {_com_sinal(alto, casas)}"


def montar(
    cfg: Config,
    historico: multiplas.Historico,
    por_tamanho: pd.DataFrame,
    tabelas_de_cash_out: dict[int, pd.DataFrame],
    distribuicao: tuple[int, np.ndarray],
    exemplo: montador.Opcao | None,
    comparativo: pd.DataFrame,
    caminho_margem: Path,
    caminho_previsto: Path,
    janela: tuple[pd.Timestamp, pd.Timestamp],
    gerado_em: str,
) -> str:
    """O relatório inteiro, em Markdown."""
    return "\n\n".join(
        [
            _cabecalho(cfg, historico, por_tamanho, janela, gerado_em),
            _resposta(por_tamanho),
            _como_foram_montadas(cfg, historico),
            _margem(por_tamanho, caminho_margem),
            _previsto_real(por_tamanho, caminho_previsto),
            _independencia(por_tamanho),
            _roi(por_tamanho),
            _cash_out(cfg, tabelas_de_cash_out, distribuicao),
            _montador(
                exemplo, comparativo, float(por_tamanho["razao_por_selecao"].mean())
            ),
            _pre_registro(gerado_em, por_tamanho),
            _conclusao(por_tamanho, tabelas_de_cash_out),
        ]
    )


# ----------------------------------------------------------------------------
def _cabecalho(cfg, historico, por_tamanho, janela, gerado_em) -> str:
    valores = multiplas.limites(cfg)
    return f"""# Fase 7 — Múltiplas e cash out

- Modelo: o oficial do projeto (Dixon-Coles, `xi = 0,003`, `m = 6`). Nada foi
  alterado nele nesta fase.
- Janela: **{janela[0].date()} a {janela[1].date()}** — a mesma da validação, com as
  temporadas de teste final trancadas (regra 7).
- Ligas: as **18 aprovadas** no filtro da Fase 2 (regra 12 e regra 13).
- Bilhetes montados: **{relatorio.inteiro(len(historico.multiplas))}**, em
  {relatorio.inteiro(historico.multiplas["data"].nunique())} rodadas, de
  {int(por_tamanho["tamanho"].min())} a {int(por_tamanho["tamanho"].max())} seleções.
- Seleções usadas: **{relatorio.inteiro(len(historico.pernas))}**.
- Faixa de odd por seleção: {relatorio.num(valores["odd_minima"], 2)} a
  {relatorio.num(valores["odd_maxima"], 2)} (`config.yaml`).
- Gerado em: {gerado_em}

> **A restrição que não é negociável:** no máximo **uma seleção por jogo**. Os
> mercados de uma mesma partida são fortemente correlacionados — se o mandante
> goleia, "mais de 2,5 gols" fica muito mais provável — e multiplicar essas duas
> chances daria um número errado para mais, sem que nenhum teste percebesse.

> **Regra 9.** Nada aqui escolhe modelo. Múltipla é consequência medida, nunca
> critério."""


def _resposta(por_tamanho: pd.DataFrame) -> str:
    duplas, meio, dez = _extremos(por_tamanho)
    razoes = por_tamanho["razao_por_selecao"]
    return f"""## As três respostas, primeiro

**1. A comissão da casa se multiplica, e isso é aritmética.** Numa aposta
simples ela é de {relatorio.pct(float(por_tamanho["margem_por_selecao"].mean()), 2)};
num bilhete de {int(dez["tamanho"])} jogos vira
**{relatorio.pct(dez["margem"])}**. Não é a casa sendo mais gananciosa com
múltiplas: é a mesma taxa, cobrada {int(dez["tamanho"])} vezes seguidas, uma em
cima da outra. O bilhete de {int(dez["tamanho"])} jogos custa
{relatorio.num(1 + dez["margem"], 2)} vezes o que ele vale.

**2. A chance de ganhar mostrada é otimista demais — mas a culpa é do modelo,
não da independência entre os jogos.** Esta é a descoberta da fase, e ela
contraria o que a especificação esperava encontrar. O modelo promete
{relatorio.pct(duplas["prevista_modelo"])} num bilhete de
{int(duplas["tamanho"])} jogos e acontece {relatorio.pct(duplas["real"])}; num de
{int(meio["tamanho"])}, promete {relatorio.pct(meio["prevista_modelo"], 2)} e
acontece {relatorio.pct(meio["real"], 2)}. Mas quando a **mesma conta** é feita com as
probabilidades do mercado, ela acerta em cheio em todos os tamanhos. Ou seja: o
produto simples não é o problema — o que entra nele é.

**3. O cash out não muda o resultado, e o motivo é uma identidade, não um
acaso.** O valor esperado de sacar é o valor esperado de não sacar multiplicado
por `(1 − taxa)`. **Não importa quando você aperta o botão** — depois de um
acerto ou depois de nove, a conta dá exatamente o mesmo. O que muda é só a
variância.

A razão entre o que o mercado diz e o que o modelo diz, **por seleção**, fica em
torno de {relatorio.num(float(razoes.mean()), 3)} em todos os
{len(por_tamanho)} tamanhos medidos. É esse número que explica tudo: o modelo
exagera a chance de cada perna em cerca de
{relatorio.pct(1 - float(razoes.mean()))}, e num bilhete de
{int(meio["tamanho"])} jogos esse exagerozinho vira
{relatorio.pct(1 - float(razoes.mean()) ** int(meio["tamanho"]))}."""


def _como_foram_montadas(cfg, historico) -> str:
    valores = multiplas.limites(cfg)
    return f"""## Como os bilhetes foram montados

Em cada data em que houve jogo, o procedimento foi sempre o mesmo:

1. pegar **uma seleção por partida** — aquela em que o modelo tem mais confiança;
2. descartar as de odd fora da faixa {relatorio.num(valores["odd_minima"], 2)}–{relatorio.num(valores["odd_maxima"], 2)};
3. ordenar da mais provável para a menos provável;
4. cortar em blocos do tamanho pedido. O primeiro bilhete leva os maiores
   favoritos do dia, o segundo os seguintes, e assim por diante. A sobra é
   descartada.

⚠️ **Por que blocos, e não um bilhete por rodada.** Duas razões, as duas sobre
honestidade estatística. A primeira é amostra: um bilhete por data daria
setecentos bilhetes por tamanho, e com uma chance de acerto de 1% isso não mede
nada — os blocos dão {relatorio.inteiro(len(historico.multiplas))}. A segunda é
que os blocos **não compartilham partidas** dentro de uma mesma rodada. Se dois
bilhetes do mesmo sábado tivessem jogos em comum, o acerto de um estaria amarrado
ao do outro, e o intervalo de confiança sairia mais estreito do que a realidade.

⚠️ **A seleção é escolhida por probabilidade, não por valor esperado** — e é uma
decisão com preço declarado. A Fase 6 mediu o que o filtro de EV faz: ele empurra
a carteira para os azarões, que é onde a casa cobra mais, e o ROI piora. Numa
múltipla isso seria pior ainda, porque cada azarão multiplica a chance de o
bilhete inteiro morrer. O preço da decisão é que estes bilhetes são de favoritos,
e o que se mede aqui vale para eles."""


def _margem(por_tamanho: pd.DataFrame, caminho: Path) -> str:
    linhas = [
        [
            str(int(linha["tamanho"])),
            relatorio.inteiro(linha["multiplas"]),
            relatorio.num(linha["odd_total"], 2),
            relatorio.pct(linha["margem"]),
            relatorio.pct(linha["margem_por_selecao"], 2),
        ]
        for _, linha in por_tamanho.iterrows()
    ]
    corpo = relatorio.tabela_markdown(
        linhas,
        [
            "Seleções",
            "Bilhetes",
            "Odd total média",
            "Comissão acumulada",
            "Equivale a, por seleção",
        ],
    )
    media = float(por_tamanho["margem_por_selecao"].mean())
    _, _, dez = _extremos(por_tamanho)
    return f"""## 1. A comissão se multiplica

{corpo}

A última coluna é a prova de que não há mistério: a comissão por seleção fica
praticamente **constante** em
{relatorio.pct(float(por_tamanho["margem_por_selecao"].min()), 2)}–{relatorio.pct(float(por_tamanho["margem_por_selecao"].max()), 2)}
nos nove tamanhos. O que cresce é o efeito de cobrá-la várias vezes:

```
comissão do bilhete = (1 + {relatorio.num(media, 4)})ⁿ − 1
```

![Comissão por tamanho de bilhete]({caminho.name})

Com {relatorio.pct(media, 2)} por seleção, um bilhete de
{int(dez["tamanho"])} jogos carrega
**{relatorio.pct(dez["margem"])}** de comissão. Em dinheiro: um bilhete que
deveria pagar R$ 100 paga cerca de
R$ {relatorio.num(100 / (1 + dez["margem"]), 0)}.

⚠️ **Esta é a única parte da fase que não depende de modelo nenhum.** Ela vale
para você, para mim e para um apostador perfeito: juntar jogos num bilhete só
multiplica a comissão, sempre. É por isso que a múltipla é o produto mais
lucrativo de uma casa de apostas."""


def _previsto_real(por_tamanho: pd.DataFrame, caminho: Path) -> str:
    linhas = [
        [
            str(int(linha["tamanho"])),
            relatorio.inteiro(linha["multiplas"]),
            relatorio.pct(linha["prevista_modelo"], 2),
            relatorio.pct(linha["prevista_mercado"], 2),
            relatorio.pct(linha["real"], 2),
            relatorio.inteiro(linha["acertos"]),
            _com_sinal(linha["desvio_relativo"], 1),
            relatorio.num(linha["razao_por_selecao"], 3),
        ]
        for _, linha in por_tamanho.iterrows()
    ]
    corpo = relatorio.tabela_markdown(
        linhas,
        [
            "Seleções",
            "Bilhetes",
            "O modelo prometeu",
            "O mercado prometeria",
            "Aconteceu",
            "Acertos",
            "Erro do modelo",
            "Razão por seleção",
        ],
    )
    razoes = por_tamanho["razao_por_selecao"]
    media = float(razoes.mean())
    return f"""## 2. A chance prometida contra a chance que aconteceu

{corpo}

![Prometido e acontecido]({caminho.name})

**O modelo erra para cima em todos os nove tamanhos**, e o erro relativo tende a
crescer com o bilhete: {_com_sinal(float(por_tamanho.iloc[0]["desvio_relativo"]), 1)}
numa dupla contra
{_com_sinal(float(_extremos(por_tamanho)[1]["desvio_relativo"]), 1)}
num bilhete de {int(_extremos(por_tamanho)[1]["tamanho"])}.

⚠️ A coluna balança bastante de uma linha para a outra, e a última delas
({_com_sinal(float(por_tamanho.iloc[-1]["desvio_relativo"]), 1)} em dez seleções)
parece dizer que o modelo acertou em cheio. Não diz: são
{relatorio.inteiro(float(por_tamanho.iloc[-1]["acertos"]))} acertos em
{relatorio.inteiro(float(por_tamanho.iloc[-1]["multiplas"]))} bilhetes, e com essa
contagem qualquer número caberia ali. **A tendência vale; cada linha isolada,
não.**

A última coluna explica o porquê, e é a coluna mais importante do relatório. Ela
é a razão entre o que o mercado diz e o que o modelo diz, **por seleção** — ou
seja, o exagero do modelo numa perna só, isolado do tamanho do bilhete. Ela fica
em {relatorio.num(float(razoes.min()), 3)}–{relatorio.num(float(razoes.max()), 3)}
nos nove tamanhos, praticamente constante.

**O que isso quer dizer, em português:** o modelo exagera a chance de cada
seleção em cerca de {relatorio.pct(1 - media)}. Só isso. Num bilhete de dois
jogos, esse exagero aparece como {relatorio.pct(1 - media**2)}; num de oito,
como {relatorio.pct(1 - media**8)}. **Não é um erro novo que aparece nas
múltiplas — é o mesmo errinho de sempre, elevado à potência do número de
jogos.**

É exatamente o que a Fase 4 já tinha medido de outro jeito: o modelo fica 0,0226
de log loss atrás do mercado. Aqui dá para ver esse número virando dinheiro, e
virando dinheiro **mais rápido** a cada jogo acrescentado ao bilhete."""


def _independencia(por_tamanho: pd.DataFrame) -> str:
    linhas = [
        [
            str(int(linha["tamanho"])),
            relatorio.pct(linha["prevista_mercado"], 2),
            relatorio.pct(linha["real"], 2),
            _com_sinal(linha["desvio_mercado_relativo"], 1),
            _intervalo(
                linha["desvio_mercado_baixo"] / linha["prevista_mercado"],
                linha["desvio_mercado_alto"] / linha["prevista_mercado"],
                1,
            ),
            relatorio.pct(linha["detectavel_relativo"], 1),
        ]
        for _, linha in por_tamanho.iterrows()
    ]
    corpo = relatorio.tabela_markdown(
        linhas,
        [
            "Seleções",
            "O mercado prometeria",
            "Aconteceu",
            "Erro do mercado",
            "IC 95% do erro",
            "Menor erro detectável",
        ],
    )
    pequenos = por_tamanho.loc[por_tamanho["tamanho"] <= 3]
    return f"""## 3. A independência entre jogos — o que a fase foi procurar

⚠️ **Leia esta seção antes de acreditar em qualquer chance de ganhar mostrada
por um app de apostas, inclusive o deste projeto.**

A chance de uma múltipla acertar é calculada como o **produto** das chances de
cada seleção. Isso supõe que os jogos são independentes: que saber o resultado de
um não muda nada sobre o outro. Dentro de uma mesma partida a suposição é
claramente falsa, e por isso o projeto proíbe duas seleções do mesmo jogo. Entre
partidas diferentes, sobra uma correlação menor e real — rodadas com muitos gols,
efeitos de calendário, e principalmente o **erro compartilhado do próprio
modelo**. Essa correlação, se existir, empurra a chance real para **baixo** da
calculada, e cada vez mais conforme o bilhete cresce.

A fase foi medir isso. O truque é usar as probabilidades **justas do mercado** no
mesmo produto: a Fase 2 mediu que o mercado é bem calibrado jogo a jogo, então se
o produto dele também errar para cima, o culpado é a suposição de independência,
e não o modelo.

{corpo}

**O resultado: não há erro detectável.** O intervalo de confiança contém o zero
em **todos os nove tamanhos**, e nos bilhetes pequenos — onde a amostra tem
força — o erro medido é praticamente nulo
({_com_sinal(float(pequenos["desvio_mercado_relativo"].mean()), 2)} na média de
duplas e triplas, com um limiar de detecção de
{relatorio.pct(float(pequenos["detectavel_relativo"].mean()), 1)}).

Ou seja: **o produto simples das probabilidades não superestimou nada**, desde
que as probabilidades que entram nele estejam certas. A correlação entre jogos
de rodadas reais, se existe, é pequena demais para aparecer em trinta e seis mil
bilhetes.

⚠️ **O limite honesto desta conclusão, que é grande e precisa ser dito.** Repare
na última coluna: o menor erro detectável cresce de
{relatorio.pct(float(por_tamanho.iloc[0]["detectavel_relativo"]), 1)} num bilhete
de dois jogos para
{relatorio.pct(float(por_tamanho.iloc[-1]["detectavel_relativo"]), 0)} num de
dez. A conclusão "não há correlação" é **forte** nos bilhetes de 2 a 4 seleções e
**fraca** de 6 em diante, onde a amostra não enxergaria nem um efeito grande. O
certo é dizer: *em bilhetes pequenos, medimos que não há; em bilhetes grandes,
não conseguimos medir.*

**E o item opcional da especificação?** A seção 7.1 prevê, "só se sobrar tempo",
modelar a correlação com um efeito compartilhado por rodada. Ele **não foi
implementado**, e agora por um motivo melhor do que falta de tempo: ele existiria
para reduzir um descasamento que não foi encontrado. Implementá-lo seria
acrescentar um parâmetro ao projeto para corrigir um problema que a medição não
achou — exatamente o tipo de complexidade que a Fase 5 decidiu não carregar."""


def _roi(por_tamanho: pd.DataFrame) -> str:
    linhas = [
        [
            str(int(linha["tamanho"])),
            relatorio.inteiro(linha["multiplas"]),
            relatorio.num(linha["odd_total"], 2),
            relatorio.inteiro(linha["acertos"]),
            _com_sinal(linha["roi"]),
            _intervalo(linha["roi_baixo"], linha["roi_alto"]),
        ]
        for _, linha in por_tamanho.iterrows()
    ]
    corpo = relatorio.tabela_markdown(
        linhas,
        ["Seleções", "Bilhetes", "Odd total média", "Acertos", "ROI", "IC 95% do ROI"],
    )
    return f"""## 4. O ROI por tamanho de bilhete

{corpo}

⚠️ **Repare no intervalo de confiança, e não no ROI.** Da sexta seleção em
diante ele passa de trinta pontos percentuais de largura, e no bilhete de dez
jogos vai de {_intervalo(float(por_tamanho.iloc[-1]["roi_baixo"]), float(por_tamanho.iloc[-1]["roi_alto"]), 0)}.
Isso não é uma medição: é uma loteria com
{relatorio.inteiro(float(por_tamanho.iloc[-1]["acertos"]))} prêmios sorteados em
{relatorio.inteiro(float(por_tamanho.iloc[-1]["multiplas"]))} bilhetes.

É o mesmo fenômeno da Fase 6, agora numa versão extrema. Um bilhete de dez jogos
paga odd média {relatorio.num(float(por_tamanho.iloc[-1]["odd_total"]), 0)} e
acerta menos de 1% das vezes — o resultado de mil bilhetes desses é decidido por
meia dúzia de sortes. **Múltipla grande é o lugar onde o ROI menos significa
alguma coisa**, e é justamente onde ele é mais citado por quem vende palpite.

O número em que se pode confiar é o da seção 1: a comissão acumulada. Ela não
depende de sorte nenhuma, e em dez jogos ela é de
{relatorio.pct(float(por_tamanho.iloc[-1]["margem"]))}."""


def _cash_out(cfg, tabelas: dict[int, pd.DataFrame], distribuicao) -> str:
    margem = cash_out.margem_da_casa(cfg)
    blocos = []
    for tamanho, tabela in sorted(tabelas.items()):
        linhas = [
            [
                str(linha["estrategia"]),
                _com_sinal(linha["ev_mercado"]),
                _com_sinal(linha["roi"]),
                _intervalo(linha["roi_baixo"], linha["roi_alto"]),
                relatorio.pct(linha["sacou"]),
            ]
            for _, linha in tabela.iterrows()
        ]
        corpo = relatorio.tabela_markdown(
            linhas,
            [
                "Estratégia",
                "Valor esperado",
                "ROI que aconteceu",
                "IC 95% do ROI",
                "Sacou em",
            ],
        )
        blocos.append(f"**Bilhetes de {tamanho} seleções**\n\n{corpo}")

    tamanho_exemplo, valores = distribuicao
    mais_comum = int(np.argmax(valores))
    linhas_dist = "\n".join(
        f"| {k} | {relatorio.pct(v, 1)} |"
        for k, v in enumerate(valores)
        if v >= 0.005
    )
    seis = sorted(tabelas)[1]
    nunca = tabelas[seis].iloc[0]
    sacar = tabelas[seis].iloc[1]
    return f"""## 5. O cash out

O cash out é o botão que a casa oferece com o bilhete em andamento: "você
acertou 4 de 6, aceita R$ 30 agora?". A oferta é o **valor justo do que falta**
menos uma taxa — aqui simulada em {relatorio.pct(margem, 0)}
(`cash_out_margem_casa` no `config.yaml`).

{(chr(10) + chr(10)).join(blocos)}

⚠️ **Duas colunas de ROI, e a que importa é a primeira.** O "ROI que aconteceu"
depende de quais bilhetes acertaram e, num bilhete de dez jogos que acerta 1% das
vezes, é quase puro ruído — repare nos intervalos. O "valor esperado" é a conta
feita com os preços, não depende de resultado nenhum, e é ele que separa as
estratégias de verdade.

Sem essa distinção a tabela levaria à conclusão **oposta** da correta: em
bilhetes de {seis} seleções, "sacar após 1 acerto" mostra ROI de
{_com_sinal(sacar["roi"])} contra {_com_sinal(nunca["roi"])} de "nunca sacar", e
parece melhor. Não é. Ele só tem menos variância — e o valor esperado dele é
{_com_sinal(sacar["ev_mercado"])} contra {_com_sinal(nunca["ev_mercado"])}.
**Sacar é pior, e é pior exatamente pela taxa.**

**O achado mais limpo da seção:** o valor esperado de "sacar após N acertos" é
**idêntico para todo N**. Sacar depois de um acerto ou depois de nove dá a mesma
conta. Isso não é coincidência dos dados — é uma identidade:

```
valor esperado de sacar = valor esperado de não sacar × (1 − taxa)
```

A chance de chegar vivo ao ponto de saque, multiplicada pela chance do que
ainda falta, é sempre a chance do bilhete inteiro. O que sobra é o desconto. **O
botão cobra a mesma coisa não importa quando você o aperta** — a única coisa que
muda é o tamanho do susto.

E a terceira regra, a que usa informação? "Sacar só quando a oferta compensa"
(isto é, quando a oferta passa do valor justo **segundo o modelo**) fica **entre
as duas**, e ainda assim perde para "nunca sacar". A explicação é a mesma de
sempre: para ganhar dinheiro identificando ofertas generosas, seria preciso ter
probabilidades melhores que as do mercado. O projeto mediu na Fase 4 que não tem.

### A distribuição dos acertos, por Monte Carlo

Num bilhete de {tamanho_exemplo} seleções, com que frequência ele termina com
cada número de acertos:

| Acertos | Frequência |
|---|---|
{linhas_dist}

O caso mais comum é **{mais_comum} de {tamanho_exemplo}** — que paga zero. Essa
tabela é a experiência de quem joga múltipla grande descrita em números: quase
sempre você vai assistir à maior parte dos jogos dar certo e não receber nada.

⚠️ **Este é o único uso do Monte Carlo nesta fase, e é de propósito.** A
especificação avisa (seção 7.1) que sortear jogos de forma independente **não**
corrige a correlação entre partidas — só reproduz o produto das probabilidades
com ruído a mais. Mas para a pergunta "como se distribuem os acertos parciais" o
sorteio é o caminho curto para uma conta que existe e é chata de fazer à mão."""


def _montador(
    exemplo: montador.Opcao | None, comparativo: pd.DataFrame, razao: float
) -> str:
    if comparativo.empty:
        return "## 6. O montador\n\nSem rodada de exemplo disponível."

    linhas = [
        [
            str(int(linha["tamanho"])),
            relatorio.num(linha["odd_total"], 2),
            relatorio.dinheiro(linha["premio"]),
            relatorio.pct(linha["prob_modelo"], 1),
            f"1 em {relatorio.num(linha['uma_em'], 1)}",
            relatorio.pct(linha["margem_acumulada"]),
        ]
        for _, linha in comparativo.iterrows()
    ]
    corpo = relatorio.tabela_markdown(
        linhas,
        [
            "Seleções",
            "Odd total",
            "Prêmio de R$ 10",
            "Chance (modelo)",
            "Ou seja",
            "Comissão acumulada",
        ],
    )
    detalhe = ""
    if exemplo is not None:
        pernas = "\n".join(
            f"| {linha['liga']} | {linha['mandante']} × {linha['visitante']} | "
            f"{linha['selecao']} | {relatorio.num(linha['odd'], 2)} | "
            f"{relatorio.pct(linha['prob'])} |"
            for _, linha in exemplo.pernas.iterrows()
        )
        detalhe = f"""

### "Quero ganhar R$ 200 com R$ 10"

O montador procura o bilhete **mais provável** que alcança o prêmio pedido. Nesta
rodada de exemplo ele encontrou {exemplo.tamanho} seleções, odd total
{relatorio.num(exemplo.odd_total, 2)}, prêmio de
R$ {relatorio.dinheiro(exemplo.premio)}:

| Liga | Jogo | Seleção | Odd | Chance |
|---|---|---|---|---|
{pernas}

Chance de ganhar, segundo o modelo: **{relatorio.pct(exemplo.prob_modelo)}** —
ou seja, 1 em {relatorio.num(exemplo.uma_em, 1)}. Comissão acumulada:
{relatorio.pct(exemplo.margem_acumulada)}.

⚠️ {montador.AVISO_DE_INDEPENDENCIA}

⚠️ **E um segundo aviso, que esta fase acabou de tornar obrigatório.** A chance
mostrada acima é a do **modelo**, e a seção 2 mediu que ele exagera a chance de
cada seleção em cerca de {relatorio.pct(1 - razao)}. Num bilhete de
{exemplo.tamanho} jogos isso são {relatorio.pct(1 - razao**exemplo.tamanho)} de
exagero. A chance real é menor que a escrita — e o app da Fase 8 vai precisar dizer isso na tela, não no rodapé."""

    return f"""## 6. O montador de bilhetes

O montador é a peça que vira tela na Fase 8. Ele responde a duas perguntas: "monte
um bilhete de N jogos" e "monte um bilhete que pague R$ X". Em ambos os casos o
critério é a **maior chance de ganhar**, nunca o maior valor esperado — a Fase 6
mostrou aonde escolher por valor esperado leva.

A tabela comparativa é o argumento da fase inteira numa figura só. Cada jogo a
mais multiplica o prêmio, multiplica a comissão e divide a chance:

{corpo}{detalhe}"""


def _pre_registro(gerado_em: str, por_tamanho: pd.DataFrame) -> str:
    de_modelo = 29
    de_aposta = 16 + N_CONFIGURACOES_FASE_7
    sortuda = por_tamanho.iloc[-1]
    return f"""## Pré-registro e multiplicidade (regra 11)

| | |
|---|---|
| Configurações de **modelo** testadas | **{de_modelo}** — Fases 3, 4 e 5. Inalterado: a Fase 7 não disputa modelo |
| Configurações de **aposta** até a Fase 6 | **16** — limites de EV × estratégias de stake × tipos de banca |
| Configurações de **aposta** na Fase 7 | **{N_CONFIGURACOES_FASE_7}** — 9 tamanhos de múltipla × (nunca sacar + sacar quando compensa), mais 45 regras de "sacar após N acertos" |
| **Total acumulado** | **{de_modelo + de_aposta}** |
| Configuração de modelo escolhida | `{{'modelo': 'dixon-coles', 'xi': 0.003, 'm': 6.0}}` — **inalterada** |
| Data | {gerado_em} |

⚠️ **O número desta fase é grande, e é por isso que ele é contado.**
{N_CONFIGURACOES_FASE_7} combinações de múltipla e cash out dão muitas chances de
alguma parecer lucrativa por acaso — e uma **pareceu**: o ROI do bilhete de
{int(sortuda["tamanho"])} seleções deu positivo
({_com_sinal(float(sortuda["roi"]))}). Sem a contagem e sem o intervalo de
confiança, essa linha viraria a manchete do relatório. Com eles, ela é o que é:
{relatorio.inteiro(float(sortuda["acertos"]))} acertos em
{relatorio.inteiro(float(sortuda["multiplas"]))} bilhetes, com intervalo de
{_intervalo(float(sortuda["roi_baixo"]), float(sortuda["roi_alto"]), 0)}.

O total **soma** e nunca é reescrito para baixo."""


def _conclusao(por_tamanho: pd.DataFrame, tabelas: dict[int, pd.DataFrame]) -> str:
    _, _, dez = _extremos(por_tamanho)
    razao = float(por_tamanho["razao_por_selecao"].mean())
    maior = max(tabelas)
    nunca = tabelas[maior].iloc[0]
    sacar = tabelas[maior].iloc[1]
    return f"""## Conclusão

A fase pedia três coisas, e as três estão medidas:

**(a) Como a margem cresce com o número de jogos.** De
{relatorio.pct(float(por_tamanho["margem_por_selecao"].mean()), 2)} por seleção
para **{relatorio.pct(dez["margem"])}** num bilhete de
{int(dez["tamanho"])}. A curva é exatamente
`(1 + m)ⁿ − 1`, e não depende de modelo nenhum.

**(b) O quanto a taxa de acerto real fica abaixo da prevista.** Fica abaixo, sim
— e a resposta de **por quê** é o resultado mais interessante do projeto até
aqui. A especificação esperava encontrar correlação entre jogos. Não é isso. O
desvio é o erro do modelo em **cada seleção** (ele exagera cerca de
{relatorio.pct(1 - razao)} por perna) **elevado à potência do tamanho do
bilhete**. Quando a mesma conta é feita com as probabilidades do mercado, o
produto acerta: o intervalo de confiança contém o zero nos
{len(por_tamanho)} tamanhos.

**(c) Se alguma regra de cash out muda o resultado.** Nenhuma. O valor esperado
de sacar é o de não sacar vezes `(1 − taxa)`, para qualquer momento de saque —
{_com_sinal(sacar["ev_mercado"])} contra {_com_sinal(nunca["ev_mercado"])} nos
bilhetes de {maior} seleções. O botão vende tranquilidade, e cobra por ela.

### O que isso significa na prática

**Múltipla é a pior forma de apostar que este projeto mediu.** A Fase 6 mostrou
uma aposta simples perdendo {relatorio.pct(abs(ROI_DA_FASE_6))}; aqui um bilhete
de {int(dez["tamanho"])} jogos
carrega {relatorio.pct(dez["margem"])} só de comissão. E a conta é impiedosa
porque é multiplicativa: **cada jogo acrescentado piora tudo ao mesmo tempo** —
multiplica a comissão, multiplica o exagero do modelo e divide a chance de
ganhar.

### O que sobra de valor

1. **O diagnóstico de calibração por multiplicação.** Um erro de
   {relatorio.pct(1 - razao)} por jogo é quase invisível numa aposta simples e
   vira {relatorio.pct(1 - razao**8)} num bilhete de oito. A múltipla
   funciona como uma lupa do erro do modelo — e essa lupa é uma ferramenta de
   diagnóstico útil, mesmo que o produto que ela examina não preste;
2. **A limitação de independência, medida em vez de suposta.** A especificação
   mandava documentar a limitação e medir o tamanho dela. Medida: não detectável
   em bilhetes pequenos, e a amostra não alcança os grandes. É uma resposta
   melhor que "provavelmente existe";
3. **O montador pronto para a Fase 8**, com os dois avisos que ele é obrigado a
   mostrar na tela: o de independência e o do exagero do modelo.

⚠️ **O que NÃO se deve concluir.** Que existe um tamanho de múltipla "certo". Não
existe: o melhor tamanho medido é **um** — que é uma aposta simples, e a Fase 6
já mostrou que ela também perde. A pergunta "quantos jogos eu ponho no bilhete?"
tem a resposta chata de que menos é sempre melhor.

---

*Apostas envolvem risco real de perda. Este projeto é educacional. Quem sentir
que perdeu o controle pode procurar apoio: Jogadores Anônimos, ou o CVV pelo
telefone 188.*"""
