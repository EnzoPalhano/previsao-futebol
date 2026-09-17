# Fase 3 — Os primeiros modelos, medidos

- Camada de ligas: **camada_tudo**
- Jogos liberados (fora do teste final): **89.455**
- Jogos trancados até a Fase 9: **27.059** (temporadas que começaram em 2024 ou depois)
- Janela de avaliação: **2023-07-01 a 2024-06-03**, com o modelo reajustado todo dia 1º
- Grupo 1 — backtest e CLV (22): B1, D1, D2, E0, E1, E2, E3, EC, F1, F2, G1, I1, I2, N1, P1, SC0, SC1, SC2, SC3, SP1, SP2, T1
- Grupo 2 — treino e calibração (16): ARG, AUT, BRA, CHN, DNK, FIN, IRL, JPN, MEX, NOR, POL, ROU, RUS, SWE, SWZ, USA
- Gerado em: 2026-09-16

> **Regra 13.** Cada tabela diz a quais ligas se refere. A comparação
> com o mercado usa **só o Grupo 1 com odd de fechamento registrada** —
> os 16 países do Grupo 2 não têm odd pré-jogo (regra 12).

> ⚠️ **Todo número aqui é provisório.** O critério oficial de escolha de
> modelo é a log loss no walk-forward rodada a rodada da Fase 4
> (regra 9). Esta medição reajusta o modelo uma vez por mês, o que
> deixa a previsão do fim do mês até 30 dias desatualizada. Isso
> penaliza todos os modelos do mesmo jeito, então a comparação entre
> eles continua valendo; o valor absoluto, não.

> ⚠️ **Nada aqui viu as temporadas de teste final** (regra 7). A trava
> é por código, em `futebol/avaliacao/divisao.py`, e conta pelo ano em
> que a temporada começou — porque campeonato de ano civil chama a
> temporada de `2024`, não de `2024/25`.

## 1. O que a Fase 3 construiu

Três modelos, todos obedecendo à mesma interface (`treinar` e `prever`) e todos
entregando a mesma coisa: uma **matriz de placares**. A chance de cada placar
possível, de 0x0 a 10x10. Todo mercado sai dessa matriz — o 1X2 é a soma dos
triângulos, o Over 2,5 é a soma das casas em que os gols passam de dois, o
"ambos marcam" é tudo fora da primeira linha e da primeira coluna. Assim as
probabilidades nunca se contradizem entre si.

| Modelo | O que ele sabe |
|---|---|
| `baseline` | a distribuição histórica de placares da liga. **Ignora quem joga** |
| `poisson` | força de ataque e de defesa de cada time + fator casa da liga |
| `dixon-coles` | o Poisson + correção dos placares baixos + jogo antigo pesa menos |

O Poisson diz que os gols de cada lado saem de uma distribuição de Poisson com
médias

```
λ = exp(nível da liga + ataque do mandante − defesa do visitante + fator casa)
μ = exp(nível da liga + ataque do visitante − defesa do mandante)
```

Ataque e defesa são lidos em relação à média da própria liga: `ataque = +0,30`
quer dizer "faz `exp(0,30)` = 1,35 vez o que um time médio daquela competição
faria". Defesa positiva é defesa boa.

**Encolhimento.** As forças não são estimadas soltas: quem tem pouca história
na competição é puxado para a média dela, com peso `n / (n + m)`, onde `n` são
os jogos do time e `m` é o `jogos_equivalentes` do `config.yaml`. É a resposta
para o time recém-promovido, que chega sem nenhum jogo naquela divisão: o
modelo o trata como um time médio, que é o que se pode honestamente dizer de
quem não se conhece.

## 2. Os modelos contra a régua

Todas as 38 competições, 11.151 jogos previstos fora
da amostra. Menor é melhor nas três notas.

| Modelo | Jogos | Log loss (1X2) | Brier | ECE | Log loss (O/U 2,5) |
|---|---|---|---|---|---|
| baseline (histórico da liga) | 11.151 | 1,0746 | 0,6502 | 0,0034 | 0,6893 |
| poisson | 11.151 | 1,0263 | 0,6157 | 0,0107 | 0,6872 |
| dixon-coles | 11.151 | 1,0192 | 0,6108 | 0,0100 | 0,6837 |

