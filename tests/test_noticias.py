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
from futebol.noticias.tipos import Desfalque, Jogador, JogoAlvo


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


# ----------------------------------------------------------------------------
# As fontes: cota, cache e casamento de times
# ----------------------------------------------------------------------------
def test_o_orcamento_trava_antes_de_estourar(tmp_path) -> None:
    """A trava age ANTES da chamada.

    Estourar a cota de graça derruba a conta pelo resto do dia, e ela só volta
    às 00:00 UTC.
    """
    from futebol.noticias import fontes

    orcamento = fontes.Orcamento(limite=3, caminho=tmp_path / "o.json")
    for _ in range(3):
        orcamento.gastar()
    assert orcamento.restam == 0
    with pytest.raises(fontes.SemCota, match="acabou"):
        orcamento.gastar()


def test_o_orcamento_sobrevive_a_reinicio(tmp_path) -> None:
    """⚠️ Guardado só em memória, tres execucoes de 40 passariam de 100.

    Cada execução do script começaria do zero e ninguém perceberia — que é
    exatamente o acidente que o limite existe para evitar.
    """
    from futebol.noticias import fontes

    caminho = tmp_path / "o.json"
    primeiro = fontes.Orcamento(limite=5, caminho=caminho)
    primeiro.gastar(4)

    segundo = fontes.Orcamento(limite=5, caminho=caminho)
    assert segundo.usadas == 4, "o contador nao sobreviveu ao reinicio"
    assert segundo.restam == 1


def test_o_orcamento_de_ontem_nao_conta_hoje(tmp_path) -> None:
    """A cota zera às 00:00 UTC."""
    import json

    from futebol.noticias import fontes

    caminho = tmp_path / "o.json"
    caminho.write_text(json.dumps({"dia": "1999-01-01", "usadas": 99}))
    assert fontes.Orcamento(limite=100, caminho=caminho).usadas == 0


def test_o_cache_expira(tmp_path) -> None:
    import os
    import time as relogio

    from futebol.noticias import fontes

    cache = fontes.Cache(pasta=tmp_path, validade_horas=1.0)
    cache.gravar("x", {"a": 1})
    assert cache.ler("x") == {"a": 1}

    # Envelhece o arquivo em duas horas.
    antigo = relogio.time() - 2 * 3600
    os.utime(tmp_path / "x.json", (antigo, antigo))
    assert cache.ler("x") is None


def test_a_fonte_falsa_so_devolve_os_times_alvo() -> None:
    """O pipeline filtra antes de buscar, e a fonte falsa imita isso.

    Se ela devolvesse tudo, os testes não pegariam um filtro quebrado na fonte
    de verdade.
    """
    from futebol.noticias import fontes

    alvo = _desfalque("A", time="ENG:Arsenal")
    intruso = _desfalque("B", time="ESP:Barcelona")
    fonte = fontes.FonteFalsa(respostas=[alvo, intruso])

    jogo = JogoAlvo("E0", "ENG:Arsenal", "ENG:Chelsea", date(2026, 9, 25))
    achados = fonte.desfalques([jogo])
    assert [d.jogador.nome for d in achados] == ["A"]


def test_time_que_nao_casa_e_descartado_e_nao_chutado() -> None:
    """⚠️ Regra 14 outra vez: associar o desfalque ao time errado é o pior erro.

    Os vocabulários da API e do projeto são diferentes e ninguém mapeou um no
    outro. Quem não casa sai da lista; chutar daria uma previsão bem formatada
    sobre o time errado.
    """
    from futebol.noticias.fontes import ApiFutebol

    alvo = {"ENG:Arsenal", "ENG:Chelsea"}
    assert ApiFutebol._casar_time("Arsenal", alvo) == "ENG:Arsenal"
    assert ApiFutebol._casar_time("ARSENAL", alvo) == "ENG:Arsenal"
    assert ApiFutebol._casar_time("Nottingham Forest", alvo) is None
    assert ApiFutebol._casar_time("", alvo) is None


