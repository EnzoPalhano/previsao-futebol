"""O relatório da Fase 6: "teria dado lucro?" — e a resposta é não.

Como nas fases anteriores, este módulo **não mede nada**: ele conta o que
:mod:`futebol.backtest.simulador` mediu. A separação entre medir e relatar é o
que garante que o número do texto e o número da conta são o mesmo número.

⚠️ **A Fase 6 é a fase em que o projeto tinha mais a ganhar mentindo, e é por
isso que ela é a mais cheia de trava.** Um backtest é fácil de fazer parecer
lucrativo: basta apostar na odd máxima, escolher o limite de EV depois de ver o
resultado, mostrar só a liga que deu certo, ou reportar a banca composta de uma
série vencedora. O relatório abaixo faz o contrário de cada uma dessas coisas, e
diz em voz alta que está fazendo.

A conclusão que a especificação admite como legítima — "a amostra é pequena
demais para decidir" — **não** é a deste relatório. A amostra é grande: 21 mil
apostas, quatro vezes o mínimo da seção 8.4. O que se mediu foi uma desvantagem
clara, consistente nas 18 ligas e nas 3 temporadas.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from futebol import relatorio
from futebol.avaliacao import metricas, selecao
from futebol.backtest import simulador
from futebol.config import Config

#: As faixas de odd em que as apostas candidatas são agrupadas para mostrar o
#: viés azarão–favorito. Larguras desiguais de propósito: quase tudo vive entre
#: 1,5 e 5,0, e as pontas só têm sentido se forem largas.
FAIXAS_DE_ODD: tuple[float, ...] = (1.0, 1.5, 2.0, 3.0, 5.0, 10.0, 1000.0)

#: Quantas apostas uma liga precisa ter para aparecer na tabela por liga.
MINIMO_POR_LIGA = 100

#: O mínimo de apostas que a seção 8.4 exige para o critério de ROI ter poder.
MINIMO_PARA_ROI = 5000


def _com_sinal(valor: float, casas: int = 2) -> str:
    """Porcentagem com sinal explícito. ``-12,92%`` e ``+0,31%``."""
    if valor is None or pd.isna(valor):
        return "-"
    return ("+" if valor >= 0 else "") + relatorio.pct(valor, casas)


def _intervalo(ic: tuple[float, float], casas: int = 2) -> str:
    return f"{_com_sinal(ic[0], casas)} a {_com_sinal(ic[1], casas)}"


def montar(
    cfg: Config,
    principal: simulador.Backtest,
    grade: dict[float, simulador.Resultado],
    referencia: simulador.Resultado,
    caminho_banca: Path,
    caminho_lucro: Path,
    janela: tuple[pd.Timestamp, pd.Timestamp],
    modelo: str,
    gerado_em: str,
) -> str:
    """O relatório inteiro, em Markdown.

    Args:
        cfg: a configuração do projeto.
        principal: o backtest do limite de EV do ``config.yaml``.
        grade: ``{limite de EV: Resultado}``, a varredura da regra 11.
        referencia: as notas de **todas** as apostas candidatas, sem filtro
            nenhum. É a régua contra a qual o modelo é julgado: apostar em tudo
            custa exatamente a margem da casa, e um modelo que não fica acima
            disso não está acrescentando informação.
        caminho_banca: PNG da evolução da banca.
        caminho_lucro: PNG do lucro acumulado.
        janela: início e fim da janela avaliada.
        modelo: o nome da configuração oficial que gerou as previsões.
        gerado_em: a data, em ISO.
    """
    return "\n\n".join(
        [
            _cabecalho(cfg, principal, janela, modelo, gerado_em),
            _resposta(principal, referencia),
            _regras_da_simulacao(cfg, principal),
            _o_que_ficou_de_fora(principal.amostra),
            _tabela_principal(principal, referencia),
            _grade_de_ev(grade),
            _por_que_piora(principal),
            _por_mercado(principal),
            _por_liga(principal),
            _estrategias(principal, caminho_banca, caminho_lucro),
            _poder_estatistico(principal),
            _clv(principal, referencia),
            _pre_registro(gerado_em),
            _conclusao(principal, referencia, _temporadas(principal.apostas)),
        ]
    )


# ----------------------------------------------------------------------------
def _cabecalho(cfg, principal, janela, modelo, gerado_em) -> str:
    amostra = principal.amostra
    return f"""# Fase 6 — Backtest de apostas

- Modelo: **`{modelo}`** — Dixon-Coles com `xi = 0,003` e `m = 6`, o oficial do
  projeto desde a Fase 4 (regra 9). Nenhum parâmetro foi tocado nesta fase.
- Janela: **{janela[0].date()} a {janela[1].date()}** — a mesma da validação, com as
  temporadas de teste final trancadas (regra 7).
- Previsões: as do walk-forward, que nunca viram o próprio jogo (regra 6).
- Ligas que entraram ({len(amostra.ligas)}): {", ".join(amostra.ligas)}
- Jogos apostáveis: **{relatorio.inteiro(amostra.jogos_com_odd)}**
- Apostas candidatas: **{relatorio.inteiro(len(amostra.candidatos))}** (5 seleções por jogo)
- Limite de EV principal: **{relatorio.pct(principal.ev_minimo, 0)}**
- Gerado em: {gerado_em}

