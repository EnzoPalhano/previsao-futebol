# Fase 2 — O mercado medido

- Camada de ligas: **camada_tudo**
- Jogos analisados: **116.514**
- Grupo 1 — backtest e CLV (22): B1, D1, D2, E0, E1, E2, E3, EC, F1, F2, G1, I1, I2, N1, P1, SC0, SC1, SC2, SC3, SP1, SP2, T1
- Grupo 2 — treino e calibração (16): ARG, AUT, BRA, CHN, DNK, FIN, IRL, JPN, MEX, NOR, POL, ROU, RUS, SWE, SWZ, USA
- Gerado em: 2026-09-16

> **Regra 13.** Cada tabela diz a quais ligas se refere. Onde estiver
> escrito *Grupo 1*, o número **não** inclui Brasil, Argentina, EUA e os
> outros 13 países do Grupo 2 — eles não têm odd pré-jogo (regra 12).

## 1. Tirar a margem é uma escolha — e ela muda o número

Odd não é probabilidade: é probabilidade **mais a comissão da casa**.
Some as três implícitas de um jogo e dá 104%, 107%. Tirar esses pontos
a mais exige uma hipótese sobre *como* a casa distribuiu a comissão, e
os três métodos discordam de propósito:

- **proporcional**: a casa cobrou a mesma fatia de todos;
- **power** e **shin**: o azarão paga comissão maior que o favorito.

Medido no 1X2 de fechamento do Grupo 1:

| Método | Log loss | Brier | ECE |
|---|---|---|---|
| proporcional | 0,9990 | 0,5970 | 0,0080 |
| power | 0,9984 | 0,5967 | 0,0023 |
| shin | 0,9985 | 0,5968 | 0,0035 |

O **power** fica mais bem calibrado: ECE de 0,0023 contra
0,0080 do proporcional — erro de calibração
3,4 vezes menor, com log loss praticamente igual. É a
evidência de que a casa **de fato** cobra mais caro no azarão, e é por
isso que o resto do projeto usa `power`.

## 2. O baseline do mercado — a meta que os modelos precisam bater

Esta é a nota que as odds tiram sozinhas, sem modelo nenhum. Um modelo
da Fase 3 só é útil se conseguir um número **menor** que este.

Referências para ler a tabela: chutar 33% para cada dá log loss
**1,0986**. O mercado de fechamento do Grupo 1 inteiro dá **0,9984**.

| Liga | Formato | Jogos | Log loss pré | Log loss fech. | Brier fech. |
|---|---|---|---|---|---|
| P1 | A | 2.142 | 0,9230 | 0,9196 | 0,5430 |
| N1 | A | 2.068 | 0,9352 | 0,9292 | 0,5499 |
| SC0 | A | 1.547 | 0,9329 | 0,9303 | 0,5497 |
| G1 | A | 1.669 | 0,9452 | 0,9374 | 0,5563 |
| I1 | A | 2.660 | 0,9640 | 0,9617 | 0,5715 |
| E0 | A | 2.660 | 0,9680 | 0,9640 | 0,5718 |
| SP1 | A | 2.660 | 0,9704 | 0,9686 | 0,5757 |
| D1 | A | 2.142 | 0,9765 | 0,9744 | 0,5788 |
| T1 | A | 2.476 | 0,9804 | 0,9747 | 0,5794 |
| B1 | A | 2.085 | 0,9884 | 0,9810 | 0,5838 |
| F1 | A | 2.337 | 0,9866 | 0,9848 | 0,5872 |
| SC2 | A | 1.149 | 1,0032 | 1,0030 | 0,6002 |
| E2 | A | 3.712 | 1,0155 | 1,0120 | 0,6057 |
| EC | A | 3.642 | 1,0161 | 1,0134 | 0,6070 |
| SC3 | A | 1.147 | 1,0331 | 1,0280 | 0,6173 |
| E1 | A | 3.864 | 1,0384 | 1,0372 | 0,6237 |
| SP2 | A | 3.234 | 1,0407 | 1,0379 | 0,6245 |
| F2 | A | 2.410 | 1,0442 | 1,0385 | 0,6241 |
| I2 | A | 2.660 | 1,0475 | 1,0411 | 0,6266 |
| D2 | A | 2.142 | 1,0418 | 1,0416 | 0,6270 |
| SC1 | A | 1.172 | 1,0517 | 1,0459 | 0,6299 |
| E3 | A | 3.752 | 1,0503 | 1,0477 | 0,6314 |

