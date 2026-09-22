"""Busca desfalques da proxima rodada e grava as duas previsoes. A Fase 10.

Uso::

    python scripts/desfalques.py --falso     # demonstra SEM chave nenhuma
    python scripts/desfalques.py             # de verdade (precisa do .env)
    python scripts/desfalques.py --avaliar   # le o caderno e diz o que da
    python scripts/desfalques.py --preencher # completa os jogos que ja aconteceram

ATENCAO, e e o enquadramento da fase inteira: isto NAO e uma hipotese validada.
Seis semanas de jogos sao ~150 previsoes, e com 150 jogos a menor melhora de log
loss detectavel e 0,0338 -- enquanto a distancia INTEIRA do modelo para o
mercado e 0,0212. Ou seja: pela log loss, o ajuste teria de superar o mercado em
60% so para o efeito aparecer. Por isso o criterio e CLV (1,60 pp com 150
apostas) e por isso a resposta, enquanto o intervalo cruzar zero, e "ainda nao
da para saber".

O pipeline filtra ANTES de buscar: jogos alvo -> times alvo -> API -> noticias
-> LLM. Nada e consultado fora dos times da proxima rodada.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from futebol import segredos
from futebol.avaliacao import divisao, selecao
from futebol.config import carregar_config
from futebol.dados import limpeza
from futebol.modelos import base
from futebol.modelos.dixon_coles import DixonColes
from futebol.noticias import ajuste as ajuste_mod
from futebol.noticias import fontes, importancia, jogos_alvo, registro
from futebol.noticias.tipos import Desfalque, Jogador, JogoAlvo
from futebol.terminal import preparar_saida

#: Um CSV de proximos jogos de mentira, para o modo --falso funcionar sem rede.
FIXTURES_FALSAS = """Div,Date,HomeTeam,AwayTeam
E0,{d1},Arsenal,Chelsea
E0,{d1},Liverpool,Everton
SP1,{d2},Barcelona,Sevilla
"""


def _desfalques_falsos(jogos: list[JogoAlvo]) -> list[Desfalque]:
    """Desfalques de mentira, claramente rotulados como tal.

    Existem para a fase ser demonstravel antes de o Enzo ter conta em lugar
    nenhum -- e para o guia poder mostrar a tela funcionando.
    """
    if not jogos:
        return []
    primeiro = jogos[0]
    return [
        Desfalque(
            jogador=Jogador("Atacante Titular", primeiro.mandante, "ataque", 0.22),
            status="fora",
            motivo="lesao muscular (EXEMPLO - dado de mentira)",
            confianca=0.9,
            fonte="fonte de exemplo, modo --falso",
            data=date.today(),
        ),
        Desfalque(
            jogador=Jogador("Zagueiro Titular", primeiro.visitante, "defesa", 0.18),
            status="duvida",
            motivo="desconforto (EXEMPLO - dado de mentira)",
            confianca=0.5,
            fonte="fonte de exemplo, modo --falso",
            data=date.today(),
        ),
    ]


def _prever(modelo, jogo: JogoAlvo) -> dict:
    return modelo.prever(
        base.Jogo(
            liga=jogo.liga,
            mandante=jogo.mandante,
            visitante=jogo.visitante,
            data=pd.Timestamp(jogo.data),
        )
    )


def main() -> int:
    preparar_saida()
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument(
        "--falso",
        action="store_true",
        help="roda com dados de mentira, sem chave e sem rede",
    )
    analise.add_argument(
        "--avaliar", action="store_true", help="le o caderno e diz o que da para dizer"
    )
    analise.add_argument(
        "--preencher",
        action="store_true",
        help="completa o resultado dos jogos que ja aconteceram",
    )
    analise.add_argument(
        "--historico",
        type=int,
        metavar="ANO",
        help=(
            "roda com lesoes REAIS de uma temporada liberada pelo plano "
            "gratuito (2022 a 2024). DEMONSTRACAO, nunca medicao."
        ),
    )
    argumentos = analise.parse_args()

    cfg = carregar_config()
    # Sem isto o .env e um arquivo decorativo: as chaves moram nele e o codigo
    # as procura em os.environ. Faltava a ponte.
    segredos.carregar(cfg.raiz)

    if argumentos.historico and argumentos.historico not in fontes.TEMPORADAS_GRATUITAS:
        liberadas = ", ".join(str(t) for t in fontes.TEMPORADAS_GRATUITAS)
        print(
            f"O plano gratuito da API cobre {liberadas}. "
            f"{argumentos.historico} exige plano pago.",
            file=sys.stderr,
        )
        return 1

    # O modo historico e uma DEMONSTRACAO e escreve no caderno de demonstracao.
    # Deixa-lo escrever no caderno de evidencia seria contamina-lo com jogos
    # cujas lesoes nao se sabe quando viraram publicas -- exatamente o que
    # torna o backtest desta fase impossivel.
    demo = argumentos.falso or bool(argumentos.historico)

    # ------------------------------------------------------------------
    # Modos que so leem o caderno
    # ------------------------------------------------------------------
    if argumentos.avaliar:
        comparacao = registro.avaliar(cfg, falso=demo)
        print("=" * 70)
        print("O QUE O CADERNO DIZ ATE AGORA")
        print("=" * 70)
        if comparacao.n:
            print(f"  jogos com resultado ... {comparacao.n}")
            print(f"  deles, com ajuste ..... {comparacao.com_ajuste}")
            print(f"  log loss cru .......... {comparacao.log_loss_cru:.4f}")
            print(f"  log loss ajustado ..... {comparacao.log_loss_ajustado:.4f}")
            print(f"  diferenca ............. {comparacao.diferenca:+.4f}")
            print(
                f"  IC 95% ................ {comparacao.ic[0]:+.4f} a "
                f"{comparacao.ic[1]:+.4f}"
            )
            print(f"  menor detectavel ...... {comparacao.detectavel:.4f}")
        print("-" * 70)
        print(f"  {comparacao.veredito}")
        print("=" * 70)
        return 0

    if argumentos.preencher:
        jogos = limpeza.carregar(cfg)
        quantos = registro.preencher_resultados(cfg, jogos, falso=demo)
        print(f"{quantos} linha(s) do caderno ganharam resultado.")
        return 0

    # ------------------------------------------------------------------
    # O pipeline
    # ------------------------------------------------------------------
    print("1. Jogos alvo dos proximos dias...")
    hoje = date.today()
    dias = int(cfg.secao("noticias")["dias_a_frente"])
    if argumentos.historico:
        # Uma rodada de verdade de uma temporada liberada. A data de referencia
        # vira uma data daquela temporada, e o resto do pipeline nao muda -- e
        # esse o ponto: o codigo e o mesmo, so a janela e outra.
        jogos_todos = limpeza.carregar(cfg)
        da_temporada = jogos_todos.loc[
            jogos_todos["temporada"].astype(str).str.startswith(
                str(argumentos.historico)
            )
        ]
        if da_temporada.empty:
            print(
                f"Nenhum jogo da temporada {argumentos.historico} na tabela.",
                file=sys.stderr,
            )
            return 1
        aprovadas = set(cfg.bruto["ligas_aprovadas_backtest"])
        da_temporada = da_temporada.loc[da_temporada["liga"].isin(aprovadas)]
        # A ultima rodada com jogo: uma data que existiu de verdade.
        hoje = pd.Timestamp(da_temporada["data"].max()).date()
        dias = 1
        print(f"  MODO HISTORICO: rodada de {hoje} (temporada {argumentos.historico})")
        do_dia = da_temporada.loc[
            pd.to_datetime(da_temporada["data"]).dt.date == hoje
        ]
        alvos_hist = [
            JogoAlvo(
                liga=str(linha["liga"]),
                mandante=str(linha["mandante"]),
                visitante=str(linha["visitante"]),
                data=hoje,
                # A temporada vem da tabela, e nao e deduzida da data: a API
                # identifica a temporada pelo ano em que ela COMECOU.
                temporada=str(linha["temporada"]),
            )
            for _, linha in do_dia.iterrows()
        ]
        leitura = jogos_alvo.Leitura(
            jogos=alvos_hist,
            linhas_lidas=len(do_dia),
            ligas_no_arquivo=tuple(sorted(do_dia["liga"].unique())),
            primeira_data=hoje,
            ultima_data=hoje,
        )
    elif argumentos.falso:
        texto = FIXTURES_FALSAS.format(
            d1=hoje.strftime("%d/%m/%Y"), d2=hoje.strftime("%d/%m/%Y")
        )
        leitura = jogos_alvo.ler_detalhado(texto, cfg, hoje=hoje)
    else:
        try:
            leitura = jogos_alvo.baixar(cfg, hoje=hoje)
        except Exception as erro:  # rede, 302, arquivo vazio...
            print(f"\nNao deu para baixar os proximos jogos: {erro}", file=sys.stderr)
            print(
                "O site responde HTTP 302 e exige User-Agent; se a sua rede "
                "filtrar o dominio, use --falso para ver o pipeline rodando.",
                file=sys.stderr,
            )
            return 1

    alvos = leitura.jogos
    if not alvos:
        # ⚠️ Antes isto dizia "nenhum jogo nas ligas aprovadas" e pronto -- uma
        # afirmacao que podia ser FALSA. Com o arquivo trazendo 198 jogos e o
        # leitor descartando todos por causa de um BOM, a mensagem culpava as
        # ligas por um defeito de leitura. Motivo errado manda procurar no
        # lugar errado, e custa mais tempo que erro nenhum.
        print("  Nenhum jogo sobrou. Por que:")
        print(f"  {leitura.por_que_vazio(hoje, dias)}")
        if leitura.linhas_lidas:
            print(
                f"\n  (lidas {leitura.linhas_lidas} linhas; ligas no arquivo: "
                f"{', '.join(leitura.ligas_no_arquivo) or 'nenhuma'})"
            )
        return 0
    times = jogos_alvo.times(alvos)
    print(f"  {len(alvos)} jogos, {len(times)} times alvo.")

    print("2. Desfalques...")
    if argumentos.falso:
        fonte = fontes.FonteFalsa(respostas=_desfalques_falsos(alvos))
        print("  MODO FALSO: os desfalques abaixo sao INVENTADOS.")
    else:
        try:
            fonte = fontes.ApiFutebol.do_ambiente(cfg)
        except fontes.SemChave as erro:
            print(f"\n{erro}", file=sys.stderr)
            return 1
    try:
        desfalques = fonte.desfalques(alvos)
    except fontes.SemCota as erro:
        print(f"\n{erro}", file=sys.stderr)
        return 1
    print(f"  {len(desfalques)} desfalques encontrados.")

    if desfalques and hasattr(fonte, "pesar"):
        print("2b. Buscando estatisticas dos jogadores (peso do desfalque)...")
        tabela_toda = limpeza.carregar(cfg)
        temporada = next(
            (a.temporada for a in alvos if a.temporada), None
        )
        contexto = importancia.contexto_dos_times(tabela_toda, temporada)
        try:
            desfalques = fonte.pesar(desfalques, contexto)
        except fontes.SemCota as erro:
            print(f"  cota acabou no meio: {erro}", file=sys.stderr)

    sem_peso = sum(1 for d in desfalques if d.jogador.peso == 0.0)
    if sem_peso:
        print(
            f"  ATENCAO: {sem_peso} deles estao com peso ZERO (sem estatisticas "
            "do jogador). Eles aparecem na tela mas NAO movem a previsao - "
            "mover seria inventar a informacao que falta."
        )

    print("3. Treinando o modelo com o que se sabe ate hoje...")
    jogos = divisao.separar(limpeza.carregar(cfg), cfg).jogos
    corte = pd.Timestamp(max(a.data for a in alvos)) + pd.Timedelta(days=1)
    candidato = selecao.candidato_oficial(cfg, jogos)
    print(f"  modelo oficial: {candidato.nome}")

    por_liga = {}
    for liga in sorted({a.liga for a in alvos}):
        da_liga = jogos.loc[jogos["liga"] == liga]
        por_liga[liga] = DixonColes(cfg=cfg).treinar(da_liga, ate_data=corte)

    print("4. Previsoes: crua e ajustada...")
    ajustes = {t: ajuste_mod.calcular(t, desfalques, cfg) for t in times}
    mexeram = [a for a in ajustes.values() if a.mexeu]
    print(f"  {len(mexeram)} de {len(times)} times com a forca alterada")
    for a in mexeram:
        print(f"    {a.resumo()}")
    linhas = []
    for alvo in alvos:
        modelo = por_liga[alvo.liga]
        try:
            cru = _prever(modelo, alvo)
        except Exception as erro:
            print(f"  pulado {alvo}: {erro}")
            continue
        ajustado_modelo = ajuste_mod.aplicar(modelo, ajustes)
        ajustada = _prever(ajustado_modelo, alvo)

        linhas.append(
            registro.linha_de_jogo(
                alvo, cru, ajustada, ajustes[alvo.mandante], ajustes[alvo.visitante]
            )
        )
        mudou = abs(ajustada["H"] - cru["H"]) > 1e-9
        marca = " <- ajustado" if mudou else ""
        print(
            f"  {alvo}: mandante {cru['H']:.1%} -> {ajustada['H']:.1%}{marca}"
        )

    if not linhas:
        print("\nNenhuma previsao pode ser feita.")
        return 1

    caminho = registro.anotar(cfg, linhas, falso=demo)
    print(f"\n5. Gravado no caderno: {caminho}")
    print(f"   {len(linhas)} previsoes, com o resultado VAZIO ate os jogos")
    print("   acontecerem. Depois rode --preencher e --avaliar.")

    print()
    print("=" * 70)
    print("ISTO NAO E UMA HIPOTESE VALIDADA.")
    print("Com ~150 jogos, a menor melhora de log loss detectavel e 0,0338,")
    print("e a distancia INTEIRA do modelo para o mercado e 0,0212. Enquanto")
    print("o intervalo de confianca cruzar zero, a resposta e 'ainda nao da")
    print("para saber' -- nem 'funciona', nem 'nao funciona'.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