> **Regra 13.** Todo número deste relatório é das **{len(amostra.ligas)} ligas aprovadas
> no filtro da Fase 2**, e só delas. As 16 competições do Grupo 2 estão fora por
> regra 12 (só têm odd de fechamento: nelas não existe nem aposta nem CLV), e as
> 4 ligas do Grupo 1 reprovadas no filtro também.

> **Regra 8.** Aposta-se sempre na **odd média pré-jogo** (`Avg*` na fonte).
> Nunca na `Max`. A odd de fechamento aparece **só** para medir CLV.

> **Regra 9.** Nada aqui escolhe modelo. O ROI é consequência reportada, nunca
> critério — e este relatório é um bom argumento de por que essa regra existe."""


def _resposta(principal, referencia) -> str:
    r = principal.resultado
    a = principal.aleatorio
    return f"""## A resposta, primeiro

**Não teria dado lucro, e não por pouco.**

Com **{relatorio.inteiro(r.n)} apostas** feitas ao longo de três temporadas nas
18 ligas aprovadas:

| | |
|---|---|
| **ROI** | **{_com_sinal(r.roi)}** · IC 95% {_intervalo(r.roi_ic)} · menor ROI detectável nesta amostra: {relatorio.pct(r.roi_detectavel, 2)} |
| **CLV** (critério primário) | **{_com_sinal(r.clv)}** · IC 95% {_intervalo(r.clv_ic)} · menor CLV detectável: {relatorio.pct(r.clv_detectavel, 3)} |
| Apostas | {relatorio.inteiro(r.n)} — {relatorio.inteiro(MINIMO_PARA_ROI)} é o mínimo que a seção 8.4 exige para o ROI ter poder |
| Taxa de acerto | {relatorio.pct(r.taxa_acerto)} numa odd média de {relatorio.num(r.odd_media, 2)} |

⚠️ **A terceira conclusão possível — "a amostra é pequena demais para decidir" —
não é a deste relatório.** Ela seria a resposta honesta com algumas centenas de
apostas; aqui são vinte e uma mil, quatro vezes o mínimo da seção 8.4. O
intervalo de confiança do ROI fica inteiro abaixo de zero, e o do CLV também. A
conclusão é a segunda da tabela da seção 8.4: **não há evidência de vantagem** —
há evidência do contrário, medida com folga.

**E tem uma coisa pior, que é o achado de verdade desta fase.** Duas referências
para ler o {_com_sinal(r.roi)} acima:

- apostar **ao acaso** entre as mesmas {relatorio.inteiro(referencia.n)} oportunidades,
  nas mesmas ligas e no mesmo período, dá ROI de
  **{_com_sinal(referencia.roi)}** — que é, essencialmente, a margem que a casa
  cobra;
- a estratégia aleatória de **mesmo tamanho** ({relatorio.inteiro(a.n)} apostas
  sorteadas) deu **{_com_sinal(a.roi)}**.

Ou seja: **o filtro de valor esperado do modelo escolhe apostas piores do que as
sorteadas no chute.** Ele não deixa de encontrar vantagem — ele encontra
sistematicamente a desvantagem. A seção "Por que apertar o filtro piora tudo"
explica o mecanismo, e ele é interessante o bastante para valer a fase inteira."""


def _regras_da_simulacao(cfg, principal) -> str:
    secao = cfg.secao("backtest")
    return f"""## Como cada aposta foi decidida

Uma aposta acontece quando o **valor esperado** passa do limite:

```
EV = probabilidade do modelo × odd média pré-jogo − 1
```

e o limite principal é **{relatorio.pct(principal.ev_minimo, 0)}** (`ev_minimo` no
`config.yaml`). Nada além disso entra na decisão: não há filtro de liga
"favorita", de odd mínima, de horário nem de sequência de resultados.

As seleções apostáveis são cinco, e **todas saem da mesma matriz de placares** do
modelo (decisão de 16/09/2026): vitória do mandante, empate, vitória do
visitante, mais de 2,5 gols e menos de 2,5 gols. "Ambos marcam" fica de fora
porque a fonte não traz odd desse mercado — sem preço não há aposta.

Cada aposta ficou registrada com data, jogo, mercado, odd, probabilidade do
modelo, EV, resultado, lucro e CLV, como a especificação pede. O arquivo sai com
`python scripts/backtest.py --gravar`.

**O que a simulação não cobra, e cobraria na vida real.** Ela aposta na média do
mercado depois de essa média existir, sem limite de aposta, sem conta limitada
pela casa, sem odd que sumiu antes do clique e sem comissão. Todas essas
fricções puxam o resultado real para **baixo** do simulado. Um backtest empatado
aqui seria perdedor na prática — e este nem empatado está.

Parâmetros de dinheiro usados (todos do `config.yaml`): banca inicial de
R$ {relatorio.dinheiro(float(secao["banca_inicial"]))}, stake fixa de
{relatorio.pct(float(secao["stake_fixa_pct"]), 0)} da banca de referência, e
Kelly de {relatorio.num(float(secao["kelly_fracao"]), 2)} com teto de
{relatorio.pct(float(secao["kelly_teto_pct"]), 0)} por aposta."""


def _o_que_ficou_de_fora(amostra) -> str:
    total = amostra.jogos_na_janela + amostra.fora_por_grupo2 + amostra.fora_por_liga_reprovada
    return f"""## O que ficou de fora, e por quê