def test_sem_chave_a_mensagem_ensina_o_que_fazer(cfg, monkeypatch) -> None:
    """Não é erro de programação: é configuração que falta."""
    from futebol.noticias import fontes

    monkeypatch.delenv("API_FUTEBOL_CHAVE", raising=False)
    with pytest.raises(fontes.SemChave, match="API_FUTEBOL_CHAVE"):
        fontes.ApiFutebol.do_ambiente(cfg)


def test_o_limite_do_config_e_o_do_plano_gratuito(cfg) -> None:
    """⚠️ Estava 200 e o plano gratuito dá 100.

    Com 200, o projeto estouraria a cota silenciosamente na metade do caminho.
    """
    assert int(cfg.secao("noticias")["limite_chamadas_dia"]) <= 100


# ----------------------------------------------------------------------------
# A extração com LLM
# ----------------------------------------------------------------------------
def _noticia(titulo: str = "N1"):
    from futebol.noticias.extracao import Noticia

    return Noticia(
        titulo=titulo,
        texto="texto qualquer",
        fonte="https://exemplo.invalido/n1",
        data=date(2026, 9, 20),
    )


def test_o_extrator_converte_o_json_em_desfalque() -> None:
    from futebol.noticias import extracao

    extrator = extracao.ExtratorFalso(
        respostas={
            "N1": [
                {
                    "jogador": "Fulano",
                    "time": "ENG:Arsenal",
                    "status": "fora",
                    "motivo": "lesão na coxa",
                    "posicao": "atacante",
                    "confianca": 0.9,
                }
            ]
        }
    )
    achados = extrator.extrair([_noticia()])
    assert len(achados) == 1
    assert achados[0].jogador.nome == "Fulano"
    assert achados[0].jogador.setor == "ataque"
    assert achados[0].confianca == 0.9
    assert achados[0].fonte.startswith("https://")


def test_o_llm_nao_da_peso_ao_jogador() -> None:
    """⚠️ A fronteira que este módulo existe para não cruzar.

    O LLM lê texto. Quem dá peso é `importancia`, com as estatísticas do
    jogador — o LLM não tem como saber quanto um jogador vale para o time, e
    deixá-lo estimar produziria um número confiante e sem origem.
    """
    from futebol.noticias import extracao

    convertido = extracao.converter(
        {
            "jogador": "Craque",
            "time": "ENG:Arsenal",
            "status": "fora",
            "motivo": "",
            "posicao": "atacante",
            "confianca": 1.0,
        },
        _noticia(),
    )
    assert convertido is not None
    assert convertido.jogador.peso == 0.0, "o LLM atribuiu peso"


def test_item_sem_time_e_descartado_e_nao_completado() -> None:
    """Desfalque com o time chutado é pior que nenhum desfalque (regra 14)."""
    from futebol.noticias import extracao

    assert extracao.converter(
        {"jogador": "X", "time": "", "status": "fora", "confianca": 1.0}, _noticia()
    ) is None
    assert extracao.converter(
        {"jogador": "", "time": "ENG:Arsenal", "status": "fora"}, _noticia()
    ) is None


def test_status_invalido_e_descartado() -> None:
    from futebol.noticias import extracao

    assert extracao.converter(
        {"jogador": "X", "time": "T", "status": "talvez", "confianca": 1.0},
        _noticia(),
    ) is None


def test_confianca_estranha_nao_quebra_nem_estoura() -> None:
    """A confiança vira peso do ajuste; fora de [0,1] envenenaria a conta."""
    from futebol.noticias import extracao

    base = {"jogador": "X", "time": "T", "status": "fora", "posicao": ""}
    assert extracao.converter({**base, "confianca": 9.0}, _noticia()).confianca == 1.0
    assert extracao.converter({**base, "confianca": -5}, _noticia()).confianca == 0.0
    assert extracao.converter({**base, "confianca": "oi"}, _noticia()).confianca == 0.5


