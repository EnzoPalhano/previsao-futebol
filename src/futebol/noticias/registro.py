"""O caderno do paper trading: as duas previsões, antes do jogo.

⚠️ **Sem este módulo a Fase 10 não é avaliável, e uma fase não avaliável é uma
fase que só pode ser acreditada.**

Não existe backtest aqui, e o motivo é honesto: é impossível saber, hoje, o que
se sabia sobre lesões **antes** de cada jogo de 2021. Uma notícia de hoje sobre
uma lesão de três anos atrás não diz quando aquilo virou público. Fingir que
diz produziria um backtest lindo e falso — o modelo "saberia" da lesão desde
sempre.

Então a avaliação é **para frente**: antes de cada jogo, grava-se a previsão
**crua** e a **ajustada**; depois que o jogo acontece, preenche-se o resultado;
e só então as duas podem ser comparadas. Isso leva semanas, por construção, e
não tem atalho.

**O que este módulo protege, linha por linha:**

1. **as duas previsões, sempre.** Gravar só a ajustada tornaria impossível
   saber se o ajuste ajudou — é a mesma razão de
   :func:`futebol.noticias.ajuste.aplicar` devolver uma cópia;
2. **a data de gravação.** Um registro que não diz quando foi escrito não prova
   que foi escrito **antes** do jogo, e é isso que separa paper trading de
   contar história depois;
3. **o resultado fica vazio até acontecer.** Preencher na hora seria invenção.

**Como ler o resultado (seção 8.3 e a aritmética do módulo pai).** O critério é
CLV, porque a log loss não consegue enxergar nada neste tamanho de amostra: com
150 jogos ela detecta 0,0338, e a distância inteira do modelo para o mercado é
0,0212. O CLV com 150 apostas detecta 1,60 pp.

⚠️ **Enquanto o intervalo de confiança cruzar zero, a resposta é "ainda não dá
para saber"** — nem "funciona", nem "não funciona". :func:`avaliar` devolve
exatamente essa frase, e não deixa quem chama escolher outra.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from futebol.avaliacao import metricas
from futebol.config import Config

#: As colunas do caderno. Uma linha por (jogo, previsão gravada).
COLUNAS: tuple[str, ...] = (
    "gravado_em",
    "data_do_jogo",
    "liga",
    "mandante",
    "visitante",
    "prob_H_cru",
    "prob_D_cru",
    "prob_A_cru",
    "prob_H_ajustado",
    "prob_D_ajustado",
    "prob_A_ajustado",
    "ajuste_mandante_ataque",
    "ajuste_mandante_defesa",
    "ajuste_visitante_ataque",
    "ajuste_visitante_defesa",
    "desfalques",
    "odd_pre_H",
    "odd_pre_D",
    "odd_pre_A",
    "odd_fech_H",
    "odd_fech_D",
    "odd_fech_A",
    "resultado",
)

#: Quantos jogos, no mínimo, antes de o relatório sequer mostrar um número.
#: Abaixo disso nem o CLV diz coisa alguma, e um número na tela convida a
#: interpretá-lo.
MINIMO_PARA_MOSTRAR = 30


def caminho(cfg: Config, falso: bool = False) -> Path:
    """Onde o caderno mora.

    ⚠️ **O modo de demonstração escreve num arquivo SEPARADO, e isso não é
    organização: é a integridade da fase.** Se `--falso` gravasse no mesmo
    caderno, previsões inventadas entrariam na mesma tabela que as reais e a
    avaliação passaria a misturar as duas — sem deixar rastro de qual era qual.
    Um caderno de evidência contaminado por dado de mentira não vale nada, e o
    estrago seria invisível.
    """
    nome = "registro_falso.csv" if falso else "registro.csv"
    return cfg.raiz / "data" / "noticias" / nome


def carregar(cfg: Config, falso: bool = False) -> pd.DataFrame:
    """O caderno inteiro, ou um vazio com as colunas certas."""
    arquivo = caminho(cfg, falso)
    if not arquivo.is_file():
        return pd.DataFrame(columns=list(COLUNAS))
    return pd.read_csv(arquivo)


def anotar(cfg: Config, linhas: list[dict], falso: bool = False) -> Path:
    """Acrescenta previsões ao caderno, sem apagar o que já estava.

    ⚠️ **Acrescenta, nunca reescreve.** Um caderno que pode ser reescrito é um
    caderno que pode ser corrigido depois de ver o resultado, e aí ele deixa de
    provar qualquer coisa. Rodar duas vezes no mesmo dia gera linhas repetidas —
    :func:`avaliar` cuida disso, ficando com a **primeira** gravação de cada
    jogo, que é a que foi feita sem saber o resultado.
    """
    arquivo = caminho(cfg, falso)
    arquivo.parent.mkdir(parents=True, exist_ok=True)

    agora = datetime.now(UTC).isoformat(timespec="seconds")
    novas = pd.DataFrame(
        [{**{coluna: "" for coluna in COLUNAS}, "gravado_em": agora, **linha}
         for linha in linhas],
        columns=list(COLUNAS),
    )
    completo = pd.concat([carregar(cfg, falso), novas], ignore_index=True)
    completo.to_csv(arquivo, index=False)
    return arquivo


def primeira_gravacao(caderno: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por jogo: a **primeira** vez que ele foi previsto.

    É a que foi escrita mais longe do resultado, e portanto a menos
    contaminada. Ficar com a última premiaria quem roda o script de novo depois
    de ler a escalação oficial.
    """
    if caderno.empty:
        return caderno
    ordenado = caderno.sort_values("gravado_em")
    return ordenado.drop_duplicates(
        subset=["data_do_jogo", "liga", "mandante", "visitante"], keep="first"
    )