Referências para ler a coluna da log loss: **1,0986**
é o que tira quem chuta 33% para cada opção, e a Fase 2 mediu
**0,9984** para o mercado de fechamento do Grupo 1 inteiro.

O que a tabela diz:

- o **baseline** bate o chute uniforme. Só a estatística da liga — quantos por
  cento dos jogos o mandante ganha, quantos terminam com mais de 2,5 gols — já
  vale alguma coisa;
- o **Poisson** bate o baseline com folga. Essa é a prova de que ele aprendeu
  algo **sobre os times**, e não só sobre a liga;
- o **Dixon-Coles** bate o Poisson. Os dois remendos (placares baixos e
  decaimento) valem a complexidade que custam;
- o melhor da fase é o **dixon-coles**, com log loss
  **1,0192**.

⚠️ O ECE do baseline é o **mais baixo** da tabela, e isso não o torna melhor.
Calibração mede se "quando digo 60%, acontece 60%" — e um modelo que sempre diz
a média da liga acerta isso por construção, sem informar nada sobre o jogo. É
por isso que o projeto escolhe por log loss, e nunca por calibração sozinha.

### O mercado, nas mesmas partidas

Comparar o modelo com o mercado só é honesto no mesmo conjunto de jogos: o
mercado só existe onde há odd registrada, e isso exclui o Grupo 2 inteiro
(regra 12) e os buracos de cobertura do Grupo 1.

| Quem prevê | Jogos | Log loss (1X2) | Brier | ECE |
|---|---|---|---|---|
| baseline (histórico da liga) | 7.799 | 1,0761 | 0,6513 | 0,0033 |
| poisson | 7.799 | 1,0208 | 0,6119 | 0,0098 |
| dixon-coles | 7.799 | 1,0147 | 0,6077 | 0,0099 |
| mercado (fechamento) | 7.799 | 0,9914 | 0,5920 | 0,0052 |

O mercado de fechamento tira **0,9914** e o melhor modelo da
fase tira **1,0147** — uma distância de
**0,0233** de log loss.

**Isto é o esperado, e não é fracasso** (Fase 4 da especificação). A odd de
fechamento embute lesão, escalação, mercado de transferência, dinheiro
profissional e o resultado de milhares de pessoas apostando. Um modelo com
força de ataque e defesa tirada de placares não deveria vencer isso — e se
vencesse na primeira tentativa, a suspeita certa seria data leakage, não
talento. O valor do projeto está em achar **onde** a diferença é pequena o
bastante para existir aposta com valor, e isso é assunto da Fase 6.

## 3. Experimento: o fator casa deve ser por liga?

O experimento pedido na Fase 3. Duas variantes do Dixon-Coles, iguais em tudo o
mais:

- **por liga** — cada competição estima o seu fator casa;
- **global** — um número só, medido em todas as ligas juntas
  (`log(gols do mandante ÷ gols do visitante)` = 0,234,
  ou seja, o mandante faz 1,26 vez o que faz
  fora) e congelado em todas.

| Variante | Log loss |
|---|---|
| fator casa por liga | 1,0192 |
| fator casa global | 1,0198 |

A comparação certa é **emparelhada**, jogo a jogo — as duas variantes preveem
exatamente as mesmas partidas, e emparelhar cancela a dificuldade de cada
jogo. A diferença (global − por liga) em log loss:

**+0,00063 (IC 95%: -0,00020 a +0,00145; n = 11.151 jogos; menor efeito detectável nesta amostra: 0,00117) — indistinguível de zero**

**A diferença não se distingue de zero nesta amostra.** O intervalo de 95% cruza o zero, e o efeito observado é menor que o menor efeito que 11 mil jogos conseguiriam detectar. A leitura honesta é *não sei dizer qual é melhor*, e não *são iguais*.

E isso faz sentido quando se olha de onde a diferença poderia vir. O fator casa
**varia muito** entre competições — a tabela abaixo mostra as cinco pontas de
cada lado, entre as 38 competições (Grupo 1 e Grupo 2 juntos, porque o fator
casa é estimado com placares e não com odds):

