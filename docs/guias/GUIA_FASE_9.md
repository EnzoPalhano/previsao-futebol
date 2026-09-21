# Guia da Fase 9 — O teste final: a resposta, uma vez

Este guia é para quem nunca programou. Os comandos são do **Windows
(PowerShell)** primeiro; a versão Mac/Linux está no fim.

Esta é a última fase obrigatória do projeto, e a mais séria — porque ela só pode
ser feita **uma vez**.

---

## Índice

1. [O que é um "cofre" e por que ele existe](#1-o-que-é-um-cofre-e-por-que-ele-existe)
2. [O que foi registrado antes de abrir](#2-o-que-foi-registrado-antes-de-abrir)
3. [Rodar o teste final](#3-rodar-o-teste-final)
4. [O resultado](#4-o-resultado)
5. [Dois defeitos que apareceram no caminho](#5-dois-defeitos-que-apareceram-no-caminho)
6. [Publicar o app](#6-publicar-o-app)
7. [Erros comuns](#7-erros-comuns)
8. [Como saber que está tudo certo](#8-como-saber-que-está-tudo-certo)

---

## 1. O que é um "cofre" e por que ele existe

Imagine que você inventa um método para prever futebol e testa nos jogos de
2021 a 2024. Você mexe num parâmetro, testa de novo, melhora. Mexe em outro,
testa, melhora mais. Depois de cinquenta tentativas, seu método acerta lindamente
os jogos de 2021 a 2024.

**Isso não quer dizer nada.** Você não descobriu como prever futebol: você
descobriu como descrever 2021–2024. É a diferença entre saber a matéria e ter
decorado a prova — e a única forma de saber qual dos dois aconteceu é aplicar
uma prova que a pessoa nunca viu.

Por isso, desde a Fase 1, duas temporadas inteiras ficaram **trancadas**:
**2024/25 e 2025/26**, com 24.779 jogos. Nenhum modelo as viu. Nenhum parâmetro
foi escolhido olhando para elas. Nenhum backtest as usou. Existe código que
impede o acesso (`futebol/avaliacao/divisao.py`), e ele não é um aviso — é uma
tranca.

⚠️ **E o cofre só vale por causa da promessa de não repetir.** Se fosse
permitido abrir, não gostar do resultado, mexer num parâmetro e abrir de novo, as
temporadas trancadas deixariam de ser uma prova e virariam mais um caderno de
exercícios. O número final não significaria nada.

---

## 2. O que foi registrado antes de abrir

Antes de abrir o cofre, era preciso escrever **exatamente** o que ia ser testado.
Isso se chama **pré-registro**, e existe para impedir um truque que engana até
quem o faz sem querer: abrir o cofre, olhar dez configurações, escolher a que
saiu melhor e apresentá-la como "o resultado".

Escolher depois de ver é escolher o acaso.

O que ficou registrado em 21/09/2026:

| O quê | Valor |
|---|---|
| Modelo | Dixon-Coles, `xi = 0,003`, `m = 6` |
| Mercados | Resultado (1X2) + Mais/Menos de 2,5 gols |
| Odd | **média pré-jogo** — nunca a máxima |
| Aposta quando | o valor esperado passa de **5%** |
| Quanto apostar | **1% da banca**, fixo |
| Ligas | as **18** aprovadas na Fase 2 |
| Configurações testadas antes | **108** |

⚠️ **Duas coisas que valem reparar aqui.**

**Primeira: o limite de 5% é o pior dos quatro que o projeto mediu.** A Fase 6
descobriu que quanto mais apertado o filtro de valor esperado, pior o resultado.
Registrar 5% assim mesmo é justamente o ponto — a alternativa seria abrir o
cofre, olhar os quatro e escolher o vencedor, que é exatamente o truque descrito
acima.

**Segunda: o pré-registro está guardado em dois lugares, e o segundo é o que
vale.** Ele mora no `CLAUDE.md`, como a especificação manda — só que esse arquivo
não vai para o Git, então ninguém consegue provar *quando* ele foi escrito. Por
isso a configuração também está congelada em código
(`src/futebol/avaliacao/teste_final.py`), e o commit que a introduz tem data e
vem **antes** do commit que traz o resultado. Essa ordem no histórico é a única
testemunha possível.

E há uma trava: antes de abrir o cofre, o programa compara o pré-registro com o
`config.yaml`. Se alguém tiver mexido na configuração depois, ele **para** em vez
de rodar com valores diferentes dos registrados.

---

## 3. Rodar o teste final

```powershell
.venv\Scripts\Activate.ps1
python scripts\teste_final.py
```

Demora alguns minutos na primeira vez (o modelo é reajustado antes de cada
rodada de cada liga, 8.914 vezes).

Se quiser só ver o resultado sem gravar nada:

```powershell
python scripts\teste_final.py --so-ver
```

---

## 4. O resultado

```
  CLV ............ -9,02%  IC -9,18% a -8,85%   <- criterio primario
  ROI ............ -14,41% IC -17,00% a -11,80%
  regua (tudo) ... ROI -7,41% em 65.715 candidatas
  log loss ....... modelo 1,0240 x mercado 1,0028

  NAO 1. CLV médio positivo, com o intervalo de 95% inteiro acima de zero
  NAO 2. Consistência em mais de uma liga e mais de uma temporada
  OK  3. Configuração pré-registrada antes de abrir o teste final
  NAO 4. ROI positivo, com o intervalo de 95% inteiro acima de zero
  OK  5. Pelo menos 5.000 apostas simuladas

  VEREDITO: SEM vantagem demonstravel
```

**Traduzindo:** apostando R$ 100 por aposta ao longo das duas temporadas, você
teria perdido cerca de **R$ 14 a cada R$ 100 apostados**. E apostando **em tudo**,
sem modelo nenhum, teria perdido R$ 7,41 — ou seja, **o modelo atrapalhou**.

CLV positivo em **0 de 18 ligas** e **0 de 2 temporadas**. Não há um cantinho
onde funcione.

### Mas tem uma notícia boa, e ela é a mais interessante do relatório

O modelo ficou a **0,0212** de distância do mercado. Na validação, essa distância
era **0,0226**.

Ou seja: **o modelo não piorou nos dados novos.** Ele é exatamente o que sempre
foi. Isso importa porque o jeito mais comum de um projeto de ML se enganar é
parecer ótimo no treino e desabar nos dados novos — e não foi o que aconteceu
aqui. O modelo é honesto; ele só é pior que o mercado.

⚠️ E se a distância tivesse ficado **muito menor**? A reação certa seria
desconfiar, não comemorar. Modelo que melhora em dados que nunca viu quase sempre
significa que os dados vazaram de algum lugar.

### Por que o CLV é o critério que decide

O CLV compara a odd que você pegou com a odd na hora em que o jogo começou. Ele
**não depende do resultado da partida** — e por isso é muito menos sujeito à
sorte que o ROI. Nesta amostra, o CLV enxergaria um efeito **15 vezes menor** que
o ROI conseguiria.

É a diferença entre "perdi porque o modelo é ruim" e "perdi porque a bola bateu
na trave". O CLV responde a primeira.

---

## 5. Dois defeitos que apareceram no caminho

Vale contar, porque os dois eram graves e nenhum deles aparecia como erro.

### O primeiro: 4.261 jogos entraram no teste final sem poder

O teste final avalia por **data**, mas as temporadas são definidas por **nome**.
A temporada europeia 2023/24 termina em **maio de 2024** — depois de 25 de
janeiro de 2024, que é quando o Brasileirão 2024 começa e a janela do teste abre.

Resultado: 4.261 jogos de 2023/24 entraram na "prova" — e eram jogos que o
projeto já tinha visto nas fases anteriores. **A primeira rodada foi descartada**
e refeita com o recorte certo (16.323 apostas viraram 13.163).

Não era vazamento do futuro — cada previsão continuou vendo só o passado dela. Era
**contaminação da prova**, que é outra coisa e igualmente fatal: uma prova feita
em parte com questões que o aluno já tinha resolvido.

### O segundo: o app passou a mostrar o cofre

O teste final gravou seus resultados num arquivo com o **mesmo nome de modelo**
dos arquivos da validação, mudando só a janela de datas. O app escolhia o arquivo
pelo nome do modelo — e passou a pegar o do teste final. Ou seja: a tela que
**nunca** pode mostrar as temporadas trancadas começou a lê-las.

O que denunciou foi o app quebrar. **Isso foi sorte.** Se os dados tivessem
encaixado, a tela mostraria o cofre sem erro nenhum, e ninguém perceberia.

Os dois viraram teste automatizado.

---

## 6. Publicar o app

O app precisa da tabela de jogos, e ela **não vai para o Git** (são mais de cem
mil partidas). Um site publicado assim sobe o código, não acha os dados e quebra
na primeira tela.

A saída escolhida na Fase 8 (e medida): versionar uma cópia reduzida.

```powershell
python scripts\preparar_deploy.py
```

Isso grava em `data\app\`:

| Arquivo | Tamanho |
|---|---|
| `jogos.parquet` | 1,44 MB |
| `previsoes_dc-xi-0.003.parquet` | 2,61 MB |

Os dois abaixo do limite de 5 MB que o projeto se impôs, e o script confere isso
antes de deixar você commitar.

⚠️ **E esses arquivos já vêm sem as temporadas trancadas.** Não é para economizar
espaço: é porque num servidor não há ninguém conferindo, e a forma mais segura de
a regra valer é **o dado nem estar lá**.

---

## 7. Erros comuns

### `PARADO: O config.yaml mudou depois do pré-registro`

Alguém alterou a configuração depois de 21/09/2026. O teste final só vale com a
configuração registrada — reverta o `config.yaml`.

⚠️ **Não faça o contrário** (mudar o pré-registro para bater com o config): isso
é escolher depois de ver, que é exatamente o que o pré-registro existe para
impedir.

### "Posso rodar de novo?"

O relatório, sim — quantas vezes quiser, e vai dar o mesmo resultado (o cálculo
pesado fica guardado). O que **não** se pode é mudar um parâmetro e rodar de
novo. Aí o cofre perde o valor, e não tem como recuperá-lo.

### `ModuleNotFoundError: No module named 'futebol'`

```powershell
pip install -e ".[dev]"
```

### "Nenhuma aposta passou no filtro de EV"

Sinal de que a janela ou as odds não chegaram — não é um resultado. Confira se
`python scripts\preparar_dados.py` rodou.

---

## 8. Como saber que está tudo certo

- [ ] `python scripts\teste_final.py` grava `docs\relatorios\final.md` e os dois
      gráficos
- [ ] o relatório mostra **CLV −9,02%** e **ROI −14,41%** em **13.163** apostas
- [ ] a tabela dos cinco critérios mostra ❌ nos critérios 1, 2 e 4 e ✅ nos 3 e 5
- [ ] o `config.yaml` **não mudou** — o teste final não altera nada (regra 9)
- [ ] `python scripts\preparar_deploy.py` grava os dois arquivos em `data\app\`,
      os dois abaixo de 5 MB
- [ ] `pytest` mostra **629 passed** (ou 628 passed + 1 skipped, se a sua rede
      bloquear o site da fonte)
- [ ] `ruff check .` mostra **All checks passed!**
- [ ] `git tag` mostra `fase-9`

Se todos estiverem marcados, **a Fase 9 está concluída — e o projeto também.**

---

## O que foi criado nesta fase

| Arquivo | Para que serve |
|---|---|
| `src/futebol/avaliacao/teste_final.py` | O pré-registro congelado e a abertura do cofre |
| `src/futebol/avaliacao/relatorio_final.py` | O relatório, com o critério de parada aplicado |
| `scripts/teste_final.py` | O comando que roda uma vez |
| `scripts/preparar_deploy.py` | Os dados reduzidos do app publicado |
| `docs/relatorios/final.md` | **O relatório final do projeto** |
| `tests/test_teste_final.py` | As travas do pré-registro e da janela |

### Versão Mac/Linux dos comandos

```bash
source .venv/bin/activate
python scripts/teste_final.py
python scripts/preparar_deploy.py
pytest
```

---

## O fim do projeto

O projeto respondeu a pergunta que se propôs a responder, e a resposta foi
**não**.

Vale dizer em voz alta o que isso significa e o que não significa.

**O que não significa:** que o modelo seja ruim em prever futebol. Ele fica a
0,02 de log loss de um mercado que agrega milhares de apostadores com informação
que este projeto não tem — escalação, lesão, motivação, dinheiro grande. Chegar
perto disso com placar e nada mais é um resultado respeitável.

**O que significa:** que não dá para ganhar dinheiro com ele. E isso era a
hipótese de partida, escrita na primeira linha da especificação, antes de
qualquer código existir.

**E por que isso é o produto.** O que foi construído aqui não é um modelo de
futebol: é uma **máquina de não se enganar**. O cofre que impediu o modelo de ver
a prova. O pré-registro que impediu a configuração de ser escolhida depois. O
intervalo de confiança em cada número. A régua de "apostar em tudo", que impede
um resultado ruim de parecer bom. A regra de escolher modelo por log loss e nunca
por lucro. O teste que pegou 4.261 jogos contaminando a prova.

Tire qualquer uma dessas peças e os **mesmos dados** produziriam um relatório
animador e falso. É por isso que o resultado negativo custou mais trabalho que um
positivo custaria — e é por isso que ele vale mais.

A **Fase 10** (notícias e desfalques) é opcional e está descrita na
especificação. Ela não muda esta conclusão: é uma demonstração de engenharia de
dados e uso de LLM, e a própria especificação avisa que, no prazo do projeto, ela
não pode ser validada estatisticamente.