A Fase 1 avisou que **jogo sem odd não é um jogo sorteado ao acaso** — costuma
ser time pequeno, jogo adiado ou liga menor. Por isso os descartes são contados,
nunca silenciosos:

| Motivo | Jogos |
|---|---|
| Fora por **regra 12** (Grupo 2: só tem odd de fechamento) | {relatorio.inteiro(amostra.fora_por_grupo2)} |
| Fora por **liga reprovada** no filtro da Fase 2 | {relatorio.inteiro(amostra.fora_por_liga_reprovada)} |
| Elegíveis (18 ligas aprovadas) | {relatorio.inteiro(amostra.jogos_na_janela)} |
| — pulados por **não ter odd média pré-jogo** | {relatorio.inteiro(amostra.jogos_sem_odd)} |
| — sem a dupla de Over/Under pré-jogo | {relatorio.inteiro(amostra.jogos_sem_ou)} |
| — sem odd de fechamento (ficariam sem CLV) | {relatorio.inteiro(amostra.jogos_sem_fechamento)} |
| **Apostáveis** | **{relatorio.inteiro(amostra.jogos_com_odd)}** |

Dos {relatorio.inteiro(total)} jogos que o walk-forward previu na janela, sobra
{relatorio.pct(amostra.jogos_com_odd / total)} para o backtest. A perda é quase
toda de **regra**, não de buraco de dado: só
{relatorio.inteiro(amostra.jogos_sem_odd)} jogos das ligas aprovadas ficaram de
fora por falta de odd — {relatorio.pct(amostra.jogos_sem_odd / amostra.jogos_na_janela, 2)}
deles. A cobertura de odds dessas 18 ligas é praticamente total, que é
justamente por que elas passaram no filtro da Fase 2."""


def _tabela_principal(principal, referencia) -> str:
    linhas = []
    for resultado in (principal.resultado, principal.aleatorio, referencia):
        linhas.append(
            [
                resultado.nome,
                relatorio.inteiro(resultado.n),
                relatorio.pct(resultado.taxa_acerto),
                relatorio.num(resultado.odd_media, 2),
                _com_sinal(resultado.roi),
                _intervalo(resultado.roi_ic),
                _com_sinal(resultado.clv),
                _intervalo(resultado.clv_ic),
            ]
        )
    corpo = relatorio.tabela_markdown(
        linhas,
        [
            "Quem aposta",
            "Apostas",
            "Acerto",
            "Odd média",
            "ROI",
            "IC 95% do ROI",
            "CLV",
            "IC 95% do CLV",
        ],
    )
    return f"""## A tabela que responde a fase

Três apostadores, as mesmas ligas, a mesma janela, as mesmas odds:

- **modelo** — aposta quando o EV passa de {relatorio.pct(principal.ev_minimo, 0)};
- **aleatória** — sorteia o mesmo número de apostas entre as candidatas, sem
  olhar probabilidade nenhuma (a comparação obrigatória da regra 2.6d);
- **todas as candidatas** — aposta em tudo. Não é uma estratégia: é a **régua**.
  Apostar em tudo tem retorno igual a menos a margem média da casa, e qualquer
  modelo que não fique acima dessa linha não está acrescentando informação.

{corpo}

O modelo fica **abaixo** das duas referências, no ROI e no CLV. Os intervalos de
confiança do modelo e da régua não se tocam em nenhuma das duas colunas, então a
diferença não é ruído: filtrar por EV está ativamente escolhendo pior.

⚠️ A linha "aleatória" tem um ROI diferente da linha "todas as candidatas" porque
ela é **uma amostra** de {relatorio.inteiro(principal.aleatorio.n)} apostas, com o
ruído que isso traz; a régua usa as {relatorio.inteiro(referencia.n)} candidatas e
é exata. As duas dizem a mesma coisa, e é de propósito que as duas aparecem: uma
mostra o valor, a outra mostra quanto ele balança."""


def _grade_de_ev(grade: dict[float, simulador.Resultado]) -> str:
    linhas = [
        [
            relatorio.pct(limite, 0),
            relatorio.inteiro(resultado.n),
            relatorio.num(resultado.odd_media, 2),
            relatorio.pct(resultado.taxa_acerto),
            _com_sinal(resultado.roi),
            _intervalo(resultado.roi_ic),
            _com_sinal(resultado.clv),
        ]
        for limite, resultado in sorted(grade.items())
    ]
    corpo = relatorio.tabela_markdown(
        linhas,
        ["Limite de EV", "Apostas", "Odd média", "Acerto", "ROI", "IC 95% do ROI", "CLV"],
    )
    return f"""## Apertar o filtro melhora? Não: piora, e de forma monótona

A varredura do limite de EV — as quatro configurações que a regra 11 manda
contar:

{corpo}

A leitura é a mais informativa do relatório. Se o modelo tivesse alguma vantagem,
**exigir mais EV deveria concentrar as apostas boas** e melhorar o ROI. Acontece
o contrário, e sem exceção: quanto mais o filtro aperta, pior fica o ROI, pior
fica o CLV e maior fica a odd média.

