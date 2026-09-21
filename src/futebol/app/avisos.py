"""Os avisos obrigatórios do app, num lugar só.

⚠️ **Este módulo é a parte mais importante da Fase 8, e não é código de
interface: é a espinha honesta do projeto.**

Até aqui, tudo o que o projeto mediu morava em relatórios — e quem lia um
relatório lia também a seção de limitações. O app quebra isso: ele é a primeira
entrega que alguém pode **usar sem ler nada**. Uma tela que mostra "68% de chance
de vitória do mandante" e "valor esperado +7%" é, sem contexto, uma recomendação
de aposta — e as Fases 6 e 7 mediram que ela seria uma recomendação ruim.

Então os avisos ficam aqui, como constantes nomeadas, por três motivos:

1. **para serem testáveis.** Há um teste que exige que cada página que mostra
   probabilidade importe o aviso que lhe corresponde. Um aviso apagado numa
   reescrita derruba o ``pytest``, em vez de sumir calado;
2. **para ficarem consistentes.** O mesmo número não pode aparecer como −12,9%
   numa tela e −13% em outra;
3. **para serem fáceis de auditar.** Quem quiser conferir se o app esconde algo
   lê este arquivo, e não sete páginas de interface.

Todo número citado aqui vem de um relatório medido, e o atributo ``origem`` diz
de qual. Nada é estimado.
"""

from __future__ import annotations

from dataclasses import dataclass

from futebol import relatorio

#: ROI de aposta simples medido na Fase 6 (21.682 apostas, EV > 5%).
ROI_FASE_6 = -0.1292

#: CLV médio medido na Fase 6 — o critério primário do projeto.
CLV_FASE_6 = -0.0782

#: ROI de apostar ao acaso entre as mesmas candidatas (Fase 6). É a régua: o
#: modelo perde **mais** que o chute.
ROI_ALEATORIO_FASE_6 = -0.0688

#: Quanto o modelo oficial fica atrás do mercado em log loss (Fase 4).
DISTANCIA_DO_MERCADO = 0.0226

#: Quanto o modelo exagera a chance de **cada** seleção (Fase 7). Numa múltipla
#: de ``n`` pernas, o exagero vira ``1 − 0,959ⁿ``.
RAZAO_POR_SELECAO = 0.959


@dataclass(frozen=True)
class Aviso:
    """Um aviso que o app é obrigado a mostrar.

    Atributos:
        titulo: a linha em negrito.
        texto: o corpo, já em Markdown.
        origem: onde o número foi medido. Serve para o leitor conferir, e para
            impedir que alguém escreva um aviso com número inventado.
    """

    titulo: str
    texto: str
    origem: str

    def como_markdown(self) -> str:
        return f"**{self.titulo}**\n\n{self.texto}\n\n*{self.origem}*"


#: Exibido na página inicial e no rodapé de toda página de aposta (seção 9 da
#: especificação).
JOGO_RESPONSAVEL = Aviso(
    titulo="Jogo responsável",
    texto=(
        "Apostas envolvem risco real de perda. Este projeto é **educacional** e "
        "não é recomendação de aposta. Quem sentir que perdeu o controle pode "
        "procurar apoio: [Jogadores Anônimos](https://jogadoresanonimos.com.br) "
        "ou o **CVV — 188** (ligação gratuita, 24 horas)."
    ),
    origem="Seção 9 da especificação do projeto.",
)

#: O aviso que acompanha toda probabilidade mostrada pelo modelo.
MODELO_PERDE_DO_MERCADO = Aviso(
    titulo="Este modelo perde do mercado",
    texto=(
        "Medido no walk-forward de validação, o modelo fica "
        f"**{relatorio.num(DISTANCIA_DO_MERCADO)} de log loss atrás** das odds de "
        "fechamento. Ou seja: quando o modelo e o mercado discordam, o mercado "
        "costuma estar mais certo. As probabilidades abaixo são o que o modelo "
        "pensa — não o que vai acontecer."
    ),
    origem="Fase 4 — docs/relatorios/fase4.md",
)

#: ⚠️ O aviso mais importante do app inteiro. Sem ele, a tela de comparar odds
#: vira uma máquina de sugerir apostas ruins.
EV_POSITIVO_NAO_E_OPORTUNIDADE = Aviso(
    titulo="Valor esperado positivo não quer dizer aposta boa",
    texto=(
        "O projeto testou exatamente esta estratégia em **21.682 apostas** e ela "
        f"perdeu **{relatorio.pct(abs(ROI_FASE_6))}**. Apostar **ao acaso** entre "
        "as mesmas oportunidades teria perdido menos: "
        f"{relatorio.pct(abs(ROI_ALEATORIO_FASE_6))}.\n\n"
        "O motivo: como `EV = probabilidade × odd − 1` é multiplicativo na odd, "
        "um mesmo erro do modelo produz EV alto no azarão e quase nada no "
        "favorito — e o azarão é justamente onde a casa cobra a maior comissão "
        "(2% em odd 1,5, mais de 21% acima de odd 10). O filtro de EV não "
        "seleciona onde o modelo sabe mais: seleciona **onde ele erra para "
        "cima**."
    ),
    origem="Fase 6 — docs/relatorios/fase6.md",
)

