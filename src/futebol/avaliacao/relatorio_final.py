"""O relatório final: o cofre aberto, lido pelo critério da seção 8.4.

⚠️ **Este relatório tem uma obrigação que nenhum outro do projeto teve: ele
precisa estar escrito de um jeito que não deixe o resultado ser reinterpretado
depois.**

Todos os outros relatórios podiam dizer "vamos medir melhor na próxima fase".
Este não pode. O cofre abre uma vez, e o que sair dele é a resposta. Por isso o
veredito não é um parágrafo de conclusão no fim: é a **tabela dos cinco
critérios**, com ✅ e ❌, o mais perto que texto consegue chegar de um resultado
que não se negocia.

Três cuidados que a estrutura toma:

1. **o critério é aplicado à linha pré-registrada, e só a ela.** Outras linhas
   aparecem como contexto (a régua, o mercado, a tabela por liga), nunca como
   veredito alternativo. Se o EV > 5% falhar e alguma outra coisa parecer boa, a
   conclusão continua sendo a da linha registrada;
2. **CLV antes de ROI**, porque é o critério primário (seção 8.3) e porque é o
   único que esta amostra consegue medir com poder;
3. **o que não deu para medir é dito**, e não omitido. Uma liga com poucas
   apostas não vira "sem vantagem": vira "amostra insuficiente", que é uma
   afirmação diferente.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from futebol import relatorio
from futebol.avaliacao import graficos, teste_final
from futebol.backtest import simulador
from futebol.config import Config

#: Ligas com menos apostas que isto ficam fora da tabela por liga — e o corte é
#: dito no relatório, porque liga omitida em silêncio é liga que some.
MINIMO_POR_LIGA = 100

#: O mínimo que a seção 8.4 exige para o ROI ter algum poder (critério 5).
MINIMO_PARA_ROI = 5000


def _sinal(valor: float, casas: int = 2) -> str:
    return ("+" if valor >= 0 else "") + relatorio.pct(valor, casas)


def _ic(intervalo: tuple[float, float], casas: int = 2) -> str:
    baixo, alto = intervalo
    return f"{_sinal(baixo, casas)} a {_sinal(alto, casas)}"


def _positivo_com_ic(medida, campo: str) -> bool:
    """O valor é positivo **e** o intervalo inteiro está acima de zero?

    É a forma que a seção 8.4 usa nos critérios 1 e 4. "Positivo" sozinho não
    basta: um ROI de +2% com intervalo de −40% a +44% não é evidência de nada.
    """
    valor = getattr(medida, campo)
    baixo, _ = getattr(medida, f"{campo}_ic")
    return bool(valor > 0 and baixo > 0)


# ----------------------------------------------------------------------------
# O veredito
# ----------------------------------------------------------------------------
def criterios(resultado: teste_final.Resultado, por_liga: pd.DataFrame) -> list[dict]:
    """Os cinco critérios da seção 8.4, aplicados à linha pré-registrada.

    Retorna:
        Uma lista de ``{numero, tipo, texto, cumprido, detalhe}``.
    """
    r = resultado.aposta
    ligas_com_amostra = len(por_liga)
    ligas_positivas = (
        int((por_liga["clv"] > 0).sum()) if ligas_com_amostra else 0
    )
    temporadas = _por_temporada(resultado.apostas)
    temporadas_positivas = int((temporadas["clv"] > 0).sum())

    consistente = (
        ligas_com_amostra > 0
        and ligas_positivas > ligas_com_amostra / 2
        and temporadas_positivas == len(temporadas)
    )

    return [
        {
            "numero": 1,
            "tipo": "primário",
            "texto": "CLV médio positivo, com o intervalo de 95% inteiro acima de zero",
            "cumprido": _positivo_com_ic(r, "clv"),
            "detalhe": f"{_sinal(r.clv)} (IC {_ic(r.clv_ic)}, {relatorio.inteiro(r.n_clv)} apostas)",
        },
        {
            "numero": 2,
            "tipo": "primário",
            "texto": "Consistência em mais de uma liga e mais de uma temporada",
            "cumprido": consistente,
            "detalhe": (
                f"CLV positivo em {ligas_positivas} de {ligas_com_amostra} ligas "
                f"com ao menos {MINIMO_POR_LIGA} apostas e em "
                f"{temporadas_positivas} de {len(temporadas)} temporadas"
            ),
        },
        {
            "numero": 3,
            "tipo": "primário",
            "texto": "Configuração pré-registrada antes de abrir o teste final",
            "cumprido": True,
            "detalhe": (
                "fechada em 21/09/2026, congelada em "
                "`avaliacao.teste_final.CONFIGURACAO` e conferida contra o "
                "`config.yaml` antes da leitura"
            ),
        },
        {
            "numero": 4,
            "tipo": "secundário",
            "texto": "ROI positivo, com o intervalo de 95% inteiro acima de zero",
            "cumprido": _positivo_com_ic(r, "roi"),
            "detalhe": f"{_sinal(r.roi)} (IC {_ic(r.roi_ic)})",
        },
        {
            "numero": 5,
            "tipo": "secundário",
            "texto": f"Pelo menos {relatorio.inteiro(MINIMO_PARA_ROI)} apostas simuladas",
            "cumprido": r.n >= MINIMO_PARA_ROI,
            "detalhe": f"{relatorio.inteiro(r.n)} apostas",
        },
    ]


def veredito(lista: list[dict]) -> tuple[bool, str]:
    """A conclusão que a seção 8.4 manda tirar, e ela não é negociável.

    Retorna:
        ``(passou, frase)``. ``passou`` é True só se **todos** os primários
        forem cumpridos.
    """
    primarios = [c for c in lista if c["tipo"] == "primário"]
    falharam = [c for c in primarios if not c["cumprido"]]
    if not falharam:
        return True, (
            "Há **indício** de vantagem, e a palavra é essa: indício. Os três "
            "critérios primários foram cumpridos, o que autoriza continuar "
            "medindo — não autoriza concluir que o modelo ganha dinheiro."
        )
    numeros = [str(c["numero"]) for c in falharam]
    lista_legivel = (
        numeros[0]
        if len(numeros) == 1
        else " e ".join([", ".join(numeros[:-1]), numeros[-1]])
    )
    plural = "o critério primário" if len(numeros) == 1 else "os critérios primários"
    return False, (
        "**O modelo não tem vantagem demonstrável sobre as casas.** Falhou "
        f"{plural} {lista_legivel} da seção 8.4, e a regra do projeto é "
        "explícita: se qualquer primário falhar, a conclusão é essa."
    )


# ----------------------------------------------------------------------------
# Recortes
# ----------------------------------------------------------------------------
def _por_temporada(apostas: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Uma linha por temporada — o critério 2 pede mais de uma."""
    linhas = []
    for temporada, da_temporada in apostas.groupby("temporada", sort=True):
        medida = simulador.medir(
            da_temporada, nome=str(temporada), amostras_bootstrap=2000, seed=seed
        )
        linhas.append({"temporada": str(temporada), **medida.como_linha()})
    return pd.DataFrame(linhas)