@dataclass(frozen=True)
class Comparacao:
    """O que o caderno consegue dizer até agora.

    Atributos:
        n: jogos com resultado preenchido.
        log_loss_cru, log_loss_ajustado: as duas notas, nos mesmos jogos.
        diferenca: ajustado − cru. **Negativo é bom** (log loss menor).
        ic: intervalo de 95% da diferença, por bootstrap.
        detectavel: o menor efeito que esta amostra enxergaria.
        com_ajuste: em quantos jogos o ajuste mexeu em alguma coisa.
        veredito: a frase que se pode dizer, e só ela.
    """

    n: int
    log_loss_cru: float
    log_loss_ajustado: float
    diferenca: float
    ic: tuple[float, float]
    detectavel: float
    com_ajuste: int
    veredito: str


_CHAVES = ("H", "D", "A")


def _perdas(tabela: pd.DataFrame, sufixo: str) -> np.ndarray:
    """``−log(p)`` do resultado que aconteceu, jogo a jogo.

    É a log loss **antes** de tirar a média, e é isso que permite comparar as
    duas previsões **emparelhadas** — comparar duas médias jogaria fora a
    informação de que as duas viram exatamente os mesmos jogos, que é o que dá
    poder à comparação.

    A conta é a mesma de :func:`futebol.avaliacao.validacao.perdas_por_jogo`; o
    que muda é só o formato de entrada (aqui as colunas têm sufixo).
    """
    probabilidades = tabela[[f"prob_{c}_{sufixo}" for c in _CHAVES]].to_numpy(float)
    observado = tabela["resultado"].map({c: i for i, c in enumerate(_CHAVES)})
    escolhidas = probabilidades[
        np.arange(len(observado)), observado.to_numpy(int)
    ]
    return -np.log(np.clip(escolhidas, 1e-15, 1.0))