#: Exigido pela seção 7.1 da especificação: acompanha **toda** chance de ganhar
#: de uma múltipla, na tela e no relatório.
INDEPENDENCIA = Aviso(
    titulo="A chance de ganhar supõe jogos independentes",
    texto=(
        "A chance mostrada é o produto das chances de cada seleção, o que supõe "
        "que o resultado de um jogo não diz nada sobre os outros. A chance real "
        "tende a ser um pouco menor, principalmente em bilhetes grandes.\n\n"
        "O projeto mediu o tamanho desse erro em 36.211 bilhetes: ele **não é "
        "detectável** em bilhetes de 2 a 4 seleções, e de 6 em diante a amostra "
        "não alcança. Ou seja — em bilhete pequeno, medimos que não há; em "
        "bilhete grande, não conseguimos medir."
    ),
    origem="Fase 7 — docs/relatorios/fase7.md",
)

#: O segundo aviso das múltiplas, que a Fase 7 tornou obrigatório.
EXAGERO_POR_SELECAO = Aviso(
    titulo="E a chance mostrada é do modelo, que exagera",
    texto=(
        "O modelo exagera a chance de **cada seleção** em cerca de "
        f"**{relatorio.pct(1 - RAZAO_POR_SELECAO)}**. Numa múltipla esse errinho é "
        "elevado à potência do número de jogos: vira "
        f"{relatorio.pct(1 - RAZAO_POR_SELECAO**2)} num bilhete de dois e "
        f"**{relatorio.pct(1 - RAZAO_POR_SELECAO**8)} num de oito**. A chance real "
        "de ganhar é menor que a escrita, e a diferença cresce com o tamanho do "
        "bilhete."
    ),
    origem="Fase 7 — docs/relatorios/fase7.md",
)

#: A odd justa é 1/probabilidade, sem margem. Ela não é uma odd que exista.
ODD_JUSTA = Aviso(
    titulo="A odd justa não é uma odd que você vá encontrar",
    texto=(
        "Ela é simplesmente `1 ÷ probabilidade`, **sem a comissão da casa**. "
        "Nenhuma casa oferece isso — a diferença entre a odd justa e a odd "
        "oferecida é exatamente como elas ganham dinheiro."
    ),
    origem="Fase 2 — docs/relatorios/fase2.md",
)

#: Acompanha a página de backtest, onde é fácil confundir sorte com vantagem.
AMOSTRA_E_INTERVALO = Aviso(
    titulo="Olhe o intervalo, não o número",
    texto=(
        "Um ROI sozinho não quer dizer nada. Com poucas apostas, qualquer "
        "resultado cabe no acaso: o projeto mediu que seriam necessárias **mais "
        "de 22 mil apostas** para confirmar um ROI verdadeiro de +2%. Por isso "
        "toda tela deste app mostra o intervalo de confiança e o número de "
        "apostas ao lado do resultado."
    ),
    origem="Fase 6 — docs/relatorios/fase6.md",
)

#: O cash out, resumido na identidade que a Fase 7 demonstrou.
CASH_OUT_COBRA_SEMPRE = Aviso(
    titulo="O cash out cobra a mesma taxa em qualquer momento",
    texto=(
        "O valor esperado de sacar é o de **não** sacar multiplicado por "
        "`(1 − taxa)`, e isso não depende de quando você aperta o botão: sacar "
        "depois de um acerto ou depois de nove dá a mesma conta. O que muda é "
        "só o tamanho do susto."
    ),
    origem="Fase 7 — docs/relatorios/fase7.md",
)

#: Todos os avisos, para o teste que confere que nenhum ficou órfão.
TODOS: tuple[Aviso, ...] = (
    JOGO_RESPONSAVEL,
    MODELO_PERDE_DO_MERCADO,
    EV_POSITIVO_NAO_E_OPORTUNIDADE,
    INDEPENDENCIA,
    EXAGERO_POR_SELECAO,
    ODD_JUSTA,
    AMOSTRA_E_INTERVALO,
    CASH_OUT_COBRA_SEMPRE,
)


def exagero_da_multipla(tamanho: int) -> float:
    """Quanto o modelo exagera a chance de um bilhete de ``tamanho`` seleções.

    É o erro por perna elevado à potência do bilhete — a conta que a Fase 7
    mediu e que o app precisa mostrar junto de cada chance de ganhar.
    """
    return 1.0 - RAZAO_POR_SELECAO**tamanho
