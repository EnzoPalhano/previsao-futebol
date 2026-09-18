# Guia da Fase 6 — Teria dado lucro? Não.

Este guia é para quem nunca programou. Os comandos são do **Windows
(PowerShell)** primeiro; a versão Mac/Linux está no fim.

A Fase 6 é a fase que todo mundo quer ver: a que simula as apostas e diz quanto
dinheiro teria dado. A resposta é **não teria dado lucro** — e não por pouco.

Mas o número do prejuízo não é a parte interessante. A parte interessante é uma
descoberta que ninguém esperava: **apostar no chute teria dado quase o dobro
menos prejuízo do que apostar seguindo o modelo.** Explico por quê ao longo do
guia, porque o motivo é bonito e vale mais que o resultado.

---

## Índice

1. [O que a fase fez](#1-o-que-a-fase-fez)
2. [As cinco travas contra se enganar](#2-as-cinco-travas-contra-se-enganar)
3. [Rodar o backtest](#3-rodar-o-backtest)
4. [O resultado](#4-o-resultado)
5. [A descoberta: por que o chute foi melhor](#5-a-descoberta-por-que-o-chute-foi-melhor)
6. [Por que a banca quebrou (e o que isso não quer dizer)](#6-por-que-a-banca-quebrou-e-o-que-isso-não-quer-dizer)
7. [Quatro ideias que valem o parágrafo](#7-quatro-ideias-que-valem-o-parágrafo)
8. [Erros comuns](#8-erros-comuns)
9. [Como saber que está tudo certo](#9-como-saber-que-está-tudo-certo)

---

## 1. O que a fase fez

A pergunta é simples: **se o projeto tivesse apostado de verdade entre julho de
2021 e junho de 2024, o que teria acontecido com o dinheiro?**

Para responder, o código percorre jogo por jogo e, em cada um, faz cinco
perguntas — uma para cada coisa em que dá para apostar:

| A aposta | Quando o modelo aposta |
|---|---|
| vitória do mandante | quando ele acha a chance **maior** do que a odd sugere |
| empate | idem |
| vitória do visitante | idem |
| mais de 2,5 gols | idem |
| menos de 2,5 gols | idem |

A conta que decide chama-se **valor esperado**, ou **EV**:

```
EV = (o que o modelo acha que vai acontecer) × (a odd oferecida) − 1
```

Um exemplo concreto. A casa paga **2,00** na vitória do mandante — ou seja, ela
está dizendo "isso acontece em 50% das vezes". O modelo olha e diz "não, isso
acontece em 60%". Então:

```
EV = 0,60 × 2,00 − 1 = +0,20  →  o modelo acha que ganha 20 centavos
                                 por real apostado, em média
```

O projeto só aposta quando esse número passa de **5%**. É a régua padrão do
`config.yaml`, e a fase testou também 0%, 2% e 10% para ver se mudava alguma
coisa.

**Números da simulação:**

- 20.189 jogos apostáveis, nas 18 ligas aprovadas na Fase 2;
- 100.945 oportunidades de aposta (5 por jogo);
- **21.682 apostas** passaram no filtro de EV;
- 3 temporadas.

---

## 2. As cinco travas contra se enganar

Backtest de aposta é um campo minado. Dá para produzir lucro em quase qualquer
um deles se você for descuidado — ou desonesto. Estas são as travas, e cada uma
tem um teste automatizado atrás:

**1. Aposta-se na odd MÉDIA, nunca na máxima.** A fonte traz as duas: a média de
umas vinte casas e a maior delas. Apostar na maior parece inofensivo e é o erro
que invalida a maioria dos projetos de aposta que se acham na internet — porque
a odd máxima quase sempre é uma casa pequena, uma odd digitada errada ou uma
aposta com limite de cinquenta reais. Você não conseguiria apostar nela de
verdade.

**2. A odd de fechamento nunca escolhe aposta.** "Fechamento" é a odd no momento
em que o jogo começa. Ela é melhor que a odd de horas antes, porque já embute
lesão, escalação e o dinheiro de quem sabe. Usá-la para decidir seria trapaça:
na hora de apostar, ela ainda não existia. Ela entra só para uma coisa, o CLV,
que explico adiante.

**3. Só as 18 ligas aprovadas.** As 16 competições do Grupo 2 (Brasileirão
incluído) têm só odd de fechamento — nelas não existe aposta possível. E 4 ligas
do Grupo 1 foram reprovadas no filtro da Fase 2 por comissão alta demais.

**4. Jogo sem odd é pulado e contado.** Foram 32, de 20.221. O número aparece no
relatório porque jogo sem odd **não é um jogo sorteado ao acaso** — costuma ser
time pequeno ou jogo adiado, e sumir com eles em silêncio enviesaria o resultado.

**5. Todo número sai com margem de erro.** Nenhum ROI aparece sozinho. Sempre com
o intervalo de confiança, o número de apostas e — o mais importante — **o menor
efeito que aquela amostra conseguiria enxergar**. Sem isso, "não achei vantagem"
fica indistinguível de "não dava para saber", e as duas frases significam coisas
completamente diferentes.

---

## 3. Rodar o backtest

```powershell
.venv\Scripts\Activate.ps1
python scripts\backtest.py
```

Leva menos de um minuto, porque ele lê as previsões que a Fase 4 já tinha
guardado. Dá para mexer nos parâmetros:

```powershell
python scripts\backtest.py --ev 0.10          # só aposta com EV acima de 10%
python scripts\backtest.py --liga E0          # só a Premier League
python scripts\backtest.py --grade            # compara os quatro limites de EV
python scripts\backtest.py --gravar           # grava cada aposta num CSV
```

E, para gerar o relatório completo com as tabelas e os dois gráficos:

```powershell
python scripts\relatorio_fase6.py
```

O relatório fica em `docs\relatorios\fase6.md`.

---

## 4. O resultado

| | |
|---|---|
| Apostas | **21.682** |
| Taxa de acerto | 31,9% (odd média 3,80) |
| **ROI** | **−12,92%** — a cada 100 reais apostados, voltaram 87 |
| Margem de erro do ROI | de −14,97% a −10,89% |
| **CLV** | **−7,82%** |
| Margem de erro do CLV | de −7,95% a −7,69% |

**ROI** quer dizer *retorno sobre o investimento*: o lucro dividido por tudo o
que foi apostado. −12,92% significa que, de cada real que passou pela mesa, doze
centavos e meio não voltaram.

E o resultado é o mesmo em toda parte:

- negativo nas **18 ligas de 18**;
- negativo nas **3 temporadas de 3**;
- negativo nas **5 seleções** (mandante, empate, visitante, over, under);
- negativo nos **4 limites de EV** testados.

⚠️ **Uma coisa importante sobre o tamanho da amostra.** A especificação do
projeto admite três conclusões possíveis para esta fase: "há vantagem", "não há
vantagem" e — a terceira, que quase sempre é a honesta — **"a amostra é pequena
demais para decidir"**.

A terceira **não** é o caso aqui, e é bom entender por quê. Com 21.682 apostas, a
menor vantagem (ou desvantagem) que a amostra consegue enxergar é de **2,03%**. O
que foi medido é **−12,92%**, seis vezes maior que isso. Não é ruído. É uma
desvantagem grande, medida com folga.

---

## 5. A descoberta: por que o chute foi melhor

Aqui está a parte que vale a fase.

O relatório compara o modelo com dois apostadores de mentira:

| Quem aposta | ROI |
|---|---|
| **o modelo** (EV > 5%) | **−12,92%** |
| alguém que sorteia as apostas no chute | −5,78% |
| alguém que aposta em absolutamente tudo | −6,88% |

Leia de novo: **apostar no chute perde menos da metade do que apostar seguindo o
modelo.** O modelo não está apenas "sem vantagem" — ele está encontrando
sistematicamente a desvantagem. E, mais estranho ainda, quanto mais o filtro
aperta, pior fica:

| Limite de EV | Apostas | ROI |
|---|---|---|
| acima de 0% | 33.475 | −11,36% |
| acima de 2% | 28.291 | −11,99% |
| acima de 5% | 21.682 | −12,92% |
| acima de 10% | 13.569 | −15,25% |

Se o modelo tivesse alguma vantagem escondida, exigir **mais** EV deveria
concentrar as apostas boas e melhorar o ROI. Acontece o contrário, sem exceção.

### O mecanismo, em três passos

**Passo 1: a comissão da casa não é igual em toda aposta.** Ela é pequena no
favorito e enorme no azarão:

| Odd da aposta | Quanto a casa cobra |
|---|---|
| até 1,50 | cerca de 2% |
| 2,00 a 3,00 | cerca de 6,5% |
| 5,00 a 10,00 | cerca de 13% |
| acima de 10,00 | **mais de 21%** |

Isso não é novidade no projeto: foi exatamente esse comportamento que fez o
método `power` vencer os outros na hora de tirar a margem das odds, lá na Fase 2.
Agora ele voltou para cobrar a conta.

**Passo 2: a fórmula do EV multiplica pela odd.** Olhe de novo:
`EV = probabilidade × odd − 1`. Suponha que o modelo erre 2 pontos percentuais
para cima, o que é um erro pequeno:

- num favorito, ele diz 62% em vez de 60%. Na odd 1,60, o EV sobe de −0,04 para
  −0,01. Quase nada;
- num azarão, ele diz 12% em vez de 10%. Na odd 9,00, o EV sobe de −0,10 para
  **+0,08** — e a aposta aparece como "oportunidade".

**Passo 3: junte os dois.** O filtro de EV não seleciona "onde o modelo sabe
mais". Ele seleciona **onde o modelo erra para cima** — e esse lugar é
sistematicamente o azarão, que é justo onde a casa cobra mais caro. Dá para ver
acontecendo na odd média: 2,86 entre todas as apostas possíveis, 3,80 entre as
que o modelo escolheu, 4,35 quando o filtro aperta para 10%.

O modelo está se mudando, sozinho, para o bairro mais caro do mercado.

⚠️ **A lição que sobrevive a esta fase, e que vale para qualquer projeto de
aposta:** com um modelo que perde do mercado, o filtro de EV **não é um filtro de
qualidade — é um amplificador do erro do modelo.** Ele só funcionaria se as
probabilidades do modelo fossem melhores que as do mercado em algum canto. A
Fase 4 já tinha medido que não são (0,0226 de log loss atrás). A Fase 6 mostrou
quanto isso custa em dinheiro.

---

## 6. Por que a banca quebrou (e o que isso não quer dizer)

O relatório mostra quatro formas de administrar o dinheiro, e **as quatro
zeram a banca**:

| Como aposta | Partindo de R$ 1.000 | Sobreviveu até |
|---|---|---|
| 1% fixo da banca inicial | R$ 0,00 | 15/09/2021 |
| 1% da banca atual | R$ 0,00 | fim da janela |
| Kelly 1/4 sobre a banca inicial | R$ 0,00 | 15/09/2021 |
| Kelly 1/4 sobre a banca atual | R$ 0,00 | fim da janela |

⚠️ **Cuidado com a conclusão aqui, porque é fácil tirar a errada.** A ruína da
banca mistura duas coisas bem diferentes:

**A parte que fala do modelo** é o ROI por unidade apostada (−12,92%). Esse
número mede a qualidade das escolhas e não depende de política de dinheiro
nenhuma.

**A parte que fala da política de aposta** é a quebra. O modelo aponta **28
apostas por dia**, em média. Apostar 1% da banca em cada uma delas significa pôr
**28% da banca em risco por dia** — e isso é inviável mesmo com um modelo
vencedor. A banca quebraria de qualquer jeito numa sequência ruim. O `config.yaml`
foi escrito pensando em poucas apostas por semana, não em 28 por dia.

Ou seja: a quebra **não é evidência extra contra o modelo**. É evidência de que
1% por aposta é demais quando se aposta 28 vezes ao dia. As duas coisas aparecem
separadas no relatório de propósito.

### As duas variantes de banca, e por que as duas aparecem

**Banca fixa**: a aposta sai sempre de 1% dos R$ 1.000 iniciais — dez reais hoje,
dez reais daqui a dois anos.

**Banca composta**: a aposta sai de 1% do que você tem **agora**. Ganhou, aposta
mais; perdeu, aposta menos.

A especificação exige as duas lado a lado, e o motivo é bem específico: a
composta **infla** o resultado numa série vencedora e **disfarça** o estrago numa
perdedora (quem aposta cada vez menos nunca chega exatamente a zero). Mostrar só
uma das duas é uma das maneiras mais comuns de escrever um relatório de aposta
enganoso sem dizer nenhuma mentira.

---

## 7. Quatro ideias que valem o parágrafo

### O CLV, e por que ele é o critério principal

**CLV** quer dizer *closing line value* — "o valor da linha de fechamento". A
ideia: compare a odd que você pegou com a odd com que o jogo fechou. Se você
pegou 2,20 numa aposta que fechou em 2,00, você comprou barato. Você sabia algo
que o mercado só descobriu depois.

O que torna o CLV especial é que **ele não depende do resultado do jogo**. São só
dois preços. Por isso ele é muito menos barulhento que o ROI — neste projeto,
**quinze vezes** menos. Na prática:

- para enxergar o ROI medido, seriam necessárias 536 apostas;
- para enxergar o CLV medido, bastariam **6**.

É por isso que o CLV foi promovido a critério primário do projeto. Ele é o único
sinal de vantagem que dá para medir de verdade nesta escala.

O CLV do modelo foi **−7,82%**, com margem de erro de apenas 0,13 ponto. Não é
dúvida; é um "não" medido com três casas decimais.

### O ROI precisa de uma quantidade absurda de apostas

Uma aposta em odd 2,00 tem **100% de volatilidade**: você ganha 1 ou perde 1. Com
esse tanto de barulho, para confirmar um ROI verdadeiro de **+2%** — que seria um
resultado excelente e realista — seriam necessárias cerca de **22.400 apostas**.

Este backtest tem 21.682. Ou seja: mesmo com 18 ligas e três temporadas, o
projeto **ainda não teria poder** para confirmar uma vantagem pequena pelo ROI.
Isso não é um defeito do projeto — é a razão pela qual a escolha de modelo é por
log loss (regra 9) e o critério primário é o CLV.

### "Testamos 16 configurações" está escrito no relatório

Quatro limites de EV × duas estratégias de stake × dois tipos de banca = **16
combinações**. O relatório diz isso em voz alta, porque testar muitas
combinações e mostrar só a melhor é a forma mais fácil de inventar um resultado.
Aqui nenhuma das 16 deu positivo, então não há vencedor para desconfiar — mas o
número fica registrado do mesmo jeito, porque a regra existe para ser cumprida
**antes** de saber o resultado.

### O que a simulação ainda não cobra

Ela aposta na média do mercado, sem limite de aposta, sem conta limitada pela
casa, sem odd que sumiu antes do clique e sem comissão de saque. Todas essas
fricções puxam o resultado real para **baixo** do simulado. Um backtest empatado
já seria perdedor na vida real — e este nem empatado está.

---

## 8. Erros comuns

### `python não é reconhecido`

O ambiente não está ligado. Rode `.venv\Scripts\Activate.ps1` — deve aparecer
`(.venv)` no começo da linha.

### `ModuleNotFoundError: No module named 'futebol'`

```powershell
pip install -e ".[dev]"
```

### O backtest reclama de liga desconhecida

`--liga` só aceita as 18 aprovadas na Fase 2. A mensagem de erro lista todas.
Pedir `SC1`, por exemplo, dá erro de propósito: ela foi reprovada por comissão
alta (8,45%).

### Quero refazer as previsões do zero

```powershell
python scripts\backtest.py --forcar
```

⚠️ Isso descarta o que estava guardado e reroda o walk-forward inteiro do modelo
oficial. Leva alguns minutos.

### Os acentos aparecem errados no PowerShell

Não afeta os arquivos gravados. Se incomodar, rode `chcp 65001` antes.

---

## 9. Como saber que está tudo certo

- [ ] `python scripts\backtest.py` termina mostrando ROI de **−12,92%** e CLV de
      **−7,82%**
- [ ] `python scripts\relatorio_fase6.py` grava `docs\relatorios\fase6.md`,
      `fase6_banca.png` e `fase6_lucro_acumulado.png`
- [ ] o relatório diz **0 de 18** ligas com ROI positivo e **0 de 18** com CLV
      positivo
- [ ] o `config.yaml` **não mudou** — a Fase 6 não mexe em modelo nenhum
      (regra 9)
- [ ] `pytest` mostra **511 passed** (ou 510 passed + 1 skipped, se a sua rede
      bloquear o site da fonte — o teste de rede vira *skip*, e isso é esperado)
- [ ] `ruff check .` mostra **All checks passed!**
- [ ] `git tag` mostra `fase-6`

Se todos estiverem marcados, **a Fase 6 está concluída**.

---

## O que foi criado nesta fase

| Arquivo | Para que serve |
|---|---|
| `src/futebol/backtest/estrategias.py` | Stake fixa, Kelly e as duas variantes de banca |
| `src/futebol/backtest/simulador.py` | Escolhe as apostas, mede ROI e CLV |
| `src/futebol/avaliacao/metricas.py` | Ganhou o tamanho de amostra e o bootstrap |
| `src/futebol/avaliacao/relatorio_fase6.py` | Monta o relatório a partir do medido |
| `scripts/backtest.py` | Roda o backtest na linha de comando |
| `scripts/relatorio_fase6.py` | Escreve o relatório e os dois gráficos |
| `docs/relatorios/fase6.md` | O relatório |

### Versão Mac/Linux dos comandos

```bash
source .venv/bin/activate
python scripts/backtest.py
python scripts/relatorio_fase6.py
pytest
```

---

## Próximo passo

A **Fase 7** é o simulador de múltiplas e cash out — a fase que mede, com dados,
o que acontece com quem junta várias apostas num bilhete só.

A expectativa já dá para calibrar com o que esta fase mostrou. Numa múltipla, as
comissões da casa **se multiplicam**: uma dupla de duas apostas com 6% de
comissão cada não custa 6%, custa cerca de 12%. E, como a Fase 6 acabou de medir,
o modelo já perde 7,8% em cada aposta isolada.

A Fase 7 também tem um ponto conceitual delicado, que a especificação manda
tratar de frente: a chance de uma múltipla acertar é calculada como o produto das
chances individuais, e isso **superestima** a chance real, porque os jogos não são
independentes de verdade. O projeto vai documentar essa limitação e **medir o
tamanho do erro** — comparando quantas múltiplas de 2, 3, 4… seleções realmente
acertaram contra quantas o modelo previa. Se o desvio crescer com o tamanho da
múltipla, é a correlação aparecendo, e isso vira um dos resultados mais
interessantes do projeto.

**Me avise quando quiser começar a Fase 7.**
