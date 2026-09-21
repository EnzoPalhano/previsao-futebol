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

import pytest

from futebol.app import avisos
from futebol.app.paginas import (
    backtest,
    cash_out,
    comparar,
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
    for valor in (avisos.ROI_FASE_6, avisos.CLV_FASE_6, avisos.ROI_ALEATORIO_FASE_6):
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