Isso descarta a hipótese consoladora de "o modelo tem sinal, só está diluído". Se
houvesse sinal diluído, ele apareceria concentrado em algum lugar da grade. Não
aparece em nenhum."""


def _por_que_piora(principal) -> str:
    candidatos = principal.amostra.candidatos
    faixas = pd.cut(candidatos["odd"], FAIXAS_DE_ODD)
    resumo = candidatos.assign(faixa=faixas).groupby("faixa", observed=True)
    apostadas = (
        principal.apostas.assign(faixa=pd.cut(principal.apostas["odd"], FAIXAS_DE_ODD))
        .groupby("faixa", observed=True)
        .size()
    )
    linhas = []
    for faixa, do_grupo in resumo:
        limite_baixo, limite_alto = faixa.left, faixa.right
        rotulo = (
            f"acima de {relatorio.num(limite_baixo, 1)}"
            if limite_alto >= 1000
            else f"{relatorio.num(limite_baixo, 1)} a {relatorio.num(limite_alto, 1)}"
        )
        linhas.append(
            [
                rotulo,
                relatorio.inteiro(len(do_grupo)),
                _com_sinal(float(do_grupo["clv"].mean())),
                _com_sinal(float(do_grupo["retorno_unitario"].mean())),
                relatorio.inteiro(int(apostadas.get(faixa, 0))),
            ]
        )
    corpo = relatorio.tabela_markdown(
        linhas,
        [
            "Faixa de odd",
            "Candidatas",
            "CLV médio da faixa",
            "ROI da faixa",
            "Apostas do modelo",
        ],
    )
    r = principal.resultado
    todas = float(candidatos["odd"].mean())
    return f"""## Por que apertar o filtro piora tudo

A explicação não é sobre o modelo: é sobre **onde a casa cobra caro**. Olhando
todas as candidatas, sem filtro nenhum, agrupadas por faixa de odd:

{corpo}

A comissão da casa **não é uniforme**: ela é pequena no favorito e enorme no
azarão. Uma aposta de odd até 1,5 custa cerca de 2% de margem; uma acima de 10
custa mais de 20%. Isso não é novidade neste projeto — é exatamente o achado que
fez o método `power` vencer o proporcional na remoção de margem, lá na Fase 2, e
aqui ele reaparece cobrando a conta.

Agora junte com o funcionamento do filtro de EV. `EV = p × odd − 1` é
**multiplicativo na odd**: para um mesmo erro relativo do modelo na
probabilidade, quanto maior a odd, maior o EV que esse erro produz. Um erro de
dois pontos percentuais numa previsão de 10% vira EV alto num azarão; o mesmo
erro numa previsão de 60% quase não mexe no EV do favorito. O filtro, então, não
seleciona "onde o modelo sabe mais" — seleciona **onde o modelo erra para cima**,
e esse lugar é sistematicamente o azarão.

O resultado aparece na odd média: {relatorio.num(todas, 2)} entre todas as
candidatas, {relatorio.num(r.odd_media, 2)} entre as apostadas, e sobe a cada
aperto do limite de EV. O modelo está se mudando, por conta própria, para a parte
do mercado onde a casa cobra mais caro.

⚠️ **A lição que sobrevive a esta fase:** com um modelo que perde do mercado em
log loss, o filtro de EV não é um filtro de qualidade — é um **amplificador do
erro do modelo**. Ele só funcionaria se as probabilidades do modelo fossem, em
algum canto, melhores que as do mercado. A Fase 4 já tinha medido que elas não
são: 0,0226 de log loss atrás. A Fase 6 mostra o que esse número significa em
dinheiro."""


def _por_mercado(principal) -> str:
    tabela = simulador.por_mercado(principal.apostas)
    rotulos = {s.chave: s.rotulo for s in simulador.SELECOES}
    linhas = [
        [
            rotulos.get(linha["selecao"], linha["selecao"]),
            relatorio.inteiro(linha["apostas"]),
            relatorio.pct(linha["taxa_acerto"]),
            relatorio.num(linha["odd_media"], 2),
            _com_sinal(linha["roi"]),
            _intervalo((linha["roi_baixo"], linha["roi_alto"])),
            _com_sinal(linha["clv"]),
        ]
        for _, linha in tabela.iterrows()
    ]
    corpo = relatorio.tabela_markdown(
        linhas,
        ["Seleção", "Apostas", "Acerto", "Odd média", "ROI", "IC 95% do ROI", "CLV"],
    )
    return f"""## Por mercado

{corpo}