def _sem_a_melhor_liga(
    apostas: pd.DataFrame, por_liga: pd.DataFrame, seed: int = 42
) -> tuple[str, simulador.Resultado] | None:
    """O resultado sem a liga de melhor CLV.

    ⚠️ Exigência da seção 8.4: "se o resultado sumir ao tirar a melhor liga, era
    sorte". Com 18 ligas, a melhor delas parece boa por acaso com facilidade.
    """
    if por_liga.empty:
        return None
    melhor = str(por_liga.loc[por_liga["clv"].idxmax(), "liga"])
    restante = apostas.loc[apostas["liga"] != melhor]
    if restante.empty:
        return None
    return melhor, simulador.medir(
        restante, nome=f"sem {melhor}", amostras_bootstrap=2000, seed=seed
    )


# ----------------------------------------------------------------------------
# O texto
# ----------------------------------------------------------------------------
def resumo_para_o_terminal(resultado: teste_final.Resultado) -> str:
    """O essencial, para quem acabou de rodar o comando."""
    r = resultado.aposta
    por_liga = simulador.por_liga(resultado.apostas, MINIMO_POR_LIGA)
    lista = criterios(resultado, por_liga)
    passou, frase = veredito(lista)

    linhas = [
        "=" * 70,
        "TESTE FINAL - a resposta, uma vez",
        "=" * 70,
        f"  janela ......... {resultado.janela.resumo()}",
        f"  apostas ........ {relatorio.inteiro(r.n)} (EV > 5%, pre-registrado)",
        f"  CLV ............ {_sinal(r.clv)}  IC {_ic(r.clv_ic)}   <- criterio primario",
        f"  ROI ............ {_sinal(r.roi)}  IC {_ic(r.roi_ic)}",
        f"  regua (tudo) ... ROI {_sinal(resultado.regua.roi)} em "
        f"{relatorio.inteiro(resultado.regua.n)} candidatas",
        f"  log loss ....... modelo {relatorio.num(resultado.medida_modelo.log_loss)} x "
        f"mercado {relatorio.num(resultado.medida_mercado.log_loss)}",
        "-" * 70,
    ]
    for c in lista:
        marca = "OK  " if c["cumprido"] else "NAO "
        linhas.append(f"  {marca}{c['numero']}. {c['texto']}")
    linhas += [
        "-" * 70,
        "  VEREDITO: " + ("ha indicio de vantagem" if passou else "SEM vantagem demonstravel"),
        "=" * 70,
    ]
    return "\n".join(linhas)


