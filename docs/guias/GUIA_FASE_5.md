# Guia da Fase 5 — Quando a resposta é "não"

Este guia é para quem nunca programou. Os comandos são do **Windows
(PowerShell)** primeiro; a versão Mac/Linux está no fim.

A Fase 5 foi a fase de tentar o *machine learning*. O resultado dela é o mais
importante de entender do projeto inteiro, porque é um resultado **negativo**: o
modelo novo, mais moderno e mais complicado, **não** foi melhor que o antigo. E
isso é uma vitória, não um fracasso — explico por quê ao longo do guia.

---

## Índice

1. [A ideia: dar mais informação ao modelo](#1-a-ideia-dar-mais-informação-ao-modelo)
2. [O que foi construído](#2-o-que-foi-construído)
3. [Rodar a medição](#3-rodar-a-medição)
4. [O resultado](#4-o-resultado)
5. [Por que "não" é um bom resultado](#5-por-que-não-é-um-bom-resultado)
6. [Três ideias que valem o parágrafo](#6-três-ideias-que-valem-o-parágrafo)
7. [Erros comuns](#7-erros-comuns)
8. [Como saber que está tudo certo](#8-como-saber-que-está-tudo-certo)

---

## 1. A ideia: dar mais informação ao modelo

Até a Fase 4, o modelo do projeto (o **Dixon-Coles**) sabia uma coisa só:
quantos gols cada time fez e tomou nos jogos anteriores, com os jogos velhos
pesando menos. Mais nada.

Mas um torcedor sabe muito mais que isso antes de um jogo. Sabe que o mandante
jogou anteontem e está morto de cansado. Sabe que o visitante vem de cinco
vitórias seguidas. Sabe que aquele jogo foi na época de estádio vazio, quando
jogar em casa valia bem menos.

A pergunta da Fase 5 é exatamente essa: **se a gente entregar todas essas
informações a um modelo moderno, ele prevê melhor?**

O modelo moderno escolhido é o **LightGBM**. Em uma frase: ele constrói centenas
de "arvorezinhas" de perguntas do tipo *"o mandante descansou mais de 5 dias? o
Elo dele é maior que o do adversário?"*, e vai somando as respostas. Ele não
precisa que ninguém diga a fórmula — ele acha os padrões sozinho. É o tipo de
modelo que ganha competições de previsão.

---

## 2. O que foi construído

**O Elo.** Uma nota por clube, que sobe quando o time ganha e desce quando
perde. O detalhe bonito é *quanto* ela se mexe: ganhar de quem você já devia
ganhar quase não muda nada; ganhar de quem era muito melhor que você muda muito.
O Elo mede surpresa.

**As 23 "features".** *Feature* é o nome técnico de "uma informação sobre o jogo,
em forma de número". As 23 são: o Elo dos dois times e a diferença, a média de
gols feitos e sofridos nos últimos 5 e 10 jogos (contando só os jogos em casa
para o mandante e só os de fora para o visitante), os pontos dos últimos 5 jogos,
quantos dias cada time descansou, se o jogo foi na época de estádio vazio, e as
próprias probabilidades do Dixon-Coles.

**O LightGBM.** Ele prevê quantos gols cada lado vai fazer, e disso sai a tabela
de placares — a mesma de sempre, de onde saem todas as probabilidades do projeto.

⚠️ **A regra mais importante desta fase:** toda feature só pode usar jogos
**anteriores** ao jogo previsto. Parece óbvio, mas é onde quase todo projeto de
previsão esportiva se engana. Uma "média dos últimos 5 jogos" escrita sem cuidado
inclui o próprio jogo — e aí o modelo está vendo o resultado que deveria prever.
O relatório fica lindo e a aposta real perde dinheiro. Há um teste automatizado
que prova que isso não acontece: ele monta as features com a tabela inteira e
com a tabela cortada no meio, e exige que os jogos do passado saiam **idênticos**
nas duas. Se acrescentar abril mudasse alguma coisa de março, havia futuro
vazando em algum lugar.

---

## 3. Rodar a medição

Abra o PowerShell na pasta do projeto e ligue o ambiente:

```powershell
.venv\Scripts\Activate.ps1
```

Agora rode a validação com o modelo novo incluído:

```powershell
python scripts\validar.py --com-gbm
```

**Na sua máquina isso leva ~2 segundos.** A medição pesada já foi feita e está
guardada em `data\processed\` — o comando lê de lá e mostra a tabela na hora.
Ver a tabela aparecer instantaneamente é o comportamento **certo**, não um sinal
de que algo foi pulado.

Os 15 minutos aparecem só para quem começar do zero (por exemplo, clonando o
repositório noutro computador): a pasta `data/` não vai para o Git, então lá ele
precisa montar as features (~1 min) e medir as três configurações de LightGBM
(~4 min cada). Se quiser ver isso acontecer de verdade, use `--forcar`.

Tempos com o cache pronto, medidos: `validar.py --com-gbm` 2 s,
`relatorio_fase5.py` 3 s, `pytest` 22 s.

Quando terminar, gere o relatório:

```powershell
python scripts\relatorio_fase5.py
```

Isso escreve `docs\relatorios\fase5.md` e o gráfico
`docs\relatorios\fase5_importancia.png`.

---

## 4. O resultado

A tabela ficou assim, no pedaço que interessa (quanto **menor** a log loss,
melhor o modelo):

| Quem prevê | Log loss |
|---|---|
| mercado (as casas de aposta) | 0,9968 |
| **dc-xi-0.003** (o modelo da Fase 4) | **1,0194** |
| gbm-raso (LightGBM regularizado) | 1,0195 |
| dixon-coles | 1,0196 |
| gbm (LightGBM completo) | 1,0197 |
| gbm-sem-dc (LightGBM sem ajuda) | 1,0245 |

O LightGBM **não** ganhou. E a diferença para o campeão é tão pequena
(0,00013) que nem dá para dizer que ele perdeu: dá para dizer que
**empataram e a medição não consegue separá-los**.

Mas duas coisas ficaram claras de verdade:

**1. Quase tudo que o LightGBM sabe veio do Dixon-Coles.** Uma das três
configurações (`gbm-sem-dc`) foi treinada **sem** as probabilidades do
Dixon-Coles, só com Elo, forma e descanso. Ela piorou bastante. O gráfico de
importância conta a mesma história: 61% do que o modelo usa para decidir vem das
quatro colunas do Dixon-Coles.

**2. As outras informações não são inúteis — só não são novidade.** Sozinhas,
elas ainda batem um modelo simples de Poisson. Elas têm sinal. O problema é que o
Dixon-Coles já tinha capturado esse sinal por outro caminho.

Resumindo em uma frase: **o LightGBM não descobriu nada sobre futebol que o
modelo de gols já não soubesse. Ele redescobriu o modelo de gols, com mais peças
móveis.**

---

## 5. Por que "não" é um bom resultado

Esta é a parte que vale mais que todo o código da fase.

Se o projeto fosse desenhado para o LightGBM ganhar, ele ganharia. Bastaria
testar trinta configurações em vez de três e ficar com a melhor; ou medir de um
jeito um pouquinho mais frouxo; ou escolher pelo lucro simulado em vez da log
loss. Qualquer uma dessas coisas produziria um gráfico bonito, uma conclusão
empolgante — e um modelo que perde dinheiro de verdade.

As regras do projeto existem para impedir isso, e nesta fase todas elas foram
acionadas:

- **regra 9** — a escolha é por log loss, não por novidade nem por sofisticação.
  Modelo novo não entra por ser novo;
- **regra 11** — foram testadas só **três** configurações, e elas estão contadas.
  Quanto mais configurações se testa, maior a chance de a melhor estar na frente
  por **acaso**. O projeto acumula esse número desde a Fase 3 (são 29 agora) e
  vai declará-lo antes de abrir o teste final;
- **regra 10** — nenhuma diferença é reportada sem intervalo de confiança e sem
  dizer qual é o menor efeito que aquela amostra conseguiria enxergar.

O que a fase comprou foi uma informação cara e valiosa: **a complexidade não
paga aqui**. E com ela veio o direito de não carregar essa complexidade nas
fases seguintes.

⚠️ E o que foi construído **não** foi desperdiçado. O Elo e as 23 features ficam
prontos no repositório. A **Fase 7** vai trazer informação que o placar não tem —
desfalques, escalação, notícia — e é aí que um modelo como o LightGBM tem chance
real de saber algo que o Dixon-Coles não sabe. O que a Fase 5 mostrou é que, *com
o que existe hoje na tabela*, esse algo não existe.

---

## 6. Três ideias que valem o parágrafo

### Importância de feature não é utilidade de feature

O gráfico mostra que `dc_A` é a coluna mais "importante" do modelo. Isso **não**
quer dizer que ela é a mais útil. O que o gráfico mede é quanto as perguntas
feitas naquela coluna reduziram o erro **durante o treino** — e uma coluna com
muitos valores diferentes dá ao modelo mais lugares onde cortar, aparecendo alto
por isso. Pior: duas colunas que dizem a mesma coisa **dividem** o crédito entre
si, então importância baixa pode significar "repetida", e não "inútil".

O único jeito honesto de saber se uma informação paga é **tirá-la e medir de
novo**. Foi o que a configuração `gbm-sem-dc` fez. As duas leituras deram a mesma
resposta, e é essa concordância que dá confiança — não o gráfico sozinho.

### Por que o modelo é retreinado só de mês em mês

O Dixon-Coles é rápido: dá para reajustá-lo antes de cada rodada. O LightGBM é
lento — fazer o mesmo levaria horas. A solução foi retreiná-lo a cada 30 dias.

Isso continua honesto, e vale entender por quê: o modelo usado para prever um
jogo de 20 de março foi treinado com jogos anteriores a 1º de março. Ele está
**desatualizado**, nunca adiantado. Ou seja, o arranjo joga **contra** o
LightGBM, nunca a favor. Se mesmo assim ele tivesse ganhado, a conclusão seria
ainda mais forte.

### Empate não é "os dois são iguais"

Quando o relatório diz "indistinguível de zero", ele **não** está dizendo que os
dois modelos são igualmente bons. Está dizendo: *com 36 mil jogos, esta medição
não consegue separar os dois*. Pode ser que um seja um tiquinho melhor e a
amostra seja pequena demais para ver.

A diferença entre as duas frases é enorme, e o projeto sempre escreve a segunda.

---

## 7. Erros comuns

### "ModuleNotFoundError: No module named 'lightgbm'"

O ambiente não está ligado, ou as dependências não foram instaladas:

```powershell
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### O `validar.py --com-gbm` parece travado

Não está. Ele imprime uma linha por configuração medida, e cada LightGBM leva
uns 4 minutos em silêncio. Se aparecer `gbm: medindo (walk-forward, alguns
minutos)...`, está trabalhando.

### Quero refazer tudo do zero

```powershell
python scripts\validar.py --com-gbm --forcar
```

⚠️ Isso descarta o que estava guardado e remede as 16 configurações. Vai levar
bem mais de meia hora.

### Os acentos aparecem errados no PowerShell

Não afeta os arquivos gravados. Se incomodar, rode `chcp 65001` antes.

---

## 8. Como saber que está tudo certo

- [ ] `python scripts\validar.py --com-gbm` termina mostrando a tabela com 16
      configurações mais o mercado
- [ ] o escolhido continua sendo `dc-xi-0.003` — a Fase 5 **não** muda o modelo
- [ ] `docs\relatorios\fase5.md` existe, junto com
      `fase5_importancia.png`
- [ ] no `config.yaml`, `xi` e `jogos_equivalentes` **não mudaram** — a única
      linha nova da fase é a `vantagem_casa` do Elo, que é parâmetro de feature
- [ ] `pytest` mostra **434 passed** (ou 433 passed + 1 skipped, se a sua rede
      bloquear o site da fonte — o teste de rede vira *skip*, e isso é esperado)
- [ ] `ruff check .` mostra **All checks passed!**
- [ ] `git tag` mostra `fase-5`

Se todos estiverem marcados, **a Fase 5 está concluída**.

---

## O que foi criado nesta fase

| Arquivo | Para que serve |
|---|---|
| `src/futebol/modelos/elo.py` | O rating Elo, atualizado por bloco de data |
| `src/futebol/features/construtor.py` | As 23 features, todas causais |
| `src/futebol/modelos/gbm.py` | O LightGBM e o retreino a cada 30 dias |
| `src/futebol/avaliacao/relatorio_fase5.py` | Monta o relatório a partir do medido |
| `scripts/relatorio_fase5.py` | Escreve o relatório e o gráfico |
| `docs/relatorios/fase5.md` | O relatório |

### Versão Mac/Linux dos comandos

```bash
source .venv/bin/activate
python scripts/validar.py --com-gbm
python scripts/relatorio_fase5.py
pytest
```

---

## Próximo passo

A **Fase 6** é o backtest de apostas: a fase que responde *"isso teria dado
lucro?"*. Ela simula, jogo a jogo, o que teria acontecido se o projeto tivesse
apostado de verdade nas temporadas de validação:

1. **onde apostar** — só onde o modelo discorda do mercado o suficiente para
   haver valor esperado positivo, e só nas 18 ligas aprovadas na Fase 2;
2. **quanto apostar** — comparando stake fixa com Kelly fracionado;
3. **quanto disso é sorte** — e esta é a parte que interessa. Algumas centenas
   de apostas produzem ROI positivo por acaso com facilidade assustadora, e a
   Fase 6 vai mostrar isso com número, não com opinião;
4. **o CLV** — se a odd em que o projeto apostou era melhor que a odd de
   fechamento. É o sinal mais confiável de que há vantagem real, e não sorte.

⚠️ Aviso desde já, para a expectativa ficar calibrada: o modelo está **0,0226**
de log loss atrás do mercado. Não é provável que a Fase 6 mostre lucro. O
objetivo dela é medir isso com honestidade — inclusive se a resposta for
desagradável.

**Me avise quando quiser começar a Fase 6.**
