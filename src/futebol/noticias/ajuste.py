"""De uma lista de desfalques para um número que o modelo entende.

**A conta, inteira.** Cada desfalque contribui com

    contribuição = peso do jogador × fator do status × confiança da fonte

e as contribuições do mesmo setor se somam. O total é preso no teto do
``config.yaml`` (``noticias.ajuste_maximo``) e vira uma **subtração** na força:

    ataque ajustado = ataque − impacto_ataque
    defesa ajustada = defesa − impacto_defesa

⚠️ **As duas são subtrações, e as duas pioram o time.** No modelo,
``λ = exp(intercepto + ataque_mandante − defesa_visitante + fator_casa)``: a
defesa entra com sinal invertido, então *positivo é defesa boa*. Tirar um
zagueiro é **subtrair** de ``defesa``, o que aumenta os gols que o time sofre.
Somar faria o time melhorar ao perder jogador — e esse erro não daria erro
nenhum, só uma previsão invertida.

**O teto existe porque a soma é ingênua.** Os pesos vêm de frações de minutos,
gols e titularidade, e nada impede que sete desfalques somem mais de 1. Sem
teto, ``exp(ataque − 1,5)`` faria um time virar um amador, o que é uma
afirmação que os dados não sustentam. O teto de 0,25 em log significa "no
máximo, o time vira ``exp(−0,25)`` = 78% do que era" — uma perda grande, e
finita. Quando ele age, o :class:`~futebol.noticias.tipos.Ajuste` diz que agiu,
em vez de truncar em silêncio.

**Por que "volta" existe.** Uma notícia de retorno **cancela** um desfalque
anterior. Sem ela, o cache acumularia lesões e nunca as soltaria: o time iria
piorando a cada rodada para sempre.
"""

from __future__ import annotations

from collections.abc import Iterable

from futebol.config import Config
from futebol.noticias.tipos import Ajuste, Desfalque

#: Quanto cada status pesa. ``volta`` é zero porque ele não é um desfalque:
#: ele **cancela** um, e o cancelamento acontece em :func:`resolver`.
FATOR_DO_STATUS: dict[str, float] = {"fora": 1.0, "duvida": 0.5, "volta": 0.0}


def limites(cfg: Config) -> dict[str, float]:
    """Os dois parâmetros da fase, do ``config.yaml``."""
    secao = cfg.secao("noticias")
    return {
        "peso_duvida": float(secao["peso_duvida"]),
        "ajuste_maximo": float(secao["ajuste_maximo"]),
    }


def resolver(desfalques: Iterable[Desfalque]) -> tuple[Desfalque, ...]:
    """Fica com a informação **mais recente** de cada jogador.

    ⚠️ Sem isto, "Fulano lesionado" de segunda e "Fulano volta" de quinta
    conviveriam, e o jogador contaria como desfalque para sempre. A notícia mais
    nova ganha; empate de data é resolvido pela **maior confiança**, que é a
    forma de a escalação oficial vencer o boato publicado no mesmo dia.

    Desfalques com status ``volta`` saem do resultado: eles cumpriram a função
    de cancelar e não têm mais nada a dizer.
    """

    def chave(d: Desfalque) -> tuple:
        # data ausente perde de qualquer data conhecida
        return (d.data is not None, d.data, d.confianca)

    melhor: dict[tuple[str, str], Desfalque] = {}
    for desfalque in desfalques:
        identidade = (desfalque.jogador.time, desfalque.jogador.nome)
        atual = melhor.get(identidade)
        if atual is None or chave(desfalque) > chave(atual):
            melhor[identidade] = desfalque

    return tuple(d for d in melhor.values() if d.status != "volta")


def _por_setor(desfalque: Desfalque, peso_duvida: float) -> tuple[float, float]:
    """A contribuição de um desfalque para (ataque, defesa).

    Quem é ``"ambos"`` entra **inteiro nos dois lados**, e não metade em cada.
    O peso já mede a fração do time que ele representa; dividi-lo de novo diria
    que perder um volante titular custa menos que perder um lateral titular, o
    que não se sustenta.
    """
    fator = FATOR_DO_STATUS[desfalque.status]
    if desfalque.status == "duvida":
        fator = peso_duvida
    contribuicao = desfalque.jogador.peso * fator * desfalque.confianca

    setor = desfalque.jogador.setor
    ataque = contribuicao if setor in ("ataque", "ambos") else 0.0
    defesa = contribuicao if setor in ("defesa", "ambos") else 0.0
    return ataque, defesa


def calcular(
    time: str, desfalques: Iterable[Desfalque], cfg: Config
) -> Ajuste:
    """O ajuste de um time, a partir dos desfalques dele.

    Args:
        time: a chave do time (``PAIS:nome``).
        desfalques: os dele. Os de outros times são **ignorados**, não é erro —
            quem chama costuma passar a lista da rodada inteira.
        cfg: de onde saem ``peso_duvida`` e ``ajuste_maximo``.
    """
    valores = limites(cfg)
    teto = valores["ajuste_maximo"]

    do_time = [d for d in resolver(desfalques) if d.jogador.time == time]
    if not do_time:
        return Ajuste(time=time)

    ataque = defesa = 0.0
    for desfalque in do_time:
        parte_ataque, parte_defesa = _por_setor(desfalque, valores["peso_duvida"])
        ataque += parte_ataque
        defesa += parte_defesa

    truncado = ataque > teto or defesa > teto
    return Ajuste(
        time=time,
        ataque=min(ataque, teto),
        defesa=min(defesa, teto),
        desfalques=tuple(do_time),
        truncado=truncado,
    )


def aplicar(modelo, ajustes: dict[str, Ajuste]):
    """Devolve uma cópia do modelo com as forças reduzidas.

    ⚠️ **Cópia, nunca no lugar.** O projeto precisa das duas previsões — a crua
    e a ajustada — para poder comparar, e mexer no modelo original apagaria a
    primeira. Um ajuste que destrói a referência dele mesmo não é avaliável.

    Args:
        modelo: um modelo já treinado, com ``.ajustes`` por liga.
        ajustes: ``{time: Ajuste}``.

    Retorna:
        Um modelo novo, com as mesmas previsões para quem não tem desfalque.
    """
    import copy
    from dataclasses import replace

    copia = copy.deepcopy(modelo)
    for ajuste_da_liga in copia.ajustes.values():
        forcas = ajuste_da_liga.forcas
        for time, ajuste in ajustes.items():
            if time not in forcas or not ajuste.mexeu:
                continue
            forca = forcas[time]
            forcas[time] = replace(
                forca,
                ataque=forca.ataque - ajuste.ataque,
                defesa=forca.defesa - ajuste.defesa,
            )
    return copia
