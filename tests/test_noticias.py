"""Testes da Fase 10 — o núcleo, sem tocar a internet.

⚠️ **Nenhum teste aqui chama API, LLM ou RSS.** A especificação exige isso
("testes com respostas de API e notícias **falsas**"), e o motivo é duplo: teste
que depende de rede falha por motivo errado, e teste que gasta chamada de API
custa dinheiro a cada execução.

O teste mais importante do arquivo é
:func:`test_perder_zagueiro_faz_o_time_sofrer_mais_gols`. Ele guarda um erro de
**sinal** que não daria erro nenhum: no modelo a defesa entra invertida
(positivo é defesa boa), então somar em vez de subtrair faria o time **melhorar**
ao perder jogador. A previsão sairia bem formatada e ao contrário.
"""

from __future__ import annotations

from datetime import date

import pytest

from futebol.config import carregar_config
from futebol.noticias import ajuste as ajuste_mod
from futebol.noticias import importancia
from futebol.noticias.tipos import Desfalque, Jogador


@pytest.fixture(scope="module")
def cfg():
    return carregar_config()


def _desfalque(
    nome: str,
    *,
    time: str = "ENG:Arsenal",
    setor: str = "ataque",
    peso: float = 0.2,
    status: str = "fora",
    confianca: float = 1.0,
    dia: int = 1,
) -> Desfalque:
    """Um desfalque de mentira, para os testes.

    ⚠️ O peso padrão é **0,2 e não 0,5** de propósito: 0,5 estoura o teto de
    0,25 do ``config.yaml``, e aí todo teste de proporção compararia dois
    valores grudados no limite — "dúvida pesa metade" daria 0,25 contra 0,25 e
    passaria a impressão de um defeito que não existe. Quem quiser testar o teto
    pede peso grande explicitamente.
    """
    return Desfalque(
        jogador=Jogador(nome=nome, time=time, setor=setor, peso=peso),
        status=status,
        confianca=confianca,
        fonte="https://exemplo.invalido/noticia",
        data=date(2026, 9, dia),
    )


# ----------------------------------------------------------------------------
# Os tipos recusam o que não pode existir
# ----------------------------------------------------------------------------
def test_desfalque_sem_fonte_e_recusado() -> None:
    """Desfalque sem origem é indistinguível de desfalque inventado."""
    with pytest.raises(ValueError, match="sem fonte"):
        Desfalque(jogador=Jogador("X", "ENG:Arsenal"), status="fora", fonte="")


def test_peso_fora_da_faixa_e_recusado() -> None:
    with pytest.raises(ValueError, match="fora de"):
        Jogador("X", "ENG:Arsenal", peso=1.5)


def test_status_desconhecido_e_recusado() -> None:
    with pytest.raises(ValueError, match="status"):
        _desfalque("X", status="machucado")


# ----------------------------------------------------------------------------
# O peso do jogador
# ----------------------------------------------------------------------------
def test_o_artilheiro_pesa_muito_mais_que_o_reserva() -> None:
    """É a razão de a fase existir: desfalque não é contagem, é tamanho."""
    artilheiro = importancia.Estatisticas(
        minutos=3000, gols=20, assistencias=8, titular=34,
        jogos_do_time=38, gols_do_time=70, posicao="attacker",
    )
    reserva = importancia.Estatisticas(
        minutos=180, gols=0, assistencias=1, titular=1,
        jogos_do_time=38, gols_do_time=70, posicao="attacker",
    )
    assert importancia.peso(artilheiro) > 5 * importancia.peso(reserva)


def test_o_goleiro_nao_e_punido_por_nao_fazer_gol() -> None:
    """Participação em gols só entra para quem ataca.

    Sem isso, todo defensor teria um terço do peso zerado por definição e
    pareceria irrelevante.
    """
    stats = dict(minutos=3420, gols=0, assistencias=0, titular=38,
                 jogos_do_time=38, gols_do_time=70)
    goleiro = importancia.peso(importancia.Estatisticas(**stats, posicao="goalkeeper"))
    atacante = importancia.peso(importancia.Estatisticas(**stats, posicao="attacker"))
    assert goleiro == pytest.approx(1.0)
    assert goleiro > atacante


