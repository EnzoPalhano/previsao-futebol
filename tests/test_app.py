"""Testes do app: as telas rodam, e os avisos obrigatórios estão nelas.

Duas famílias de teste, e as duas existem por motivos diferentes:

1. **as páginas executam sem estourar.** O ``AppTest`` do Streamlit roda cada
   tela de verdade, com a tabela de jogos real, e falha se qualquer exceção
   subir. Sem isso, um erro numa página só apareceria para quem abrisse o app
   e clicasse naquela aba;
2. **os avisos continuam lá.** A Fase 8 é a primeira entrega que alguém pode
   usar sem ler relatório nenhum, e tudo o que as Fases 6 e 7 mediram — o
   modelo perde do mercado, o filtro de EV escolhe pior que o chute, a chance
   da múltipla é otimista — precisa estar **na tela**. Um aviso apagado numa
   reescrita não dá erro: só transforma o app numa máquina de sugerir apostas
   ruins. Daí o teste.

⚠️ Os testes que precisam da tabela de jogos são **pulados** quando ela não
existe, em vez de falharem: ``data/processed/`` não vai para o Git (regra 4),
então num clone novo ela não está lá, e um CI vermelho por isso seria ruído.
Os testes de aviso não dependem de dado nenhum e rodam sempre.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

from futebol.app import avisos
from futebol.app.paginas import (
    backtest,
    cash_out,
    comparar,
    comum,
    desempenho,
    inicio,
    multiplas,
    prever,
)

#: O app inteiro, para o ``AppTest``. Caminho absoluto de proposito: o
#: AppTest resolve caminho relativo contra o arquivo que o chama, e nao
#: contra a raiz do projeto.
APP = Path(__file__).resolve().parents[1] / "src" / "futebol" / "app" / "streamlit_app.py"

#: Quanto tempo uma página pode levar. O backtest percorre cem mil apostas
#: candidatas na primeira execução.
TEMPO_LIMITE = 180


RAIZ = Path(__file__).resolve().parents[1]


def _tem_dados() -> bool:
    return (RAIZ / "data" / "processed" / "jogos.parquet").is_file()


precisa_de_dados = pytest.mark.skipif(
    not _tem_dados(),
    reason="data/processed/jogos.parquet nao existe (rode scripts/preparar_dados.py)",
)


# ----------------------------------------------------------------------------
# Os avisos obrigatórios
# ----------------------------------------------------------------------------
def test_todo_aviso_diz_onde_o_numero_foi_medido() -> None:
    """Aviso que cita número sem origem é indistinguível de número inventado."""
    for aviso in avisos.TODOS:
        assert aviso.origem, f"o aviso {aviso.titulo!r} nao diz a origem"
        assert aviso.titulo and aviso.texto


def test_o_aviso_de_jogo_responsavel_traz_o_cvv() -> None:
    """Exigência da seção 9 da especificação."""
    assert "188" in avisos.JOGO_RESPONSAVEL.texto


def test_a_pagina_de_previsao_avisa_que_o_modelo_perde_do_mercado() -> None:
    fonte = inspect.getsource(prever)
    assert "MODELO_PERDE_DO_MERCADO" in fonte
    assert "ODD_JUSTA" in fonte


def test_a_pagina_de_odds_avisa_que_ev_positivo_nao_e_oportunidade() -> None:
    """O aviso mais importante do app: sem ele a tela vira uma recomendação."""
    assert "EV_POSITIVO_NAO_E_OPORTUNIDADE" in inspect.getsource(comparar)


def test_a_pagina_de_multiplas_traz_os_dois_avisos_obrigatorios() -> None:
    """Independência (seção 7.1) e o exagero por seleção (Fase 7)."""
    fonte = inspect.getsource(multiplas)
    assert "INDEPENDENCIA" in fonte
    assert "EXAGERO_POR_SELECAO" in fonte


def test_a_pagina_de_backtest_avisa_sobre_amostra_e_intervalo(  ) -> None:
    assert "AMOSTRA_E_INTERVALO" in inspect.getsource(backtest)


def test_a_pagina_de_cash_out_avisa_que_a_taxa_e_sempre_a_mesma() -> None:
    assert "CASH_OUT_COBRA_SEMPRE" in inspect.getsource(cash_out)


def test_toda_pagina_de_aposta_tem_rodape_de_jogo_responsavel() -> None:
    """A seção 9 pede o aviso na página inicial; o projeto põe em todas."""
    for pagina in (inicio, prever, comparar, backtest, multiplas, cash_out, desempenho):
        assert "comum.rodape()" in inspect.getsource(pagina), (
            f"a pagina {pagina.__name__} nao chama o rodape de jogo responsavel"
        )


# ----------------------------------------------------------------------------
# Defeitos que já apareceram na tela, e que não podem voltar
# ----------------------------------------------------------------------------
def test_dinheiro_em_markdown_escapa_o_cifrao() -> None:
    r"""O cifrão abre fórmula LaTeX no Markdown do Streamlit.

    Duas quantias na mesma frase — "ganha R$ 6,10 por bilhete de R$ 10,00" —
    faziam tudo entre os dois cifrões virar equação: o negrito parava de
    funcionar e os ``**`` apareciam crus. Era o que a linha de valor esperado da
    página de múltiplas mostrava.
    """
    assert comum.reais(6.1).startswith("R\\$")


def test_a_pagina_de_multiplas_nao_escreve_cifrao_cru_em_markdown() -> None:
    """A correção acima só vale se a linha de valor esperado usar o ajudante.

    ⚠️ O teste olha **a chamada de ``st.markdown``**, e não o módulo inteiro: o
    ``st.metric`` logo acima escreve ``R$`` cru de propósito e está certo, porque
    métrica não passa por Markdown. A regra não é "nunca escreva cifrão": é
    "nunca escreva cifrão cru onde o Markdown vai ler".
    """
    fonte = inspect.getsource(multiplas.mostrar_bilhete)
    markdown = fonte.split("st.markdown(", 1)[1]
    assert "comum.reais(" in markdown
    assert "R$ {" not in markdown, "cifrão cru dentro de texto em Markdown"


def test_o_backtest_mede_com_o_mesmo_bootstrap_do_relatorio() -> None:
    """Tela e documento não podem publicar intervalos diferentes.

    Com ``amostras_bootstrap=2000`` a tela dava IC de -14,90% a -10,91% para a
    mesma configuração que o relatório da Fase 6 publica como -14,97% a
    -10,89%. Os dois eram ruído de reamostragem, e os dois estavam certos — mas
    a mesma medição não pode sair com dois valores. O jeito de garantir é a
    página não escolher: usa o padrão de ``simulador.medir``, que é o que o
    relatório usa.
    """
    assert "amostras_bootstrap" not in inspect.getsource(backtest)


def test_a_banca_e_desenhada_em_escala_logaritmica() -> None:
    """Eixo linear mente sobre banca: R$ 10 e R$ 0,10 viram a mesma linha.

    A página reaproveita o gráfico do relatório em vez de um ``st.line_chart``,
    que só desenha em escala linear.
    """
    fonte = inspect.getsource(backtest)
    assert "graficos.evolucao_da_banca" in fonte
    assert "st.line_chart(" not in fonte


def test_o_grafico_por_competicao_preserva_a_ordem() -> None:
    """``st.bar_chart`` reordena por nome e jogava fora a ordenação do código.

    A legenda da seção convida a ler a ordem ("barra curta é competição em que a
    diferença é pequena"), e num gráfico alfabético essa leitura é impossível.
    """
    fonte = inspect.getsource(desempenho)
    assert "graficos.distancia_do_mercado" in fonte
    assert "st.bar_chart(" not in fonte


def test_o_app_declara_que_a_pagina_esta_em_portugues() -> None:
    """Sem isso o Chrome traduz o app de português para português.

    O Streamlit serve ``<html lang="en">``. O navegador acredita na declaração,
    não no texto, e passa um tradutor automático por cima: "Apostas envolvem
    risco real de perda" virava "Apostas de envolvimento risco real de perda", e
    "Início" virava "Não se trata de uma questão de". Num app qualquer seria
    feio; aqui adultera os **avisos obrigatórios**, que são o produto da fase.
    """
    from futebol.app import streamlit_app

    fonte = inspect.getsource(streamlit_app.declarar_idioma)
    assert "pt-BR" in fonte


def test_o_exagero_da_multipla_cresce_com_o_tamanho() -> None:
    """É o erro por perna elevado à potência do bilhete (Fase 7)."""
    valores = [avisos.exagero_da_multipla(k) for k in range(1, 9)]
    assert valores == sorted(valores)
    assert valores[0] == pytest.approx(1 - avisos.RAZAO_POR_SELECAO)


def test_os_numeros_dos_avisos_batem_com_os_relatorios() -> None:
    """Número copiado à mão é número que envelhece calado.

    Os avisos citam resultados das Fases 6 e 7. Se um relatório for regerado com
    outro valor, este teste avisa antes de o app passar a mentir.
    """
    fase6 = RAIZ / "docs" / "relatorios" / "fase6.md"
    if not fase6.is_file():
        pytest.skip("relatorio da Fase 6 ainda nao foi gerado")
    texto = fase6.read_text(encoding="utf-8")
    valores = (
        avisos.ROI_FASE_6,
        avisos.CLV_FASE_6,
        avisos.ROI_APOSTAR_EM_TUDO_FASE_6,
        avisos.ROI_SORTEIO_FASE_6,
    )
    for valor in valores:
        citado = f"{abs(valor) * 100:.2f}".replace(".", ",")
        assert citado in texto, f"{citado}% nao aparece no relatorio da Fase 6"


# ----------------------------------------------------------------------------
# As páginas executam
# ----------------------------------------------------------------------------
def _rodar(pagina: str):
    from streamlit.testing.v1 import AppTest

    teste = AppTest.from_file(str(APP), default_timeout=TEMPO_LIMITE)
    teste.run()
    # A navegação do Streamlit escolhe a primeira página; para as outras, o
    # teste chama a função da tela diretamente no mesmo contexto.
    return teste


@precisa_de_dados
def test_o_app_abre_sem_estourar() -> None:
    teste = _rodar("inicio")
    assert not teste.exception, teste.exception


@precisa_de_dados
@pytest.mark.parametrize(
    "pagina",
    [inicio, prever, comparar, backtest, multiplas, cash_out, desempenho],
    ids=lambda p: p.__name__.rsplit(".", 1)[-1],
)
def test_cada_pagina_roda_sem_estourar(pagina) -> None:
    """Uma exceção numa tela só apareceria para quem clicasse naquela aba."""
    from streamlit.testing.v1 import AppTest

    fonte = (
        "from futebol.app.paginas import "
        f"{pagina.__name__.rsplit('.', 1)[-1]} as pagina\n"
        "pagina.mostrar()\n"
    )
    teste = AppTest.from_string(fonte, default_timeout=TEMPO_LIMITE)
    teste.run()
    assert not teste.exception, f"{pagina.__name__}: {teste.exception}"


@precisa_de_dados
def test_a_pagina_inicial_mostra_o_resultado_negativo() -> None:
    """O veredito vem antes da ferramenta — é o ponto da tela de abertura."""
    from streamlit.testing.v1 import AppTest

    teste = AppTest.from_string(
        "from futebol.app.paginas import inicio\ninicio.mostrar()\n",
        default_timeout=TEMPO_LIMITE,
    )
    teste.run()
    texto = " ".join(bloco.value for bloco in teste.markdown)
    assert "não há vantagem" in texto.lower()


@precisa_de_dados
def test_o_app_nunca_oferece_o_cache_do_teste_final() -> None:
    """Regra 7: a tela não pode ler as temporadas trancadas. Nem por acidente.

    ⚠️ Isto chegou a acontecer. O cache do walk-forward é um arquivo por
    ``<janela>__<candidato>__<assinatura>``, e a Fase 9 grava um cache do
    **mesmo candidato** (``dc-xi-0.003``) numa janela diferente — a trancada.
    Como ``modelos_medidos`` chaveava só pelo nome do candidato, os dois
    arquivos colidiam e o do teste final vencia por vir depois na ordem: o app
    passava a servir as temporadas do cofre.

    O que denunciou foi um ``KeyError``, porque os índices do cofre não existem
    na tabela do app. Isso foi **sorte**: com os índices batendo, a tela teria
    mostrado dados do teste final sem erro nenhum.
    """
    from futebol.app import dados
    from futebol.avaliacao import selecao

    cfg = dados.config()
    da_validacao = f"{pd.Timestamp(selecao.INICIO_VALIDACAO).date()}_"
    for nome, caminho in dados.modelos_medidos(cfg).items():
        janela = caminho.stem.split("__")[0]
        assert janela.startswith(da_validacao), (
            f"o candidato {nome!r} veio da janela {janela!r}, que nao e a de "
            "validacao - a regra 7 proibe o app de ler o teste final"
        )
