"""Testes das notas de previsão: log loss, Brier e calibração.

Estas funções decidem qual modelo o projeto escolhe (regra 9). Um erro aqui
não apareceria como erro — apareceria como um modelo ruim ganhando do bom.
Por isso os valores conferidos são os que dá para calcular na mão.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from futebol.avaliacao import metricas

#: Um 1X2 em que a previsão foi perfeita: 100% no que aconteceu.
PERFEITA = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
OBSERVADO_PERFEITO = np.array([0, 1])

#: "Não faço ideia": um terço para cada.
UNIFORME = np.full((3, 3), 1 / 3)


# ----------------------------------------------------------------------------
# Log loss
# ----------------------------------------------------------------------------
def test_previsao_perfeita_da_zero() -> None:
    assert metricas.log_loss(PERFEITA, OBSERVADO_PERFEITO) == pytest.approx(0.0)


def test_chute_uniforme_no_1x2_da_ln3() -> None:
    """1,0986 é a referência do projeto: a nota de quem não sabe nada."""
    assert metricas.log_loss(UNIFORME, np.array([0, 1, 2])) == pytest.approx(math.log(3))


def test_erro_confiante_e_punido_muito_mais_que_erro_humilde() -> None:
    """É esta assimetria que faz a log loss ser a métrica de escolha."""
    confiante = np.array([[0.98, 0.01, 0.01]])
    humilde = np.array([[0.40, 0.35, 0.25]])
    aconteceu_o_outro = np.array([2])

    nota_confiante = metricas.log_loss(confiante, aconteceu_o_outro)
    nota_humilde = metricas.log_loss(humilde, aconteceu_o_outro)
    assert nota_confiante > 3 * nota_humilde


def test_probabilidade_zero_nao_vira_infinito() -> None:
    """Um único jogo com 0% não pode apagar a avaliação inteira."""
    nota = metricas.log_loss(np.array([[0.0, 0.5, 0.5]]), np.array([0]))
    assert np.isfinite(nota) and nota > 30


# ----------------------------------------------------------------------------
# Brier
# ----------------------------------------------------------------------------
def test_brier_perfeito_e_zero() -> None:
    assert metricas.brier(PERFEITA, OBSERVADO_PERFEITO) == pytest.approx(0.0)


def test_brier_do_chute_uniforme() -> None:
    """(1-1/3)² + (1/3)² + (1/3)² = 0,6667."""
    assert metricas.brier(UNIFORME, np.array([0, 1, 2])) == pytest.approx(2 / 3)


def test_brier_e_menos_severo_que_log_loss_no_erro_confiante() -> None:
    confiante = np.array([[0.98, 0.01, 0.01]])
    erro = np.array([2])
    assert metricas.brier(confiante, erro) < 2.0
    assert metricas.log_loss(confiante, erro) > 4.0


# ----------------------------------------------------------------------------
# O que fica de fora da conta
# ----------------------------------------------------------------------------
def test_jogo_sem_odd_nao_conta_como_erro() -> None:
    """Buraco nos dados não é culpa do modelo: a linha sai da média."""
    probabilidades = np.array([[0.5, 0.3, 0.2], [np.nan, np.nan, np.nan]])
    nota = metricas.log_loss(probabilidades, np.array([0, 1]))
    assert nota == pytest.approx(-math.log(0.5))


def test_resultado_marcado_com_menos_um_fica_de_fora() -> None:
    probabilidades = np.array([[0.5, 0.3, 0.2], [0.5, 0.3, 0.2]])
    assert metricas.log_loss(probabilidades, np.array([0, -1])) == pytest.approx(
        -math.log(0.5)
    )


def test_tamanhos_diferentes_falham_com_mensagem_clara() -> None:
    with pytest.raises(ValueError, match="resultado"):
        metricas.log_loss(UNIFORME, np.array([0]))


def test_sem_nenhuma_linha_valida_a_nota_e_vazia() -> None:
    vazio = np.array([[np.nan, np.nan, np.nan]])
    assert math.isnan(metricas.log_loss(vazio, np.array([0])))
    assert math.isnan(metricas.brier(vazio, np.array([0])))


# ----------------------------------------------------------------------------
# Calibração
# ----------------------------------------------------------------------------
def _amostra_calibrada(p: float, n: int, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """n jogos em que a opção 0 tem probabilidade p — e acontece com essa taxa."""
    gerador = np.random.default_rng(seed)
    probabilidades = np.tile([p, 1 - p], (n, 1))
    observado = (gerador.random(n) >= p).astype(int)
    return probabilidades, observado


def test_mercado_bem_calibrado_tem_ece_perto_de_zero() -> None:
    probabilidades, observado = _amostra_calibrada(0.25, 20000)
    assert metricas.ece(probabilidades, observado) < 0.01


def test_ece_pega_quem_exagera_na_confianca() -> None:
    """Diz 80%, acontece 50%: é isso que o ECE tem que enxergar."""
    n = 5000
    probabilidades = np.tile([0.8, 0.2], (n, 1))
    observado = np.tile([0, 1], n // 2)  # metade e metade
    assert metricas.ece(probabilidades, observado) > 0.25


def test_tabela_de_calibracao_compara_dito_com_acontecido() -> None:
    probabilidades, observado = _amostra_calibrada(0.25, 10000)
    linhas = metricas.tabela_calibracao(probabilidades, observado)

    assert linhas, "a tabela não pode sair vazia"
    for linha in linhas:
        assert abs(linha["diferenca"]) < 0.02
        assert linha["n"] > 0


def test_cada_probabilidade_cai_numa_faixa_so() -> None:
    probabilidades, observado = _amostra_calibrada(0.25, 1000)
    linhas = metricas.tabela_calibracao(probabilidades, observado)
    # Cada jogo gera duas afirmações (0,25 e 0,75).
    assert sum(linha["n"] for linha in linhas) == 2000


# ----------------------------------------------------------------------------
# Piso de ruído
# ----------------------------------------------------------------------------
def test_piso_de_ruido_existe_mesmo_com_mercado_perfeito() -> None:
    """O ponto todo da função: ECE alto pode ser só amostra pequena."""
    probabilidades, _ = _amostra_calibrada(0.25, 300)
    assert metricas.piso_de_ruido_ece(probabilidades, repeticoes=40) > 0.005


def test_piso_de_ruido_cai_quando_a_amostra_cresce() -> None:
    pequena, _ = _amostra_calibrada(0.25, 300)
    grande, _ = _amostra_calibrada(0.25, 12000)

    piso_pequeno = metricas.piso_de_ruido_ece(pequena, repeticoes=40)
    piso_grande = metricas.piso_de_ruido_ece(grande, repeticoes=40)
    assert piso_grande < piso_pequeno / 2


def test_piso_de_ruido_e_reproduzivel() -> None:
    probabilidades, _ = _amostra_calibrada(0.3, 500)
    primeiro = metricas.piso_de_ruido_ece(probabilidades, repeticoes=20, seed=42)
    segundo = metricas.piso_de_ruido_ece(probabilidades, repeticoes=20, seed=42)
    assert primeiro == segundo


def test_simulacao_nunca_sorteia_opcao_inexistente() -> None:
    """Arredondamento no acumulado já produziu índice 3 num mercado de 3 opções."""
    quase_certo = np.tile([1.0, 0.0, 0.0], (500, 1))
    assert np.isfinite(metricas.piso_de_ruido_ece(quase_certo, repeticoes=10))


# ----------------------------------------------------------------------------
# Poder estatistico (Fase 6)
# ----------------------------------------------------------------------------
def test_desvio_padrao_da_aposta_bate_com_a_secao_8_1() -> None:
    """Odd 2,00 -> 1,0 (100% de volatilidade por aposta); odd 3,00 -> 1,41."""
    assert metricas.desvio_padrao_da_aposta(2.0) == pytest.approx(1.0)
    assert metricas.desvio_padrao_da_aposta(3.0) == pytest.approx(1.4142, abs=1e-4)


def test_desvio_padrao_da_aposta_e_a_conta_exata_de_uma_odd_justa() -> None:
    """Confere a formula simulando: p = 1/odd, retorno odd-1 ou -1."""
    odd = 4.0
    gerador = np.random.default_rng(0)
    ganhou = gerador.random(400_000) < 1 / odd
    retornos = np.where(ganhou, odd - 1.0, -1.0)
    assert retornos.std(ddof=1) == pytest.approx(
        metricas.desvio_padrao_da_aposta(odd), rel=0.01
    )


def test_tamanho_amostra_reproduz_a_tabela_da_especificacao() -> None:
    """ROI verdadeiro de 2% em odd media 2,00 pede ~9.600 apostas."""
    n = metricas.tamanho_amostra(0.02, metricas.desvio_padrao_da_aposta(2.0))
    assert n == pytest.approx(9604, rel=0.01)


def test_tamanho_amostra_na_odd_alta_pede_o_dobro() -> None:
    """A outra linha da tabela: 2% em odd 3,00 pede ~19.100."""
    n = metricas.tamanho_amostra(0.02, metricas.desvio_padrao_da_aposta(3.0))
    assert n == pytest.approx(19_208, rel=0.01)


def test_detectar_efeito_menor_custa_o_quadrado() -> None:
    """Metade do efeito, quatro vezes a amostra. E o que torna ROI inviavel."""
    grande = metricas.tamanho_amostra(0.04, 1.0)
    pequeno = metricas.tamanho_amostra(0.02, 1.0)
    assert pequeno == pytest.approx(4 * grande)


def test_efeito_zero_nunca_e_detectavel() -> None:
    assert metricas.tamanho_amostra(0.0, 1.0) == float("inf")


def test_efeito_detectavel_e_o_inverso_de_tamanho_amostra() -> None:
    """As duas funcoes sao a mesma conta resolvida para variaveis diferentes."""
    n = metricas.tamanho_amostra(0.03, 1.2)
    assert metricas.efeito_detectavel(int(round(n)), 1.2) == pytest.approx(0.03, rel=1e-3)


def test_o_poder_de_80_por_cento_exige_efeito_maior() -> None:
    """2,8 erros-padrao contra 1,96: perguntas diferentes, numeros diferentes."""
    apareceu = metricas.efeito_detectavel(1000, 1.0, metricas.Z_95)
    teria_visto = metricas.efeito_detectavel(1000, 1.0, metricas.Z_PODER_80)
    assert teria_visto > apareceu


def test_efeito_detectavel_sem_amostra_e_indefinido() -> None:
    assert math.isnan(metricas.efeito_detectavel(0, 1.0))


# ----------------------------------------------------------------------------
# Bootstrap
# ----------------------------------------------------------------------------
def test_bootstrap_cobre_a_media_verdadeira() -> None:
    gerador = np.random.default_rng(1)
    valores = gerador.normal(0.05, 1.0, 5000)
    baixo, alto = metricas.bootstrap_ic(valores, amostras=2000)
    assert baixo < valores.mean() < alto


def test_bootstrap_encolhe_com_a_amostra() -> None:
    gerador = np.random.default_rng(2)
    pequena = gerador.normal(0.0, 1.0, 200)
    grande = gerador.normal(0.0, 1.0, 20_000)

    estreito = np.diff(metricas.bootstrap_ic(grande, amostras=1000))[0]
    largo = np.diff(metricas.bootstrap_ic(pequena, amostras=1000))[0]
    assert estreito < largo / 5


def test_bootstrap_aguenta_a_distribuicao_torta_de_uma_aposta() -> None:
    """Pilha de -1 com alguns +9: nada parecido com uma normal, e tudo bem."""
    retornos = np.where(np.arange(2000) % 10 == 0, 9.0, -1.0)
    baixo, alto = metricas.bootstrap_ic(retornos, amostras=1000)
    assert baixo < 0.0 < alto


def test_bootstrap_e_reproduzivel() -> None:
    valores = np.random.default_rng(3).normal(0, 1, 500)
    assert metricas.bootstrap_ic(valores, amostras=500, seed=9) == (
        metricas.bootstrap_ic(valores, amostras=500, seed=9)
    )


def test_bootstrap_de_uma_observacao_so_nao_existe() -> None:
    baixo, alto = metricas.bootstrap_ic([0.5])
    assert math.isnan(baixo) and math.isnan(alto)


def test_bootstrap_ignora_valores_faltando() -> None:
    """Aposta sem odd de fechamento nao tem CLV, e nao pode virar zero."""
    com_buraco = np.array([0.1, np.nan, 0.1, 0.1, np.nan, 0.1])
    baixo, alto = metricas.bootstrap_ic(com_buraco, amostras=200)
    assert baixo == pytest.approx(0.1) and alto == pytest.approx(0.1)


def test_bootstrap_de_amostra_grande_nao_estoura_a_memoria() -> None:
    """Cem mil apostas x dez mil repeticoes seriam um bilhao de numeros."""
    valores = np.random.default_rng(4).normal(0, 1, 100_000)
    baixo, alto = metricas.bootstrap_ic(valores, amostras=2000)
    assert baixo < 0.0 < alto