def montar(
    resultado: teste_final.Resultado,
    cfg: Config,
    caminho_banca: Path,
    caminho_clv: Path,
    gerado_em: date,
) -> str:
    """O relatório inteiro, em Markdown."""
    por_liga = simulador.por_liga(resultado.apostas, MINIMO_POR_LIGA)
    temporadas = _por_temporada(resultado.apostas)
    lista = criterios(resultado, por_liga)
    passou, frase = veredito(lista)
    sem_melhor = _sem_a_melhor_liga(resultado.apostas, por_liga)

    partes = [
        _cabecalho(resultado, gerado_em),
        _o_veredito(lista, passou, frase),
        _a_resposta(resultado),
        _o_pre_registro(),
        _de_onde_saiu(resultado),
        _o_modelo_contra_o_mercado(resultado),
        _o_clv(resultado),
        _por_liga_texto(por_liga, sem_melhor, caminho_clv),
        _por_temporada_texto(temporadas),
        _por_mercado_texto(resultado),
        _a_banca(resultado, cfg, caminho_banca),
        _o_que_isto_nao_diz(resultado),
        _fecho(passou, frase),
    ]
    return "\n\n".join(partes) + "\n"


def _cabecalho(resultado: teste_final.Resultado, gerado_em: date) -> str:
    j = resultado.janela
    return f"""# Teste final — o cofre aberto

*Gerado em {gerado_em.strftime("%d/%m/%Y")} por `python scripts/teste_final.py`.*

Este relatório é o fim da linha do projeto. As temporadas que ele mede estiveram
trancadas desde a Fase 1: nenhum modelo as viu, nenhum parâmetro foi escolhido
olhando para elas, nenhum backtest as usou. Elas foram abertas **uma vez**, com
a configuração registrada antes, para responder uma pergunta:

> O que este projeto vinha afirmando se sustenta em dados que ele nunca tocou?

**Janela:** {j.resumo()}.

**O que continua trancado:** {relatorio.inteiro(j.ainda_trancados)} jogos das
temporadas em andamento (2026, 2026/27). Temporada incompleta não é amostra de
temporada, e o cofre foi desenhado mais largo que o teste de propósito."""