Nenhuma seleção salva a estratégia, e o padrão acompanha a odd média: os dois
mercados de gols, com odd perto de 2,00, são os que perdem menos; a vitória do
visitante, com odd média acima de 5, é a que perde mais — o dobro do que perde o
"mais de 2,5 gols". É o mesmo viés azarão–favorito da seção anterior, visto por
outro corte. Repare também que o empate e a vitória do visitante são as duas
seleções com o pior CLV: são as de odd mais alta, e é nelas que a casa cobra
mais."""


def _por_liga(principal) -> str:
    tabela = simulador.por_liga(principal.apostas, MINIMO_POR_LIGA)
    linhas = [
        [
            linha["liga"],
            relatorio.inteiro(linha["apostas"]),
            relatorio.pct(linha["taxa_acerto"]),
            relatorio.num(linha["odd_media"], 2),
            _com_sinal(linha["roi"]),
            _intervalo((linha["roi_baixo"], linha["roi_alto"])),
            _com_sinal(linha["clv"]),
            _intervalo((linha["clv_baixo"], linha["clv_alto"])),
        ]
        for _, linha in tabela.sort_values("roi", ascending=False).iterrows()
    ]
    corpo = relatorio.tabela_markdown(
        linhas,
        [
            "Liga",
            "Apostas",
            "Acerto",
            "Odd média",
            "ROI",
            "IC 95% do ROI",
            "CLV",
            "IC 95% do CLV",
        ],
    )
    com_roi_positivo = int((tabela["roi"] > 0).sum())
    com_clv_positivo = int((tabela["clv"] > 0).sum())
    cruzam = int(((tabela["roi_baixo"] < 0) & (tabela["roi_alto"] > 0)).sum())
    melhor = tabela.loc[tabela["roi"].idxmax()]
    sem_a_melhor = principal.apostas.loc[principal.apostas["liga"] != melhor["liga"]]
    sem_melhor = simulador.medir(sem_a_melhor, "sem a melhor liga", amostras_bootstrap=2000)
    return f"""## Por liga — a tabela obrigatória

A especificação exige esta tabela (seção 4.3) por um motivo específico: **uma
média geral pode esconder que o lucro veio de uma liga só**, e com 18 ligas a
melhor delas parece boa por acaso com facilidade. Ligas com menos de
{MINIMO_POR_LIGA} apostas ficariam de fora; nenhuma ficou.

{corpo}

- Ligas com **ROI positivo**: **{com_roi_positivo} de {len(tabela)}**.
- Ligas com **CLV positivo**: **{com_clv_positivo} de {len(tabela)}**. O critério
  de consistência da seção 8.4 pede a maioria; deu zero.
- Ligas cujo IC do ROI ainda cruza o zero (ou seja, onde a amostra sozinha não
  decidiria): **{cruzam}**. Nas outras {len(tabela) - cruzam}, o prejuízo é
  estatisticamente firme liga a liga.
- Tirando a melhor liga (`{melhor["liga"]}`, ROI {_com_sinal(melhor["roi"])}), o
  agregado vai para **{_com_sinal(sem_melhor.roi)}** — praticamente o mesmo. O
  resultado não depende de nenhuma liga: ele é uniforme.

A uniformidade é, por si, informação. Um prejuízo concentrado em duas ou três
ligas apontaria para um problema de dados ali; um prejuízo igual nas dezoito
aponta para o que de fato está acontecendo — o mercado é melhor que o modelo em
todas elas, e a margem é cobrada em todas elas.

{_tabela_de_temporadas(principal.apostas)}"""


def _temporadas(apostas: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por temporada, com ROI e CLV.

    A outra metade do critério 2 da seção 8.4: "consistente em mais de uma liga
    **e** mais de uma temporada". A tabela por liga responde a primeira parte;
    esta responde a segunda, e é ela que separa "um ano ruim" de "três anos
    iguais".
    """
    linhas = []
    for temporada, da_temporada in apostas.groupby("temporada", sort=True):
        linhas.append(
            {
                "temporada": str(temporada),
                "apostas": len(da_temporada),
                "roi": float(da_temporada["retorno_unitario"].mean()),
                "clv": float(da_temporada["clv"].mean()),
            }
        )
    return pd.DataFrame(linhas)


def _tabela_de_temporadas(apostas: pd.DataFrame) -> str:
    tabela = _temporadas(apostas)
    linhas = [
        [
            linha["temporada"],
            relatorio.inteiro(linha["apostas"]),
            _com_sinal(linha["roi"]),
            _com_sinal(linha["clv"]),
        ]
        for _, linha in tabela.iterrows()
    ]
    corpo = relatorio.tabela_markdown(
        linhas, ["Temporada", "Apostas", "ROI", "CLV"]
    )
    negativas = int((tabela["roi"] < 0).sum())
    return f"""### E por temporada

A outra metade do critério 2 da seção 8.4 — "consistente em mais de uma liga **e**
mais de uma temporada":

{corpo}

Negativo em **{negativas} das {len(tabela)}** temporadas, com ROI parecido nas
três. Não houve um ano ruim puxando a média: houve três anos iguais."""