| Liga | Fator casa (log) | Gols do mandante ÷ do visitante | Jogos |
|---|---|---|---|
| USA | 0,407 | 1,50 | 4.754 |
| SP2 | 0,338 | 1,40 | 2.310 |
| BRA | 0,308 | 1,36 | 4.559 |
| ARG | 0,293 | 1,34 | 4.890 |
| NOR | 0,288 | 1,33 | 2.900 |
| DNK | 0,126 | 1,13 | 2.568 |
| SC1 | 0,119 | 1,13 | 812 |
| SC2 | 0,115 | 1,12 | 789 |
| AUT | 0,099 | 1,10 | 2.254 |
| FIN | 0,097 | 1,10 | 2.198 |

O padrão não é aleatório: no topo estão campeonatos de país grande, com viagem
longa entre cidades (Brasil, EUA), e embaixo ligas compactas ou com cultura de
mando mais fraca. Isso conversa com o que a Fase 2 já havia medido sobre a queda
do fator casa nos estádios vazios de 2020/21.

Só que a **maioria dos jogos** está em ligas cujo fator casa é próximo da média
geral. Quem pagaria o preço de um número único são as competições das pontas, e
elas são uma fatia pequena da amostra — por isso a diferença média fica
espremida contra o ruído, mesmo com 11 mil jogos.

**Decisão: fica o fator casa por liga** (`modelos.poisson.fator_casa:
por_liga`), por três motivos, e nenhum deles é "ganhou o teste":

1. em nenhuma medição ele apareceu **pior**;
2. custa um parâmetro por competição, com centenas ou milhares de jogos para
   estimá-lo — não é o tipo de parâmetro que causa sobreajuste;
3. o número único é indefensável nas pontas: aplicar a vantagem de casa do
   futebol japonês ao Brasileirão é errado por uma razão física (viagem,
   altitude, público), não estatística.

A Fase 4 revisita isso com o walk-forward oficial, onde a amostra é maior.

⚠️ Um efeito de graça, que não aparece na tabela: como o Dixon-Coles é
reajustado a cada data de previsão e os jogos recentes pesam mais, o fator casa
estimado **muda ao longo do tempo** por si só. O experimento acima compara
"por liga" com "único"; a variação no tempo já está dentro das duas.

## 4. Vale fazer jogo antigo pesar menos?

O decaimento temporal dá a cada jogo o peso `exp(−xi · dias)`. Com `xi = 0` o
modelo acha que 2019 e o mês passado valem o mesmo; quanto maior o `xi`, mais
curta a memória.

| xi | Meia-vida | Log loss | Brier | ECE |
|---|---|---|---|---|
| 0,0000 | sem decaimento | 1,0254 | 0,6153 | 0,0073 |
| 0,0005 | 1386 dias | 1,0220 | 0,6128 | 0,0075 |
| 0,0010 | 693 dias | 1,0201 | 0,6115 | 0,0084 |
| 0,0018 | 385 dias | 1,0192 | 0,6108 | 0,0100 |
| 0,0030 | 231 dias | 1,0198 | 0,6113 | 0,0106 |
| 0,0050 | 139 dias | 1,0229 | 0,6134 | 0,0103 |

Ligar o decaimento vale a pena. A diferença entre não ter memória curta
(`xi = 0`) e usar o valor do `config.yaml`, medida emparelhada jogo a jogo:

**+0,00629 (IC 95%: +0,00418 a +0,00841; n = 11.151 jogos; menor efeito detectável nesta amostra: 0,00302) — diferença real**

O melhor ponto desta grade é `xi = 0,0018`
(meia-vida de 385 dias), com log loss
1,0192.

⚠️ **Este número NÃO é a escolha do `xi`** (regra 9). A escolha sai do
walk-forward de validação da Fase 4, rodada a rodada, e o que está aqui é uma
varredura grossa de sanidade: ela mostra que o parâmetro importa e em que
vizinhança ficar, e serve para o Enzo ver o formato da curva. Escolher agora,
com uma medição mensal e uma grade de 6 pontos, seria decidir com
a ferramenta errada.

## 5. Quanto encolher a força de quem tem pouca história?