def _o_veredito(lista: list[dict], passou: bool, frase: str) -> str:
    linhas = [
        [
            f"{c['numero']}",
            c["tipo"],
            c["texto"],
            "✅" if c["cumprido"] else "❌",
            c["detalhe"],
        ]
        for c in lista
    ]
    tabela = relatorio.tabela_markdown(
        linhas, ["#", "Tipo", "Critério (seção 8.4)", "", "Medido"]
    )
    return f"""## O veredito

{tabela}

{frase}

⚠️ **Esta tabela é o resultado do projeto, e ela não se renegocia.** Se algum
número mais abaixo parecer melhor que o da linha pré-registrada, ele **não**
substitui o veredito: escolher a linha depois de ver qual saiu melhor é
exatamente o que o pré-registro existe para impedir."""


def _a_resposta(resultado: teste_final.Resultado) -> str:
    r = resultado.aposta
    regua = resultado.regua
    diferenca = r.roi - regua.roi
    return f"""## A resposta em números

| | Valor | IC 95% | Apostas |
|---|---|---|---|
| **CLV** (critério primário) | **{_sinal(r.clv)}** | {_ic(r.clv_ic)} | {relatorio.inteiro(r.n_clv)} |
| **ROI** | **{_sinal(r.roi)}** | {_ic(r.roi_ic)} | {relatorio.inteiro(r.n)} |
| CLV bruto (odd pega ÷ odd de fechamento − 1) | {_sinal(r.clv_bruto)} | — | {relatorio.inteiro(r.n_clv)} |
| Taxa de acerto | {relatorio.pct(r.taxa_acerto)} | — | odd média {relatorio.num(r.odd_media, 2)} |

**A régua, sem a qual esses números não se leem.** Apostar em **todas** as
{relatorio.inteiro(regua.n)} candidatas — sem modelo nenhum, sem filtro — daria
ROI de {_sinal(regua.roi)} e CLV de {_sinal(regua.clv)}. O filtro de EV do
modelo entregou {_sinal(r.roi)}, ou seja **{_sinal(diferenca)}** em relação a
apostar sem pensar.

O menor efeito que esta amostra conseguiria detectar é
{relatorio.pct(r.roi_detectavel, 2)} no ROI e {relatorio.pct(r.clv_detectavel, 3)}
no CLV. É por isso que o CLV é o critério primário: ele enxerga um efeito
{relatorio.num(r.roi_detectavel / r.clv_detectavel, 0)} vezes menor que o ROI,
na mesma amostra."""


def _o_pre_registro() -> str:
    c = teste_final.CONFIGURACAO
    return f"""## O que estava registrado antes de abrir

Congelado em `src/futebol/avaliacao/teste_final.py` e conferido contra o
`config.yaml` **antes** da primeira leitura de temporada trancada. O commit que
traz essas constantes antecede, no histórico do Git, o commit que traz este
relatório — e essa ordem é a única testemunha possível, porque o `CLAUDE.md`
deste projeto não é versionado.

| O quê | Valor |
|---|---|
| Modelo | Dixon-Coles, `xi = {c["xi"]}`, `m = {c["jogos_equivalentes"]:g}`, fator casa por liga |
| Mercados | 1X2 (mandante, empate, visitante) + Over/Under 2,5 |
| Odd da aposta | **média pré-jogo** — nunca a máxima (regra 8) |
| Odd do CLV | fechamento, margem removida pelo método `power` |
| Limite de EV | **{relatorio.pct(float(c["ev_minimo"]), 0)}** |
| Stake | fixa, {relatorio.pct(float(c["stake_fixa_pct"]), 0)} da banca |
| Banca | fixa (a composta aparece ao lado) |
| Ligas | as 18 aprovadas pelo filtro da Fase 2 |
| Configurações testadas antes | **{teste_final.CONFIGURACOES_TESTADAS}** |

⚠️ **O limite de EV registrado é 5%, e o projeto já sabia que era o pior dos
quatro que a Fase 6 mediu.** Registrá-lo assim mesmo é o ponto: a alternativa
seria abrir o cofre, olhar os quatro e escolher o que saiu melhor — que é
seleção por ROI, o que a regra 9 proíbe, e que produziria um número sem
significado."""


