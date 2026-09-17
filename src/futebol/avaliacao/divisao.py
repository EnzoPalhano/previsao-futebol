"""O cofre: quais temporadas estão proibidas até a Fase 9.

A regra 7 do projeto é curta e é a mais fácil de furar sem perceber: **as
temporadas de teste final não podem ser usadas antes da Fase 9**. Elas estão em
``avaliacao.temporadas_teste_final`` no ``config.yaml``.

O motivo não é burocracia. Todo número que se olha antes de decidir vira
decisão: se o ``xi`` do Dixon-Coles for escolhido olhando 2024/25, o resultado
que 2024/25 vai dar no fim não é mais uma estimativa de desempenho futuro — é
uma medida do quanto se ajustou aos dados até acertá-los. O teste final só vale
como teste final se for aberto **uma vez**, depois de tudo estar escolhido.

Este módulo existe para essa trava ser código, e não intenção.

**Como uma temporada é reconhecida.** O ``config.yaml`` fala em códigos do site
(``2425``), e a tabela fala em ``2024/25`` — e em ``2024`` nas competições de
ano civil (Brasil, EUA, Noruega, Japão…). Comparar texto com texto deixaria
metade das competições passar em silêncio, que é exatamente a armadilha
registrada no CLAUDE.md. Por isso a comparação é pelo **ano em que a temporada
começou**::

    2425 -> começa em 2024  ->  estão trancadas todas as temporadas que
                                começaram em 2024 ou depois

Esse corte é deliberadamente mais largo que a lista do config: a temporada em
andamento (2026/27, enquanto este texto é escrito) também fica trancada. Sobrar
dado de fora do treino custa um pouco de precisão; deixar dado do futuro entrar
custa a credibilidade do projeto inteiro.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from futebol.config import Config
from futebol.dados import limpeza


@dataclass(frozen=True)
class Divisao:
    """O que ficou de fora, para o relatório poder dizer.

    Atributos:
        jogos: os jogos liberados para treino e validação.
        trancados: quantos jogos ficaram no cofre.
        ano_de_corte: o ano a partir do qual as temporadas estão trancadas.
        temporadas_trancadas: os nomes delas, para conferência.
    """

    jogos: pd.DataFrame
    trancados: int
    ano_de_corte: int
    temporadas_trancadas: tuple[str, ...]

    def resumo(self) -> str:
        """Uma linha para o relatório e para a tela."""
        lista = ", ".join(self.temporadas_trancadas)
        return (
            f"{len(self.jogos)} jogos liberados; {self.trancados} trancados até a "
            f"Fase 9 (temporadas que começaram em {self.ano_de_corte} ou depois: {lista})"
        )


def ano_de_corte(cfg: Config) -> int:
    """O ano em que começa a primeira temporada de teste final.

    Levanta:
        ValueError: se a lista do ``config.yaml`` estiver vazia — sem ela não há
            teste final, e um projeto sem teste final não deveria rodar.
    """
    codigos = cfg.secao("avaliacao")["temporadas_teste_final"]
    if not codigos:
        raise ValueError(
            "avaliacao.temporadas_teste_final está vazia no config.yaml. "
            "Sem teste final reservado não existe avaliação honesta (regra 7)."
        )
    return min(
        limpeza.ano_inicial(limpeza.temporada_do_codigo(codigo)) for codigo in codigos
    )


def e_teste_final(temporada: str, ano: int) -> bool:
    """A temporada está trancada? Vale para ``2024/25`` e para ``2024``."""
    return limpeza.ano_inicial(temporada) >= ano


def separar(jogos: pd.DataFrame, cfg: Config) -> Divisao:
    """Devolve só os jogos liberados, e o registro do que ficou de fora.

    É esta função que todo experimento anterior à Fase 9 deve chamar antes de
    medir qualquer coisa.
    """
    ano = ano_de_corte(cfg)
    trancada = jogos["temporada"].map(lambda t: e_teste_final(t, ano))
    return Divisao(
        jogos=jogos.loc[~trancada].copy(),
        trancados=int(trancada.sum()),
        ano_de_corte=ano,
        temporadas_trancadas=tuple(
            sorted(jogos.loc[trancada, "temporada"].unique())
        ),
    )


def usa_teste_final(jogos: pd.DataFrame, cfg: Config) -> bool:
    """Esta tabela contém jogo de temporada trancada?

    Serve de aviso, não de proibição: prever de verdade um jogo de amanhã
    **precisa** do histórico recente, e isso é legítimo. O que a regra 7 proíbe
    é usar essas temporadas para **comparar** modelos ou escolher parâmetros.
    """
    ano = ano_de_corte(cfg)
    return bool(jogos["temporada"].map(lambda t: e_teste_final(t, ano)).any())
