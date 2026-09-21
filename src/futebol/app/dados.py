"""O que o app carrega, e o cache que o torna usável.

Sem cache, este app seria inútil: a tabela tem 116 mil jogos, e o Streamlit
**reexecuta o script inteiro** a cada clique. Ler o Parquet de novo a cada
caixinha marcada faria cada interação levar segundos.

A divisão do módulo é proposital:

- as funções que **calculam** são puras e não sabem que Streamlit existe. São
  elas que os testes chamam;
- as funções que **guardam** são casquinhas finas com ``@st.cache_data`` em
  cima.

Isso não é organização por gosto. Lógica dentro de função cacheada é lógica que
só roda com um servidor Streamlit no ar — ou seja, lógica sem teste. E a Fase 8
é justamente a fase em que um número errado deixa de aparecer num relatório que
alguém revisa e passa a aparecer numa tela que alguém usa.

⚠️ **Duas travas do projeto continuam valendo aqui**, e é fácil esquecê-las numa
interface:

- **regra 7** — o app nunca mostra as temporadas de teste final. Tudo o que ele
  carrega passa por :func:`futebol.avaliacao.divisao.separar`;
- **regra 6** — prever um jogo de uma data D treina o modelo só com o que era
  conhecido antes de D. É o mesmo caminho do ``scripts/prever.py``, e não um
  atalho escrito para a tela.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from futebol.avaliacao import divisao, selecao
from futebol.config import Config, carregar_config
from futebol.dados import limpeza
from futebol.modelos import base
from futebol.modelos.baseline import Baseline
from futebol.modelos.dixon_coles import DixonColes
from futebol.modelos.poisson import Poisson

#: Quanto tempo o cache de dados vale. Uma hora chega: a tabela só muda quando
#: alguém roda ``scripts/preparar_dados.py``.
VALIDADE = 3600

#: Os modelos que a página de previsão oferece. O Elo fica de fora porque ele
#: não é um modelo: é uma feature (decisão da Fase 5). O LightGBM também, porque
#: ele precisa das features da tabela inteira e não entrou no projeto.
MODELOS: dict[str, type[base.Modelo]] = {
    "Dixon-Coles (o oficial)": DixonColes,
    "Poisson": Poisson,
    "Baseline (só o histórico da liga)": Baseline,
}


class ErroDeDados(Exception):
    """Falta um arquivo que o app precisa, e a tela explica o que fazer."""


# ----------------------------------------------------------------------------
# A tabela de jogos
# ----------------------------------------------------------------------------
def caminho_da_tabela(cfg: Config) -> Path:
    return cfg.raiz / "data" / "processed" / "jogos.parquet"


def pasta_do_deploy(cfg: Config) -> Path:
    """Os dados versionados que o app usa quando publicado.

    ⚠️ Existe porque `data/processed/` não vai para o Git (regra 4) e um deploy
    ingênuo sobe o código, não acha os dados e quebra na primeira tela. A Fase 8
    decidiu versionar dados reduzidos (4,05 MB medidos, os dois arquivos abaixo
    do limite de 5 MB) e a Fase 9 executou; `scripts/preparar_deploy.py` os
    gera.

    Localmente esta pasta é ignorada: `data/processed/` vem primeiro, porque é o
    dado fresco. Ela só entra em cena onde o outro não existe.
    """
    return cfg.raiz / "data" / "app"


@st.cache_resource(ttl=VALIDADE)
def config() -> Config:
    return carregar_config()


@st.cache_data(ttl=VALIDADE)
def carregar() -> pd.DataFrame:
    """A tabela de jogos, **sem** as temporadas de teste final (regra 7).

    Levanta:
        ErroDeDados: se o Parquet não existir. A mensagem diz o comando que o
            gera — um app que só falha com ``FileNotFoundError`` deixa quem
            abriu sem saber o que fazer.
    """
    cfg = config()
    caminho = caminho_da_tabela(cfg)
    if caminho.is_file():
        return divisao.separar(limpeza.carregar(cfg), cfg).jogos

    # Sem `data/processed/`, o app está publicado: usa os dados versionados por
    # `scripts/preparar_deploy.py`. Eles **já vêm** sem as temporadas do cofre,
    # e isso é de propósito — num servidor, a forma mais segura de a regra 7
    # valer é o dado trancado nem estar lá.
    do_deploy = pasta_do_deploy(cfg) / "jogos.parquet"
    if do_deploy.is_file():
        return pd.read_parquet(do_deploy)

    raise ErroDeDados(
        f"A tabela de jogos não existe em {caminho} nem em {do_deploy}. "
        "Rode, no terminal:\n\n"
        "    python scripts/baixar_dados.py\n"
        "    python scripts/preparar_dados.py"
    )


@st.cache_data(ttl=VALIDADE)
def ligas() -> list[str]:
    """As competições disponíveis, em ordem."""
    return sorted(carregar()["liga"].unique())


@st.cache_data(ttl=VALIDADE)
def ligas_aprovadas() -> list[str]:
    """As 18 que passaram no filtro da Fase 2 — as únicas apostáveis (regra 12)."""
    return sorted(config().bruto["ligas_aprovadas_backtest"])


def times_da_liga(jogos: pd.DataFrame, liga: str) -> list[str]:
    """Os clubes de uma competição, do mais recente para o mais antigo.

    A ordem é por último jogo, e não alfabética, de propósito: numa liga com
    trinta anos de histórico, os times que ainda jogam nela ficam no topo, e é
    isso que quem abre a tela quer encontrar.
    """
    da_liga = jogos.loc[jogos["liga"] == liga]
    ultimo = pd.concat(
        [
            da_liga[["mandante", "data"]].rename(columns={"mandante": "time"}),
            da_liga[["visitante", "data"]].rename(columns={"visitante": "time"}),
        ]
    )
    return list(
        ultimo.groupby("time")["data"].max().sort_values(ascending=False).index
    )


# ----------------------------------------------------------------------------
# Previsão de um jogo
# ----------------------------------------------------------------------------
def prever(
    jogos: pd.DataFrame,
    liga: str,
    mandante: str,
    visitante: str,
    data: pd.Timestamp,
    cfg: Config,
) -> pd.DataFrame:
    """As probabilidades de cada modelo para um confronto.

    ⚠️ Cada modelo é treinado **só com os jogos anteriores a ``data``**
    (regra 6). É por isso que mudar a data muda a previsão: o modelo vê o
    passado daquele dia, e nada além.

    Retorna:
        Uma linha por modelo, com as colunas de
        :data:`futebol.modelos.base.CHAVES_PREVISAO`.
    """
    jogo = base.Jogo(liga=liga, mandante=mandante, visitante=visitante, data=data)
    linhas = []
    for nome, classe in MODELOS.items():
        modelo = classe(cfg=cfg).treinar(jogos, ate_data=data)
        linhas.append({"modelo": nome, **modelo.prever(jogo)})
    return pd.DataFrame(linhas)


def matriz_de_placares(
    jogos: pd.DataFrame, liga: str, mandante: str, visitante: str, data, cfg: Config
):
    """A matriz de placares do modelo oficial, para a tabela de placares prováveis."""
    modelo = DixonColes(cfg=cfg).treinar(jogos, ate_data=data)
    return modelo.matriz_de_placares(
        base.Jogo(liga=liga, mandante=mandante, visitante=visitante, data=data)
    )


def placares_mais_provaveis(matriz, quantos: int = 8) -> pd.DataFrame:
    """Os placares exatos mais prováveis, do mais para o menos."""
    linhas = [
        {"placar": f"{gols_casa} × {gols_fora}", "probabilidade": float(valor)}
        for gols_casa, linha in enumerate(matriz)
        for gols_fora, valor in enumerate(linha)
    ]
    tabela = pd.DataFrame(linhas).sort_values("probabilidade", ascending=False)
    return tabela.head(quantos).reset_index(drop=True)


# ----------------------------------------------------------------------------
# O cache do walk-forward, que a página de backtest usa
# ----------------------------------------------------------------------------
def modelos_medidos(cfg: Config) -> dict[str, Path]:
    """Os candidatos que já têm walk-forward gravado em disco.

    ⚠️ A página de backtest só oferece estes. Rodar um walk-forward novo levaria
    minutos, e um app que trava por minutos num clique não é um app — é um
    script com botões. Quem quiser medir uma configuração nova roda
    ``scripts/validar.py``, que é onde isso pertence.

    ⚠️⚠️ **Só entram os caches da janela de VALIDAÇÃO, e isto é a regra 7.** O
    nome do arquivo é ``<janela>__<candidato>__<assinatura>``, e a Fase 9 grava
    um cache do **mesmo candidato** numa janela diferente — a trancada. Chaveando
    só pelo nome do candidato, os dois arquivos colidiam e o do teste final
    vencia: o app passava a ler as temporadas que ele nunca pode mostrar.

    O que denunciou foi um ``KeyError`` (os índices do cofre não existem na
    tabela do app, que exclui as temporadas trancadas), e isso foi **sorte** —
    tivessem os índices batido, a tela mostraria dados do teste final em
    silêncio. É a armadilha de sempre do projeto numa forma nova: chave que
    ignora parte do que identifica o arquivo.
    """
    pasta = selecao.pasta_do_cache(cfg)
    if not pasta.is_dir():
        return {}
    da_validacao = f"{pd.Timestamp(selecao.INICIO_VALIDACAO).date()}_"
    encontrados = {}
    for caminho in sorted(pasta.glob("*.parquet")):
        # O nome é "<janela>__<candidato>__<assinatura>.parquet".
        partes = caminho.stem.split("__")
        if len(partes) == 3 and partes[0].startswith(da_validacao):
            encontrados[partes[1]] = caminho

    if not encontrados:
        # App publicado: só o modelo oficial viaja, como `previsoes_<nome>`.
        # As telas que comparam candidatos ficam com um modelo só — melhor que
        # carregar 40 MB de cache para um servidor por causa de uma tabela.
        for caminho in sorted(pasta_do_deploy(cfg).glob("previsoes_*.parquet")):
            encontrados[caminho.stem.removeprefix("previsoes_")] = caminho
    return encontrados


@st.cache_data(ttl=VALIDADE)
def previsoes(nome: str) -> pd.DataFrame:
    """As previsões do walk-forward de um candidato já medido."""
    caminhos = modelos_medidos(config())
    if nome not in caminhos:
        raise ErroDeDados(
            f"O modelo {nome!r} não tem walk-forward gravado. Rode "
            "`python scripts/validar.py` para medi-lo."
        )
    return pd.read_parquet(caminhos[nome])


@st.cache_data(ttl=VALIDADE)
def nome_do_modelo_oficial() -> str:
    """Qual candidato corresponde ao que está no ``config.yaml``."""
    cfg = config()
    return selecao.candidato_oficial(cfg, carregar()).nome


@st.cache_data(ttl=VALIDADE)
def candidatos_de_aposta(nome: str) -> pd.DataFrame:
    """Todas as apostas possíveis de um modelo medido, com odd, EV e resultado.

    É a base das páginas de backtest, múltiplas e cash out. Cacheada porque
    montá-la percorre cem mil linhas e nenhuma tela precisa refazer isso a cada
    clique.
    """
    from futebol.backtest import simulador

    return simulador.preparar(carregar(), previsoes(nome), config()).candidatos


@st.cache_data(ttl=VALIDADE)
def rodadas_disponiveis(nome: str) -> list[pd.Timestamp]:
    """As datas em que houve jogo apostável, da mais recente para a mais antiga.

    ⚠️ O app não tem jogos futuros: a fonte é um histórico. Então "a rodada" das
    páginas de múltipla é uma **data do passado**, escolhida por quem usa. É uma
    limitação real e a tela diz isso — inventar uma rodada futura seria inventar
    os dados dela.
    """
    return sorted(candidatos_de_aposta(nome)["data"].unique(), reverse=True)