def _de_onde_saiu(resultado: teste_final.Resultado) -> str:
    a = resultado.amostra
    return f"""## De onde as apostas saíram

Jogo sem odd não é um jogo sorteado ao acaso — costuma ser time pequeno, jogo
adiado ou liga menor —, então quantos ficaram de fora e por quê precisa estar
escrito (regra 13).

| | Jogos |
|---|---|
| Previstos pelo walk-forward nas ligas aprovadas | {relatorio.inteiro(a.jogos_na_janela)} |
| Com a odd pré-jogo de 1X2 completa | {relatorio.inteiro(a.jogos_com_odd)} |
| Sem odd pré-jogo (fora) | {relatorio.inteiro(a.jogos_sem_odd)} |
| Sem a dupla de Over/Under | {relatorio.inteiro(a.jogos_sem_ou)} |
| Sem odd de fechamento (não dá para medir CLV) | {relatorio.inteiro(a.jogos_sem_fechamento)} |
| Fora por serem do Grupo 2 (regra 12) | {relatorio.inteiro(a.fora_por_grupo2)} |
| Fora por liga reprovada na Fase 2 | {relatorio.inteiro(a.fora_por_liga_reprovada)} |

**Ligas que entraram ({len(a.ligas)}):** {", ".join(a.ligas)}."""


def _o_modelo_contra_o_mercado(resultado: teste_final.Resultado) -> str:
    modelo = resultado.medida_modelo
    mercado = resultado.medida_mercado
    distancia = modelo.log_loss - mercado.log_loss
    return f"""## O modelo contra o mercado, fora da amostra

Antes de qualquer conta de dinheiro: o modelo prevê melhor ou pior que as odds,
em dados que ele nunca viu?

| Quem prevê | Jogos | Log loss | Brier | Acurácia | Calibração (ECE) |
|---|---|---|---|---|---|
| {modelo.nome} | {relatorio.inteiro(modelo.n)} | {relatorio.num(modelo.log_loss)} | {relatorio.num(modelo.brier)} | {relatorio.pct(modelo.acuracia)} | {relatorio.num(modelo.ece)} |
| mercado (fechamento) | {relatorio.inteiro(mercado.n)} | {relatorio.num(mercado.log_loss)} | {relatorio.num(mercado.brier)} | {relatorio.pct(mercado.acuracia)} | {relatorio.num(mercado.ece)} |

**Distância: {relatorio.num(distancia)} de log loss.** Na validação (Fase 5,
36.413 jogos) essa distância era 0,0226. Se o número aqui for parecido, é a
notícia mais importante do relatório depois do veredito: significa que o modelo
**não piorou** fora da amostra — ele é consistentemente o que sempre foi, e o
que ele sempre foi é pior que o mercado.

Uma distância muito **menor** aqui mereceria desconfiança, não comemoração: a
primeira hipótese seria vazamento, não talento."""