⚠️ **A tabela sai separada por formato** porque até 2018/19 (formato B)
a odd de fechamento é da Pinnacle, e não a média do mercado — as duas
não são a mesma medida.

O fechamento é sempre melhor que o pré-jogo. Isso é o mercado
aprendendo: entre a abertura e o apito entram dinheiro e informação
(escalação, lesão, clima). É também a razão de o CLV existir como
critério — bater a odd de fechamento é evidência de ter acertado antes
do mercado.

No Grupo 2 (63.184 jogos, só fechamento de 1X2), o
baseline é **1,0053** de log loss.
Esses jogos servem para treinar e para medir calibração — nunca para
backtest de aposta (regra 12).

## 3. Quanto a casa cobra, liga a liga

*Resposta à pergunta 1: qual é a margem média da casa em cada liga?*

O número é o **overround**: a soma das probabilidades implícitas menos
1. Quanto menor, melhor para quem aposta. A tabela abaixo atualiza a da
seção 4.3 da especificação, que usou só a temporada 2024/25 no Grupo 1 —
aqui estão **todas** as temporadas.

| Liga | Grupo | Jogos | Margem média | Margem mediana |
|---|---|---|---|---|
| E0 | 1 | 2.660 | 4,27% | 4,09% |
| SP1 | 1 | 2.660 | 4,75% | 4,58% |
| D1 | 1 | 2.142 | 4,76% | 4,58% |
| I1 | 1 | 2.660 | 4,87% | 4,71% |
| F1 | 1 | 2.337 | 5,02% | 4,90% |
| E1 | 1 | 3.864 | 5,41% | 5,28% |
| N1 | 1 | 2.068 | 5,72% | 5,58% |
| P1 | 1 | 2.142 | 6,15% | 5,93% |
| SC0 | 1 | 1.547 | 6,21% | 6,09% |
| B1 | 1 | 2.085 | 6,30% | 6,16% |
| D2 | 1 | 2.142 | 6,34% | 6,13% |
| T1 | 1 | 2.447 | 6,50% | 6,35% |
| SWE | 2 | 3.551 | 6,51% | 6,24% |
| DNK | 2 | 3.000 | 6,51% | 6,32% |
| E2 | 1 | 3.712 | 6,56% | 6,49% |
| USA | 2 | 6.187 | 6,58% | 6,35% |
| RUS | 2 | 3.334 | 6,59% | 6,59% |
| NOR | 2 | 3.542 | 6,63% | 6,44% |
| E3 | 1 | 3.752 | 6,73% | 6,65% |
| BRA | 2 | 5.585 | 6,79% | 6,75% |
| AUT | 2 | 2.674 | 6,87% | 6,75% |
| I2 | 1 | 2.657 | 6,97% | 6,76% |
| F2 | 1 | 2.410 | 7,01% | 6,82% |
| SP2 | 1 | 3.234 | 7,03% | 6,77% |
| JPN | 2 | 4.593 | 7,06% | 6,95% |
| ARG | 2 | 6.370 | 7,08% | 7,15% |
| SWZ | 2 | 2.719 | 7,10% | 6,95% |
| POL | 2 | 4.149 | 7,25% | 7,09% |
| FIN | 2 | 2.688 | 7,27% | 7,04% |
| G1 | 1 | 1.669 | 7,33% | 7,15% |
| MEX | 2 | 4.724 | 7,47% | 7,44% |
| IRL | 2 | 2.716 | 7,74% | 7,51% |
| CHN | 2 | 3.009 | 8,03% | 7,86% |
| SC1 | 1 | 1.172 | 8,23% | 7,98% |
| ROU | 2 | 4.253 | 8,36% | 8,18% |
| EC | 1 | 3.642 | 8,47% | 8,29% |
| SC2 | 1 | 1.149 | 9,10% | 8,79% |
| SC3 | 1 | 1.147 | 9,19% | 8,92% |