def test_noticia_sem_desfalque_devolve_lista_vazia() -> None:
    """É o caso comum, e é uma resposta correta — não um erro."""
    from futebol.noticias import extracao

    extrator = extracao.ExtratorFalso(respostas={})
    assert extrator.extrair([_noticia()]) == []


def test_o_esquema_obriga_os_campos_que_o_ajuste_usa() -> None:
    """A garantia vem do JSON Schema, não de pedir educadamente no prompt.

    "Responda só JSON" funciona quase sempre — e "quase sempre", num pipeline
    que roda sozinho toda semana, significa quebrar numa quinta-feira qualquer.
    """
    from futebol.noticias import extracao

    item = extracao.ESQUEMA["properties"]["desfalques"]["items"]
    assert set(item["required"]) >= {"jogador", "time", "status", "confianca"}
    assert item["additionalProperties"] is False
    assert item["properties"]["status"]["enum"] == ["fora", "duvida", "volta"]


def test_a_instrucao_proibe_o_llm_de_opinar_sobre_o_jogo() -> None:
    """O LLM lê texto; a probabilidade sai do Dixon-Coles."""
    from futebol.noticias import extracao

    instrucao = extracao.INSTRUCAO.lower()
    assert "não estima probabilidade" in instrucao
    assert "não sugere aposta" in instrucao


def test_sem_chave_da_anthropic_a_mensagem_ensina(cfg, monkeypatch) -> None:
    from futebol.noticias import extracao

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(extracao.SemChaveDaAnthropic, match="ANTHROPIC_API_KEY"):
        extracao.Extrator.do_ambiente(cfg)


def test_recusa_do_modelo_nao_vira_silencio() -> None:
    """Numa recusa o conteúdo pode não existir.

    Tratar isso como "nenhum desfalque" faria uma falha virar silêncio — e o
    pipeline seguiria achando que simplesmente não há lesão nenhuma.
    """
    from futebol.noticias import extracao

    class RespostaRecusada:
        stop_reason = "refusal"
        content: list = []

    assert extracao.Extrator._converter_resposta(RespostaRecusada(), _noticia()) == []


# ----------------------------------------------------------------------------
# Os proximos jogos
# ----------------------------------------------------------------------------
CSV_FIXTURES = """Div,Date,Time,HomeTeam,AwayTeam
E0,25/09/2026,15:00,Arsenal,Chelsea
E0,26/09/2026,17:30,Liverpool,Everton
SC1,25/09/2026,15:00,Falkirk,Ayr
E0,30/12/2026,15:00,Arsenal,Tottenham
E0,,15:00,Fulham,Brentford
E0,25/09/2026,15:00,,Wolves
"""


def test_os_jogos_alvo_respeitam_a_janela_e_as_ligas(cfg) -> None:
    """Só as 18 aprovadas (regra 12), e só os próximos dias.

    A SC1 do CSV é a segunda divisão escocesa, reprovada no filtro da Fase 2; o
    jogo de dezembro está fora da janela de 7 dias.
    """
    from futebol.noticias import jogos_alvo

    achados = jogos_alvo.ler(CSV_FIXTURES, cfg, hoje=date(2026, 9, 24), dias=7)
    nomes = [(j.liga, j.mandante, j.visitante) for j in achados]

    assert len(achados) == 2, f"esperava 2, veio {nomes}"
    assert all(j.liga == "E0" for j in achados), "liga reprovada entrou"
    assert all(date(2026, 9, 24) <= j.data <= date(2026, 10, 1) for j in achados)


def test_o_jogo_alvo_usa_a_chave_pais_nome(cfg) -> None:
    """Regra 14.

    Guardar o nome solto faria o ajuste procurar um time que o modelo não
    conhece — e não achar nada, em silêncio.
    """
    from futebol.noticias import jogos_alvo

    achados = jogos_alvo.ler(CSV_FIXTURES, cfg, hoje=date(2026, 9, 24), dias=7)
    for jogo in achados:
        assert ":" in jogo.mandante, f"{jogo.mandante} sem prefixo de pais"
        assert ":" in jogo.visitante


