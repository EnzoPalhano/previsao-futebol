# Guia da Fase 3 — O primeiro modelo

> **Para quem é este guia:** para alguém que nunca programou. Cada comando está
> explicado, junto com o que deve aparecer na tela. Os comandos são para o
> **PowerShell do Windows**; no fim há a versão Mac/Linux.

**O que a Fase 3 faz:** ela constrói o **primeiro modelo do projeto**. Até agora tudo
era preparação: baixar dados (Fase 1) e medir as casas de aposta (Fase 2). Agora o
projeto passa a ter opinião própria sobre um jogo.

No fim desta fase você digita isto:

```powershell
python scripts/prever.py --mandante "Arsenal" --visitante "Chelsea"
```

e o computador responde quanto ele acha que cada resultado vale.

**Tempo estimado:** 1 minuto para a primeira previsão. O relatório completo da fase
demora uns 4 minutos, porque mede treze configurações diferentes.

---

## Índice

1. [A primeira previsão](#1-a-primeira-previsão)
2. [Lendo a resposta](#2-lendo-a-resposta)
3. [Os três modelos, em português](#3-os-três-modelos-em-português)
4. [O relatório da fase](#4-o-relatório-da-fase)
5. [O que os números dizem](#5-o-que-os-números-dizem)
6. [Os três experimentos da fase](#6-os-três-experimentos-da-fase)
7. [Duas ideias que valem o parágrafo](#7-duas-ideias-que-valem-o-parágrafo)
8. [Brincando com o comando](#8-brincando-com-o-comando)
9. [Erros comuns](#9-erros-comuns)
10. [Como saber que está tudo certo](#10-como-saber-que-está-tudo-certo)

---

## 1. A primeira previsão

```powershell
cd C:\Users\Usuario\Documents\Jogos_Probabilidade
.venv\Scripts\Activate.ps1
python scripts/prever.py --mandante "Arsenal" --visitante "Chelsea"
```

O que aparece:

```
==================================================================
ENG:Arsenal  x  ENG:Chelsea
==================================================================
Competicao : liga E0: a mais recente em que os dois jogaram (até 2026-05-24)
Data       : 2026-09-16
Modelo     : dixon_coles
Treino     : jogos anteriores a 2026-09-16 (o mais recente e de 2026-09-15)
             decaimento xi=0.0018 (meia-vida de 385 dias), rho=-0.0737
Historico  : 266 jogos do mandante e 266 do visitante nesta liga

Gols esperados: 1.88 (mandante)  x  0.91 (visitante)

1X2
  vitoria do mandante     59.4%   odd justa   1.68
  empate                  23.6%   odd justa   4.24
  vitoria do visitante    17.0%   odd justa   5.89

Gols (2,5)
  mais de 2,5 gols        53.0%   odd justa   1.89
  menos de 2,5 gols       47.0%   odd justa   2.13

Ambos marcam
  ambos marcam            51.6%   odd justa   1.94
  nao ambos marcam        48.4%   odd justa   2.06

Placares mais provaveis
  1 x 1    11.3%
  2 x 0    10.8%
  1 x 0    10.7%
  2 x 1     9.9%
  0 x 0     6.9%
```

Se você recebeu um erro em vez disso, vá para a [seção 9](#9-erros-comuns).

---

## 2. Lendo a resposta

Três coisas merecem atenção nessa tela.

**"Odd justa" não é recomendação de aposta.** Ela é só `1 ÷ probabilidade`: se o modelo
acha que o Arsenal ganha em 59,4% dos casos, a odd que pagaria exatamente o preço justo
é 1,68. A casa nunca oferece a odd justa — ela oferece um pouco menos, e essa diferença é
a comissão dela (foi o que a Fase 2 mediu). Decidir se vale apostar exige comparar as
duas, e isso é **Fase 6**.

**O placar mais provável tem 11% de chance.** Ou seja: o mais provável é que ele **não**
aconteça. Isso não é defeito do modelo, é como o futebol é. Quem promete "o placar exato
será 2x1" está vendendo certeza que não existe.

**Trocar a data muda a resposta.** O modelo é treinado com os jogos **anteriores** à data
que você pedir — nunca com o próprio jogo, nunca com o que veio depois. Experimente:

```powershell
python scripts/prever.py --mandante "Arsenal" --visitante "Chelsea" --data 2021-01-01
```

A previsão muda, porque em janeiro de 2021 o Arsenal e o Chelsea eram outros times. Essa
disciplina tem nome — evitar *data leakage* — e é o que separa um projeto honesto de um
que parece funcionar no computador e perde dinheiro na vida real.

---

## 3. Os três modelos, em português

A fase construiu três modelos. Eles existem juntos porque um serve de régua para o outro.

### `baseline` — o modelo burro

Ele não olha quem está jogando. Responde tudo com a estatística da liga: "na Premier
League, o mandante ganha 44% das vezes, então Arsenal x Chelsea é 44%, e Luton x Man City
também é 44%".

Parece inútil, e é justamente por isso que ele importa: **se um modelo esperto não
conseguir bater o burro, ele não aprendeu nada sobre os times**. É a régua mais barata
que existe.

### `poisson` — força de ataque e força de defesa

Aqui o modelo passa a conhecer os times. A ideia, que é dos anos 1980:

- cada time tem uma **força de ataque** (faz mais ou menos gol que a média da liga);
- cada time tem uma **força de defesa** (sofre mais ou menos gol que a média);
- jogar em casa dá um bônus, o **fator casa**;
- com essas três coisas, sai o número esperado de gols de cada lado — o `1.88 x 0.91`
  que aparece na tela.

Você pode ver as forças que ele estimou:

```powershell
python scripts/prever.py --mandante "Arsenal" --visitante "Chelsea" --forcas
```

No fim da tela aparece a liga inteira ordenada. Ataque `+0,52` quer dizer "faz 1,68 vez
o que um time médio da Premier League faria". Defesa positiva é defesa **boa**.

### `dixon_coles` — o Poisson com dois remendos

O Poisson tem duas falhas conhecidas, e este modelo conserta as duas:

1. **placares baixos.** 0x0 e 1x1 acontecem **mais** do que a conta do Poisson prevê, e
   1x0 e 0x1 acontecem **menos**. Faz sentido de assistir futebol: jogo travado segue
   travado, e num 1x1 tardio os dois times param de arriscar. Como 0x0 e 1x1 são empates
   e 1x0 não é, essa correção mexe direto na probabilidade de **empate**;
2. **jogo antigo pesa demais.** Para o Poisson puro, o Chelsea de 2019 conta tanto quanto
   o do mês passado. O Dixon-Coles faz o passado desbotar: cada jogo vale
   `exp(−xi × dias)`. Com o valor atual, um jogo de **385 dias atrás vale metade** de um
   jogo de hoje. É isso que aparece na tela como "meia-vida de 385 dias".

Este é o melhor modelo da fase, e é o padrão do comando.

---

## 4. O relatório da fase

```powershell
python scripts/relatorio_fase3.py
```

**Demora cerca de 4 minutos** e imprime o progresso enquanto mede. No fim:

```
Relatorio gravado: docs\relatorios\fase3.md (299 linhas)
```

Abra o arquivo `docs/relatorios/fase3.md`. Ele responde, com número, as perguntas da
fase.

⚠️ A primeira linha que ele imprime é importante:

```
89.455 jogos liberados; 27.059 trancados até a Fase 9
```

As duas temporadas mais recentes estão **trancadas por código**. Elas só serão abertas na
Fase 9, uma única vez. Se a gente as olhasse agora, todo ajuste que fizéssemos daqui até
lá seria, sem perceber, um ajuste *para acertar aquelas temporadas* — e o resultado final
deixaria de significar "o modelo funciona" e passaria a significar "o modelo decorou".

---

## 5. O que os números dizem

Esta é a tabela central do relatório (11.151 jogos previstos, 38 competições):

| Quem prevê | Log loss | Leitura |
|---|---|---|
| chute uniforme (33/33/33) | 1,0986 | nenhuma informação |
| `baseline` | 1,0746 | só a estatística da liga |
| `poisson` | 1,0263 | conhece os times |
| `dixon_coles` | **1,0192** | o melhor da fase |
| mercado de fechamento | **0,9914** | o que as casas sabem |

**Log loss é uma nota em que menor é melhor.** Ela não mede "quantos jogos acertou": mede
o quanto o modelo foi confiante nas coisas certas. Cravar 90% num jogo e errar é muito
pior que dizer 55% e errar — e é essa diferença que a nota captura. É a métrica oficial
de escolha de modelo do projeto, pela regra 9.

Duas conclusões:

**1. Os modelos funcionam.** Cada degrau da tabela é um degrau real: conhecer os times
vale mais que conhecer só a liga, e os remendos do Dixon-Coles valem mais que o Poisson
puro.

**2. O mercado ganha — e isso é o esperado.** A odd de fechamento embute lesão,
escalação, notícia de vestiário e o dinheiro de milhares de apostadores profissionais. Um
modelo que só olha placares antigos não deveria vencer isso. Se tivesse vencido de
primeira, a suspeita certa seria **erro no código**, não talento.

Então o projeto é inútil? Não. A pergunta que interessa não é "meu modelo é melhor que o
mercado em média?", mas **"existe algum jogo em que o mercado errou mais que eu?"**. Isso
é assunto da Fase 6, e é uma pergunta bem mais modesta.

---

## 6. Os três experimentos da fase

### O fator casa deve ser por liga?

A especificação pediu esse teste, e a resposta é honesta mas desconfortável: **não deu
para saber**. A diferença medida foi de 0,0006 de log loss, e a menor diferença que 11
mil jogos conseguem enxergar é 0,0012. Ou seja: a diferença observada é menor que o
ruído.

Isso é diferente de "são iguais". É "esta amostra não responde".

O projeto ficou com o fator casa **por liga** de qualquer forma, e o relatório explica por
quê — não porque ganhou o teste, mas porque o fator casa **varia muito** entre
competições:

| Liga | Mandante faz quantas vezes o que faz fora |
|---|---|
| Estados Unidos | 1,50 |
| Brasil | 1,36 |
| Dinamarca | 1,13 |
| Áustria | 1,10 |

Aplicar a vantagem de casa do futebol austríaco ao Brasileirão está errado por uma razão
física — viagem de avião, altitude, torcida — mesmo que a estatística não consiga provar
isso com um ano de dados.

### Vale fazer jogo antigo pesar menos?

Aqui deu diferença clara: ligar o decaimento melhorou a log loss em 0,0063, com margem de
erro bem longe do zero. A curva do relatório mostra um fundo em volta de uma meia-vida de
um ano — memória curta demais fica ruidosa, memória longa demais acha que o time ainda
tem o técnico de 2019.

⚠️ **O valor definitivo desse parâmetro ainda não foi escolhido.** A escolha exige o
walk-forward da Fase 4, e fazer isso agora, com uma medição mensal, seria usar a
ferramenta errada. O `config.yaml` diz `PROVISORIO` ao lado dele.

### Quanto confiar em quem tem pouca história?

O problema real: um time que acabou de subir de divisão não tem nenhum jogo naquela
divisão. O que o modelo deve achar dele?

A resposta do projeto chama-se **encolhimento**: quem tem pouca história é puxado para a
média da liga.

```
força usada ≈ (jogos do time ÷ (jogos do time + 6)) × força que os jogos dele pedem
```

O `6` é quantos jogos de história "a média da liga" vale. Com 6 jogos, o time fica na
metade do caminho; com uma temporada inteira, quase toda a força é dele; com zero jogos,
ele é simplesmente **um time médio daquela divisão** — que é a única coisa honesta a se
dizer sobre quem não se conhece.

O relatório testou de 1 a 20 e o fundo da curva ficou em 6, com a curva bem rasa entre 2
e 12. Curva rasa é boa notícia: significa que a escolha não é delicada.

---

## 7. Duas ideias que valem o parágrafo

### A matriz de placares

Os três modelos não preveem "vitória do mandante". Eles preveem **o placar** — a chance
de 0x0, de 1x0, de 2x1, de cada combinação até 10x10. Uma tabela de 121 casas.

Todo o resto sai dessa tabela por soma:

```
                 visitante 0   1   2
    mandante 0         D   A   A       vitória do mandante = triângulo de baixo
    mandante 1         H   D   A       empate = a diagonal
    mandante 2         H   H   D       vitória do visitante = triângulo de cima
```

"Mais de 2,5 gols" é a soma das casas em que os gols somam 3 ou mais. "Ambos marcam" é
tudo fora da primeira linha e da primeira coluna.

Por que isso importa: como **todas** as probabilidades saem da mesma tabela, elas nunca
podem se contradizer. Se o 1X2 e o Over/Under viessem de contas separadas, o projeto
poderia acabar apostando ao mesmo tempo em "empate" e em "muitos gols" de um jeito
incoerente — e nenhum teste perceberia.

### Por que não escolher o modelo pelo lucro

Parece óbvio escolher o modelo que teria dado mais lucro. É errado, e a regra 9 do projeto
proíbe.

O lucro de um backtest depende de algumas centenas de apostas, cada uma valendo 0 ou 1.
Nesse tamanho de amostra, a diferença entre um modelo bom e um modelo **sortudo** é
invisível. A log loss usa **todos** os 11 mil jogos e a probabilidade inteira — não só o
que deu certo — e por isso enxerga a diferença com muito menos dados.

Quem escolhe modelo por ROI está, na prática, escolhendo o modelo mais sortudo do
passado.

---

## 8. Brincando com o comando

```powershell
# um modelo diferente
python scripts/prever.py --mandante "Palmeiras" --visitante "Flamengo" --modelo poisson

# comparar os três no mesmo jogo
python scripts/prever.py --mandante "Bayern Munich" --visitante "Dortmund" --modelo baseline
python scripts/prever.py --mandante "Bayern Munich" --visitante "Dortmund" --modelo poisson
python scripts/prever.py --mandante "Bayern Munich" --visitante "Dortmund" --modelo dixon_coles

# ver as forças de toda a liga
python scripts/prever.py --mandante "Real Madrid" --visitante "Barcelona" --forcas

# uma data no passado (o Grupo 1 comeca em 2019/20; antes disso, so o Grupo 2)
python scripts/prever.py --mandante "Leicester" --visitante "Arsenal" --data 2021-01-01

# mais placares na lista
python scripts/prever.py --mandante "Ajax" --visitante "PSV Eindhoven" --placares 10

# a mesma dupla numa divisão específica
python scripts/prever.py --mandante "Sunderland" --visitante "Leeds" --liga E1
```

Uma brincadeira que ensina: peça `--modelo baseline` e depois `--modelo dixon_coles` para
um jogo muito desequilibrado (Man City x um recém-promovido). O burro dará quase o mesmo
número que daria para qualquer jogo; o Dixon-Coles dará 80% e alguma coisa. A diferença
entre os dois **é** o que o modelo aprendeu.

---

## 9. Erros comuns

### "'Atletico' pode ser mais de um time: BRA:Atletico GO, BRA:Atletico-MG"

O nome que você digitou serve para mais de um clube, e o projeto **se recusa a escolher
por você**. Existe Everton na Inglaterra e no Chile, River Plate na Argentina e no
Uruguai: um chute aqui daria uma previsão bonita sobre o time errado.

Escreva a chave inteira, ou diga a liga:

```powershell
python scripts/prever.py --mandante "BRA:Atletico-MG" --visitante "BRA:Flamengo RJ"
python scripts/prever.py --mandante "Atletico" --visitante "Sevilla" --liga SP1
```

### "Não achei nenhum time parecido com 'Grêmio'"

Os nomes são os da fonte (football-data.co.uk), e a fonte não tem todas as ligas do mundo —
só as 38 competições do projeto. Tente um pedaço do nome (`nottm`, `sheff`), que a busca
aceita.

### "data\processed\jogos.parquet não existe ainda"

Falta montar a tabela de jogos:

```powershell
python scripts/preparar_dados.py
```

### "A liga 'XX' não estava no treino"

Você pediu uma competição que não está na camada ativa do `config.yaml`. A lista de ligas
disponíveis vem na própria mensagem de erro.

### "a liga E0 nao tem nenhum jogo anterior a 2016-01-01"

A `--data` que você pediu é anterior ao começo da liga na tabela. As 22 ligas do Grupo 1
começam em **2019/20**; os 16 países do Grupo 2 (Brasil, Argentina, EUA…) vão até 2012. A
mensagem diz a data do primeiro jogo daquela liga.

### A tela mostra "NOTA: o treino inclui as temporadas de teste final"

Isso é **normal** quando você prevê um jogo de hoje: para valer, uma previsão real precisa
do histórico recente. O aviso está ali para lembrar de uma coisa: uma rodada assim nunca
pode ser usada para comparar modelos nem escolher parâmetro. Quem faz comparação é o
`relatorio_fase3.py`, e ele tranca essas temporadas.

### O relatório demora muito

São treze configurações, cada uma reajustando 38 ligas por mês da janela. Quatro minutos
é o esperado. Para só conferir que funciona:

```powershell
python scripts/relatorio_fase3.py --so-ver
```

### Os acentos aparecem errados no PowerShell

Não afeta os arquivos gravados. Se incomodar, rode `chcp 65001` antes.

---

## 10. Como saber que está tudo certo

- [ ] `python scripts/prever.py --mandante "Arsenal" --visitante "Chelsea"` mostra as
      probabilidades
- [ ] as três probabilidades do 1X2 somam 100%
- [ ] `python scripts/relatorio_fase3.py` grava `docs/relatorios/fase3.md`
- [ ] no relatório, `dixon-coles` tem log loss **menor** que `poisson`, que tem log loss
      menor que `baseline`
- [ ] no relatório, o **mercado** tem a menor log loss de todas (é o esperado!)
- [ ] `pytest` mostra **309 passed** (6 desses testes precisam de internet)
- [ ] `ruff check .` mostra **All checks passed!**
- [ ] `git tag` mostra `fase-3`

Se todos estiverem marcados, **a Fase 3 está concluída**.

---

## O que foi criado nesta fase

| Arquivo | Para que serve |
|---|---|
| `src/futebol/modelos/base.py` | O contrato dos modelos e a matriz de placares |
| `src/futebol/modelos/baseline.py` | O modelo burro, que serve de régua |
| `src/futebol/modelos/poisson.py` | Força de ataque, de defesa e fator casa |
| `src/futebol/modelos/dixon_coles.py` | Placares baixos + jogo antigo pesa menos |
| `src/futebol/consulta.py` | Traduz "Arsenal" em `ENG:Arsenal` e acha a competição |
| `src/futebol/avaliacao/divisao.py` | Tranca as temporadas de teste final até a Fase 9 |
| `src/futebol/avaliacao/relatorio_fase3.py` | Mede os modelos e escreve o relatório |
| `scripts/prever.py` | O comando de previsão |
| `scripts/relatorio_fase3.py` | Gera o relatório da fase |
| `docs/relatorios/fase3.md` | O relatório |

### Versão Mac/Linux dos comandos

```bash
source .venv/bin/activate
python scripts/prever.py --mandante "Arsenal" --visitante "Chelsea"
python scripts/relatorio_fase3.py
pytest
```

---

## Próximo passo

A **Fase 4** é a fase da honestidade. Ela constrói o *walk-forward* de verdade: em vez de
reajustar o modelo uma vez por mês, reajusta a cada rodada, do jeito que a vida real
exigiria. É de lá que sai:

1. **a escolha oficial do modelo**, por log loss (regra 9);
2. **a escolha do `xi` e do encolhimento**, que nesta fase ficaram marcados como
   provisórios;
3. **os gráficos de calibração** — onde o modelo é confiável e onde ele se engana;
4. **um teste automatizado contra data leakage**, para a disciplina virar código.

**Me avise quando quiser começar a Fase 4.**