**O padrão da especificação se confirma:** as cinco grandes ligas
europeias cobram de 4,3% a 5,0%; as divisões inferiores e as ligas
menores cobram de 7% a 9,3% — o dobro.

⚠️ **Margem baixa não quer dizer fácil de ganhar.** Na Premier League a
margem é baixa *porque o mercado é eficiente*: a taxa é barata e a linha
é quase impossível de bater. Na quarta divisão escocesa a taxa é cara,
mas a casa tem menos informação. Qual dos dois efeitos ganha é uma das
perguntas que este projeto existe para responder — e ela só será
respondida na Fase 6, com backtest.

### O mercado aperta a margem até o apito

Comparando a odd média pré-jogo com a de fechamento (Grupo 1, formato A):

| Liga | Margem pré-jogo | Margem fechamento | Aperto |
|---|---|---|---|
| N1 | 6,01% | 5,72% | 0,29% |
| G1 | 7,62% | 7,33% | 0,28% |
| B1 | 6,55% | 6,30% | 0,25% |
| SP2 | 7,26% | 7,03% | 0,23% |
| P1 | 6,37% | 6,15% | 0,22% |
| SC1 | 8,45% | 8,23% | 0,22% |
| D2 | 6,54% | 6,34% | 0,20% |
| SC0 | 6,41% | 6,21% | 0,20% |
| E0 | 4,46% | 4,27% | 0,19% |
| E1 | 5,57% | 5,41% | 0,17% |
| EC | 8,62% | 8,47% | 0,15% |
| SC3 | 9,33% | 9,19% | 0,14% |
| F2 | 7,14% | 7,01% | 0,13% |
| F1 | 5,15% | 5,02% | 0,13% |
| E3 | 6,85% | 6,73% | 0,11% |
| T1 | 6,61% | 6,50% | 0,11% |
| E2 | 6,66% | 6,56% | 0,10% |
| SP1 | 4,85% | 4,75% | 0,10% |
| SC2 | 9,19% | 9,10% | 0,09% |
| I1 | 4,96% | 4,87% | 0,09% |
| D1 | 4,84% | 4,76% | 0,08% |
| I2 | 7,05% | 6,97% | 0,07% |

O aperto é positivo em **todas** as ligas: a margem cai entre a abertura
e o apito. Como o projeto aposta na odd pré-jogo (regra 8), é a coluna
da esquerda — a mais cara — que o modelo precisa vencer.

## 4. A margem mudou ao longo dos anos?

Comparando a primeira temporada medida (2019/20) com a última
(2025/26), no 1X2 de fechamento do Grupo 1:

| Liga | Temporadas | 2019/20 | 2025/26 | Variação |
|---|---|---|---|---|
| SC0 | 7 | 6,52% | 6,98% | 0,46% |
| E2 | 7 | 6,31% | 7,04% | 0,72% |
| N1 | 7 | 5,90% | 6,82% | 0,91% |
| E3 | 7 | 6,47% | 7,44% | 0,97% |
| E1 | 7 | 5,31% | 6,35% | 1,04% |
| B1 | 7 | 6,29% | 7,38% | 1,09% |
| F1 | 7 | 5,13% | 6,26% | 1,13% |
| T1 | 7 | 6,71% | 7,99% | 1,27% |
| I1 | 7 | 4,93% | 6,28% | 1,34% |
| G1 | 7 | 7,56% | 8,91% | 1,35% |
| SP1 | 7 | 4,76% | 6,13% | 1,37% |
| P1 | 7 | 6,39% | 7,87% | 1,48% |
| D1 | 7 | 4,77% | 6,34% | 1,57% |
| E0 | 7 | 4,07% | 5,67% | 1,60% |
| I2 | 7 | 6,98% | 8,65% | 1,67% |
| D2 | 7 | 6,33% | 8,02% | 1,69% |
| F2 | 7 | 6,97% | 8,66% | 1,69% |
| EC | 7 | 8,12% | 9,90% | 1,79% |
| SC1 | 7 | 7,93% | 9,88% | 1,95% |
| SP2 | 7 | 6,85% | 9,06% | 2,21% |
| SC3 | 7 | 8,99% | 11,33% | 2,34% |
| SC2 | 7 | 8,83% | 11,21% | 2,39% |

