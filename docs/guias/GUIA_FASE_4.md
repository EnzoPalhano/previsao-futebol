# Guia da Fase 4 — A hora da verdade

> **Para quem é este guia:** para alguém que nunca programou. Cada comando está
> explicado, junto com o que deve aparecer na tela. Os comandos são para o
> **PowerShell do Windows**; no fim há a versão Mac/Linux.

**O que a Fase 4 faz:** ela responde a pergunta que a Fase 3 deixou em aberto —
*os modelos prestam?* E responde do jeito difícil, que é o único que vale:
simulando o que teria acontecido se você tivesse usado o modelo **naquela época,
com o que se sabia naquele dia**.

É também a fase que **escolhe** o modelo e os parâmetros do projeto. Até aqui o
`config.yaml` tinha a palavra `PROVISORIO` ao lado de dois números. Depois desta
fase, não tem mais.

**Tempo estimado:** a primeira medição demora de 30 a 60 minutos (é muita
conta). Depois disso, tudo é instantâneo, porque o resultado fica guardado.

---

## Índice

1. [A ideia: walk-forward](#1-a-ideia-walk-forward)
2. [Rodar a validação](#2-rodar-a-validação)
3. [O relatório e os gráficos](#3-o-relatório-e-os-gráficos)
4. [Os resultados](#4-os-resultados)
5. [O que foi escolhido, e por quê](#5-o-que-foi-escolhido-e-por-quê)
6. [Três ideias que valem o parágrafo](#6-três-ideias-que-valem-o-parágrafo)
7. [Erros comuns](#7-erros-comuns)
8. [Como saber que está tudo certo](#8-como-saber-que-está-tudo-certo)

---

## 1. A ideia: walk-forward

Imagine que você quer saber se um modelo de previsão presta. A tentação é
treiná-lo com tudo o que existe e ver se ele "acerta" os jogos. Isso não mede
nada: o modelo já viu esses jogos, é como aplicar uma prova com a resposta no
verso da folha.

O jeito honesto tem nome: **walk-forward**. É assim:

```
  jogos até sexta ───► treina o modelo ───► prevê os jogos de sábado
  jogos até sábado ──► treina de novo ────► prevê os jogos de domingo
  jogos até domingo ─► treina de novo ────► prevê os jogos de terça
  ...e assim por diante, por três temporadas
```

Em nenhum momento o modelo vê o jogo que está prevendo, nem qualquer jogo
posterior a ele. É exatamente a situação de quem vai apostar: você só tem o
passado.

O preço disso é computação. São **mais de dez mil treinos por configuração
testada** — um para cada data em que cada uma das 38 competições jogou. É por
isso que esta fase demora.

---

## 2. Rodar a validação

```powershell
cd C:\Users\Usuario\Documents\Jogos_Probabilidade
.venv\Scripts\Activate.ps1
python scripts/validar.py
```

O script mostra as 13 configurações que vão disputar, e depois vai medindo uma a
uma:

```
89455 jogos liberados; 27059 trancados até a Fase 9
Janela de validacao: 2021-07-01 a 2024-06-03

13 configuracao(oes) a medir:
  baseline         histórico de placares da liga; ignora quem joga
  poisson          ataque, defesa e fator casa por liga, sem decaimento
  dixon-coles      Poisson + placares baixos + decaimento (xi=0.0018)
  ...

  baseline: medindo (walk-forward, alguns minutos)...
    36446 jogos previstos em 38 competições, com 11054 ajustes de modelo
```

**Pode ir tomar um café.** Na primeira vez são 30 a 60 minutos. Cada
configuração medida é guardada em `data/processed/validacao/`, então rodar de
novo é instantâneo — o script diz `lido do cache`.

⚠️ A primeira linha é a mais importante: **27.059 jogos ficam trancados**. São
as duas temporadas mais recentes, reservadas para a Fase 9. Elas serão abertas
uma única vez, no fim do projeto, e nada até lá pode olhá-las — nem para
espiar.

---

## 3. O relatório e os gráficos

```powershell
python scripts/relatorio_fase4.py
```

Isso lê o que já foi medido e escreve três arquivos em `docs/relatorios/`:

| Arquivo | O que é |
|---|---|
| `fase4.md` | o relatório da fase |
| `fase4_calibracao.png` | a curva de calibração dos modelos e do mercado |
| `fase4_distancia_do_mercado.png` | quanto o modelo perde do mercado, liga por liga |

---

## 4. Os resultados

<!--NUMEROS-->

---

## 5. O que foi escolhido, e por quê

<!--ESCOLHA-->

---

## 6. Três ideias que valem o parágrafo

### Log loss, e por que não "quantos por cento o modelo acerta"

A acurácia — a porcentagem de acertos — é a métrica mais intuitiva e uma das
piores para este projeto. Três motivos:

1. **ela ignora a confiança.** Dizer "95% de chance do Arsenal" e o Arsenal
   perder conta igual a dizer "34%" e o Arsenal perder. Para quem aposta, esses
   dois erros custam valores completamente diferentes;
2. **ela ignora o empate.** O empate quase nunca é o resultado *mais provável*
   de um jogo — fica em torno de 26%. Um modelo que nunca aponta empate pode ter
   acurácia alta e ser inútil;
3. **ela depende da liga.** Onde o mandante ganha 48% das vezes, apontar sempre
   o mandante já dá 48% de acerto, sem modelo nenhum.

A **log loss** conserta os três: ela olha a probabilidade que o modelo deu ao
resultado que realmente aconteceu, e pune com força quem erra com confiança. É
a métrica oficial do projeto (regra 9), e a acurácia aparece no relatório só
como tradução para quem está começando.

### Calibração: "quando eu digo 60%, acontece 60%?"

É o que o gráfico `fase4_calibracao.png` mostra. A linha tracejada é a
calibração perfeita. Um ponto abaixo dela significa que o modelo prometeu mais
do que entregou — confiança demais.

⚠️ **Calibração não é conhecimento.** Um modelo que responde sempre a média da
liga ("44%, 26%, 30%") fica quase perfeito nesse gráfico e não sabe nada sobre
jogo nenhum. Ela importa por outro motivo, e é um motivo prático: na Fase 6, a
decisão de apostar vai ser tomada comparando a probabilidade do modelo com a odd
da casa. Se a probabilidade do modelo for inflada, o projeto vai "encontrar
valor" onde não existe valor nenhum.

### Por que não escolher o modelo pelo lucro

Essa é a regra 9, e é a regra que mais protege o projeto.

O lucro de um backtest se apoia em algumas centenas de apostas, cada uma valendo
0 ou 1. Nesse tamanho de amostra, a diferença entre um modelo **bom** e um
modelo **sortudo** não aparece — as duas coisas produzem curvas de lucro
parecidas. Já a log loss usa todas as 36 mil partidas e a probabilidade inteira,
não só o que deu certo.

Escolher por lucro é, na prática, escolher o modelo que teve mais sorte no
passado. E sorte não se repete.

---

## 7. Erros comuns

### "data\processed\jogos.parquet não existe ainda"

Falta montar a tabela de jogos: `python scripts/preparar_dados.py`.

### O `validar.py` parece travado

Ele não está: cada configuração leva alguns minutos e o script só imprime
quando termina uma. Se quiser acompanhar de perto, meça uma só:

```powershell
python scripts/validar.py --so-um dixon-coles
```

### Quero refazer a medição do zero

O resultado fica guardado em `data/processed/validacao/`. Para ignorar o que
está lá:

```powershell
python scripts/validar.py --forcar
```

Isso é necessário quando o código do modelo muda — senão você compara o modelo
novo com números do modelo velho.

### Os acentos aparecem errados no PowerShell

Não afeta os arquivos gravados. Se incomodar, rode `chcp 65001` antes.

---

## 8. Como saber que está tudo certo

- [ ] `python scripts/validar.py` termina mostrando a tabela e a linha
      `ESCOLHIDO (regra 9, ...)`
- [ ] no relatório, a ordem é: baseline pior que Poisson, Poisson pior que
      Dixon-Coles, e o **mercado melhor que todos**
- [ ] `docs/relatorios/fase4.md` existe, junto com os dois `.png`
- [ ] o `config.yaml` não tem mais a palavra `PROVISORIO`
- [ ] `pytest` mostra **363 passed** (ou 362 passed + 1 skipped, se a sua rede
      bloquear o site da fonte — o teste de rede vira *skip*, e isso é esperado)
- [ ] `ruff check .` mostra **All checks passed!**
- [ ] `git tag` mostra `fase-4`

Se todos estiverem marcados, **a Fase 4 está concluída**.

---

## O que foi criado nesta fase

| Arquivo | Para que serve |
|---|---|
| `src/futebol/avaliacao/validacao.py` | O walk-forward e a trava contra vazamento |
| `src/futebol/avaliacao/selecao.py` | As 13 configurações candidatas e a escolha |
| `src/futebol/avaliacao/graficos.py` | Os dois gráficos da fase |
| `src/futebol/avaliacao/relatorio_fase4.py` | Monta o relatório a partir do medido |
| `scripts/validar.py` | Roda a validação (a parte demorada) |
| `scripts/relatorio_fase4.py` | Escreve o relatório e os gráficos |
| `docs/relatorios/fase4.md` | O relatório |

### Versão Mac/Linux dos comandos

```bash
source .venv/bin/activate
python scripts/validar.py
python scripts/relatorio_fase4.py
pytest
```

---

## Próximo passo

A **Fase 5** tenta bater o Dixon-Coles com *machine learning*. O modelo de agora
só sabe uma coisa: quantos gols cada time fez e tomou. A Fase 5 monta *features* —
números que descrevem o jogo antes de ele acontecer — e entrega tudo a um
LightGBM:

1. **rating Elo** de cada time, atualizado jogo a jogo, e a diferença entre os dois;
2. **médias móveis** de gols feitos e sofridos (últimos 5 e 10 jogos), separando
   casa e fora, e pontos nos últimos 5 jogos;
3. **dias de descanso** desde o jogo anterior de cada time;
4. **as próprias probabilidades do Dixon-Coles** como entrada — assim o ML só
   precisa descobrir o que sobra depois do que o modelo de gols já explica;
5. **marcação da temporada de estádio vazio** (2020/21), em que o fator casa caiu.

Toda feature é calculada **só com jogos anteriores** ao jogo previsto (regra 6), e a
medição é o mesmo walk-forward desta fase — mesma janela, mesmas rodadas, mesmo
critério de log loss (regra 9). Se o LightGBM não ganhar do Dixon-Coles nessa
medição, ele não entra: a tabela da Fase 4 ganha mais uma linha e o campeão
continua sendo quem é.

**Me avise quando quiser começar a Fase 5.**