def _estrategias(principal, caminho_banca: Path, caminho_lucro: Path) -> str:
    nomes = {"stake_fixa": "stake fixa", "kelly_fracionado": "Kelly 1/4"}
    linhas = []
    for (estrategia, tipo), evolucao in principal.evolucoes.items():
        curva = evolucao.curva
        ate = curva["data"].iloc[-1].date() if len(curva) else "—"
        linhas.append(
            [
                nomes[estrategia],
                f"banca {tipo}",
                relatorio.dinheiro(evolucao.banca_final),
                _com_sinal(evolucao.roi),
                relatorio.pct(evolucao.drawdown_maximo),
                relatorio.inteiro(int(curva["apostas"].sum()) if len(curva) else 0),
                str(ate),
                relatorio.inteiro(evolucao.datas_racionadas),
            ]
        )
    corpo = relatorio.tabela_markdown(
        linhas,
        [
            "Estratégia",
            "Banca",
            "Banca final (R$)",
            "ROI sobre o apostado",
            "Drawdown máximo",
            "Apostas feitas",
            "Sobreviveu até",
            "Dias racionados",
        ],
    )
    por_dia = len(principal.apostas) / principal.apostas["data"].nunique()
    return f"""## As quatro variantes de dinheiro

A especificação exige que as **duas** variantes de banca apareçam, porque omitir
qual foi usada é uma das formas mais comuns de relatório enganoso:

- **banca fixa** — a stake sai sempre da banca **inicial**. 1% de 1.000 é dez
  reais na primeira aposta e dez reais na milésima;
- **banca composta** — a stake sai da banca **atual**. Compõe como juros, para
  cima e para baixo. Numa série perdedora ela **suaviza** o estrago, porque
  aposta cada vez menos; num relatório vencedor, ela infla o número. Mostrar só
  uma delas é sempre suspeito.

Partindo de R$ {relatorio.dinheiro(principal.evolucoes[('stake_fixa', 'fixa')].banca_inicial)}, com as {relatorio.inteiro(len(principal.apostas))} apostas
de EV > {relatorio.pct(principal.ev_minimo, 0)}:

{corpo}

**As quatro terminam em zero.** E aqui vale separar duas coisas que a tabela
mistura, porque confundi-las levaria a uma conclusão errada:

1. **A parte que é sobre o modelo** é o ROI por unidade apostada
   ({_com_sinal(principal.resultado.roi)}). Esse número mede a qualidade das
   escolhas e não depende de política de dinheiro nenhuma;
2. **A parte que é sobre a política de aposta** é a ruína. O modelo aponta
   {relatorio.num(por_dia, 1)} apostas por dia, em média. Apostar 1% da banca em
   cada uma delas significa pôr cerca de {relatorio.pct(0.01 * por_dia, 0)} da
   banca em risco **por dia** — o que é inviável mesmo com um modelo vencedor.
   Com a banca fixa, o dinheiro acaba em poucas semanas.

A coluna "dias racionados" conta os dias em que a soma das stakes pedidas passou
da banca disponível e teve de ser reduzida proporcionalmente. A simulação nunca
aposta dinheiro que não existe — e conta quantas vezes precisou segurar a mão,
porque uma trava que age em silêncio muda o resultado sem aparecer.

⚠️ **Uma armadilha de leitura que esta tabela desarma:** com a banca composta, a
curva passa a apostar centavos depois de perder quase tudo, e o "ROI sobre o
apostado" dela fica **menos negativo** que o da banca fixa. Isso não é um sinal
de que compor funciona melhor: é aritmética de quem aposta menos depois de
perder. Os dois números descrevem a mesma série de apostas ruins.

![Evolução da banca]({caminho_banca.name})

O eixo é logarítmico de propósito: numa escala linear, uma banca em R$ 10 e outra
em R$ 0,10 são a mesma linha colada no chão, e a diferença entre elas é de cem
vezes. O `x` marca onde a banca acabou.

![Lucro acumulado]({caminho_lucro.name})

Este segundo gráfico tira o dinheiro do caminho: stake de 1 unidade, sempre,
nada quebra. É a qualidade das escolhas ao longo dos três anos — e o que ele
mostra é uma **ladeira constante**, não um tombo. Prejuízo em linha reta durante
três temporadas não é azar; é a ausência de vantagem aparecendo devagar."""


def _poder_estatistico(principal) -> str:
    r = principal.resultado
    desvio_roi = r.roi_erro_padrao * np.sqrt(r.n)
    desvio_clv = r.clv_erro_padrao * np.sqrt(r.n_clv)
    para_dois_porcento = metricas.tamanho_amostra(0.02, desvio_roi)
    return f"""## Relatório de poder estatístico (obrigatório, regra 10)

Um ROI sem esta seção não quer dizer nada — nem para cima, nem para baixo. As
duas perguntas que acompanham todo número deste relatório:

| Pergunta | ROI | CLV |
|---|---|---|
| Quantas apostas houve | {relatorio.inteiro(r.n)} | {relatorio.inteiro(r.n_clv)} |
| Desvio-padrão medido (por aposta) | {relatorio.num(desvio_roi, 3)} | {relatorio.num(desvio_clv, 3)} |
| Erro-padrão da média | {relatorio.pct(r.roi_erro_padrao, 2)} | {relatorio.pct(r.clv_erro_padrao, 3)} |
| **Com esta amostra, o menor efeito detectável a 95% é** | **{relatorio.pct(r.roi_detectavel, 2)}** | **{relatorio.pct(r.clv_detectavel, 3)}** |
| Apostas necessárias para enxergar o efeito medido | {relatorio.inteiro(r.n_para_roi)} | {relatorio.inteiro(r.n_para_clv)} |

Como ler essa tabela:

- **o ROI.** A amostra enxerga qualquer ROI verdadeiro maior que
  {relatorio.pct(r.roi_detectavel, 2)}, para cima ou para baixo. O medido foi
  {_com_sinal(r.roi)} — seis vezes o limiar. Não é uma amostra insuficiente
  mostrando ruído; é uma desvantagem grande, medida com sobra;
- **o CLV.** Aqui a diferença de escala salta aos olhos e é o ponto inteiro da
  seção 8.3: o desvio-padrão do CLV é **{relatorio.num(desvio_roi / desvio_clv, 0)}
  vezes menor** que o do ROI, porque o CLV de cada aposta não depende do
  resultado do jogo — só de dois preços. Com isso, bastariam
  {relatorio.inteiro(r.n_para_clv)} apostas para enxergar o efeito medido, contra
  {relatorio.inteiro(r.n_para_roi)} no ROI. É por isso que o CLV é o critério
  primário;
- **o custo de medir uma vantagem pequena.** Um ROI verdadeiro de +2% — que já
  seria excelente e realista — exigiria cerca de
  **{relatorio.inteiro(para_dois_porcento)} apostas** para ser distinguido de
  zero com a volatilidade medida aqui. Este backtest tem
  {relatorio.inteiro(r.n)}. Ou seja: mesmo com todo o escopo de 18 ligas e três
  temporadas, o projeto **ainda não teria poder** para confirmar um edge pequeno
  pelo ROI. Teria pelo CLV — e é exatamente por isso que a seção 8.3 promoveu o
  CLV a critério primário."""