A margem caiu em **0 das 22** ligas do Grupo 1. O mercado
ficou mais barato para o apostador — o que costuma andar junto com
ficar mais difícil de bater, porque margem menor é sinal de mais
dinheiro e mais modelos disputando a mesma linha.

## 5. Quanto vale jogar em casa — e o que aconteceu em 2020

*Resposta à pergunta 3: a vantagem de jogar em casa mudou ao longo dos anos?*

**Sim, e muito.** Em 2020 e 2021 os estádios ficaram vazios, e a
vantagem de mando caiu em quase todas as ligas do mundo ao mesmo tempo.
É o experimento natural mais interessante deste conjunto de dados.

Por temporada, nas 22 ligas do Grupo 1 (todas de agosto a maio):

| Temporada | Jogos | Vitórias do mandante | Pontos por jogo | Saldo de gols |
|---|---|---|---|---|
| 2019/20 | 6.904 | 43,5% | 1,573 | 0,304 |
| 2020/21 | 7.648 | 40,8% | 1,488 | 0,183 |
| 2021/22 | 7.822 | 42,5% | 1,538 | 0,266 |
| 2022/23 | 7.830 | 44,2% | 1,582 | 0,299 |
| 2023/24 | 7.799 | 43,1% | 1,553 | 0,285 |
| 2024/25 | 7.681 | 43,7% | 1,573 | 0,283 |
| 2025/26 | 7.646 | 43,1% | 1,555 | 0,273 |

Comparando as temporadas jogadas sem público (2019/20 e 2020/21 na
Europa, 2020 e 2021 nos campeonatos de ano civil) com as demais, o
mando caiu em **29 de 38** competições:

| Liga | Pontos/jogo com público | Pontos/jogo sem público | Queda |
|---|---|---|---|
| AUT | 1,552 | 1,359 | 0,193 |
| ARG | 1,615 | 1,454 | 0,161 |
| SC0 | 1,618 | 1,494 | 0,124 |
| FIN | 1,583 | 1,465 | 0,119 |
| CHN | 1,629 | 1,531 | 0,098 |
| ROU | 1,597 | 1,501 | 0,097 |
| D1 | 1,571 | 1,479 | 0,092 |
| E0 | 1,564 | 1,478 | 0,086 |
| BRA | 1,732 | 1,653 | 0,079 |
| SP2 | 1,645 | 1,574 | 0,072 |
| USA | 1,750 | 1,680 | 0,070 |
| T1 | 1,618 | 1,549 | 0,069 |
| E1 | 1,567 | 1,503 | 0,064 |
| RUS | 1,572 | 1,508 | 0,064 |
| IRL | 1,538 | 1,479 | 0,059 |

⚠️ A temporada 2019/20 entra na conta como 'portões fechados', mas só a
parte final dela foi jogada sem público — o que **diminui** o efeito
medido, não aumenta.

**Consequência direta para a Fase 3:** um modelo que trate o fator casa
como constante ao longo das sete temporadas vai errar num pedaço grande
do treino. Esta tabela é a justificativa para o fator casa variável no
tempo.

### Mando por liga (todas as temporadas)