def test_sem_dados_o_peso_e_zero() -> None:
    """Zero significa "não sei" — e sem saber, o ajuste certo é não mexer."""
    assert importancia.peso(importancia.Estatisticas()) == 0.0
    assert importancia.sem_estatisticas("X", "ENG:Arsenal").peso == 0.0


def test_a_fracao_nao_passa_de_um() -> None:
    """A API reporta minutos de quem trocou de time no meio da temporada.

    Sem o teto, a razão passaria de 1 e um jogador sozinho estouraria o time.
    """
    absurdo = importancia.Estatisticas(
        minutos=99_999, gols=50, assistencias=50, titular=99,
        jogos_do_time=10, gols_do_time=5, posicao="attacker",
    )
    assert importancia.peso(absurdo) <= 1.0


def test_o_meio_campo_conta_nos_dois_lados() -> None:
    assert importancia.setor("midfielder") == "ambos"
    assert importancia.setor("goalkeeper") == "defesa"
    assert importancia.setor("posicao que nao existe") == "ambos"


# ----------------------------------------------------------------------------
# O ajuste
# ----------------------------------------------------------------------------
def test_sem_desfalque_nao_ha_ajuste(cfg) -> None:
    resultado = ajuste_mod.calcular("ENG:Arsenal", [], cfg)
    assert not resultado.mexeu
    assert resultado.resumo().endswith("sem desfalques relevantes")


def test_duvida_pesa_metade_de_um_fora(cfg) -> None:
    """É o `peso_duvida: 0.5` do config.yaml, virado conta."""
    fora = ajuste_mod.calcular("ENG:Arsenal", [_desfalque("A")], cfg)
    duvida = ajuste_mod.calcular(
        "ENG:Arsenal", [_desfalque("A", status="duvida")], cfg
    )
    assert duvida.ataque == pytest.approx(fora.ataque / 2)


def test_confianca_baixa_mexe_menos(cfg) -> None:
    """Um boato não pode valer o mesmo que a escalação oficial."""
    certo = ajuste_mod.calcular("ENG:Arsenal", [_desfalque("A")], cfg)
    boato = ajuste_mod.calcular(
        "ENG:Arsenal", [_desfalque("A", confianca=0.3)], cfg
    )
    assert boato.ataque == pytest.approx(certo.ataque * 0.3)


def test_o_teto_do_config_age_e_diz_que_agiu(cfg) -> None:
    """Sem teto, sete desfalques fariam o time virar um amador."""
    muitos = [
        _desfalque(f"J{i}", peso=0.9, setor="ambos") for i in range(7)
    ]
    resultado = ajuste_mod.calcular("ENG:Arsenal", muitos, cfg)
    teto = ajuste_mod.limites(cfg)["ajuste_maximo"]
    assert resultado.ataque == pytest.approx(teto)
    assert resultado.defesa == pytest.approx(teto)
    assert resultado.truncado, "o teto agiu em silencio"
    assert "no teto" in resultado.resumo()


def test_o_ajuste_ignora_desfalque_de_outro_time(cfg) -> None:
    """Quem chama passa a rodada inteira; filtrar é trabalho daqui."""
    do_outro = _desfalque("B", time="ENG:Chelsea")
    resultado = ajuste_mod.calcular("ENG:Arsenal", [do_outro], cfg)
    assert not resultado.mexeu


def test_atacante_nao_mexe_na_defesa(cfg) -> None:
    resultado = ajuste_mod.calcular(
        "ENG:Arsenal", [_desfalque("A", setor="ataque")], cfg
    )
    assert resultado.ataque > 0
    assert resultado.defesa == 0.0