def test_linha_sem_data_ou_sem_time_e_pulada(cfg) -> None:
    """O arquivo do football-data traz linhas incompletas."""
    from futebol.noticias import jogos_alvo

    achados = jogos_alvo.ler(CSV_FIXTURES, cfg, hoje=date(2026, 9, 24), dias=7)
    assert all(j.mandante.split(":")[-1] for j in achados)


def test_a_lista_de_times_alvo_nao_repete(cfg) -> None:
    from futebol.noticias import jogos_alvo

    achados = jogos_alvo.ler(CSV_FIXTURES, cfg, hoje=date(2026, 9, 24), dias=7)
    assert len(jogos_alvo.times(achados)) == 4


# ----------------------------------------------------------------------------
# O caderno do paper trading
# ----------------------------------------------------------------------------
def _cfg_temporario(cfg, tmp_path):
    """Um config com a raiz num diretório descartável."""

    class ConfigTemporario:
        def __init__(self, original, raiz):
            self.raiz = raiz
            self.bruto = original.bruto
            self.seed = original.seed

        def secao(self, nome):
            return self.bruto[nome]

    return ConfigTemporario(cfg, tmp_path)


def _linhas(n: int, *, com_ajuste: bool, ajustado_melhor: bool) -> list[dict]:
    """n jogos em que o mandante sempre venceu."""
    linhas = []
    for i in range(n):
        p_cru = 0.45
        p_aj = 0.55 if ajustado_melhor else 0.35
        linhas.append(
            {
                "data_do_jogo": f"2026-09-{(i % 28) + 1:02d}",
                "liga": "E0",
                "mandante": "ENG:A",
                "visitante": f"ENG:B{i}",
                "prob_H_cru": p_cru,
                "prob_D_cru": 0.30,
                "prob_A_cru": 0.25,
                "prob_H_ajustado": p_aj,
                "prob_D_ajustado": 0.30,
                "prob_A_ajustado": round(1 - p_aj - 0.30, 4),
                "ajuste_mandante_ataque": 0.1 if com_ajuste else 0.0,
                "ajuste_mandante_defesa": 0.0,
                "ajuste_visitante_ataque": 0.0,
                "ajuste_visitante_defesa": 0.0,
                "desfalques": "Fulano (fora)" if com_ajuste else "",
                "resultado": "H",
            }
        )
    return linhas


def test_o_caderno_vazio_nao_inventa_conclusao(cfg, tmp_path) -> None:
    from futebol.noticias import registro

    resultado = registro.avaliar(_cfg_temporario(cfg, tmp_path))
    assert resultado.n == 0
    assert "Nenhum jogo com resultado" in resultado.veredito


def test_o_caderno_acrescenta_e_nunca_reescreve(cfg, tmp_path) -> None:
    """⚠️ Caderno reescrevível pode ser corrigido depois de ver o resultado."""
    from futebol.noticias import registro

    temporario = _cfg_temporario(cfg, tmp_path)
    registro.anotar(temporario, _linhas(2, com_ajuste=True, ajustado_melhor=True))
    registro.anotar(temporario, _linhas(3, com_ajuste=True, ajustado_melhor=True))
    assert len(registro.carregar(temporario)) == 5


def test_a_primeira_gravacao_e_a_que_vale(cfg, tmp_path) -> None:
    """Ficar com a última premiaria quem roda de novo após a escalação sair."""
    from futebol.noticias import registro

    temporario = _cfg_temporario(cfg, tmp_path)
    registro.anotar(temporario, _linhas(1, com_ajuste=True, ajustado_melhor=True))
    registro.anotar(temporario, _linhas(1, com_ajuste=True, ajustado_melhor=False))

    caderno = registro.carregar(temporario)
    assert len(caderno) == 2

    unica = registro.primeira_gravacao(caderno)
    assert len(unica) == 1
    assert float(unica.iloc[0]["prob_H_ajustado"]) == 0.55, "ficou com a segunda"


