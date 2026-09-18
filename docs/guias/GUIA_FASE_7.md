# Guia da Fase 7 — Múltiplas: por que a casa adora elas

Este guia é para quem nunca programou. Os comandos são do **Windows
(PowerShell)** primeiro; a versão Mac/Linux está no fim.

Múltipla (ou "acumulada") é juntar várias apostas num bilhete só. Três jogos de
odd 2,00 viram odd 8,00, e dez reais viram oitenta. É a aposta mais divertida que
existe e a mais lucrativa **para a casa** — e esta fase mede exatamente por quê.

Ela também tem uma surpresa. O projeto foi procurar um defeito específico nas
múltiplas, tinha quase certeza de que ia encontrar, e **não encontrou**. O que
encontrou no lugar foi melhor.

---

## Índice

1. [O que é uma múltipla, e o truque da casa](#1-o-que-é-uma-múltipla-e-o-truque-da-casa)
2. [Rodar a medição](#2-rodar-a-medição)
3. [Descoberta 1: a comissão se multiplica](#3-descoberta-1-a-comissão-se-multiplica)
4. [Descoberta 2: a lupa do erro](#4-descoberta-2-a-lupa-do-erro)
5. [O que a fase foi procurar e não achou](#5-o-que-a-fase-foi-procurar-e-não-achou)
6. [Descoberta 3: o cash out cobra a mesma coisa sempre](#6-descoberta-3-o-cash-out-cobra-a-mesma-coisa-sempre)
7. [O montador de bilhetes](#7-o-montador-de-bilhetes)
8. [Erros comuns](#8-erros-comuns)
9. [Como saber que está tudo certo](#9-como-saber-que-está-tudo-certo)

---

## 1. O que é uma múltipla, e o truque da casa

Numa aposta simples, você escolhe um jogo. Se acertar, recebe. Simples.

Numa múltipla, você escolhe vários e **todos** precisam dar certo. Em troca, as
odds se multiplicam:

```
3 jogos de odd 2,00  →  2,00 × 2,00 × 2,00 = odd 8,00
R$ 10 apostados      →  R$ 80 se os três derem certo
```

Parece generoso. E é aqui que está o truque, que quase ninguém percebe.

**A comissão da casa também se multiplica.** Toda odd já vem com uma "taxa"
embutida — no nosso caso, medida em cerca de **4,4%** por aposta. Numa aposta
simples você paga 4,4%. Numa múltipla de três, você não paga 4,4%: paga

```
1,044 × 1,044 × 1,044 − 1 = 13,8%
```

Três vezes a taxa, cada uma cobrada em cima da anterior. Igual a juros de cartão
de crédito, e pelo mesmo motivo matemático.

A fase mediu isso em **36.211 bilhetes** montados nas rodadas de 2021 a 2024, de
2 a 10 seleções cada, sempre com as odds reais do mercado.

⚠️ **Uma regra que o projeto nunca quebra:** no máximo **uma seleção por jogo**.
Nada de "o Flamengo vence" + "sai mais de 2,5 gols" **no mesmo jogo**. Esses dois
eventos andam juntos — se o Flamengo goleia, os dois acontecem —, e multiplicar as
chances deles daria um número inflado. Essa é uma das poucas coisas em que as
casas de aposta e este projeto concordam, aliás: muitas casas nem deixam você
fazer isso.

---

## 2. Rodar a medição

```powershell
.venv\Scripts\Activate.ps1
python scripts\relatorio_fase7.py
```

Leva menos de dois minutos. O relatório fica em `docs\relatorios\fase7.md`, com
dois gráficos ao lado.

---

## 3. Descoberta 1: a comissão se multiplica

| Jogos no bilhete | Comissão da casa | Equivale a, por jogo |
|---|---|---|
| 2 | 9,1% | 4,47% |
| 3 | 14,0% | 4,46% |
| 4 | 19,0% | 4,45% |
| 6 | 29,7% | 4,43% |
| 8 | 41,4% | 4,42% |
| 10 | **54,0%** | 4,41% |

Olhe a coluna da direita: **a taxa por jogo é sempre a mesma**, em torno de
4,4%. A casa não está sendo mais gananciosa com múltiplas. É a mesma taxa de
sempre, cobrada dez vezes seguidas.

E o efeito é brutal. Um bilhete de dez jogos custa **1,54 vez** o que ele vale.
Traduzindo: um bilhete que deveria pagar R$ 100 paga R$ 65.

⚠️ **Esta é a única parte da fase que não depende do nosso modelo.** Ela vale
para você, para mim e para um apostador perfeito que acertasse tudo. Juntar jogos
num bilhete só multiplica a comissão, sempre, para todo mundo. É por isso que a
múltipla é o produto favorito de qualquer casa de apostas.

---

## 4. Descoberta 2: a lupa do erro

Aqui a fase mediu uma coisa que eu achei o resultado mais bonito do projeto até
agora.

| Jogos | O modelo prometeu | Aconteceu | Erro |
|---|---|---|---|
| 2 | 36,1% | 33,5% | −7,2% |
| 4 | 13,8% | 11,2% | −18,7% |
| 8 | 2,27% | 1,68% | −25,9% |

O modelo promete mais do que entrega, e **o erro cresce muito** conforme o
bilhete aumenta. De onde vem isso?

A resposta: **de um errinho de nada, multiplicado.**

O modelo exagera a chance de cada jogo em cerca de **4%**. Só isso. Numa aposta
simples esse erro é praticamente invisível — você nem notaria. Mas numa múltipla
ele é elevado à potência do número de jogos:

| Jogos | O errinho de 4% vira |
|---|---|
| 1 | 4,1% |
| 2 | 8,1% |
| 4 | 15,5% |
| 8 | **28,5%** |

**A múltipla funciona como uma lupa do erro do modelo.** Um defeito quase
imperceptível numa aposta vira um exagero de 28% num bilhete de oito jogos.

E dá para provar que é isso, e não outra coisa: o relatório calcula a "razão por
seleção" — o exagero de **uma perna só**, isolado do tamanho do bilhete. Ela fica
em 0,956 a 0,963 nos nove tamanhos. Praticamente constante. Se o problema fosse
outro, esse número desabaria conforme o bilhete crescesse.

É, aliás, o mesmo defeito que a Fase 4 já tinha medido de outro jeito (o modelo
fica 0,0226 de log loss atrás do mercado). A múltipla só deixa ele visível a olho
nu.

---

## 5. O que a fase foi procurar e não achou

Esta é a parte que vale entender com calma, porque é ciência de verdade.

### A suspeita

Quando você multiplica as chances de vários jogos, está supondo que eles são
**independentes** — que o resultado de um não diz nada sobre o outro. E isso é
meio duvidoso:

- num sábado de muitos gols, todos os jogos tendem a ter mais gols;
- o calendário, o clima, a rodada;
- e principalmente: **se o modelo está errando naquele mês, ele erra na mesma
  direção em todos os jogos**.

Se isso for verdade, a chance real de acertar uma múltipla é **menor** que a
calculada — e cada vez menor conforme o bilhete cresce. A especificação do
projeto dizia, com todas as letras, que se esse desvio crescesse com o tamanho da
múltipla, "está vendo a correlação em ação".

### O teste

Como separar "o modelo está errado" de "a suposição de independência está
errada"? As duas coisas produzem o mesmo sintoma.

O truque: **refazer a conta usando as probabilidades do mercado**, no lugar das
do modelo. A Fase 2 já tinha medido que o mercado acerta muito bem jogo a jogo.
Então:

- se o produto do **mercado** também errar para cima → o problema é a
  independência;
- se o produto do **mercado** acertar → o problema era só o nosso modelo.

### O resultado

| Jogos | O mercado prometeria | Aconteceu | Erro | Margem de erro |
|---|---|---|---|---|
| 2 | 33,53% | 33,51% | −0,1% | ±2,7% |
| 3 | 19,76% | 19,72% | −0,2% | ±4,8% |
| 4 | 11,75% | 11,23% | −4,4% | ±7,5% |

**O mercado acerta em cheio.** O erro é praticamente zero nos bilhetes pequenos,
e a margem de erro contém o zero nos nove tamanhos.

Conclusão: **a correlação entre jogos, se existe, é pequena demais para aparecer
em 36 mil bilhetes.** O produto simples das probabilidades não é o problema — o
problema era o que a gente estava colocando dentro dele.

⚠️ **O limite honesto, que precisa ser dito.** A margem de erro cresce muito com
o tamanho do bilhete: de ±2,7% numa dupla para ±75% num bilhete de dez. Ou seja,
num bilhete grande a gente não conseguiria enxergar nem um efeito enorme. A frase
correta é: **"em bilhetes pequenos, medimos que não há; em bilhetes grandes, não
conseguimos medir."**

Reparar nessa diferença — entre "medi que não existe" e "não consegui medir" — é
provavelmente a habilidade mais útil que este projeto inteiro ensina.

---

## 6. Descoberta 3: o cash out cobra a mesma coisa sempre

Cash out é o botão que aparece com o bilhete em andamento: *"você acertou 4 de 6,
aceita R$ 30 agora?"*.

A conta que a casa faz é simples: ela calcula quanto o bilhete ainda vale (a
chance do que falta × o prêmio) e oferece esse valor **menos uma taxa** — aqui
simulada em 8%.

O projeto testou três estratégias em todos os tamanhos de bilhete:

| Estratégia | O que rende, em média (bilhete de 10) |
|---|---|
| nunca sacar | −34,8% |
| sacar depois de 1 acerto | −40,0% |
| sacar depois de 5 acertos | −40,0% |
| sacar depois de 9 acertos | −40,0% |
| sacar só quando parece vantajoso | −36,6% |

Repare nas linhas do meio. **São todas idênticas.** Sacar depois de um acerto,
de cinco ou de nove dá exatamente o mesmo resultado esperado.

Isso não é coincidência dos dados — é uma conta que fecha sempre:

```
o que vale sacar = o que vale não sacar × (1 − taxa)
```

**O botão cobra a mesma taxa não importa quando você o aperta.** O que muda é só
o tamanho do susto: sacar cedo é um resultado mais previsível e mais pobre.

⚠️ **Uma armadilha de leitura que essa tabela ensina a desarmar.** No relatório
há duas colunas de resultado: "o que aconteceu" e "o que era esperado". No
bilhete de dez, "nunca sacar" teve o **melhor** resultado real (+7,95%!), porque
16 bilhetes sortudos acertaram. A margem de erro daquele número vai de −54% a
+87%: é uma loteria, não uma medição. A coluna do valor esperado não depende de
sorte nenhuma — e é essa que decide.

**E a terceira estratégia, a "inteligente"?** Ela só saca quando o modelo acha
que a casa está pagando bem. Ficou no meio, e **ainda assim perdeu para nunca
sacar**. O motivo já é velho conhecido: para identificar uma oferta generosa,
você precisaria ter probabilidades melhores que as do mercado. A Fase 4 mediu que
não temos.

---

## 7. O montador de bilhetes

O montador é a peça que vira tela na Fase 8. Você diz "quero um bilhete de 5
jogos" ou "quero ganhar R$ 200 com R$ 10", e ele monta o bilhete com a **maior
chance de ganhar** que atende ao pedido.

A tabela que ele produz é o argumento da fase inteira numa figura só:

| Jogos | Prêmio de R$ 10 | Chance de ganhar | Ou seja | Comissão |
|---|---|---|---|---|
| 1 | R$ 14,50 | 76,1% | 1 em 1,3 | 1,9% |
| 3 | R$ 25,53 | 41,6% | 1 em 2,4 | 6,1% |
| 5 | R$ 55,97 | 22,4% | 1 em 4,5 | 12,7% |
| 7 | R$ 125,08 | 11,4% | 1 em 8,7 | 20,7% |
| 10 | R$ 313,63 | 4,0% | 1 em 25,1 | 31,8% |

Cada jogo a mais faz **três coisas ruins ao mesmo tempo**: multiplica a comissão,
multiplica o exagero do modelo e divide a chance de ganhar. O prêmio sobe, sim —
mas sobe menos do que a chance cai. É essa a troca que o bilhete grande esconde.

⚠️ **Dois avisos que o app da Fase 8 vai ser obrigado a mostrar na tela** (não no
rodapé, não em letra miúda):

1. a chance mostrada supõe que os jogos são independentes;
2. a chance mostrada é a do **modelo**, que exagera cerca de 4% por jogo — num
   bilhete de 7 jogos, isso são 25% de exagero.

### O gostinho de sorte

Para fechar, uma tabela que vale mais que qualquer sermão. Num bilhete de **10
jogos**, com que frequência ele termina com cada número de acertos:

| Acertos | Frequência |
|---|---|
| 5 | 20,5% |
| **6** | **24,9%** |
| 7 | 21,1% |
| 8 | 11,6% |
| 9 | 3,7% |
| **10 (ganha!)** | **0,6%** |

O resultado mais comum é **6 de 10**. Que paga zero. A experiência típica de quem
joga múltipla grande é essa: assistir à maior parte dos jogos dar certo, chegar
perto, e não receber nada.

---

## 8. Erros comuns

### `python não é reconhecido`

O ambiente não está ligado. Rode `.venv\Scripts\Activate.ps1` — deve aparecer
`(.venv)` no começo da linha.

### `ModuleNotFoundError: No module named 'futebol'`

```powershell
pip install -e ".[dev]"
```

### "Por que não tem bilhete de 1 jogo na tabela principal?"

Porque bilhete de um jogo não é múltipla: é uma aposta simples, e a Fase 6 já
mediu essas. Ele aparece só na tabela do montador, como referência.

### Quero mudar a faixa de odd das seleções

No `config.yaml`, seção `multiplas`: `odd_minima_selecao` e
`odd_maxima_selecao`. ⚠️ Mudar isso muda todos os números da fase — e cada nova
combinação testada precisa entrar na contagem da regra 11.

### Os acentos aparecem errados no PowerShell

Não afeta os arquivos gravados. Se incomodar, rode `chcp 65001` antes.

---

## 9. Como saber que está tudo certo

- [ ] `python scripts\relatorio_fase7.py` grava `docs\relatorios\fase7.md`,
      `fase7_margem.png` e `fase7_previsto_real.png`
- [ ] o relatório mostra comissão de **54,0%** no bilhete de 10 seleções
- [ ] a "razão por seleção" fica entre **0,956 e 0,963** nos nove tamanhos
- [ ] o valor esperado de "sacar após N acertos" é **idêntico para todo N**
- [ ] o `config.yaml` **não mudou** — a Fase 7 não mexe em modelo nenhum
      (regra 9)
- [ ] `pytest` mostra **590 passed** (ou 589 passed + 1 skipped, se a sua rede
      bloquear o site da fonte — o teste de rede vira *skip*, e isso é esperado)
- [ ] `ruff check .` mostra **All checks passed!**
- [ ] `git tag` mostra `fase-7`

Se todos estiverem marcados, **a Fase 7 está concluída**.

---

## O que foi criado nesta fase

| Arquivo | Para que serve |
|---|---|
| `src/futebol/backtest/multiplas.py` | Monta os bilhetes e mede previsto × real |
| `src/futebol/backtest/montador.py` | Monta por tamanho ou por prêmio alvo |
| `src/futebol/backtest/cash_out.py` | O botão de sacar, e as estratégias |
| `src/futebol/avaliacao/relatorio_fase7.py` | Monta o relatório a partir do medido |
| `scripts/relatorio_fase7.py` | Escreve o relatório e os dois gráficos |
| `docs/relatorios/fase7.md` | O relatório |

### Versão Mac/Linux dos comandos

```bash
source .venv/bin/activate
python scripts/relatorio_fase7.py
pytest
```

---

## Próximo passo

A **Fase 8** é o aplicativo — a primeira vez que o projeto vira algo que dá para
abrir e clicar, em vez de ler num arquivo de texto. Serão cinco páginas:

1. **Início**, com a explicação do projeto e o aviso de jogo responsável;
2. **Prever jogo**: escolher liga e times, ver as probabilidades e os placares
   mais prováveis;
3. **Comparar com odds**: você digita as odds que viu no site da casa, e o app
   mostra o valor esperado de cada mercado;
4. **Montar múltipla**: o montador desta fase, com os dois avisos obrigatórios;
5. **Resultados**: as tabelas das Fases 4 a 7, inclusive as ruins.

⚠️ E a Fase 8 tem uma responsabilidade que as outras não tinham: **ela é a
primeira que alguém pode usar sem ler o relatório.** Tudo o que as Fases 6 e 7
descobriram — que o modelo perde do mercado, que o filtro de valor esperado
escolhe pior que o chute, que a chance mostrada é otimista — precisa estar na
tela, e não escondido num arquivo. Um app que mostrasse só as probabilidades
bonitas seria, na prática, uma mentira com interface.

**Me avise quando quiser começar a Fase 8.**
