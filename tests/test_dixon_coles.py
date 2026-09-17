"""Testes do Dixon-Coles: a correção dos placares baixos e o decaimento.

Os dois remendos são testados separados, e isso é de propósito: com ``xi = 0``
o modelo é "Poisson + correção de placares", e com ``rho = 0`` ele é "Poisson
com memória". Testar um efeito de cada vez é o que permite dizer, na Fase 4,
qual dos dois trouxe a melhora.

O teste mais bonito do arquivo é
:func:`test_a_correcao_nao_muda_a_soma_da_matriz`: as quatro correções do
artigo de 1997 se cancelam exatamente, e é isso que garante que a matriz
corrigida continua sendo uma distribuição de probabilidade. Se a fórmula for
copiada com um sinal trocado, essa soma denuncia.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import check_grad

from futebol.modelos import base
from futebol.modelos import dixon_coles as DC
from futebol.modelos import poisson as P
from simulacao import ATAQUE, DEFESA, TIMES, rodizio, simular_liga, tabela_de_jogos


# ----------------------------------------------------------------------------
# 1. A correção de placares baixos
# ----------------------------------------------------------------------------
def test_tau_conferido_na_mao() -> None:
    """As quatro fórmulas do artigo, com λ = 2, μ = 1 e rho = −0,1."""
    lam, mu, rho = 2.0, 1.0, -0.1
    valor = lambda x, y: float(  # noqa: E731 - lambda curta é o mais legível aqui
        DC.tau(np.array([x]), np.array([y]), np.array([lam]), np.array([mu]), rho)[0]
    )

    assert valor(0, 0) == pytest.approx(1 - lam * mu * rho)  # 1,2
    assert valor(0, 1) == pytest.approx(1 + lam * rho)  # 0,8
    assert valor(1, 0) == pytest.approx(1 + mu * rho)  # 0,9
    assert valor(1, 1) == pytest.approx(1 - rho)  # 1,1


def test_tau_nao_mexe_em_placar_alto() -> None:
    """A correção é só dos placares baixos; o resto do Poisson fica intacto."""
    gols_mandante = np.array([0, 1, 2, 3, 0, 2])
    gols_visitante = np.array([2, 2, 1, 0, 3, 2])
    fator = DC.tau(
        gols_mandante, gols_visitante, np.full(6, 1.5), np.full(6, 1.2), -0.1
    )
    assert np.allclose(fator, 1.0), "só 0x0, 0x1, 1x0 e 1x1 podem mudar"


def test_a_correcao_nao_muda_a_soma_da_matriz() -> None:
    """As quatro correções se cancelam exatamente — é o achado do artigo.

    ``−λμρ·P(0,0) + λρ·P(0,1) + μρ·P(1,0) − ρ·P(1,1) = 0``, porque
    ``P(0,1) = μ·P(0,0)``, ``P(1,0) = λ·P(0,0)`` e ``P(1,1) = λμ·P(0,0)``.
    """
    matriz = P.matriz_poisson(1.7, 1.2, max_gols=10)
    for rho in (-0.12, -0.03, 0.0, 0.05):
        corrigida = DC.aplicar_na_matriz(matriz, 1.7, 1.2, rho)
        assert corrigida.sum() == pytest.approx(matriz.sum(), abs=1e-12)


def test_rho_negativo_engorda_o_empate() -> None:
    """O efeito conhecido: mais 0x0 e 1x1, menos 1x0 e 0x1.

    ⚠️ É por isso que a correção importa para apostar: 0x0 e 1x1 são empates,
    1x0 e 0x1 não. Ela mexe direto no mercado em que o Poisson puro erra mais.
    """
    lam, mu = 1.5, 1.2
    puro = P.matriz_poisson(lam, mu, max_gols=10)
    corrigido = base.normalizar_matriz(DC.aplicar_na_matriz(puro, lam, mu, -0.10))

    assert corrigido[0, 0] > puro[0, 0]
    assert corrigido[1, 1] > puro[1, 1]
    assert corrigido[1, 0] < puro[1, 0]
    assert corrigido[0, 1] < puro[0, 1]
    assert (
        base.mercados_da_matriz(corrigido)["D"] > base.mercados_da_matriz(puro)["D"]
    )


def test_rho_zero_nao_muda_nada() -> None:
    matriz = P.matriz_poisson(1.4, 1.1, max_gols=8)
    assert np.allclose(DC.aplicar_na_matriz(matriz, 1.4, 1.1, 0.0), matriz)


def test_gradiente_com_a_correcao_bate_com_o_numerico() -> None:
    """Agora com o ``rho`` no vetor de parâmetros."""
    jogos = simular_liga(TIMES, ATAQUE, DEFESA, voltas=4)
    times, indice_mandante, indice_visitante = P._indices_dos_times(jogos)
    gerador = np.random.default_rng(11)
    argumentos = (
        jogos["gols_mandante"].to_numpy(dtype=float),
        jogos["gols_visitante"].to_numpy(dtype=float),
        indice_mandante,
        indice_visitante,
        gerador.uniform(0.3, 1.0, len(jogos)),
        len(times),
        2.0,
        DC.CorrecaoPlacaresBaixos(),
    )
    ponto = np.append(gerador.normal(0.0, 0.3, 2 + 2 * len(times)), -0.05)

    erro = check_grad(
        lambda x: P._nll_e_gradiente(x, *argumentos)[0],
        lambda x: P._nll_e_gradiente(x, *argumentos)[1],
        ponto,
    )
    assert erro < 1e-4, f"gradiente analítico divergiu do numérico em {erro}"


# ----------------------------------------------------------------------------
# 2. O decaimento temporal
# ----------------------------------------------------------------------------
def test_peso_cai_pela_metade_na_meia_vida() -> None:
    xi = 0.0018
    dias = DC.meia_vida(xi)
    assert dias == pytest.approx(385.08, abs=0.1)

    referencia = pd.Timestamp("2024-07-01")
    datas = pd.Series([referencia, referencia - pd.Timedelta(days=round(dias))])
    pesos = DC.pesos_por_decaimento(datas, referencia, xi)
    assert pesos[0] == pytest.approx(1.0)
    assert pesos[1] == pytest.approx(0.5, abs=0.001)


def test_xi_zero_faz_todo_jogo_valer_igual() -> None:
    """Com ``xi = 0`` o Dixon-Coles é um Poisson com correção de placares."""
    datas = pd.Series(pd.date_range("2019-01-01", periods=100, freq="30D"))
    pesos = DC.pesos_por_decaimento(datas, datas.max(), 0.0)
    assert np.allclose(pesos, 1.0)
    assert DC.meia_vida(0.0) == float("inf")


def test_jogo_do_futuro_no_decaimento_e_erro() -> None:
    """Peso maior que 1 seria o sintoma de vazamento de futuro (regra 6)."""
    datas = pd.Series([pd.Timestamp("2025-01-01")])
    with pytest.raises(base.ErroDeModelo, match="vazamento"):
        DC.pesos_por_decaimento(datas, pd.Timestamp("2024-01-01"), 0.002)


def test_xi_negativo_e_recusado() -> None:
    with pytest.raises(base.ErroDeModelo, match="xi"):
        DC.DixonColes(max_gols=6, xi=-0.001)


def test_o_decaimento_conta_da_data_da_previsao() -> None:
    """E não do último jogo disputado — liga fora de temporada envelhece também."""
    jogos = simular_liga(TIMES, ATAQUE, DEFESA, voltas=2)
    corte = jogos["data"].max() + pd.Timedelta(days=200)
    modelo = DC.DixonColes(max_gols=8, xi=0.002).treinar(jogos, ate_data=corte)
    assert modelo.referencia_do_decaimento == corte


def test_memoria_curta_valoriza_o_que_e_recente() -> None:
    """Um time que era ruim e virou goleador: quem tem memória curta percebe.

    Este é o teste que mostra o decaimento fazendo o que promete. O mesmo
    histórico, dois modelos: o de memória longa faz a média dos dois períodos,
    o de memória curta acredita no período recente.
    """
    confrontos = rodizio(TIMES, voltas=4)
    metade = len(confrontos) // 2
    virou = TIMES[5]

    gols_mandante = []
    gols_visitante = []
    for posicao, (casa, fora) in enumerate(confrontos):
        recente = posicao >= metade
        if casa == virou:
            gols_mandante.append(4 if recente else 0)
            gols_visitante.append(0 if recente else 1)
        elif fora == virou:
            gols_mandante.append(0 if recente else 1)
            gols_visitante.append(4 if recente else 0)
        else:
            gols_mandante.append(1)
            gols_visitante.append(1)

    jogos = tabela_de_jogos(confrontos, gols_mandante, gols_visitante)

    memoria_longa = DC.DixonColes(max_gols=8, xi=0.0).treinar(jogos)
    memoria_curta = DC.DixonColes(max_gols=8, xi=0.02).treinar(jogos)

    ataque_longo = memoria_longa.ajuste_da_liga("E0").forcas[virou].ataque
    ataque_curto = memoria_curta.ajuste_da_liga("E0").forcas[virou].ataque
    assert ataque_curto > ataque_longo + 0.2


# ----------------------------------------------------------------------------
# 3. O rho é estimado a partir dos dados?
# ----------------------------------------------------------------------------
def _simular_com_correcao(
    rho: float, voltas: int = 40, seed: int = 5, liga: str = "E0"
) -> pd.DataFrame:
    """Sorteia placares da distribuição do Dixon-Coles, não da Poisson pura.

    Sem isso, o teste de recuperação do ``rho`` seria desonesto: ele pediria ao
    ajuste que encontrasse um efeito que não está nos dados.
    """
    gerador = np.random.default_rng(seed)
    confrontos = rodizio(TIMES, voltas)
    placares = []
    for casa, fora in confrontos:
        lam = float(np.exp(0.1 + ATAQUE[casa] - DEFESA[fora] + 0.25))
        mu = float(np.exp(0.1 + ATAQUE[fora] - DEFESA[casa]))
        matriz = base.normalizar_matriz(
            DC.aplicar_na_matriz(P.matriz_poisson(lam, mu, 10), lam, mu, rho)
        )
        sorteado = gerador.choice(matriz.size, p=matriz.ravel())
        placares.append(divmod(int(sorteado), matriz.shape[1]))

    return tabela_de_jogos(
        confrontos,
        [placar[0] for placar in placares],
        [placar[1] for placar in placares],
        liga=liga,
    )


def test_recupera_o_rho_que_gerou_os_placares() -> None:
    jogos = _simular_com_correcao(rho=-0.10)
    ajuste = P.ajustar_liga(jogos, "E0", correcao=DC.CorrecaoPlacaresBaixos())

    assert ajuste.convergiu, ajuste.mensagem
    assert ajuste.extras["rho"] == pytest.approx(-0.10, abs=0.04)


def test_sem_correcao_nos_dados_o_rho_fica_perto_de_zero() -> None:
    """Se o efeito não existe, o modelo não pode inventá-lo."""
    jogos = simular_liga(TIMES, ATAQUE, DEFESA, voltas=40)
    ajuste = P.ajustar_liga(jogos, "E0", correcao=DC.CorrecaoPlacaresBaixos())
    assert ajuste.extras["rho"] == pytest.approx(0.0, abs=0.04)


# ----------------------------------------------------------------------------
# 4. O modelo inteiro
# ----------------------------------------------------------------------------
def test_previsao_soma_um_e_nao_tem_negativo() -> None:
    modelo = DC.DixonColes(max_gols=10, xi=0.0018).treinar(
        simular_liga(TIMES, ATAQUE, DEFESA)
    )
    previsao = modelo.prever(base.Jogo("E0", TIMES[0], TIMES[5]))

    for grupo in base.GRUPOS_COMPLEMENTARES:
        assert sum(previsao[chave] for chave in grupo) == pytest.approx(1.0)
    assert all(valor >= 0 for valor in previsao.values())


def test_com_rho_negativo_o_empate_e_maior_que_no_poisson() -> None:
    """O efeito da correção chegando até a previsão de mercado."""
    jogos = _simular_com_correcao(rho=-0.12, voltas=20)
    poisson = P.Poisson(max_gols=10).treinar(jogos)
    dixon_coles = DC.DixonColes(max_gols=10, xi=0.0).treinar(jogos)

    assert dixon_coles.rho_da_liga("E0") < -0.05
    jogo = base.Jogo("E0", TIMES[2], TIMES[3])
    assert dixon_coles.prever(jogo)["D"] > poisson.prever(jogo)["D"]


def test_resumo_mostra_rho_e_meia_vida() -> None:
    modelo = DC.DixonColes(max_gols=8, xi=0.0018).treinar(
        pd.concat(
            [
                simular_liga(TIMES, ATAQUE, DEFESA, liga="E0", seed=1),
                simular_liga(TIMES, ATAQUE, DEFESA, liga="SP1", seed=2),
            ]
        )
    )
    resumo = modelo.resumo()
    assert sorted(resumo["liga"]) == ["E0", "SP1"]
    assert not resumo["rho_no_limite"].any()
    assert np.allclose(resumo["meia_vida_dias"], 385.08, atol=0.1)
    assert resumo["convergiu"].all()


def test_o_peso_de_um_time_cai_com_o_decaimento() -> None:
    """Com decaimento, "quantos jogos o time tem" passa a ser peso, não contagem.

    É isso que faz o encolhimento puxar de volta para a média da liga um time
    cujo histórico ficou velho.
    """
    jogos = simular_liga(TIMES, ATAQUE, DEFESA, voltas=4)
    modelo = DC.DixonColes(max_gols=8, xi=0.005).treinar(jogos)
    forca = modelo.ajuste_da_liga("E0").forcas[TIMES[0]]
    assert forca.peso < forca.jogos