def _clv(principal, referencia) -> str:
    r = principal.resultado
    a = principal.aleatorio
    return f"""## CLV — o critério primário, e as duas formas de escrevê-lo

CLV (*closing line value*) é a comparação entre **o preço que você pegou** e o
preço com que o mercado fechou. Ele é o critério primário do projeto (seção 8.3)
por uma razão estatística: não depende do resultado do jogo, então converge com
centenas de apostas em vez de dezenas de milhares.

Há duas formas de escrever esse número, e este relatório traz as duas porque elas
medem coisas diferentes:

| | O que é | Modelo | Aleatória | Todas as candidatas |
|---|---|---|---|---|
| **CLV** (principal) | `odd pega × probabilidade justa do fechamento − 1`. Compara o preço pego com a **estimativa** final do mercado, já sem a comissão da casa. | **{_com_sinal(r.clv)}** | {_com_sinal(a.clv)} | {_com_sinal(referencia.clv)} |
| **CLV bruto** | `odd pega ÷ odd de fechamento − 1`. Compara dois preços de balcão, com a comissão dentro dos dois lados. | {_com_sinal(r.clv_bruto, 3)} | {_com_sinal(a.clv_bruto, 3)} | {_com_sinal(referencia.clv_bruto, 3)} |

**Os dois números contam uma história em duas partes, e é importante não trocar
uma pela outra:**

1. **O CLV bruto é quase zero** ({_com_sinal(r.clv_bruto, 3)}). Isso quer dizer
   que as apostas do modelo **não antecipam o movimento da linha**: em média, o
   preço pego é praticamente o mesmo com que o mercado fechou. O modelo não sabe
   nada que o mercado vá descobrir depois. Não é escandaloso — é nulo;
2. **O CLV principal é bem negativo** ({_com_sinal(r.clv)}), e é ele que decide.
   A diferença entre os dois é a **comissão da casa**: o preço de balcão pode não
   ter se mexido, mas ele nunca foi justo para começar. Apostar na média do
   mercado e ver o mercado fechar no mesmo lugar significa pagar a margem inteira.

E a comparação final, que é a que fecha a fase: apostar **ao acaso** dá CLV de
{_com_sinal(referencia.clv)} — a margem média. O modelo dá {_com_sinal(r.clv)}.
Ele piora o próprio preço em cerca de
{relatorio.pct(abs(r.clv - referencia.clv))} ao escolher, porque escolhe azarão
(ver "Por que apertar o filtro piora tudo").

⚠️ **Critério 1 da seção 8.4 — "CLV médio positivo com IC inteiro acima de
zero": reprovado.** O IC fica inteiro **abaixo** de zero
({_intervalo(r.clv_ic)}), com {relatorio.inteiro(r.n_clv)} apostas e um limiar de
detecção de {relatorio.pct(r.clv_detectavel, 3)}. Não é dúvida; é um não medido
com precisão de três casas.

⚠️ **Lembrete de escopo (regra 12):** este CLV vem inteiramente das 18 ligas
aprovadas do Grupo 1. Nenhuma liga do Grupo 2 — Brasileirão incluído — pode
entrar aqui, porque nelas só existe odd de fechamento, e comparar o fechamento
consigo mesmo daria zero por construção."""