def _o_clv(resultado: teste_final.Resultado) -> str:
    r = resultado.aposta
    return f"""## O CLV, que é o critério que decide

O CLV compara a odd que se pegou com a odd de fechamento. Ele **não depende do
resultado do jogo**, então a variância por aposta é uma ordem de grandeza menor
que a do ROI — e ele converge com centenas de apostas, não dezenas de milhares.
Na escala deste projeto é o único sinal de vantagem que dá para medir de
verdade, e por isso a seção 8.3 o promoveu a critério primário.

Ele é reportado de duas formas, e as duas são necessárias:

| Forma | Valor | O que diz |
|---|---|---|
| **CLV justo** (decide) | **{_sinal(r.clv)}** | odd pega × probabilidade justa do fechamento − 1 |
| CLV bruto | {_sinal(r.clv_bruto)} | odd pega ÷ odd de fechamento − 1 |

O **bruto** responde "o modelo antecipa o movimento da linha?". O **justo**
responde "o preço que ele pegou era bom?" — e a diferença entre os dois é
exatamente a comissão da casa, que o preço de balcão sempre carregou.

**E é por isso que ele decide.** Com a volatilidade medida nesta amostra,
bastariam **{relatorio.inteiro(r.n_para_clv)} apostas** para um CLV do tamanho
do observado aparecer com significância — contra
**{relatorio.inteiro(r.n_para_roi)}** para o ROI observado. Os dois números são
pequenos porque os dois efeitos são **grandes**; o que eles comparam é o poder
das duas réguas, e o CLV é ordens de grandeza mais sensível."""


def _por_liga_texto(
    por_liga: pd.DataFrame,
    sem_melhor: tuple[str, simulador.Resultado] | None,
    caminho_clv: Path,
) -> str:
    if por_liga.empty:
        return f"""## Liga a liga

Nenhuma liga alcançou {MINIMO_POR_LIGA} apostas. O critério 2 não pode ser
conferido, e a conclusão correta sobre consistência é **amostra insuficiente**."""

    tabela = relatorio.de_dataframe(
        por_liga.sort_values("clv", ascending=False),
        {
            "liga": "Liga",
            "apostas": "Apostas",
            "roi": "ROI",
            "clv": "CLV",
            "clv_detectavel": "menor CLV detectável",
        },
        {
            "apostas": "inteiro",
            "roi": "pct2",
            "clv": "pct2",
            "clv_detectavel": "pct2",
        },
    )
    positivas = int((por_liga["clv"] > 0).sum())

    nota = ""
    if sem_melhor is not None:
        liga, medida = sem_melhor
        nota = f"""
**Tirando a melhor liga ({liga}):** CLV {_sinal(medida.clv)}
(IC {_ic(medida.clv_ic)}) em {relatorio.inteiro(medida.n_clv)} apostas. A seção
8.4 exige esta linha: se o resultado sumisse ao tirar a melhor liga, era sorte.
Com 18 ligas, a melhor delas parece boa por acaso com facilidade."""

    return f"""## Liga a liga

Uma média geral pode esconder que tudo veio de uma liga só. O critério 2 da
seção 8.4 — "CLV positivo na maioria das ligas com amostra suficiente" — só pode
ser conferido aqui.

{tabela}

Ligas com menos de {MINIMO_POR_LIGA} apostas ficam de fora da tabela.
**CLV positivo em {positivas} de {len(por_liga)}** ligas listadas.
{nota}

![CLV por liga no teste final]({caminho_clv.name})"""


def _por_temporada_texto(temporadas: pd.DataFrame) -> str:
    tabela = relatorio.de_dataframe(
        temporadas,
        {
            "temporada": "Temporada",
            "apostas": "Apostas",
            "taxa_acerto": "Acerto",
            "roi": "ROI",
            "clv": "CLV",
        },
        {"apostas": "inteiro", "taxa_acerto": "pct", "roi": "pct2", "clv": "pct2"},
    )
    return f"""## Temporada a temporada

A outra metade do critério 2. Um resultado que aparece numa temporada e some na
seguinte é ruído com sorte de calendário.

{tabela}"""


def _por_mercado_texto(resultado: teste_final.Resultado) -> str:
    tabela = relatorio.de_dataframe(
        simulador.por_mercado(resultado.apostas),
        {
            "quem": "Seleção",
            "apostas": "Apostas",
            "odd_media": "Odd média",
            "roi": "ROI",
            "clv": "CLV",
        },
        {"apostas": "inteiro", "odd_media": "num2", "roi": "pct2", "clv": "pct2"},
    )
    return f"""## Por mercado

Onde o filtro de EV levou as apostas. A Fase 6 mediu que ele empurra para o
azarão, que é onde a casa cobra mais caro — esta tabela diz se isso se repetiu
fora da amostra.

{tabela}"""