| Liga | Jogos | Vitórias do mandante | Empates | Pontos por jogo | Saldo de gols |
|---|---|---|---|---|---|
| USA | 6.188 | 49,4% | 25,2% | 1,733 | 0,510 |
| BRA | 5.585 | 48,4% | 26,9% | 1,722 | 0,451 |
| NOR | 3.542 | 47,3% | 24,0% | 1,660 | 0,455 |
| SP2 | 3.234 | 44,2% | 29,8% | 1,625 | 0,331 |
| SP1 | 2.660 | 45,2% | 26,7% | 1,622 | 0,346 |
| CHN | 3.015 | 45,3% | 25,5% | 1,615 | 0,360 |
| MEX | 4.724 | 44,6% | 27,1% | 1,609 | 0,354 |
| T1 | 2.476 | 44,7% | 25,6% | 1,598 | 0,333 |
| ARG | 6.370 | 43,1% | 30,2% | 1,596 | 0,296 |
| POL | 4.149 | 44,0% | 27,1% | 1,591 | 0,327 |
| SC0 | 1.547 | 44,7% | 24,3% | 1,583 | 0,339 |
| RUS | 3.416 | 44,1% | 25,8% | 1,580 | 0,324 |
| N1 | 2.068 | 44,6% | 24,0% | 1,578 | 0,374 |
| FIN | 2.688 | 43,9% | 25,5% | 1,572 | 0,253 |
| ROU | 4.253 | 43,0% | 27,8% | 1,567 | 0,304 |
| D2 | 2.142 | 43,5% | 26,1% | 1,567 | 0,289 |
| E2 | 3.712 | 43,7% | 25,2% | 1,563 | 0,254 |
| SWZ | 2.720 | 43,5% | 25,5% | 1,559 | 0,320 |
| SWE | 3.551 | 43,5% | 25,0% | 1,555 | 0,326 |
| DNK | 3.000 | 43,0% | 26,1% | 1,552 | 0,251 |
| E1 | 3.864 | 42,9% | 26,1% | 1,549 | 0,259 |
| D1 | 2.142 | 43,2% | 24,7% | 1,544 | 0,317 |
| F2 | 2.410 | 41,8% | 28,8% | 1,541 | 0,229 |
| E0 | 2.660 | 43,4% | 23,6% | 1,539 | 0,237 |
| B1 | 2.085 | 43,2% | 24,3% | 1,538 | 0,278 |
| F1 | 2.337 | 43,0% | 24,7% | 1,537 | 0,249 |
| I2 | 2.660 | 40,7% | 31,6% | 1,536 | 0,263 |
| E3 | 3.752 | 42,1% | 27,2% | 1,535 | 0,228 |
| EC | 3.642 | 42,8% | 25,1% | 1,534 | 0,259 |
| IRL | 2.716 | 42,8% | 24,9% | 1,532 | 0,279 |
| P1 | 2.142 | 42,7% | 25,0% | 1,531 | 0,247 |
| SC2 | 1.149 | 42,6% | 24,9% | 1,528 | 0,207 |
| SC3 | 1.147 | 42,5% | 24,8% | 1,524 | 0,202 |
| G1 | 1.669 | 41,6% | 27,1% | 1,521 | 0,259 |
| AUT | 2.674 | 42,1% | 24,9% | 1,513 | 0,241 |
| SC1 | 1.172 | 40,6% | 28,8% | 1,506 | 0,230 |
| I1 | 2.660 | 40,6% | 26,3% | 1,481 | 0,187 |
| JPN | 4.593 | 41,1% | 24,8% | 1,480 | 0,173 |

## 6. Os gols se parecem com uma Poisson?

Média de **2,67 gols por jogo** nas 38 competições. A
pergunta que importa para a Fase 3 é se a distribuição desses gols se
parece com uma Poisson — porque é nessa hipótese que os modelos de
Poisson e Dixon-Coles se apoiam.

| Gols no jogo | Jogos | Observado | Poisson | Diferença |
|---|---|---|---|---|
| 0.0 | 8.881 | 7,62% | 6,94% | 0,68% |
| 1.0 | 21.009 | 18,03% | 18,52% | -0,48% |
| 2.0 | 28.254 | 24,25% | 24,70% | -0,45% |
| 3.0 | 25.745 | 22,10% | 21,96% | 0,13% |
| 4.0 | 16.866 | 14,48% | 14,65% | -0,17% |
| 5.0 | 9.276 | 7,96% | 7,82% | 0,15% |
| 6.0 | 4.126 | 3,54% | 3,48% | 0,07% |
| 7.0 | 1.627 | 1,40% | 1,32% | 0,07% |
| 8.0 | 535 | 0,46% | 0,44% | 0,02% |