def test_o_resultado_fica_vazio_ate_o_jogo_acontecer(cfg) -> None:
    """Preencher na hora da previsão seria invenção: o jogo não aconteceu."""
    from futebol.noticias import registro
    from futebol.noticias.tipos import Ajuste

    jogo = JogoAlvo("E0", "ENG:A", "ENG:B", date(2026, 9, 25))
    linha = registro.linha_de_jogo(
        jogo,
        {"H": 0.5, "D": 0.3, "A": 0.2},
        {"H": 0.55, "D": 0.28, "A": 0.17},
        Ajuste("ENG:A"),
        Ajuste("ENG:B"),
    )
    assert linha["resultado"] == ""


def test_sem_ajuste_nenhum_nao_ha_o_que_comparar(cfg, tmp_path) -> None:
    """Com as duas colunas iguais, qualquer número seria ruído puro."""
    from futebol.noticias import registro

    temporario = _cfg_temporario(cfg, tmp_path)
    registro.anotar(temporario, _linhas(40, com_ajuste=False, ajustado_melhor=True))
    resultado = registro.avaliar(temporario)
    assert resultado.com_ajuste == 0
    assert "não há o que comparar" in resultado.veredito.lower()


def test_amostra_pequena_diz_ainda_nao_da_para_saber(cfg, tmp_path) -> None:
    """⚠️ A regra da especificação, virada código."""
    from futebol.noticias import registro

    temporario = _cfg_temporario(cfg, tmp_path)
    registro.anotar(temporario, _linhas(5, com_ajuste=True, ajustado_melhor=True))
    resultado = registro.avaliar(temporario)
    assert "ainda não dá para saber" in resultado.veredito.lower()


def test_melhora_consistente_e_chamada_de_indicio(cfg, tmp_path) -> None:
    """Nunca "funciona": a amostra é pequena por construção."""
    from futebol.noticias import registro

    temporario = _cfg_temporario(cfg, tmp_path)
    registro.anotar(temporario, _linhas(60, com_ajuste=True, ajustado_melhor=True))
    resultado = registro.avaliar(temporario)
    assert resultado.diferenca < 0, "melhorar tem de dar diferenca NEGATIVA"
    assert "indício" in resultado.veredito.lower()
    assert "prova" in resultado.veredito.lower()


def test_piora_consistente_manda_desligar_e_nao_afinar(cfg, tmp_path) -> None:
    """⚠️ Afinar até ficar bonito é o sobreajuste que o projeto inteiro evita."""
    from futebol.noticias import registro

    temporario = _cfg_temporario(cfg, tmp_path)
    registro.anotar(temporario, _linhas(60, com_ajuste=True, ajustado_melhor=False))
    resultado = registro.avaliar(temporario)
    assert resultado.diferenca > 0
    assert "desligá-lo" in resultado.veredito


def test_preencher_resultados_completa_so_o_que_aconteceu(cfg, tmp_path) -> None:
    import pandas as pd

    from futebol.noticias import registro

    temporario = _cfg_temporario(cfg, tmp_path)
    linhas = _linhas(2, com_ajuste=True, ajustado_melhor=True)
    for linha in linhas:
        linha["resultado"] = ""
    registro.anotar(temporario, linhas)

    jogos = pd.DataFrame(
        [
            {
                "data": linhas[0]["data_do_jogo"],
                "liga": "E0",
                "mandante": "ENG:A",
                "visitante": "ENG:B0",
                "resultado": "H",
            }
        ]
    )
    assert registro.preencher_resultados(temporario, jogos) == 1

    caderno = registro.carregar(temporario)
    assert (caderno["resultado"] == "H").sum() == 1