def _a_banca(
    resultado: teste_final.Resultado, cfg: Config, caminho: Path
) -> str:
    from futebol.backtest import estrategias

    secao = cfg.secao("backtest")
    inicial = float(secao["banca_inicial"])
    evolucoes = {}
    for estrategia in ("stake_fixa", "kelly_fracionado"):
        for tipo in ("fixa", "composta"):
            rotulo = f"{estrategia.replace('_', ' ')} · banca {tipo}"
            evolucoes[rotulo] = estrategias.simular_banca(
                resultado.apostas,
                estrategias.criar(estrategia, secao),
                inicial,
                tipo,
            )

    linhas = [
        [
            rotulo,
            f"R$ {relatorio.dinheiro(e.banca_final)}",
            relatorio.pct(e.drawdown_maximo),
            relatorio.inteiro(e.datas_racionadas),
            "sim" if e.quebrou else "não",
        ]
        for rotulo, e in evolucoes.items()
    ]
    tabela = relatorio.tabela_markdown(
        linhas, ["Estratégia", "Banca final", "Pior queda", "Dias racionados", "Quebrou?"]
    )

    graficos.evolucao_da_banca(
        evolucoes,
        caminho,
        banca_inicial=inicial,
        titulo="A banca no teste final",
        subtitulo=(
            f"{relatorio.inteiro(resultado.aposta.n)} apostas · EV > 5% · "
            "escala logarítmica"
        ),
    )

    return f"""## O que aconteceria com o dinheiro

⚠️ **Esta seção mede a política de dinheiro, não o modelo.** O ROI por unidade
apostada, lá em cima, é que mede a qualidade das escolhas. Uma banca que quebra
com um modelo vencedor é possível (basta apostar demais por dia), e uma que
sobrevive com um perdedor também. As duas coisas precisam ser lidas separadas.

{tabela}

![A banca no teste final]({caminho.name})

A banca pré-registrada é a **stake fixa com banca fixa**. As outras três estão
aqui porque a Fase 6 as reportou, e omiti-las agora seria escolher o que mostrar
depois de ver o resultado.

⚠️ **"Banca final R$ 0,00" com "quebrou: não" não é contradição.** Na banca
composta cada aposta é uma fração do que sobrou, então ela se aproxima do zero
sem nunca chegar: o valor arredonda para R$ 0,00 e a banca segue tecnicamente
viva. É a razão de a coluna "quebrou" existir separada do valor — e de a banca
final ser guardada direto, nunca recalculada como `inicial + lucro`, que em
ponto flutuante apagaria a diferença entre "sobrou um centésimo de centavo" e
"acabou"."""


def _o_que_isto_nao_diz(resultado: teste_final.Resultado) -> str:
    r = resultado.aposta
    return f"""## O que este teste não diz

Um relatório final honesto precisa marcar os limites do que mediu.

- **Não diz que o modelo é ruim em previsão.** Ele diz que o modelo é pior que o
  mercado, que é coisa diferente. O mercado é um agregador de milhares de
  apostadores com informação que este projeto não tem — escalação, lesão,
  motivação, dinheiro grande. Ficar a {relatorio.num(resultado.medida_modelo.log_loss - resultado.medida_mercado.log_loss)}
  de log loss dele, com placar e nada mais, é um resultado respeitável.
- **Não diz que nenhuma estratégia de aposta funciona.** Diz que **esta**, com
  este modelo, nestas ligas, nestes mercados e neste período, não funcionou.
- **Não mede o que não tem amostra.** O menor efeito detectável aqui é
  {relatorio.pct(r.roi_detectavel, 2)} no ROI. Uma vantagem real menor que isso
  existiria sem aparecer — e é por isso que o relatório nunca escreve "não
  existe vantagem", e sim "não há vantagem demonstrável".
- **Não vale para odds máximas.** Tudo aqui é na odd média pré-jogo (regra 8).
  Quem consegue sistematicamente a melhor odd entre vinte casas está jogando
  outro jogo — e é justamente assim que quase todo backtest amador produz lucro
  no papel."""