A Poisson acerta o formato geral, e **erra de um jeito específico**:
jogos de 0 gol acontecem mais do que ela prevê, e jogos de 1 e 2 gols
um pouco menos. Esse desvio é conhecido e tem nome — é exatamente ele
que o ajuste de **Dixon-Coles** corrige, inflando a probabilidade dos
placares baixos (0-0, 1-0, 0-1, 1-1). Saber disso **antes** de treinar
é o motivo de esta seção existir.

### Mais de 2,5 gols, por liga

| Liga | Jogos | Gols por jogo | Mais de 2,5 gols |
|---|---|---|---|
| D1 | 2.142 | 3,16 | 61,3% |
| N1 | 2.068 | 3,06 | 58,8% |
| D2 | 2.142 | 2,96 | 58,5% |
| SWZ | 2.720 | 3,01 | 58,2% |
| NOR | 3.542 | 3,00 | 57,8% |
| USA | 6.188 | 2,91 | 56,9% |
| CHN | 3.015 | 2,92 | 56,1% |
| AUT | 2.674 | 2,91 | 55,4% |
| B1 | 2.085 | 2,86 | 55,0% |
| E0 | 2.660 | 2,86 | 55,0% |
| T1 | 2.476 | 2,83 | 54,1% |
| SWE | 3.551 | 2,80 | 53,9% |
| DNK | 3.000 | 2,80 | 53,6% |
| SC2 | 1.149 | 2,82 | 53,4% |
| F1 | 2.337 | 2,78 | 52,9% |
| SC0 | 1.547 | 2,72 | 52,6% |
| EC | 3.642 | 2,79 | 52,4% |
| I1 | 2.660 | 2,73 | 52,0% |
| SC3 | 1.147 | 2,73 | 51,3% |
| MEX | 4.724 | 2,67 | 50,5% |
| POL | 4.149 | 2,65 | 49,5% |
| FIN | 2.688 | 2,64 | 49,1% |
| E2 | 3.712 | 2,61 | 49,0% |
| P1 | 2.142 | 2,59 | 49,0% |
| SC1 | 1.172 | 2,62 | 48,6% |
| JPN | 4.593 | 2,62 | 48,6% |
| IRL | 2.716 | 2,58 | 47,9% |
| E1 | 3.864 | 2,52 | 46,9% |
| E3 | 3.752 | 2,53 | 46,8% |
| RUS | 3.416 | 2,53 | 46,7% |
| SP1 | 2.660 | 2,57 | 46,6% |
| G1 | 1.669 | 2,47 | 46,4% |
| I2 | 2.660 | 2,47 | 44,8% |
| F2 | 2.410 | 2,41 | 43,9% |
| BRA | 5.585 | 2,40 | 43,7% |
| ROU | 4.253 | 2,41 | 43,5% |
| SP2 | 3.234 | 2,31 | 41,1% |
| ARG | 6.370 | 2,23 | 38,9% |

## 7. O mercado é bem calibrado?

*Resposta à pergunta 2.*

**Sim, notavelmente.** Agrupando todas as afirmações de probabilidade do
mercado de fechamento do Grupo 1 e conferindo o que de fato aconteceu:

| Faixa | Afirmações | Previsto | Aconteceu | Diferença |
|---|---|---|---|---|
| 0%-5% | 884 | 3,7% | 3,5% | -0,2 p.p. |
| 5%-10% | 3.454 | 7,9% | 6,9% | -0,9 p.p. |
| 10%-20% | 18.280 | 15,9% | 16,0% | +0,1 p.p. |
| 20%-30% | 62.442 | 25,9% | 25,8% | -0,1 p.p. |
| 30%-40% | 32.508 | 34,1% | 34,0% | -0,1 p.p. |
| 40%-50% | 20.008 | 44,6% | 44,9% | +0,3 p.p. |
| 50%-60% | 11.473 | 54,6% | 54,0% | -0,5 p.p. |
| 60%-70% | 6.004 | 64,5% | 65,7% | +1,2 p.p. |
| 70%-85% | 4.150 | 76,1% | 76,8% | +0,7 p.p. |
| 85%-100% | 691 | 88,5% | 88,4% | -0,0 p.p. |