# ----------------------------------------------------------------------------
# "Volta" cancela
# ----------------------------------------------------------------------------
def test_a_noticia_mais_nova_ganha(cfg) -> None:
    """Sem isto, o time iria piorando a cada rodada para sempre."""
    lesionado = _desfalque("A", dia=1)
    voltou = _desfalque("A", status="volta", dia=5)
    resultado = ajuste_mod.calcular("ENG:Arsenal", [lesionado, voltou], cfg)
    assert not resultado.mexeu, "a volta nao cancelou a lesao"


def test_a_volta_antiga_nao_cancela_a_lesao_nova(cfg) -> None:
    """A ordem importa nos dois sentidos."""
    voltou = _desfalque("A", status="volta", dia=1)
    lesionado = _desfalque("A", dia=5)
    resultado = ajuste_mod.calcular("ENG:Arsenal", [voltou, lesionado], cfg)
    assert resultado.mexeu


def test_no_mesmo_dia_ganha_quem_tem_mais_confianca(cfg) -> None:
    """A escalação oficial vence o boato publicado no mesmo dia."""
    boato = _desfalque("A", dia=3, confianca=0.4)
    oficial = _desfalque("A", dia=3, status="volta", confianca=1.0)
    resultado = ajuste_mod.calcular("ENG:Arsenal", [boato, oficial], cfg)
    assert not resultado.mexeu


def test_o_mesmo_jogador_nao_conta_duas_vezes(cfg) -> None:
    """Duas fontes sobre a mesma lesão são uma lesão."""
    uma = ajuste_mod.calcular("ENG:Arsenal", [_desfalque("A", dia=1)], cfg)
    duas = ajuste_mod.calcular(
        "ENG:Arsenal", [_desfalque("A", dia=1), _desfalque("A", dia=2)], cfg
    )
    assert duas.ataque == pytest.approx(uma.ataque)


# ----------------------------------------------------------------------------
# O ajuste aplicado a um modelo de verdade
# ----------------------------------------------------------------------------
RAIZ = __import__("pathlib").Path(__file__).resolve().parents[1]

precisa_de_dados = pytest.mark.skipif(
    not (RAIZ / "data" / "processed" / "jogos.parquet").is_file(),
    reason="data/processed/jogos.parquet nao existe",
)


@pytest.fixture(scope="module")
def modelo_treinado(cfg):
    """Um Dixon-Coles de verdade, numa liga só, para os testes de sinal."""
    import pandas as pd

    from futebol.avaliacao import divisao
    from futebol.dados import limpeza
    from futebol.modelos.dixon_coles import DixonColes

    jogos = divisao.separar(limpeza.carregar(cfg), cfg).jogos
    da_liga = jogos.loc[jogos["liga"] == "E0"]
    corte = pd.Timestamp(da_liga["data"].max()) + pd.Timedelta(days=1)
    return DixonColes(cfg=cfg).treinar(da_liga, ate_data=corte), da_liga, corte


def _prever(modelo, da_liga, corte):
    from futebol.modelos import base

    times = sorted(set(da_liga["mandante"]) & set(da_liga["visitante"]))
    jogo = base.Jogo(
        liga="E0", mandante=times[0], visitante=times[1], data=corte
    )
    return jogo, modelo.prever(jogo), modelo.matriz_de_placares(jogo)


def _gols_esperados(matriz) -> tuple[float, float]:
    """(gols do mandante, gols do visitante) segundo a matriz de placares."""
    import numpy as np

    matriz = np.asarray(matriz, dtype=float)
    casa = float((matriz.sum(axis=1) * np.arange(matriz.shape[0])).sum())
    fora = float((matriz.sum(axis=0) * np.arange(matriz.shape[1])).sum())
    return casa, fora


