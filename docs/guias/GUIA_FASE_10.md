# Guia da Fase 10 — Desfalques: dando ao modelo o que o placar não conta

Este guia é para quem nunca programou. Os comandos são do **Windows
(PowerShell)** primeiro; a versão Mac/Linux está no fim.

O modelo do projeto olha uma coisa só: resultados passados. Ele não sabe que o
artilheiro está lesionado, que o goleiro está suspenso, que metade do time
pegou uma virose. Esta fase tenta contar isso a ele.

---

## Índice

1. [A pergunta, e por que ela é mais difícil do que parece](#1-a-pergunta-e-por-que-ela-é-mais-difícil-do-que-parece)
2. [Ver funcionando agora, sem conta em lugar nenhum](#2-ver-funcionando-agora-sem-conta-em-lugar-nenhum)
3. [Criar as chaves de API](#3-criar-as-chaves-de-api)
4. [Rodar de verdade](#4-rodar-de-verdade)
5. [Como o ajuste funciona](#5-como-o-ajuste-funciona)
6. [O LLM, e a única coisa que ele faz aqui](#6-o-llm-e-a-única-coisa-que-ele-faz-aqui)
7. [Ler o resultado (e a paciência que ele exige)](#7-ler-o-resultado-e-a-paciência-que-ele-exige)
8. [Erros comuns](#8-erros-comuns)
9. [Como saber que está tudo certo](#9-como-saber-que-está-tudo-certo)

---

## 1. A pergunta, e por que ela é mais difícil do que parece

"Se o time perdeu o artilheiro, ele fica pior — então a previsão deve piorar."
Isso é obviamente verdade, e é aí que mora a armadilha.

**O mercado já sabe da lesão.** Ela saiu no jornal. As casas de aposta leram o
mesmo jornal e já ajustaram a odd. Então a pergunta desta fase **não** é "a
lesão importa?" — é muito mais difícil:

> O projeto consegue incorporar a lesão **melhor do que o preço já incorporou**?

E há um segundo problema, que é de aritmética pura. O projeto mediu quanto
precisaria de amostra:

| Jogos observados | Menor melhora de log loss detectável |
|---|---|
| 50 (≈ 2 semanas) | 0,0585 |
| **150 (≈ 6 semanas)** | **0,0338** |
| 600 (≈ meio ano) | 0,0169 |

Agora compare: a distância **inteira** entre o modelo e o mercado é **0,0212**
(medida no teste final da Fase 9).

Ou seja: com seis semanas de jogos, o ajuste teria de **superar o mercado em
60%** só para o efeito ser detectável. Não vai acontecer. A log loss
simplesmente não consegue responder essa pergunta nessa amostra.

**Por isso o critério é o CLV**, que enxerga muito mais fino (1,60 pp com 150
apostas). E mesmo com ele:

> ⚠️ Enquanto o intervalo de confiança cruzar zero, a resposta honesta é
> **"ainda não dá para saber"** — nem "funciona", nem "não funciona".

Esta fase é uma **demonstração de engenharia**: pipeline de coleta filtrada,
extração estruturada com LLM, ajuste parametrizado e registro honesto. Ela não
é, e não pode ser, uma hipótese validada no prazo do projeto.

---

## 2. Ver funcionando agora, sem conta em lugar nenhum

```powershell
.venv\Scripts\Activate.ps1
python scripts\desfalques.py --falso
```

Isso roda o pipeline inteiro com desfalques **inventados**. Você vai ver algo
assim:

```
1. Jogos alvo dos proximos dias...
  3 jogos, 6 times alvo.
2. Desfalques...
  MODO FALSO: os desfalques abaixo sao INVENTADOS.
  2 desfalques encontrados.
3. Treinando o modelo com o que se sabe ate hoje...
4. Previsoes: crua e ajustada...
  ENG:Arsenal × ENG:Chelsea: mandante 53.8% -> 47.4% <- ajustado
  ENG:Liverpool × ENG:Everton: mandante 55.0% -> 55.0%
```

O Arsenal perdeu o atacante titular e caiu de 53,8% para 47,4%. O Liverpool não
tinha desfalque, e a previsão não mudou.

Depois abra o app e vá em **Desfalques**:

```powershell
streamlit run src\futebol\app\streamlit_app.py
```

⚠️ **O modo `--falso` grava num arquivo separado** (`registro_falso.csv`). Ele
nunca toca o caderno de verdade. Se gravasse no mesmo, previsões inventadas
entrariam na mesma tabela que as reais e a avaliação passaria a misturar as
duas — sem deixar rastro de qual era qual.

---

## 3. Criar as chaves de API

Precisa de duas, e as duas têm plano gratuito.

### 3.1 API de futebol (lesões e suspensões)

1. vá em **dashboard.api-football.com** e crie uma conta (não pede cartão);
2. no painel, copie a sua **API key**.

⚠️ **O plano gratuito dá 100 chamadas por dia.** A cota zera à meia-noite (no
horário de Londres em janeiro, uma hora antes no horário de verão) e o que
sobra **não acumula**. O projeto conta as chamadas e **para** antes de estourar —
estourar de graça derruba a sua conta pelo resto do dia.

### 3.2 API da Anthropic (ler as notícias)

1. vá em **console.anthropic.com**, crie a conta;
2. em *API Keys*, crie uma chave e copie.

Essa é paga por uso, mas o uso aqui é minúsculo: ler alguns parágrafos de
notícia por rodada.

### 3.3 Pôr as chaves no lugar

```powershell
Copy-Item .env.exemplo .env
notepad .env
```

Preencha assim (sem aspas, sem espaço depois do `=`):

```
API_FUTEBOL_CHAVE=sua_chave_aqui
ANTHROPIC_API_KEY=sua_chave_aqui
```

⚠️ **O arquivo `.env` NUNCA vai para o Git**, e isso já está garantido no
`.gitignore`. Chave de API em repositório público é chave roubada em questão de
horas — há robôs que varrem o GitHub procurando exatamente isso.

---

## 4. Rodar de verdade

```powershell
python scripts\desfalques.py
```

O pipeline faz, nesta ordem:

1. **jogos alvo** — os das próximas 7 dias, só nas 18 ligas aprovadas;
2. **times alvo** — os que jogam neles;
3. **API de futebol** — lesões e suspensões desses times;
4. **notícias** — só com o nome desses times, das últimas 72h;
5. **LLM** — lê cada notícia e devolve JSON;
6. **peso** — quanto cada jogador vale para o time dele;
7. **ajuste** — reduz a força do time;
8. **caderno** — grava as duas previsões, com o resultado vazio.

⚠️ **A ordem é "filtrar antes de buscar", e isso é o que segura a conta.** Nada é
consultado fora dos times da próxima rodada. Buscar primeiro e filtrar depois
apareceria como uma conta no fim do mês, não como um erro na tela.

Depois que os jogos acontecerem (e depois de rodar `preparar_dados.py` de novo
para baixar os resultados):

```powershell
python scripts\desfalques.py --preencher
python scripts\desfalques.py --avaliar
```

---

## 5. Como o ajuste funciona

Cada jogador que está fora contribui com:

```
peso do jogador  ×  fator do status  ×  confiança da fonte
```

**O peso** é quanto ele significa para o time — a média de três frações:
minutos jogados, participação em gols e titularidade. É o que separa "o
artilheiro está fora" de "o terceiro goleiro está fora".

⚠️ Participação em gols só conta para quem ataca. Usar ela para todo mundo
zeraria um terço do peso de todo zagueiro e faria goleiro parecer irrelevante.

⚠️ **Jogador sem estatística fica com peso ZERO** — e isso significa "não sei",
não "não importa". Ele aparece na tela (você precisa saber que a notícia
existe), mas não move a previsão. Mover seria inventar a informação que falta.

**O fator do status**: `fora` = 1, `dúvida` = 0,5 (é o `peso_duvida` do
`config.yaml`). `volta` cancela um desfalque anterior — sem isso o time iria
piorando a cada rodada para sempre.

**A confiança** vem da fonte: escalação oficial ≈ 0,9; "deve desfalcar" ≈ 0,5;
boato ≈ 0,2.

**E há um teto** (`ajuste_maximo: 0.25`). Sem ele, sete desfalques somados
fariam o time virar um amador — uma afirmação que os dados não sustentam. Quando
o teto age, a tela diz que agiu.

### O detalhe que quase inverteu tudo

No modelo, a defesa entra com **sinal invertido**: um número de defesa **maior**
significa defesa **melhor**. Então tirar um zagueiro é *subtrair* da defesa.

Somar, em vez de subtrair, faria o time **melhorar** ao perder jogador — e esse
erro **não daria erro nenhum**. A previsão sairia bem formatada e ao contrário.
Há dois testes que fazem exatamente isso: tiram um zagueiro e exigem que o
adversário passe a marcar mais.

---

## 6. O LLM, e a única coisa que ele faz aqui

Este é o único lugar do projeto onde uma IA entra. Vale ser explícito:

| O LLM faz | O LLM **não** faz |
|---|---|
| Lê um texto de notícia | Calcular probabilidade |
| Diz quem está fora e por quê | Opinar sobre o jogo |
| Estima o quanto o texto é firme | Escolher aposta |
| Devolve JSON estruturado | Encostar em qualquer número do modelo |

A probabilidade continua saindo do Dixon-Coles, que é uma conta fechada e
auditável.

**Por que a fronteira é essa.** Um LLM não tem como estimar a chance de um time
ganhar melhor que um modelo ajustado em cem mil jogos. Pedir isso a ele
produziria um número confiante, plausível e **sem origem** — exatamente o tipo
de número que este projeto inteiro foi construído para não produzir.

Extrair "Fulano está fora por lesão na coxa, segundo o ge.globo" de um parágrafo,
por outro lado, é o que ele faz melhor que qualquer regra escrita à mão.

⚠️ E o formato da resposta é **garantido pela API** (JSON Schema), não por pedir
"responda só JSON" no prompt. Pedir educadamente funciona quase sempre — e
"quase sempre", num pipeline que roda sozinho toda semana, significa quebrar
numa quinta-feira qualquer.

---

## 7. Ler o resultado (e a paciência que ele exige)

```powershell
python scripts\desfalques.py --avaliar
```

O comando responde uma de cinco coisas, e **só ele decide qual**:

| Situação | O que ele diz |
|---|---|
| Caderno vazio | "Nenhum jogo com resultado ainda" |
| Nenhum desfalque encontrado | "Não há o que comparar" |
| Menos de 30 jogos | "**Ainda não dá para saber**" |
| IC cruzando zero | "**Ainda não dá para saber**" |
| IC todo do lado bom | "É um **indício**, não uma prova" |
| IC todo do lado ruim | "O ajuste atrapalha — **desligue-o**" |

Repare que **"funciona" não está na lista.** O melhor que esta fase pode
produzir é *indício*.

E repare no último: se o ajuste piorar, a resposta certa é **desligar**, não
calibrar até ficar bonito. Calibrar até ficar bonito é o sobreajuste que a Fase 6
documentou e que o projeto inteiro evita.

### Por que não dá para fazer backtest disto

Seria muito mais rápido testar nos jogos de 2021-2024 — e é impossível.

Para saber se a notícia teria ajudado naquele jogo, seria preciso saber **o que
se sabia antes dele**. Uma notícia de hoje sobre uma lesão de 2022 não diz
quando aquilo virou público. Fingir que diz produziria um backtest lindo e
falso: o modelo "saberia" da lesão desde sempre.

Por isso a avaliação é **para frente**, e leva meses. Não tem atalho.

---

## 8. Erros comuns

### `Falta API_FUTEBOL_CHAVE`

O `.env` não existe ou está vazio. Volte à seção 3. Enquanto isso, `--falso`
mostra o pipeline funcionando.

### `O orçamento de 100 chamadas/dia acabou`

Você gastou a cota. Ela zera às 00:00 UTC e não acumula. Alternativas: esperar,
ou reduzir `noticias.dias_a_frente` no `config.yaml` (menos dias = menos
chamadas).

### `Nao deu para baixar os proximos jogos`

O site responde HTTP 302 e exige `User-Agent` — e algumas redes filtram o
domínio. É o mesmo problema já registrado nos downloads do histórico. Use
`--falso` para conferir que o resto funciona.

### "Achou desfalques mas nada mudou na previsão"

Provavelmente todos vieram com **peso zero** (sem estatísticas do jogador). O
script avisa quando isso acontece. É o comportamento certo: sem saber quanto o
jogador vale, mover a previsão seria inventar.

### "O time do desfalque não bateu com nenhum do projeto"

Os nomes da API e os do projeto são vocabulários diferentes, e ninguém mapeou um
no outro — a Fase 1 inteira foi gasta mapeando ~1.500 nomes de **uma** fonte. O
que não casa é **descartado**, nunca chutado: associar o desfalque ao time
errado é o pior erro possível aqui.

### `ModuleNotFoundError: No module named 'futebol'`

```powershell
pip install -e ".[dev]"
```

---

## 9. Como saber que está tudo certo

- [ ] `python scripts\desfalques.py --falso` roda e mostra pelo menos uma
      previsão mudando
- [ ] o app tem **oito** telas, e a última é **Desfalques**
- [ ] a tela mostra o aviso **vermelho** de "não está validado" **antes** de
      qualquer número
- [ ] `python scripts\desfalques.py --avaliar` diz "Nenhum jogo com resultado
      ainda" (com o caderno vazio)
- [ ] `data\noticias\` existe e **não** aparece no `git status`
- [ ] o `.env` **não** aparece no `git status`
- [ ] `pytest` mostra **687 passed** (ou 686 + 1 skipped, se a sua rede
      bloquear o site da fonte)
- [ ] `ruff check .` mostra **All checks passed!**
- [ ] `git tag` mostra `fase-10`

---

## O que foi criado nesta fase

| Arquivo | Para que serve |
|---|---|
| `src/futebol/noticias/tipos.py` | O vocabulário: desfalque, jogador, ajuste |
| `src/futebol/noticias/importancia.py` | Quanto um jogador vale para o time |
| `src/futebol/noticias/ajuste.py` | De desfalques para um número que o modelo entende |
| `src/futebol/noticias/fontes.py` | A API de futebol, com cota e cache |
| `src/futebol/noticias/extracao.py` | O LLM que lê notícia e devolve JSON |
| `src/futebol/noticias/jogos_alvo.py` | Os próximos jogos — o filtro que vem antes |
| `src/futebol/noticias/registro.py` | O caderno do paper trading |
| `src/futebol/app/paginas/desfalques.py` | A oitava tela |
| `scripts/desfalques.py` | O comando que roda tudo |

### Versão Mac/Linux dos comandos

```bash
source .venv/bin/activate
cp .env.exemplo .env
python scripts/desfalques.py --falso
python scripts/desfalques.py
```

---

## O fim do projeto

Esta era a última fase, e ela termina do jeito que o projeto inteiro treinou
para terminar: com um pipeline que funciona, uma hipótese registrada, e a
recusa de dizer que ela está provada.

A pergunta central do projeto já tinha resposta desde a Fase 9: **não há
vantagem demonstrável sobre as casas de aposta.** Esta fase não muda isso e não
tentou mudar — ela acrescenta uma informação nova ao modelo e monta a máquina
para medir, honestamente, se ela ajuda. A medição leva meses e o resultado mais
provável é "não faz diferença detectável".

Se isso parece um anticlímax, vale olhar de novo para o que foi construído:

- um cofre que impediu o modelo de ver o teste até o fim;
- um pré-registro com data, no histórico do Git, que impediu a configuração de
  ser escolhida depois de ver o resultado;
- uma régua ("apostar em tudo") que impede um resultado ruim de parecer bom;
- intervalos de confiança em cada número, e o menor efeito detectável ao lado;
- **687 testes**, e vários deles existem só para guardar erros que já
  aconteceram uma vez;
- um app que dá o resultado ruim na primeira tela.

Qualquer uma dessas peças ausente, e os **mesmos dados** produziriam um
relatório animador e falso. Foi mais trabalho chegar ao "não" do que teria sido
chegar a um "sim" — e é por isso que o "não" vale alguma coisa.