O erro de calibração médio (ECE) é de **0,0023**
— menos de meio ponto percentual. Quando o mercado de fechamento diz
60%, acontece perto de 60%. Isso é a definição prática de um mercado
difícil de bater, e é o adversário do projeto.

⚠️ **Mas há um padrão nos restos**, e ele é o efeito mais famoso dos
mercados de aposta: os **favoritos vencem mais** do que a odd dizia
(+0,9 p.p. nas faixas acima de 60%) e os
**azarões vencem menos** (-0,8 p.p. abaixo de
15%). É o *viés favorito-azarão*, e ele
sobrevive mesmo depois de tirar a margem pelo método que melhor o
corrige. Quem aposta em azarão paga caro duas vezes: na comissão maior
e na probabilidade inflada.

## 8. Quais ligas entram no backtest

*Resposta à pergunta 4, e ao pedido original: "quero as ligas em que tem
apostas boas".*

A lista abaixo **não** foi escolhida a dedo. Ela é o resultado de aplicar
os cortes do `config.yaml` às medições desta fase:

- margem máxima no 1X2 pré-jogo: **8%**
- cobertura mínima de odds: **90%**
- jogos mínimos: **1000**
- ECE máximo: **2.0×** o piso de ruído da liga

🔎 **Sobre o corte de calibração.** Medir calibração com o ECE cru pune
liga pequena: com 1.200 jogos, o ECE é alto **mesmo num mercado**
**perfeito**, só por acaso amostral. Por isso o ECE de cada liga é
comparado com o piso de ruído dela — o ECE que apareceria se aquele
mercado fosse perfeito, estimado por simulação. Este critério foi fixado
**depois** de ver os números (o corte anterior, absoluto, reprovava a
Grécia por ser pequena). Nenhuma liga foi reprovada por ele: quem caiu,
caiu por margem.

| Liga | Jogos | Cobertura | Margem pré | ECE | Piso de ruído | ECE/piso | Log loss | Aprovada |
|---|---|---|---|---|---|---|---|---|
| E0 | 2.660 | 100,0% | 4,46% | 0,0094 | 0,0100 | 0,94 | 0,9680 | True |
| D1 | 2.142 | 100,0% | 4,84% | 0,0136 | 0,0111 | 1,22 | 0,9765 | True |
| SP1 | 2.660 | 100,0% | 4,85% | 0,0116 | 0,0094 | 1,23 | 0,9704 | True |
| I1 | 2.660 | 100,0% | 4,96% | 0,0078 | 0,0092 | 0,84 | 0,9640 | True |
| F1 | 2.337 | 100,0% | 5,15% | 0,0120 | 0,0097 | 1,23 | 0,9866 | True |
| E1 | 3.864 | 100,0% | 5,57% | 0,0093 | 0,0073 | 1,28 | 1,0384 | True |
| N1 | 2.068 | 100,0% | 6,01% | 0,0099 | 0,0114 | 0,87 | 0,9352 | True |
| P1 | 2.142 | 100,0% | 6,37% | 0,0128 | 0,0106 | 1,20 | 0,9230 | True |
| SC0 | 1.547 | 100,0% | 6,41% | 0,0110 | 0,0128 | 0,87 | 0,9329 | True |
| D2 | 2.142 | 100,0% | 6,54% | 0,0094 | 0,0097 | 0,97 | 1,0418 | True |
| B1 | 2.085 | 100,0% | 6,55% | 0,0082 | 0,0110 | 0,74 | 0,9884 | True |
| T1 | 2.476 | 98,8% | 6,61% | 0,0128 | 0,0100 | 1,28 | 0,9804 | True |
| E2 | 3.712 | 100,0% | 6,66% | 0,0115 | 0,0075 | 1,54 | 1,0155 | True |
| E3 | 3.752 | 99,9% | 6,85% | 0,0045 | 0,0070 | 0,65 | 1,0503 | True |
| I2 | 2.660 | 99,7% | 7,05% | 0,0056 | 0,0081 | 0,70 | 1,0475 | True |
| F2 | 2.410 | 100,0% | 7,14% | 0,0045 | 0,0088 | 0,51 | 1,0442 | True |
| SP2 | 3.234 | 100,0% | 7,26% | 0,0060 | 0,0075 | 0,81 | 1,0407 | True |
| G1 | 1.669 | 99,9% | 7,62% | 0,0221 | 0,0116 | 1,90 | 0,9452 | True |
| SC1 | 1.172 | 100,0% | 8,45% | 0,0186 | 0,0134 | 1,39 | 1,0517 | False |
| EC | 3.642 | 99,6% | 8,62% | 0,0094 | 0,0079 | 1,19 | 1,0161 | False |
| SC2 | 1.149 | 100,0% | 9,19% | 0,0131 | 0,0141 | 0,93 | 1,0032 | False |
| SC3 | 1.147 | 100,0% | 9,33% | 0,0119 | 0,0141 | 0,85 | 1,0331 | False |