@precisa_de_dados
def test_perder_zagueiro_faz_o_time_sofrer_mais_gols(cfg, modelo_treinado) -> None:
    """⚠️ O teste de SINAL, e o mais importante do arquivo.

    No modelo, ``λ = exp(intercepto + ataque_mandante − defesa_visitante + casa)``:
    a defesa entra **invertida**, positivo é defesa boa. Então tirar um zagueiro
    tem de ser uma SUBTRAÇÃO em ``defesa``, o que aumenta os gols sofridos.

    Somar em vez de subtrair faria o time **melhorar** ao perder jogador — e esse
    erro não levanta exceção nenhuma: a previsão sai bem formatada e ao
    contrário. É exatamente o tipo de defeito que só um teste de direção pega.
    """
    modelo, da_liga, corte = modelo_treinado
    jogo, _, matriz_antes = _prever(modelo, da_liga, corte)

    zagueiro = Desfalque(
        jogador=Jogador(jogo.visitante, jogo.visitante, "defesa", peso=0.2),
        status="fora",
        fonte="https://exemplo.invalido/lesao",
        data=date(2026, 9, 1),
    )
    ajustado = ajuste_mod.aplicar(
        modelo, {jogo.visitante: ajuste_mod.calcular(jogo.visitante, [zagueiro], cfg)}
    )
    _, _, matriz_depois = _prever(ajustado, da_liga, corte)

    gols_do_mandante_antes, _ = _gols_esperados(matriz_antes)
    gols_do_mandante_depois, _ = _gols_esperados(matriz_depois)

    assert gols_do_mandante_depois > gols_do_mandante_antes, (
        "o visitante perdeu um zagueiro e passou a sofrer MENOS gols - "
        "o sinal do ajuste de defesa esta invertido"
    )


@precisa_de_dados
def test_perder_atacante_faz_o_time_marcar_menos(cfg, modelo_treinado) -> None:
    """A outra direção, pelo mesmo motivo."""
    modelo, da_liga, corte = modelo_treinado
    jogo, _, matriz_antes = _prever(modelo, da_liga, corte)

    atacante = Desfalque(
        jogador=Jogador(jogo.mandante, jogo.mandante, "ataque", peso=0.2),
        status="fora",
        fonte="https://exemplo.invalido/lesao",
        data=date(2026, 9, 1),
    )
    ajustado = ajuste_mod.aplicar(
        modelo, {jogo.mandante: ajuste_mod.calcular(jogo.mandante, [atacante], cfg)}
    )
    _, _, matriz_depois = _prever(ajustado, da_liga, corte)

    antes, _ = _gols_esperados(matriz_antes)
    depois, _ = _gols_esperados(matriz_depois)
    assert depois < antes, "o mandante perdeu o atacante e passou a marcar MAIS"


@precisa_de_dados
def test_aplicar_nao_mexe_no_modelo_original(cfg, modelo_treinado) -> None:
    """O projeto precisa das DUAS previsões para poder comparar.

    Um ajuste que sobrescreve o modelo cru destrói a própria referência dele —
    e aí não há como avaliar se ele ajudou.
    """
    modelo, da_liga, corte = modelo_treinado
    _, antes, _ = _prever(modelo, da_liga, corte)

    jogo, _, _ = _prever(modelo, da_liga, corte)
    desfalque = Desfalque(
        jogador=Jogador(jogo.mandante, jogo.mandante, "ambos", peso=0.2),
        status="fora",
        fonte="https://exemplo.invalido/lesao",
    )
    ajuste_mod.aplicar(
        modelo, {jogo.mandante: ajuste_mod.calcular(jogo.mandante, [desfalque], cfg)}
    )

    _, depois, _ = _prever(modelo, da_liga, corte)
    assert depois == antes, "aplicar() mexeu no modelo original"


@precisa_de_dados
def test_time_sem_desfalque_preve_exatamente_igual(cfg, modelo_treinado) -> None:
    """O ajuste não pode vazar para quem não tem desfalque nenhum."""
    modelo, da_liga, corte = modelo_treinado
    jogo, antes, _ = _prever(modelo, da_liga, corte)

    ajustado = ajuste_mod.aplicar(modelo, {})
    _, depois, _ = _prever(ajustado, da_liga, corte)
    assert depois == antes
