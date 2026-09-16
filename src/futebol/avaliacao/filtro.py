"""Quais ligas valem a pena apostar — decidido por medição, não por opinião.

O pedido original do Enzo foi "as ligas em que tem apostas boas". Este módulo
é a resposta com número. Ele mede quatro coisas por liga e aplica os cortes
que estão no ``config.yaml``:

1. **margem da casa** — quanto ela cobra por aposta. É a barreira que o modelo
   precisa vencer antes de lucrar um centavo;
2. **cobertura de odds** — de que adianta uma liga boa sem odd registrada;
3. **calibração do mercado** — o mercado daquela liga é confiável;
4. **número de jogos** — histórico suficiente para treinar e para medir.

⚠️ **Margem baixa não quer dizer "fácil de ganhar".** Nas grandes ligas a
margem é baixa *porque o mercado é eficiente*: a taxa é barata e a linha é
quase impossível de bater. Nas ligas menores a margem é alta, mas as casas têm
menos informação. Qual dos dois efeitos ganha é uma das perguntas que este
projeto existe para responder — o filtro só descarta o caso em que a conta
nem começa de pé: margem tão alta que exigiria uma vantagem irreal.

A conta que manda é sempre:

    para lucrar, a vantagem do modelo precisa ser MAIOR que a margem da casa

🔎 **Sobre o critério de calibração.** Medir calibração com o ECE cru pune liga
pequena: com 1.200 jogos, o ECE é alto **mesmo num mercado perfeito**, só por
acaso amostral. Por isso o corte aqui é *relativo*: o ECE da liga é comparado
com o piso de ruído dela (:func:`futebol.avaliacao.metricas.piso_de_ruido_ece`),
e reprova quem estiver acima de um múltiplo desse piso.

⚠️ **Regra 12:** liga do Grupo 2 nunca é aprovada, por mais bem comportada que
seja — sem odd pré-jogo não existe aposta a simular.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from futebol.avaliacao import metricas
from futebol.config import Config
from futebol.odds import mercado

#: O método de remoção de margem usado para julgar a calibração das ligas.
#: ``power`` foi o mais bem calibrado no conjunto inteiro do Grupo 1
#: (ECE 0,0023 contra 0,0080 do proporcional). Ver o relatório da Fase 2.
METODO_PADRAO = "power"

#: Repetições da simulação que estima o piso de ruído do ECE. 200 já deixa a
#: estimativa estável na terceira casa, que é toda a precisão que o corte usa.
REPETICOES_PISO = 200


@dataclass(frozen=True)
class Criterios:
    """Os cortes do filtro, lidos do ``config.yaml``.

    Atributos:
        margem_maxima: margem média máxima aceita no 1X2 pré-jogo.
        cobertura_minima: fração mínima de jogos com odd pré-jogo completa.
        jogos_minimos: histórico mínimo.
        fator_ece_maximo: quantas vezes o piso de ruído o ECE pode ser.
    """

    margem_maxima: float
    cobertura_minima: float
    jogos_minimos: int
    fator_ece_maximo: float

    @classmethod
    def do_config(cls, cfg: Config) -> Criterios:
        secao = cfg.secao("filtro_qualidade_mercado")
        return cls(
            margem_maxima=float(secao["margem_maxima"]),
            cobertura_minima=float(secao["cobertura_minima_odds"]),
            jogos_minimos=int(secao["jogos_minimos"]),
            fator_ece_maximo=float(secao.get("fator_ece_maximo", 2.0)),
        )


def medir_liga(
    bloco: pd.DataFrame, *, metodo: str = METODO_PADRAO, repeticoes: int = REPETICOES_PISO
) -> dict:
    """Mede uma liga nas quatro dimensões do filtro.

    A medição usa a odd **pré-jogo**, não a de fechamento: é nela que o projeto
    aposta (regra 8), então é a margem dela que o modelo precisa vencer.
    """
    colunas_pre = list(mercado.COLUNAS[("1x2", "pre")])
    completas = bloco[colunas_pre].notna().all(axis=1)

    medida: dict = {
        "liga": bloco["liga"].iloc[0],
        "grupo": bloco["grupo"].iloc[0],
        "jogos": len(bloco),
        "jogos_com_odd": int(completas.sum()),
        "cobertura": float(completas.mean()),
    }

    if not completas.any():
        # O caso do Grupo 2 inteiro: existe liga, existe jogo, não existe odd
        # pré-jogo. Nada a medir — e nada a aprovar.
        medida.update(
            margem_pre=float("nan"),
            margem_fech=float("nan"),
            ece=float("nan"),
            piso_ece=float("nan"),
            fator_ece=float("nan"),
            log_loss=float("nan"),
            brier=float("nan"),
        )
        return medida

    com_odd = bloco[completas]
    observado = mercado.resultado_observado(com_odd, "1x2")
    probabilidades = mercado.probabilidades_do_mercado(com_odd, "1x2", "pre", metodo)

    ece = metricas.ece(probabilidades, observado)
    piso = metricas.piso_de_ruido_ece(probabilidades, repeticoes=repeticoes)

    medida.update(
        margem_pre=float(
            mercado.overround(com_odd[colunas_pre].to_numpy(dtype=float)).mean()
        ),
        margem_fech=_margem_fechamento(bloco),
        ece=ece,
        piso_ece=piso,
        fator_ece=ece / piso if piso else float("nan"),
        log_loss=metricas.log_loss(probabilidades, observado),
        brier=metricas.brier(probabilidades, observado),
    )
    return medida


def _margem_fechamento(bloco: pd.DataFrame) -> float:
    """A margem de fechamento, só para a tabela do relatório (não é critério)."""
    colunas = list(mercado.COLUNAS[("1x2", "fech")])
    completas = bloco[colunas].notna().all(axis=1)
    if not completas.any():
        return float("nan")
    return float(mercado.overround(bloco.loc[completas, colunas].to_numpy(float)).mean())


def _reprovacoes(medida: dict, criterios: Criterios) -> list[str]:
    """Os motivos pelos quais a liga não passou. Lista vazia = aprovada."""
    motivos: list[str] = []

    if medida["grupo"] != "grupo1":
        # Regra 12: sem odd pré-jogo não há aposta simulável. Este motivo é
        # estrutural, não uma nota baixa — por isso vem primeiro e sozinho.
        return ["sem odd pré-jogo (Grupo 2, regra 12)"]

    if medida["jogos"] < criterios.jogos_minimos:
        motivos.append(
            f"histórico curto ({medida['jogos']} jogos < {criterios.jogos_minimos})"
        )
    if medida["cobertura"] < criterios.cobertura_minima:
        motivos.append(
            f"cobertura de odds baixa ({medida['cobertura']:.1%} < "
            f"{criterios.cobertura_minima:.0%})"
        )
    if medida["margem_pre"] > criterios.margem_maxima:
        motivos.append(
            f"margem alta ({medida['margem_pre']:.2%} > {criterios.margem_maxima:.0%})"
        )
    if medida["fator_ece"] > criterios.fator_ece_maximo:
        motivos.append(
            f"calibração fora do esperado (ECE {medida['fator_ece']:.1f}x o piso de "
            f"ruído, limite {criterios.fator_ece_maximo:.1f}x)"
        )
    return motivos


def avaliar(
    jogos: pd.DataFrame,
    cfg: Config,
    *,
    metodo: str = METODO_PADRAO,
    repeticoes: int = REPETICOES_PISO,
) -> pd.DataFrame:
    """Aplica o filtro a todas as ligas da tabela.

    Retorna:
        Uma linha por liga, com as quatro medidas, a coluna ``aprovada`` e a
        coluna ``motivos`` (texto vazio quando passou). Ordenada pela margem
        pré-jogo, que é o critério que mais reprova.
    """
    criterios = Criterios.do_config(cfg)
    linhas = []
    for _, bloco in jogos.groupby("liga", observed=True):
        medida = medir_liga(bloco, metodo=metodo, repeticoes=repeticoes)
        motivos = _reprovacoes(medida, criterios)
        medida["aprovada"] = not motivos
        medida["motivos"] = "; ".join(motivos)
        linhas.append(medida)

    tabela = pd.DataFrame(linhas)
    return tabela.sort_values(["aprovada", "margem_pre"], ascending=[False, True]).reset_index(
        drop=True
    )


def ligas_aprovadas(avaliacao: pd.DataFrame) -> list[str]:
    """Só os códigos das ligas aprovadas, em ordem, para gravar no config."""
    return sorted(avaliacao.loc[avaliacao["aprovada"], "liga"])