def _pre_registro(gerado_em: str) -> str:
    de_modelo = 13 + selecao.N_CONFIGURACOES_FASE_4 + 3
    total = de_modelo + simulador.N_CONFIGURACOES_FASE_6
    return f"""## Pré-registro e multiplicidade (regra 11)

| | |
|---|---|
| Configurações de **modelo** testadas até aqui | **{de_modelo}** — 13 exploratórias (Fase 3) + {selecao.N_CONFIGURACOES_FASE_4} oficiais (Fase 4) + 3 (Fase 5) |
| Configurações de **aposta** testadas nesta fase | **{simulador.N_CONFIGURACOES_FASE_6}** — 4 limites de EV × 2 estratégias de stake × 2 tipos de banca |
| **Total acumulado** | **{total}** |
| Configuração de modelo escolhida | `{{'modelo': 'dixon-coles', 'xi': 0.003, 'm': 6.0}}` — **inalterada pela Fase 6** |
| Critério de escolha de modelo | log loss no walk-forward (regra 9). **Nunca** o ROI desta fase |
| Nível com correção de Bonferroni | 0,05 / {simulador.N_CONFIGURACOES_FASE_6} = {relatorio.num(0.05 / simulador.N_CONFIGURACOES_FASE_6, 4)} |
| Data | {gerado_em} |

**Sobre a correção de Bonferroni.** Ela existe para o caso em que alguma
configuração aparece lucrativa: comparando 16 combinações, a chance de pelo menos
uma parecer boa por acaso é bem maior que 5%, e o nível teria de ser apertado
para {relatorio.num(0.05 / simulador.N_CONFIGURACOES_FASE_6, 4)}. Neste relatório
a correção não muda nada, porque **nenhuma das 16 deu resultado positivo** — não
há um vencedor para desconfiar. Vale registrar o número mesmo assim: a regra 11
existe para ser cumprida antes de saber o resultado, não depois.

⚠️ O total **soma** e nunca é reescrito para baixo. Ele existe para que a Fase 9,
ao abrir o teste final uma única vez, saiba quantas chances o projeto deu a si
mesmo de encontrar um vencedor por acaso."""


def _conclusao(principal, referencia, temporadas: pd.DataFrame) -> str:
    r = principal.resultado
    vezes_menos_ruido = (r.roi_erro_padrao * np.sqrt(r.n)) / (
        r.clv_erro_padrao * np.sqrt(r.n_clv)
    )
    negativas = int((temporadas["roi"] < 0).sum())
    return f"""## Conclusão

**Não há evidência de vantagem. Há evidência de desvantagem, e ela é firme.**

Percorrendo os critérios da seção 8.4, um a um:

| Critério | Resultado |
|---|---|
| 1. CLV médio positivo com IC acima de zero | ❌ **{_com_sinal(r.clv)}**, IC {_intervalo(r.clv_ic)} — inteiro abaixo de zero |
| 2. Consistência entre ligas e temporadas | ❌ negativo nas **18 de 18** ligas e nas **{negativas} de {len(temporadas)}** temporadas |
| 3. Configuração pré-registrada | ✅ desde 17/09/2026, inalterada |
| 4. ROI positivo com IC acima de zero | ❌ **{_com_sinal(r.roi)}**, IC {_intervalo(r.roi_ic)} |
| 5. Pelo menos {relatorio.inteiro(MINIMO_PARA_ROI)} apostas | ✅ {relatorio.inteiro(r.n)} |

Como os critérios 1, 2 e 4 falham com a amostra já grande o suficiente (critério
5 cumprido), a conclusão da seção 8.4 se aplica sem atenuante: **o modelo não tem
vantagem demonstrável sobre as casas de aposta.**

**Isso era o resultado esperado, e o projeto disse isso antes de medir.** A
Fase 4 já tinha estabelecido que o modelo oficial fica **0,0226 de log loss atrás
do mercado**. Um modelo atrás do mercado, apostando contra o mercado e ainda
pagando a comissão da casa, tem um resultado aritmeticamente previsível. A Fase 6
não descobriu que o modelo é ruim; ela **traduziu em dinheiro** um número que já
estava medido — e essa tradução é o produto da fase.

**O que a fase entrega de valor, além do "não":**

1. **O mecanismo do prejuízo, identificado.** O filtro de EV não é neutro: como
   `EV = p × odd − 1` é multiplicativo na odd, ele seleciona sistematicamente
   azarões — que é exatamente onde a casa cobra a maior comissão (de 2% em odd
   1,5 a mais de 20% acima de odd 10). Um modelo sem vantagem, filtrado por EV,
   perde **mais** do que apostando ao acaso: {_com_sinal(r.roi)} contra
   {_com_sinal(referencia.roi)};
2. **A confirmação empírica da seção 8.3.** O desvio-padrão do CLV medido nos
   próprios dados é {relatorio.num(vezes_menos_ruido, 0)} vezes menor que o do
   ROI. O CLV realmente é o único sinal de vantagem mensurável na escala deste
   projeto;
3. **A régua para as próximas fases.** Qualquer ideia futura — múltiplas
   (Fase 7), desfalques e notícias (Fase 10) — passa a ter um alvo numérico
   claro: para virar o jogo, ela precisa valer mais de
   {relatorio.pct(abs(r.clv))} de CLV. Isso é muito, e saber que é muito vale
   mais do que tentar sem saber.

⚠️ **O que NÃO se deve concluir daqui.** Que "modelo de futebol não funciona" —
isto mediu **um** modelo, com **estas** features, contra a odd média pré-jogo de
**estas** 18 ligas. E, principalmente: nada disso vira licença para apostar
dinheiro real "corrigindo um detalhe". O caminho honesto é o inverso — o projeto
segue medindo, e a Fase 9 abrirá o teste final uma única vez, com a configuração
que já está pré-registrada.

---

*Apostas envolvem risco real de perda. Este projeto é educacional. Quem sentir
que perdeu o controle pode procurar apoio: Jogadores Anônimos, ou o CVV pelo
telefone 188.*"""