def _fecho(passou: bool, frase: str) -> str:
    extra = (
        """
Mesmo assim: começar com valores mínimos, apostar só dinheiro que se pode
perder, e lembrar que as casas costumam limitar contas lucrativas."""
        if passou
        else """
**E isso não é o fracasso do projeto — é o produto dele.** O que foi construído
aqui é a máquina de não se enganar: o cofre que impediu o modelo de ver o teste,
o pré-registro que impediu a configuração de ser escolhida depois, o intervalo
de confiança em cada número, a régua de "apostar em tudo" que impede um ROI
ruim de parecer bom, e a regra de escolher modelo por log loss e nunca por
lucro. Qualquer um desses pedaços ausente produziria, com os mesmos dados, um
relatório animador e falso.

Havia caminhos fáceis para um resultado bonito: usar a odd máxima, varrer
parâmetros até o backtest fechar no azul, escolher a liga e o período que deram
certo, ou simplesmente não separar um teste final. Nenhum foi tomado, e o preço
disso é esta conclusão."""
    )
    return f"""## Conclusão

{frase}
{extra}"""


# ----------------------------------------------------------------------------
# Gravação
# ----------------------------------------------------------------------------
def escrever(
    resultado: teste_final.Resultado,
    cfg: Config,
    pasta: str,
    hoje: date | None = None,
) -> list[Path]:
    """Grava o relatório e os dois gráficos. Retorna os caminhos."""
    destino = Path(pasta)
    destino.mkdir(parents=True, exist_ok=True)
    caminho_banca = destino / "final_banca.png"
    caminho_clv = destino / "final_clv_por_liga.png"

    texto = montar(
        resultado, cfg, caminho_banca, caminho_clv, hoje or date.today()
    )
    _grafico_de_clv(resultado, caminho_clv)

    caminho = destino / "final.md"
    caminho.write_text(texto, encoding="utf-8")
    return [caminho, caminho_banca, caminho_clv]


def _grafico_de_clv(resultado: teste_final.Resultado, caminho: Path) -> Path:
    """O CLV de cada liga, com a barra de erro — porque o critério 2 é por liga."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tabela = simulador.por_liga(resultado.apostas, MINIMO_POR_LIGA)
    tabela = tabela.sort_values("clv")

    altura = max(4.0, 0.26 * len(tabela) + 1.6)
    figura, eixo = plt.subplots(figsize=(8.0, altura), dpi=150)
    figura.patch.set_facecolor("white")
    eixo.set_facecolor("white")
    for lado in ("top", "right"):
        eixo.spines[lado].set_visible(False)

    posicoes = range(len(tabela))
    baixos = tabela["clv"] - tabela["clv_baixo"]
    altos = tabela["clv_alto"] - tabela["clv"]
    eixo.errorbar(
        tabela["clv"],
        posicoes,
        xerr=[baixos, altos],
        fmt="o",
        color="#1f77b4",
        ecolor="#9ecae1",
        capsize=3,
        markersize=5,
    )
    eixo.axvline(0.0, color="#d62728", linewidth=1.2, linestyle="--")
    eixo.set_yticks(list(posicoes))
    eixo.set_yticklabels(tabela["liga"])
    eixo.set_xlabel("CLV (a linha vermelha é o zero)")
    eixo.xaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"{v * 100:.0f}%".replace(".", ","))
    )
    eixo.grid(False)
    eixo.xaxis.grid(True, color="#e8e8e8", linewidth=0.8)
    figura.tight_layout()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    figura.savefig(caminho, facecolor="white", bbox_inches="tight")
    plt.close(figura)
    return caminho
