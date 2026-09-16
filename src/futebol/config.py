"""Carregamento da configuração central do projeto.

Todo parâmetro ajustável do projeto mora em ``config.yaml``, na raiz do
repositório. Este módulo lê esse arquivo e entrega os valores já validados,
para que nenhum outro módulo precise saber onde o arquivo fica.

Uso típico::

    from futebol.config import carregar_config

    cfg = carregar_config()
    print(cfg.seed)
    print(cfg.ligas_ativas())
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Raiz do projeto: sobe de src/futebol/config.py até a pasta que contém config.yaml.
RAIZ_PROJETO: Path = Path(__file__).resolve().parents[2]
CAMINHO_CONFIG_PADRAO: Path = RAIZ_PROJETO / "config.yaml"


class ErroDeConfiguracao(Exception):
    """Erro ao ler ou validar o ``config.yaml``."""


@dataclass(frozen=True)
class Config:
    """Configuração do projeto já carregada e validada.

    Atributos:
        bruto: o dicionário completo lido do YAML, para acesso a chaves
            que ainda não ganharam um atributo dedicado.
        seed: semente aleatória fixa, para resultados reproduzíveis.
        raiz: caminho da raiz do projeto.
    """

    bruto: dict[str, Any]
    seed: int
    raiz: Path

    # ------------------------------------------------------------------
    # Ligas
    # ------------------------------------------------------------------
    @property
    def camada_ativa(self) -> str:
        """Nome da camada de ligas atualmente ativa."""
        return str(self.bruto["ligas"]["ativa"])

    def ligas_ativas(self) -> dict[str, list[str]]:
        """Devolve as ligas da camada ativa, separadas por grupo.

        Retorna:
            Dicionário com as chaves ``grupo1`` e ``grupo2``.

            - ``grupo1``: ligas com odds pré-jogo **e** de fechamento.
              São as únicas que podem entrar no backtest de apostas e no CLV.
            - ``grupo2``: países com **apenas** odds de fechamento de 1X2.
              Servem para treino e calibração, nunca para backtest.

        Levanta:
            ErroDeConfiguracao: se a camada ativa não existir no arquivo.
        """
        camadas = self.bruto["ligas"]["camadas"]
        nome = self.camada_ativa
        if nome not in camadas:
            disponiveis = ", ".join(sorted(camadas))
            raise ErroDeConfiguracao(
                f"Camada de ligas {nome!r} não existe no config.yaml. "
                f"Camadas disponíveis: {disponiveis}."
            )
        camada = camadas[nome] or {}
        return {
            "grupo1": list(camada.get("grupo1") or []),
            "grupo2": list(camada.get("grupo2") or []),
        }

    def temporadas_grupo1(self) -> list[int]:
        """Temporadas do Grupo 1, no formato do site (2425 = 2024/25)."""
        return list(self.bruto["temporadas"]["grupo1"])

    # ------------------------------------------------------------------
    # Acesso genérico
    # ------------------------------------------------------------------
    def secao(self, nome: str) -> dict[str, Any]:
        """Devolve uma seção inteira do ``config.yaml``.

        Args:
            nome: nome da seção (ex.: ``"backtest"``, ``"modelos"``).

        Levanta:
            ErroDeConfiguracao: se a seção não existir.
        """
        if nome not in self.bruto:
            raise ErroDeConfiguracao(
                f"Seção {nome!r} não existe no config.yaml. "
                f"Seções presentes: {', '.join(sorted(self.bruto))}."
            )
        return dict(self.bruto[nome])


# Seções que precisam existir para o projeto funcionar.
_SECOES_OBRIGATORIAS: tuple[str, ...] = (
    "seed",
    "ligas",
    "temporadas",
    "fontes",
    "filtro_qualidade_mercado",
    "modelos",
    "backtest",
    "multiplas",
    "avaliacao",
)


def carregar_config(caminho: Path | str | None = None) -> Config:
    """Lê e valida o ``config.yaml``.

    Args:
        caminho: caminho do arquivo. Se omitido, usa o ``config.yaml``
            da raiz do projeto.

    Retorna:
        Um :class:`Config` pronto para uso.

    Levanta:
        ErroDeConfiguracao: se o arquivo não existir, não for um mapeamento
            YAML válido, ou faltar alguma seção obrigatória.
    """
    caminho = Path(caminho) if caminho is not None else CAMINHO_CONFIG_PADRAO

    if not caminho.is_file():
        raise ErroDeConfiguracao(
            f"Arquivo de configuração não encontrado: {caminho}. "
            "Ele deve ficar na raiz do projeto, ao lado do pyproject.toml."
        )

    with caminho.open(encoding="utf-8") as arquivo:
        bruto = yaml.safe_load(arquivo)

    if not isinstance(bruto, dict):
        raise ErroDeConfiguracao(
            f"O arquivo {caminho} não contém um mapeamento YAML válido."
        )

    faltando = [s for s in _SECOES_OBRIGATORIAS if s not in bruto]
    if faltando:
        raise ErroDeConfiguracao(
            f"Seções obrigatórias faltando no config.yaml: {', '.join(faltando)}."
        )

    return Config(bruto=bruto, seed=int(bruto["seed"]), raiz=caminho.parent)
