"""Ler notícia e devolver JSON. O único lugar do projeto onde um LLM entra.

⚠️ **E vale dizer com todas as letras o que ele faz e o que ele não faz.**

O LLM **lê texto** e devolve campos estruturados: quem está fora, por quê, com
que confiança. Ele **não calcula probabilidade**, não opina sobre o jogo, não
escolhe aposta e não encosta em nenhum número que vá para o modelo. A
probabilidade continua saindo do Dixon-Coles, que é uma conta fechada e
auditável.

Essa fronteira não é preciosismo. Um LLM não tem como estimar a chance de um
time ganhar melhor que um modelo ajustado em cem mil jogos, e pedir isso a ele
produziria um número confiante, plausível e sem origem — exatamente o tipo de
número que este projeto inteiro foi construído para não produzir. Extrair
"Fulano está fora por lesão na coxa, segundo o ge.globo" de um parágrafo de
texto é, ao contrário, o que ele faz melhor que qualquer regex.

**Como a saída é garantida.** Não por pedir "responda só JSON" no prompt e
torcer: por ``output_config.format`` com JSON Schema, que faz a API garantir o
formato. Pedir educadamente funciona quase sempre, e "quase sempre" num
pipeline que roda sozinho toda semana significa quebrar numa quinta-feira
qualquer.

**A confiança vem do LLM e é usada como peso.** Uma notícia dizendo "Fulano
deve desfalcar" não pode valer o mesmo que a escalação oficial — é
:data:`~futebol.noticias.fontes.CONFIANCA_DA_API` contra o que o extrator
estimou. O valor entra multiplicando o ajuste, em
:func:`futebol.noticias.ajuste.calcular`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from futebol.config import Config
from futebol.noticias import importancia
from futebol.noticias.tipos import Desfalque

#: O modelo usado na extração. Fica no ``config.yaml`` para o Enzo poder trocar
#: por um mais barato sem mexer em código — a tarefa é leitura de texto curto, e
#: um modelo menor dá conta. O padrão é o mais capaz.
MODELO_PADRAO = "claude-opus-5"

#: O esquema da resposta. É ele que a API **garante** — não o prompt.
ESQUEMA: dict = {
    "type": "object",
    "properties": {
        "desfalques": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "jogador": {"type": "string"},
                    "time": {"type": "string"},
                    "status": {"type": "string", "enum": ["fora", "duvida", "volta"]},
                    "motivo": {"type": "string"},
                    "posicao": {"type": "string"},
                    "confianca": {"type": "number"},
                },
                "required": [
                    "jogador",
                    "time",
                    "status",
                    "motivo",
                    "posicao",
                    "confianca",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["desfalques"],
    "additionalProperties": False,
}

INSTRUCAO = """\
Você lê notícias de futebol e extrai APENAS informação sobre jogadores que vão \
ou não vão jogar. Nada mais.

Regras:
- devolva um item por jogador citado como fora, em dúvida ou retornando;
- `status`: "fora" (lesão, suspensão, corte confirmado), "duvida" \
(questionável, "deve desfalcar", "não treinou"), "volta" (estava fora e \
retorna);
- `time`: o nome do clube como aparece no texto, sem inventar;
- `posicao`: goleiro, zagueiro, lateral, meio-campo ou atacante, se o texto \
disser. Se não disser, string vazia — NÃO adivinhe pela fama do jogador;
- `confianca`: de 0 a 1, quanto o próprio texto é firme. Escalação oficial ou \
confirmação do clube ≈ 0,9; "deve ficar fora", "segundo apurou a reportagem" \
≈ 0,5; boato, especulação ou "pode ser que" ≈ 0,2;
- notícia sem informação de desfalque devolve lista vazia. **Isso é o caso \
comum e é uma resposta correta** — não force um item para preencher.

