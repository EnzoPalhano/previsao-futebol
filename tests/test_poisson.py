"""Testes do Poisson: a conta do ajuste, o encolhimento e o fator casa.

Modelo é código que sempre devolve *algum* número, e número plausível é a
armadilha: um sinal trocado no gradiente ou um encolhimento que não encolhe
produzem previsões que parecem certas e são erradas. Por isso aqui há três
tipos de teste, em ordem de força:

1. **gradiente contra derivada numérica** — se o gradiente analítico estiver
   errado, o otimizador anda para o lado errado e nada mais importa;
2. **recuperação de parâmetros conhecidos** — placares sorteados de forças que
   o teste escolheu, e o ajuste tem que reencontrá-las;
3. **comportamento** — encolhimento, fator casa, time desconhecido.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import check_grad

from futebol.modelos import base
from futebol.modelos import poisson as P


def _rodizio(times: list[str], voltas: int = 1) -> list[tuple[str, str]]:
    """Todos contra todos, em casa e fora, repetido ``voltas`` vezes."""
    return [
        (casa, fora)
        for _ in range(voltas)
        for casa in times
        for fora in times
        if casa != fora
    ]


def _simular(
    times: list[str],
    ataque: dict[str, float],
    defesa: dict[str, float],
    intercepto: float = 0.1,
    fator_casa: float = 0.25,
    voltas: int = 6,
    liga: str = "E0",
    seed: int = 42,
) -> pd.DataFrame:
    """Sorteia placares a partir de forças conhecidas.

    É o teste mais honesto que existe para um modelo de estimação: se os dados
    vieram destes parâmetros, o ajuste tem que devolver estes parâmetros.
    """
    gerador = np.random.default_rng(seed)
    confrontos = _rodizio(times, voltas)
    lam = np.array(
        [
            np.exp(intercepto + ataque[casa] - defesa[fora] + fator_casa)
            for casa, fora in confrontos
        ]
    )
    mu = np.array(
        [np.exp(intercepto + ataque[fora] - defesa[casa]) for casa, fora in confrontos]
    )
    return pd.DataFrame(
        {
            "data": pd.date_range("2019-08-01", periods=len(confrontos), freq="D"),
            "liga": [liga] * len(confrontos),
            "mandante": [c for c, _ in confrontos],
            "visitante": [f for _, f in confrontos],
            "gols_mandante": gerador.poisson(lam),
            "gols_visitante": gerador.poisson(mu),
        }
    )


#: Uma liga de seis times com forças conhecidas, do melhor para o pior.
TIMES = [f"ENG:T{i}" for i in range(6)]
ATAQUE = dict(zip(TIMES, [0.5, 0.3, 0.1, -0.1, -0.3, -0.5], strict=True))
DEFESA = dict(zip(TIMES, [0.4, 0.2, 0.0, 0.0, -0.2, -0.4], strict=True))


# ----------------------------------------------------------------------------
# 1. O gradiente está certo?
# ----------------------------------------------------------------------------
def test_gradiente_analitico_bate_com_o_numerico() -> None:
    """A derivada escrita à mão contra a derivada calculada por diferença.

    Este é o teste que protege o módulo inteiro. Um gradiente errado não
    quebra nada: só faz o otimizador parar no lugar errado, com um modelo
    plausível e pior do que deveria ser.
    """
    jogos = _simular(TIMES, ATAQUE, DEFESA, voltas=3)
    times, indice_mandante, indice_visitante = P._indices_dos_times(jogos)
    gerador = np.random.default_rng(7)
    pesos = gerador.uniform(0.3, 1.0, len(jogos))
    argumentos = (
        jogos["gols_mandante"].to_numpy(dtype=float),
        jogos["gols_visitante"].to_numpy(dtype=float),
        indice_mandante,
        indice_visitante,
        pesos,
        len(times),
        2.0,
        None,
    )
    ponto = gerador.normal(0.0, 0.3, 2 + 2 * len(times))

    erro = check_grad(
        lambda x: P._nll_e_gradiente(x, *argumentos)[0],
        lambda x: P._nll_e_gradiente(x, *argumentos)[1],
        ponto,
    )
    assert erro < 1e-4, f"gradiente analítico divergiu do numérico em {erro}"


# ----------------------------------------------------------------------------
# 2. O ajuste reencontra as forças que geraram os dados?
# ----------------------------------------------------------------------------
def test_recupera_as_forcas_que_geraram_os_placares() -> None:
    jogos = _simular(TIMES, ATAQUE, DEFESA, voltas=12)
    ajuste = P.ajustar_liga(jogos, "E0", jogos_equivalentes=6)

    assert ajuste.convergiu, ajuste.mensagem
    for time in TIMES:
        assert ajuste.forcas[time].ataque == pytest.approx(ATAQUE[time], abs=0.12)
        assert ajuste.forcas[time].defesa == pytest.approx(DEFESA[time], abs=0.12)
    assert ajuste.fator_casa == pytest.approx(0.25, abs=0.08)
    assert ajuste.intercepto == pytest.approx(0.1, abs=0.08)


def test_a_ordem_das_forcas_e_a_certa() -> None:
    """Mesmo com amostra menor, a ordem entre os times tem que sair certa."""
    jogos = _simular(TIMES, ATAQUE, DEFESA, voltas=6)
    tabela = P.ajustar_liga(jogos, "E0").tabela_de_forcas()
    assert list(tabela["time"]) == TIMES


def test_as_forcas_tem_media_zero() -> None:
    """É o que dá sentido a "ataque acima da média da liga".

    A penalização do encolhimento não só encolhe: ela ancora a média das forças
    em zero, deixando o nível de gols todo no intercepto. Sem isso, o modelo
    seria indeterminado — somar 1 a todos os ataques e 1 ao intercepto daria
    exatamente as mesmas previsões.
    """
    ajuste = P.ajustar_liga(_simular(TIMES, ATAQUE, DEFESA), "E0")
    ataques = [forca.ataque for forca in ajuste.forcas.values()]
    defesas = [forca.defesa for forca in ajuste.forcas.values()]
    assert np.mean(ataques) == pytest.approx(0.0, abs=1e-3)
    assert np.mean(defesas) == pytest.approx(0.0, abs=1e-3)


# ----------------------------------------------------------------------------
# 3. Encolhimento
# ----------------------------------------------------------------------------
def test_time_com_poucos_jogos_fica_perto_da_media() -> None:
    """O caso do time recém-promovido (Fase 3 da especificação).

    Dois times fazem 5x0 em todos os seus jogos. Um deles jogou duas vezes, o
    outro jogou cinquenta. O modelo tem que acreditar muito mais no segundo.
    """
    jogos = _simular(TIMES, ATAQUE, DEFESA, voltas=6)
    estreante = pd.DataFrame(
        {
            "data": pd.to_datetime(["2020-05-01", "2020-05-08"]),
            "liga": ["E0"] * 2,
            "mandante": ["ENG:Novo"] * 2,
            "visitante": TIMES[:2],
            "gols_mandante": [5, 5],
            "gols_visitante": [0, 0],
        }
    )
    veterano = pd.DataFrame(
        {
            "data": pd.date_range("2020-06-01", periods=50, freq="3D"),
            "liga": ["E0"] * 50,
            "mandante": ["ENG:Velho"] * 50,
            "visitante": [TIMES[i % 6] for i in range(50)],
            "gols_mandante": [5] * 50,
            "gols_visitante": [0] * 50,
        }
    )
    ajuste = P.ajustar_liga(
        pd.concat([jogos, estreante, veterano], ignore_index=True),
        "E0",
        jogos_equivalentes=6,
    )

    ataque_estreante = ajuste.forcas["ENG:Novo"].ataque
    ataque_veterano = ajuste.forcas["ENG:Velho"].ataque
    assert 0 < ataque_estreante < ataque_veterano, (
        "os dois golearam sempre; quem tem mais jogos tem que ficar mais longe da média"
    )


def test_encolhimento_maior_puxa_mais_para_a_media() -> None:
    jogos = _simular(TIMES, ATAQUE, DEFESA, voltas=2)
    frouxo = P.ajustar_liga(jogos, "E0", jogos_equivalentes=1)
    apertado = P.ajustar_liga(jogos, "E0", jogos_equivalentes=200)

    melhor = TIMES[0]
    assert abs(apertado.forcas[melhor].ataque) < abs(frouxo.forcas[melhor].ataque)


def test_time_desconhecido_e_um_time_medio_da_liga() -> None:
    """Prever um time que não estava no treino não pode quebrar o app."""
    ajuste = P.ajustar_liga(_simular(TIMES, ATAQUE, DEFESA), "E0")
    forca = ajuste.forca("ENG:NuncaVisto")
    assert (forca.ataque, forca.defesa, forca.jogos) == (0.0, 0.0, 0)


# ----------------------------------------------------------------------------
# 4. Fator casa
# ----------------------------------------------------------------------------
def test_fator_casa_global_e_a_razao_dos_gols() -> None:
    jogos = pd.DataFrame(
        {
            "data": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "liga": ["E0", "E0"],
            "mandante": ["ENG:A", "ENG:B"],
            "visitante": ["ENG:B", "ENG:A"],
            "gols_mandante": [2, 2],
            "gols_visitante": [1, 1],
        }
    )
    assert P.fator_casa_global(jogos) == pytest.approx(np.log(2.0))


def test_fator_casa_fixo_nao_e_estimado() -> None:
    """A versão "fator casa constante" do experimento da Fase 3."""
    jogos = _simular(TIMES, ATAQUE, DEFESA, fator_casa=0.40)
    ajuste = P.ajustar_liga(jogos, "E0", fator_casa_fixo=0.10)
    assert ajuste.fator_casa == pytest.approx(0.10)


def test_cada_liga_estima_o_seu_fator_casa() -> None:
    """Uma liga com casa fortíssima e outra sem vantagem nenhuma.

    As voltas são muitas de propósito: com 180 jogos o erro-padrão do fator
    casa fica perto de 0,07, e um teste apertado em cima disso falharia por
    sorte do sorteio. Estimar fator casa exige amostra — o que é, por si, uma
    informação útil sobre o experimento da Fase 3.
    """
    com_vantagem = _simular(
        TIMES, ATAQUE, DEFESA, fator_casa=0.50, voltas=20, liga="BRA", seed=1
    )
    sem_vantagem = _simular(
        TIMES, ATAQUE, DEFESA, fator_casa=0.00, voltas=20, liga="JPN", seed=2
    )
    modelo = P.Poisson(max_gols=8).treinar(pd.concat([com_vantagem, sem_vantagem]))

    assert modelo.ajuste_da_liga("BRA").fator_casa == pytest.approx(0.50, abs=0.08)
    assert modelo.ajuste_da_liga("JPN").fator_casa == pytest.approx(0.00, abs=0.08)
    assert (
        modelo.ajuste_da_liga("BRA").fator_casa
        > modelo.ajuste_da_liga("JPN").fator_casa + 0.3
    )


def test_modo_global_congela_o_mesmo_fator_nas_duas_ligas() -> None:
    com_vantagem = _simular(TIMES, ATAQUE, DEFESA, fator_casa=0.50, liga="BRA", seed=1)
    sem_vantagem = _simular(TIMES, ATAQUE, DEFESA, fator_casa=0.00, liga="JPN", seed=2)
    jogos = pd.concat([com_vantagem, sem_vantagem])
    modelo = P.Poisson(max_gols=8, fator_casa="global").treinar(jogos)

    medido = P.fator_casa_global(jogos)
    assert modelo.fator_casa_medido == pytest.approx(medido)
    assert modelo.ajuste_da_liga("BRA").fator_casa == pytest.approx(medido)
    assert modelo.ajuste_da_liga("JPN").fator_casa == pytest.approx(medido)


def test_modo_de_fator_casa_invalido_e_recusado() -> None:
    with pytest.raises(base.ErroDeModelo, match="fator_casa"):
        P.Poisson(fator_casa="chute")


# ----------------------------------------------------------------------------
# 5. A matriz de placares e a previsão
# ----------------------------------------------------------------------------
def test_matriz_e_o_produto_de_duas_poisson() -> None:
    """Independência entre os lados: a matriz é o produto das duas marginais."""
    matriz = P.matriz_poisson(1.5, 1.1, max_gols=10)
    assert matriz.sum() == pytest.approx(1.0)
    # P(0x0) = exp(-1,5) · exp(-1,1), a menos da normalização da cauda cortada.
    assert matriz[0, 0] == pytest.approx(np.exp(-1.5) * np.exp(-1.1), rel=1e-4)
    # As marginais voltam a ser as duas Poisson originais.
    assert matriz.sum(axis=1)[2] == pytest.approx(
        np.exp(-1.5) * 1.5**2 / 2, rel=1e-4
    )


def test_matriz_maior_soma_mais_perto_de_um_antes_de_normalizar() -> None:
    """A cauda cortada encolhe quando a matriz cresce; 10 gols já é folga."""
    from scipy.stats import poisson as sp

    perdido_com_10 = 1 - sp.cdf(10, 1.5) * sp.cdf(10, 1.1)
    assert perdido_com_10 < 1e-6


def test_media_de_gols_invalida_e_recusada() -> None:
    with pytest.raises(base.ErroDeModelo, match="inválidas"):
        P.matriz_poisson(0.0, 1.2)


def test_previsao_soma_um_e_nao_tem_negativo() -> None:
    modelo = P.Poisson(max_gols=10).treinar(_simular(TIMES, ATAQUE, DEFESA))
    previsao = modelo.prever(base.Jogo("E0", TIMES[0], TIMES[5]))

    for grupo in base.GRUPOS_COMPLEMENTARES:
        assert sum(previsao[chave] for chave in grupo) == pytest.approx(1.0)
    assert all(valor >= 0 for valor in previsao.values())


def test_o_time_mais_forte_em_casa_e_favorito() -> None:
    modelo = P.Poisson(max_gols=10).treinar(_simular(TIMES, ATAQUE, DEFESA))
    forte_em_casa = modelo.prever(base.Jogo("E0", TIMES[0], TIMES[5]))
    fraco_em_casa = modelo.prever(base.Jogo("E0", TIMES[5], TIMES[0]))

    assert forte_em_casa["H"] > 0.6
    # O mesmo confronto, com os papéis trocados: a chance de o time fraco
    # ganhar sobe quando ele joga em casa. É o fator casa aparecendo.
    assert fraco_em_casa["H"] > forte_em_casa["A"]


def test_ao_contrario_do_baseline_a_previsao_depende_dos_times() -> None:
    modelo = P.Poisson(max_gols=10).treinar(_simular(TIMES, ATAQUE, DEFESA))
    um = modelo.prever(base.Jogo("E0", TIMES[0], TIMES[5]))
    outro = modelo.prever(base.Jogo("E0", TIMES[2], TIMES[3]))
    assert um["H"] > outro["H"] + 0.1


# ----------------------------------------------------------------------------
# 6. Erros e bordas
# ----------------------------------------------------------------------------
def test_liga_fora_do_treino_diz_quais_existem() -> None:
    modelo = P.Poisson(max_gols=8).treinar(_simular(TIMES, ATAQUE, DEFESA))
    with pytest.raises(base.ErroDeModelo, match="E0"):
        modelo.prever(base.Jogo("SP1", "ESP:Barcelona", "ESP:Real Madrid"))


def test_cada_liga_e_ajustada_com_os_jogos_dela_so() -> None:
    """Forças de ligas diferentes não são comparáveis; misturá-las corromperia."""
    inglaterra = _simular(TIMES, ATAQUE, DEFESA, liga="E0", seed=1)
    espanha = _simular(
        [f"ESP:T{i}" for i in range(6)],
        dict(zip([f"ESP:T{i}" for i in range(6)], [0.0] * 6, strict=True)),
        dict(zip([f"ESP:T{i}" for i in range(6)], [0.0] * 6, strict=True)),
        liga="SP1",
        seed=2,
    )
    modelo = P.Poisson(max_gols=8).treinar(pd.concat([inglaterra, espanha]))

    assert set(modelo.ajuste_da_liga("E0").forcas) == set(TIMES)
    assert modelo.ajuste_da_liga("E0").jogos == len(inglaterra)


def test_numero_errado_de_pesos_e_recusado() -> None:
    jogos = _simular(TIMES, ATAQUE, DEFESA, voltas=1)
    with pytest.raises(base.ErroDeModelo, match="peso"):
        P.ajustar_liga(jogos, "E0", pesos=np.ones(3))


def test_peso_zero_apaga_o_jogo() -> None:
    """A base do decaimento temporal: peso é o quanto o jogo ainda conta."""
    jogos = _simular(TIMES, ATAQUE, DEFESA, voltas=4)
    absurdo = pd.DataFrame(
        {
            "data": [jogos["data"].max() + pd.Timedelta(days=1)],
            "liga": ["E0"],
            "mandante": [TIMES[5]],
            "visitante": [TIMES[0]],
            "gols_mandante": [15],
            "gols_visitante": [0],
        }
    )
    completo = pd.concat([jogos, absurdo], ignore_index=True)
    pesos = np.append(np.ones(len(jogos)), 0.0)

    com_peso_zero = P.ajustar_liga(completo, "E0", pesos=pesos)
    sem_o_jogo = P.ajustar_liga(jogos, "E0")
    assert com_peso_zero.forcas[TIMES[5]].ataque == pytest.approx(
        sem_o_jogo.forcas[TIMES[5]].ataque, abs=1e-4
    )


def test_resumo_tem_uma_linha_por_liga() -> None:
    modelo = P.Poisson(max_gols=8).treinar(
        pd.concat(
            [
                _simular(TIMES, ATAQUE, DEFESA, liga="E0", seed=1),
                _simular(TIMES, ATAQUE, DEFESA, liga="SP1", seed=2),
            ]
        )
    )
    resumo = modelo.resumo()
    assert sorted(resumo["liga"]) == ["E0", "SP1"]
    assert resumo["convergiu"].all()
    assert (resumo["vantagem_casa"] > 1).all()