O `m` (`modelos.shrinkage.jogos_equivalentes`) é **quantos jogos de história a
média da liga vale**. A força que o modelo usa fica em torno de

```
força do time ≈ (n / (n + m)) · força que os jogos dele pedem
```

Com `m` grande, todo mundo vira time médio (o modelo deixa de distinguir os
times); com `m` perto de zero, três jogos bons fazem um time parecer o Bayern.

| jogos_equivalentes (m) | Peso próprio com 10 jogos | Log loss | Brier | ECE |
|---|---|---|---|---|
| 1 | 90,9% | 1,0209 | 0,6119 | 0,0119 |
| 2 | 83,3% | 1,0200 | 0,6114 | 0,0098 |
| 6 | 62,5% | 1,0192 | 0,6108 | 0,0100 |
| 12 | 45,5% | 1,0202 | 0,6114 | 0,0091 |
| 20 | 33,3% | 1,0226 | 0,6130 | 0,0132 |

O melhor ponto desta grade é `m = 6`, e a
curva é rasa entre 2 e 12 — o modelo não é sensível a essa escolha na faixa
razoável, o que é uma boa notícia.

⚠️ Igual ao `xi`: provisório, escolha definitiva na Fase 4.

## 6. A correção dos placares baixos, liga por liga

O `rho` do Dixon-Coles mede o quanto 0x0 e 1x1 acontecem **mais** (e 1x0 e 0x1
**menos**) do que a independência entre os dois times preveria. `rho` negativo
é o caso conhecido na literatura, e o efeito cai direto na probabilidade de
**empate** — o mercado em que o Poisson puro erra mais.

O projeto estima um `rho` por competição, junto com o resto:

| Liga | rho | Jogos |
|---|---|---|
| D1 | -0,1455 | 1.530 |
| SC1 | -0,1291 | 812 |
| N1 | -0,1184 | 1.456 |
| I2 | -0,1080 | 1.900 |
| ARG | -0,1068 | 4.890 |
| BRA | 0,0109 | 4.559 |
| E1 | 0,0254 | 2.760 |
| P1 | 0,0600 | 1.530 |

Em 33 das 38 competições o `rho` saiu negativo, como a
literatura prevê. Onde ele fica perto de zero, a correção simplesmente não faz
nada naquela liga — o que é o comportamento correto: o parâmetro é estimado, não
imposto.

⚠️ Nenhuma liga encostou no limite de |rho| ≤ 0,15 imposto pelo código. Esse limite existe porque um
`rho` muito negativo pode empurrar a probabilidade de um placar para baixo de
zero, e probabilidade negativa não existe.

## 7. O que este relatório não diz

Vale mais listar o que **não** está aqui do que enfeitar o que está:

- **não há walk-forward oficial.** A medição é mensal, não rodada a rodada. A
  Fase 4 refaz tudo isso do jeito certo, e é dela que sai a escolha do modelo;
- **não há nenhuma aposta.** Nem ROI, nem CLV, nem valor esperado. Comparar a
  probabilidade do modelo com a odd da casa é a Fase 6, e a lista de ligas
  aprovadas para isso já está no `config.yaml` desde a Fase 2 (18 ligas);
- **as temporadas de teste final continuam fechadas** (regra 7). Elas serão
  abertas uma única vez, na Fase 9, com a configuração já pré-registrada;
- **nenhuma feature de formulário.** Elo, médias móveis, dias de descanso e
  desfalques são das Fases 5 e 7. O que está medido aqui é o quanto se consegue
  **só com placares**.

**Contagem de configurações testadas (regra 11).** Nesta fase foram medidas
**13** configurações distintas na janela de validação: os 3
modelos, as 2 variantes de fator casa, a grade de 6 valores
de `xi` e a grade de 5 valores de encolhimento
(descontadas as repetições entre as grades e o padrão do `config.yaml`).

Registrar isso não é formalidade. Quanto mais configurações são testadas, maior
a chance de a melhor delas estar na frente **por sorte** — e é por isso que o
número precisa estar escrito antes de o teste final ser aberto. Nenhuma destas
13 olhou o teste final. O total acumulado vive no pré-registro
do CLAUDE.md e cresce na Fase 4.