Você NÃO opina sobre o resultado do jogo, NÃO estima probabilidade e NÃO \
sugere aposta. Só extrai o que está escrito."""


class SemChaveDaAnthropic(Exception):
    """Falta ``ANTHROPIC_API_KEY`` no ``.env``."""


@dataclass(frozen=True)
class Noticia:
    """Um texto a ser lido, e de onde ele veio."""

    titulo: str
    texto: str
    fonte: str
    data: date | None = None

    def como_prompt(self) -> str:
        return f"Título: {self.titulo}\n\nTexto: {self.texto}"


@dataclass
class ExtratorFalso:
    """Devolve o que você mandar. É com ele que os testes rodam.

    A especificação exige testes com notícias **falsas**; além disso, cada
    chamada de verdade custa dinheiro, e um teste que gasta dinheiro a cada
    execução é um teste que as pessoas param de rodar.
    """

    respostas: dict[str, list[dict]] = field(default_factory=dict)
    chamadas: int = field(init=False, default=0)

    def extrair(self, noticias: Iterable[Noticia]) -> list[Desfalque]:
        achados = []
        for noticia in noticias:
            self.chamadas += 1
            for bruto in self.respostas.get(noticia.titulo, []):
                convertido = converter(bruto, noticia)
                if convertido is not None:
                    achados.append(convertido)
        return achados


@dataclass
class Extrator:
    """O extrator de verdade, com a API da Anthropic.

    ⚠️ **Nunca executou contra a API neste ambiente** — não há chave aqui. A
    chamada segue a documentação oficial (``output_config.format`` com JSON
    Schema) e a conversão tolera campo faltando, mas a primeira execução de
    verdade é a primeira prova.
    """

    modelo: str = MODELO_PADRAO
    max_tokens: int = 4096
    chamadas: int = field(init=False, default=0)

    @classmethod
    def do_ambiente(cls, cfg: Config) -> Extrator:
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise SemChaveDaAnthropic(
                "Falta ANTHROPIC_API_KEY. Crie uma chave em "
                "console.anthropic.com, e:\n\n"
                "    Copy-Item .env.exemplo .env\n"
                "    # abra o .env e preencha ANTHROPIC_API_KEY=...\n\n"
                "Enquanto isso, `python scripts/desfalques.py --falso` mostra o "
                "pipeline rodando sem chamar a API."
            )
        secao = cfg.secao("noticias")
        return cls(modelo=str(secao.get("modelo_extracao", MODELO_PADRAO)))

    def extrair(self, noticias: Iterable[Noticia]) -> list[Desfalque]:
        """Uma chamada por notícia; devolve os desfalques de todas."""
        import anthropic

        cliente = anthropic.Anthropic()
        achados: list[Desfalque] = []

        for noticia in noticias:
            self.chamadas += 1
            resposta = cliente.messages.create(
                model=self.modelo,
                max_tokens=self.max_tokens,
                system=INSTRUCAO,
                messages=[{"role": "user", "content": noticia.como_prompt()}],
                # É isto — e não um pedido no prompt — que garante o formato.
                output_config={"format": {"type": "json_schema", "schema": ESQUEMA}},
            )
            achados.extend(self._converter_resposta(resposta, noticia))
        return achados

    @staticmethod
    def _converter_resposta(resposta, noticia: Noticia) -> list[Desfalque]:
        # `stop_reason` é conferido antes de `content`: numa recusa o conteúdo
        # pode não existir, e tratar isso como "nenhum desfalque" faria uma
        # falha virar silêncio.
        if getattr(resposta, "stop_reason", None) == "refusal":
            return []
        texto = next(
            (b.text for b in resposta.content if getattr(b, "type", "") == "text"), ""
        )
        if not texto:
            return []
        try:
            dados = json.loads(texto)
        except json.JSONDecodeError:
            return []
        convertidos = (
            converter(bruto, noticia) for bruto in dados.get("desfalques", [])
        )
        return [d for d in convertidos if d is not None]


def converter(bruto: dict, noticia: Noticia) -> Desfalque | None:
    """Do JSON do extrator para :class:`Desfalque`.

    Retorna ``None`` quando o item não dá para aproveitar — sem nome de jogador
    ou sem time, por exemplo. Descartar é melhor que completar: um desfalque com
    o time chutado é pior que nenhum desfalque (regra 14).

    ⚠️ O ``peso`` sai **zero** daqui. Quem dá peso é
    :mod:`futebol.noticias.importancia`, com as estatísticas do jogador. O LLM
    não tem como saber quanto um jogador vale para o time, e deixá-lo estimar
    seria exatamente a fronteira que este módulo existe para não cruzar.
    """
    nome = str(bruto.get("jogador") or "").strip()
    time = str(bruto.get("time") or "").strip()
    if not nome or not time:
        return None

    status = str(bruto.get("status") or "").strip().lower()
    if status not in ("fora", "duvida", "volta"):
        return None

    try:
        confianca = float(bruto.get("confianca", 0.5))
    except (TypeError, ValueError):
        confianca = 0.5

    return Desfalque(
        jogador=importancia.sem_estatisticas(
            nome, time, str(bruto.get("posicao") or "")
        ),
        status=status,
        motivo=str(bruto.get("motivo") or "").strip(),
        confianca=max(0.0, min(1.0, confianca)),
        fonte=noticia.fonte,
        data=noticia.data,
    )