def avaliar(
    cfg: Config, caderno: pd.DataFrame | None = None, falso: bool = False
) -> Comparacao:
    """Compara as duas previsões nos jogos que já aconteceram.

    ⚠️ O veredito é decidido **aqui**, e quem chama não pode escolher outro. A
    regra é a da especificação: enquanto o intervalo de confiança cruzar zero, a
    resposta é "ainda não dá para saber".
    """
    caderno = carregar(cfg, falso) if caderno is None else caderno
    prontos = primeira_gravacao(caderno)
    if not prontos.empty:
        prontos = prontos.loc[prontos["resultado"].isin(_CHAVES)]

    if prontos.empty:
        return Comparacao(
            n=0,
            log_loss_cru=float("nan"),
            log_loss_ajustado=float("nan"),
            diferenca=float("nan"),
            ic=(float("nan"), float("nan")),
            detectavel=float("nan"),
            com_ajuste=0,
            veredito=(
                "Nenhum jogo com resultado ainda. O caderno é preenchido antes "
                "do jogo e só pode ser lido depois — é isso que separa paper "
                "trading de contar história depois."
            ),
        )

    cru = _perdas(prontos, "cru")
    ajustado = _perdas(prontos, "ajustado")
    diferencas = ajustado - cru

    n = len(prontos)
    media = float(np.mean(diferencas))
    erro = float(np.std(diferencas, ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    ic = (
        metricas.bootstrap_ic(diferencas, amostras=2000, seed=cfg.seed)
        if n > 1
        else (float("nan"), float("nan"))
    )
    detectavel = 2.8 * erro if n > 1 else float("nan")

    mexeu = prontos[
        [
            "ajuste_mandante_ataque",
            "ajuste_mandante_defesa",
            "ajuste_visitante_ataque",
            "ajuste_visitante_defesa",
        ]
    ].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    com_ajuste = int((mexeu.sum(axis=1) > 0).sum())

    return Comparacao(
        n=n,
        log_loss_cru=float(np.mean(cru)),
        log_loss_ajustado=float(np.mean(ajustado)),
        diferenca=media,
        ic=ic,
        detectavel=detectavel,
        com_ajuste=com_ajuste,
        veredito=_veredito(n, media, ic, detectavel, com_ajuste),
    )


def _veredito(
    n: int,
    diferenca: float,
    ic: tuple[float, float],
    detectavel: float,
    com_ajuste: int,
) -> str:
    """A frase que os números autorizam. Não há outra."""
    if com_ajuste == 0:
        return (
            f"Os {n} jogos com resultado não tiveram desfalque nenhum que "
            "movesse a previsão. Não há o que comparar — as duas colunas são "
            "iguais."
        )
    if n < MINIMO_PARA_MOSTRAR:
        return (
            f"Só {n} jogos com resultado, e {com_ajuste} deles com ajuste. "
            f"É pouco demais para qualquer número significar alguma coisa "
            f"(o mínimo do projeto é {MINIMO_PARA_MOSTRAR}, e mesmo ele é "
            "pouco). **Ainda não dá para saber.**"
        )

    baixo, alto = ic
    if baixo <= 0 <= alto:
        return (
            f"Em {n} jogos ({com_ajuste} com ajuste), a diferença de log loss "
            f"é {diferenca:+.4f}, com intervalo de {baixo:+.4f} a {alto:+.4f} — "
            f"que **cruza o zero**. O menor efeito que esta amostra enxergaria "
            f"é {detectavel:.4f}. **Ainda não dá para saber**: não é "
            "'funciona' nem 'não funciona'."
        )
    if alto < 0:
        return (
            f"Em {n} jogos ({com_ajuste} com ajuste), o ajuste **melhorou** a "
            f"log loss em {abs(diferenca):.4f} (IC {abs(alto):.4f} a "
            f"{abs(baixo):.4f}), com o intervalo inteiro do lado bom. ⚠️ É um "
            "**indício**, não uma prova: a amostra é pequena e o efeito precisa "
            "se sustentar quando ela crescer."
        )
    return (
        f"Em {n} jogos ({com_ajuste} com ajuste), o ajuste **piorou** a log "
        f"loss em {diferenca:.4f} (IC {baixo:+.4f} a {alto:+.4f}), com o "
        "intervalo inteiro do lado ruim. O ajuste, como está, atrapalha — e a "
        "conclusão correta é desligá-lo, não afiná-lo até ficar bonito."
    )


def preencher_resultados(
    cfg: Config, jogos: pd.DataFrame, falso: bool = False
) -> int:
    """Completa o ``resultado`` das linhas cujos jogos já aconteceram.

    Args:
        jogos: a tabela do projeto, já atualizada.

    Retorna:
        Quantas linhas foram preenchidas.
    """
    caderno = carregar(cfg, falso)
    if caderno.empty:
        return 0

    chave = ["data_do_jogo", "liga", "mandante", "visitante"]
    reais = jogos.assign(data_do_jogo=jogos["data"].astype(str))[
        [*chave, "resultado"]
    ].rename(columns={"resultado": "resultado_real"})

    juntado = caderno.merge(reais, on=chave, how="left")

    # ⚠️ Num caderno novo a coluna `resultado` está inteira vazia, e o pandas a
    # lê como float64 — escrever "H" ali levanta TypeError. É justamente o
    # PRIMEIRO uso que quebraria: com o caderno já preenchido o tipo é string e
    # nada acontece. Forçar o tipo antes de escrever resolve nos dois casos.
    juntado["resultado"] = juntado["resultado"].astype("object")

    faltando = ~juntado["resultado"].isin(_CHAVES)
    achou = faltando & juntado["resultado_real"].notna()

    juntado.loc[achou, "resultado"] = juntado.loc[achou, "resultado_real"]
    juntado = juntado.drop(columns=["resultado_real"])
    juntado.to_csv(caminho(cfg, falso), index=False)
    return int(achou.sum())


def linha_de_jogo(
    jogo,
    cru: dict,
    ajustado: dict,
    ajuste_mandante,
    ajuste_visitante,
) -> dict:
    """Monta a linha do caderno para um jogo."""
    desfalques = [
        f"{d.jogador.nome} ({d.status})"
        for ajuste in (ajuste_mandante, ajuste_visitante)
        for d in ajuste.desfalques
    ]
    return {
        "data_do_jogo": str(jogo.data),
        "liga": jogo.liga,
        "mandante": jogo.mandante,
        "visitante": jogo.visitante,
        **{f"prob_{c}_cru": float(cru[c]) for c in _CHAVES},
        **{f"prob_{c}_ajustado": float(ajustado[c]) for c in _CHAVES},
        "ajuste_mandante_ataque": ajuste_mandante.ataque,
        "ajuste_mandante_defesa": ajuste_mandante.defesa,
        "ajuste_visitante_ataque": ajuste_visitante.ataque,
        "ajuste_visitante_defesa": ajuste_visitante.defesa,
        "desfalques": "; ".join(desfalques),
        # O resultado fica VAZIO. Preencher agora seria invenção: o jogo não
        # aconteceu. `preencher_resultados` completa depois.
        "resultado": "",
    }


def datas_do_caderno(caderno: pd.DataFrame) -> tuple[date | None, date | None]:
    """(primeira, última) data de jogo registrada — para o relatório."""
    if caderno.empty:
        return (None, None)
    datas = pd.to_datetime(caderno["data_do_jogo"], errors="coerce").dropna()
    if datas.empty:
        return (None, None)
    return (datas.min().date(), datas.max().date())