### Aprovadas (18)

`B1, D1, D2, E0, E1, E2, E3, F1, F2, G1, I1, I2, N1, P1, SC0, SP1, SP2, T1`

São **46.220 jogos** elegíveis para o backtest de
apostas da Fase 6.

### Reprovadas (4)

| Liga | Motivo |
|---|---|
| SC1 | margem alta (8.45% > 8%) |
| EC | margem alta (8.62% > 8%) |
| SC2 | margem alta (9.19% > 8%) |
| SC3 | margem alta (9.33% > 8%) |

Todas as quatro caíram pelo mesmo motivo: margem acima de 8%. São as
divisões mais baixas da Escócia e a quinta divisão inglesa — exatamente
onde a casa cobra mais caro por ter menos informação. Para lucrar ali, o
modelo precisaria de uma vantagem de mais de 8% sobre o mercado, o que
seria extraordinário.

⚠️ **Os 16 países do Grupo 2 não aparecem nesta lista** e nunca
aparecerão: sem odd pré-jogo não existe aposta para simular (regra 12).
Eles continuam valendo para treinar os modelos e para medir calibração —
são 63.184 jogos, mais da metade do total.

## 9. As quatro respostas, em uma frase cada

| Pergunta | Resposta |
|---|---|
| Qual a margem média da casa em cada liga? | De **4,3%** (Premier League) a **9,3%** (4ª divisão escocesa) no 1X2 de fechamento. As cinco grandes europeias cobram metade do que cobram as divisões menores. |
| O mercado é bem calibrado? | **Sim**: ECE de 0,0023 no fechamento do Grupo 1. Sobra um viés favorito-azarão de +0,9 p.p. nos favoritos. |
| A vantagem de jogar em casa mudou? | **Mudou muito.** Caiu em 2020-21, com os estádios vazios, e voltou a subir depois. O fator casa não pode ser uma constante no modelo. |
| Quais ligas passaram no filtro? | **18 das 22** do Grupo 1. Reprovadas: SC1, SC2, SC3 e EC, todas por margem acima de 8%. |

---

## O que a Fase 3 recebe daqui

1. **A meta:** log loss de 0,9984 no fechamento do Grupo 1. Um modelo que não chegue perto disso não é útil.
2. **Um alerta:** a Poisson simples erra nos placares de poucos gols — o ajuste de Dixon-Coles nasce daí.
3. **Um requisito:** o fator casa precisa variar no tempo.
4. **Um método:** `power` para tirar a margem, por ser o mais bem calibrado.
5. **Um escopo:** 18 ligas aprovadas para aposta; 38 competições para treinar.
