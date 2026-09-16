# Guia da Fase 1 — Trazendo os jogos para dentro do projeto

> **Para quem é este guia:** para alguém que nunca programou. Cada comando está explicado,
> junto com o que deve aparecer na tela quando dá certo e o que fazer quando dá errado.
> Os comandos são para o **PowerShell do Windows**; no fim há a versão Mac/Linux.

**O que a Fase 1 faz:** ela pega os arquivos de resultados e odds do site
football-data.co.uk, confere se eles ainda são do jeito que esperávamos, limpa tudo e junta
numa **tabela única de jogos**. Nenhum modelo é treinado ainda, nenhuma aposta é simulada.

Pense num caderno de receitas onde cada página veio de um lugar diferente: umas em português,
outras em inglês, umas com "farinha" e outras com "flour". Antes de cozinhar, alguém precisa
copiar tudo para um caderno só, com as mesmas palavras. É isso que a Fase 1 faz.

**Tempo estimado:** 5 minutos para rodar.

---

## Índice

1. [Antes de começar](#1-antes-de-começar)
2. [Baixar os dados](#2-baixar-os-dados)
3. [Montar a tabela de jogos](#3-montar-a-tabela-de-jogos)
4. [Ver o relatório de cobertura](#4-ver-o-relatório-de-cobertura)
5. [Rodar os testes](#5-rodar-os-testes)
6. [O que o projeto aprendeu sobre os dados](#6-o-que-o-projeto-aprendeu-sobre-os-dados)
7. [Quando você quiser ligar mais ligas](#7-quando-você-quiser-ligar-mais-ligas)
8. [Erros comuns](#8-erros-comuns)
9. [Como saber que está tudo certo](#9-como-saber-que-está-tudo-certo)

---

## 1. Antes de começar

Abra o **PowerShell** na pasta do projeto e ligue o ambiente virtual:

```powershell
cd C:\Users\Usuario\Documents\Jogos_Probabilidade
.venv\Scripts\Activate.ps1
```

**Deu certo** se aparecer `(.venv)` no começo da linha, assim:

```
(.venv) PS C:\Users\Usuario\Documents\Jogos_Probabilidade>
```

Esse `(.venv)` é o sinal de que você está "dentro" do projeto. Sem ele, os comandos abaixo
não vão funcionar. Se a Fase 0 ainda não foi feita, comece pelo
[`GUIA_FASE_0.md`](GUIA_FASE_0.md).

---

## 2. Baixar os dados

```powershell
python scripts/baixar_dados.py
```

Este comando lê o `config.yaml`, vê quais ligas estão ligadas e baixa os arquivos que
faltam. **Ele não rebaixa o que já está no disco** — rodar duas vezes seguidas é seguro e
rápido.

**Deve aparecer algo assim:**

```
Camada ativa: camada_aprendizado
  Grupo 1 (backtest + CLV): E0
  Grupo 2 (treino apenas):  nenhuma
  Temporadas do Grupo 1:    [1920, 2021, 2122, 2223, 2324, 2425, 2526]

  mmz4281/1920/E0.csv             380 jogos    120.4 KB  (ja existia)
  ...

7 arquivo(s): 0 baixado(s), 7 reaproveitado(s) do disco.
Manifesto atualizado: data\manifesto.json
```

### O que é o manifesto

Toda vez que um arquivo é baixado, o projeto anota num arquivo chamado
`data/manifesto.json`: de qual endereço ele veio, em que dia, quantas linhas tinha e uma
"impressão digital" (um código chamado SHA-256, que muda se **qualquer** caractere do
arquivo mudar).

Isso existe por um motivo prático: **o football-data reescreve os arquivos**. Eles corrigem
um placar errado, acrescentam odds que faltavam. Sem o manifesto, daqui a seis meses você
não conseguiria explicar por que o mesmo comando deu um número diferente.

Para conferir se o que está no seu disco hoje ainda é o que gerou os resultados:

```powershell
python scripts/baixar_dados.py --conferir
```

**Se tudo estiver igual:** `OK: os 7 arquivos do manifesto conferem com o disco.`

---

## 3. Montar a tabela de jogos

```powershell
python scripts/preparar_dados.py
```

Este é o comando principal da fase. Ele lê os CSVs baixados e grava a tabela final em
`data/processed/jogos.parquet`.

**Deve aparecer:**

```
Camada ativa: camada_aprendizado
  Grupo 1 (backtest + CLV): E0
  Grupo 2 (treino apenas):  nenhuma

7 arquivo(s) lidos, 2660 linha(s).
Jogos na tabela: 2660

Nenhuma linha descartada.

Jogos por grupo:
  grupo1:    2660 jogos  - backtest de apostas + CLV

Jogos por liga:
  E0       2660 jogos  2019-08-09 a 2026-05-24    28 times

Tabela gravada: data\processed\jogos.parquet (77.1 KB)
```

### O que aconteceu com cada jogo no caminho

| Etapa | O que o projeto faz |
|---|---|
| **Detecta o formato** | O site tem **três** formatos diferentes de arquivo, e o programa descobre qual é sozinho |
| **Traduz os nomes das colunas** | `FTHG` e `HG` viram `gols_mandante` nos dois casos |
| **Arruma as datas** | `16/08/2024` e `16/08/24` viram a mesma data |
| **Padroniza os times** | `Man United` vira `ENG:Man United` — com o país na frente |
| **Recalcula o resultado** | Se o placar diz 1x2, o resultado é vitória do visitante, mesmo que a fonte diga outra coisa |
| **Descarta o que não é jogo** | Linha vazia, jogo adiado sem placar, data que não dá para ler |

### Por que o nome do time tem um país na frente

Existe **Nacional** no Uruguai e em Portugal. **River Plate** na Argentina e no Uruguai.
**Everton** na Inglaterra e no Chile. Se o projeto guardasse só "Everton", os jogos dos dois
clubes iriam para a mesma pilha, e a "força do Everton" seria uma mistura sem sentido de dois
times de continentes diferentes — sem nenhuma mensagem de erro avisando.

Por isso todo time é guardado como `PAÍS:nome`: `ENG:Everton` e `CHI:Everton` são duas coisas
diferentes, e não tem como confundir.

### Se aparecer um time desconhecido

O projeto tem uma lista de nomes conhecidos em `src/futebol/dados/mapa_times.csv`. Se
aparecer um time que não está lá, o comando **para** e escreve:

```
PAROU: 3 nome(s) de time fora do mapa.

  ESP:Ath Bilbao               -> Athletic Bilbao
  ...

A lista completa esta em data\nomes_pendentes.csv.
```

Isso é de propósito, e é uma das proteções mais importantes do projeto. Um time não
reconhecido não daria erro: ele simplesmente sumiria das contas, e o resultado final ficaria
errado sem nenhum aviso. Melhor parar e perguntar.

**O que fazer:** abra `data/nomes_pendentes.csv` no Excel, confira a coluna `nome_padrao`
(o projeto já sugere a melhor correspondência), corrija o que estiver errado e copie as
linhas revisadas para `src/futebol/dados/mapa_times.csv`. Depois rode o comando de novo.

---

## 4. Ver o relatório de cobertura

```powershell
python scripts/relatorio_cobertura.py
```

Este comando responde à pergunta que decide o tamanho real do projeto: **em quantos jogos
existe odd?** Um jogo sem odd é um jogo que não dá para transformar em aposta simulada.

O relatório completo fica em
[`docs/relatorios/cobertura_fase1.md`](../relatorios/cobertura_fase1.md), separado por liga,
por temporada e por mercado.

### O aviso mais importante do relatório

Jogo sem odd **não é um jogo sorteado ao acaso**. A odd costuma faltar em time pequeno, em
divisão menor, em jogo adiado e remarcado. Se o backtest simplesmente ignorar esses jogos, o
que sobra é um conjunto mais fácil de prever do que a realidade — e o resultado final fica
otimista sem que ninguém tenha mentido.

Por isso o relatório mostra **quantos são, de quais ligas e de quais times**, e compara a
média de gols dos jogos com e sem odd. A Fase 6 vai ter que declarar o que faz com eles.

Na Premier League, por enquanto, o buraco é zero: os 2.660 jogos têm os quatro mercados
completos. Isso muda quando as divisões menores forem ligadas.

---

## 5. Rodar os testes

```powershell
pytest
```

**Deve terminar com:**

```
125 passed
```

Se algum falhar, **não continue** — a mensagem diz o que quebrou. Os testes desta fase
verificam coisas como: não há jogo duplicado, não há gol negativo, o resultado bate com o
placar, um time fora do mapa faz o processo parar, e cada formato de arquivo produz as
colunas que deveria.

---

## 6. O que o projeto aprendeu sobre os dados

Coisas que só apareceram ao abrir os arquivos de verdade, e que agora estão tratadas no
código:

| Descoberta | Por que importa |
|---|---|
| O site responde com um **redirecionamento (302)** e recusa quem não se identifica | Sem tratar isso, o download volta vazio e parece que o arquivo não existe |
| Existem **três** formatos de arquivo, não dois | A quebra é exatamente entre as temporadas 2018/19 e 2019/20 |
| Os arquivos do Grupo 2 começam com **três bytes invisíveis** (BOM) | Sem remover, a primeira coluna vem com lixo colado no nome |
| A Rússia não traz as odds da Bet365 nem da Betfair | O arquivo continua utilizável: o projeto usa a odd **média**, que está lá |
| Até 2018/19, a odd de fechamento é da **Pinnacle**, não a média do mercado | Comparar média com Pinnacle infla a medida de CLV; o projeto marca esses jogos |
| A Argentina tem **duas competições** no mesmo arquivo, e alguns países usam ano civil | Por isso cada jogo guarda a competição e a temporada em formato único |

### Os dois grupos de ligas

Esta é a decisão registrada nesta fase (tarefa 1e):

| Grupo | Quem é | Que odds tem | Serve para |
|---|---|---|---|
| **1** | 22 ligas europeias | pré-jogo **e** fechamento, 1X2 **e** Over/Under | treino, calibração, **backtest de aposta e CLV** |
| **2** | 16 países (Brasil, Argentina, EUA, Japão…) | só fechamento de 1X2 | treino e calibração **apenas** |

Você escolheu a **opção 1**: aproveitar os ~63.200 jogos do Grupo 2 para treinar e calibrar os
modelos, sem deixá-los entrar no backtest de apostas. Em troca, existe uma regra que o projeto
passa a seguir sempre: **toda tabela de resultado precisa dizer quais ligas entraram naquela
análise**. Um número que mistura liga apostável com liga só de treino não quer dizer nada.

É por isso que cada jogo na tabela carrega uma coluna `grupo`.

---

## 7. Quando você quiser ligar mais ligas

Hoje o projeto está rodando com **uma liga só** (a Premier League), de propósito: é mais fácil
descobrir problemas com 28 times do que com 1.500.

Para ampliar, abra o `config.yaml` e troque uma linha:

```yaml
ligas:
  ativa: camada_aprendizado    # troque aqui
```

As opções são:

| Camada | O que liga | Jogos aproximados |
|---|---|---|
| `camada_aprendizado` | só a Premier League | 2.660 |
| `camada_principal` | 8 ligas grandes + Brasil | ~25.000 |
| `camada_completa_backtest` | as 22 ligas apostáveis | ~53.800 |
| `camada_tudo` | as 38 competições | ~117.000 |

Depois é só rodar de novo, na ordem: `baixar_dados.py`, `preparar_dados.py`,
`relatorio_cobertura.py`.

⚠️ **O que esperar na primeira vez:** o `preparar_dados.py` vai parar pedindo revisão de
nomes de times. Quanto maior a camada, mais nomes. Isso é o trabalho real de ampliar o
escopo — e é por isso que ele não foi feito de uma vez.

---

## 8. Erros comuns

### "não é reconhecido como um cmdlet" ao rodar `python`

O ambiente virtual não está ligado. Rode `.venv\Scripts\Activate.ps1` e confira se aparece
`(.venv)` no começo da linha.

### "7 arquivo(s) da camada ... não estão em data/raw/"

Você pulou o passo 2. Rode `python scripts/baixar_dados.py` primeiro.

### "data\processed\jogos.parquet não existe ainda"

Você pulou o passo 3. Rode `python scripts/preparar_dados.py` primeiro.

### "PAROU: N nome(s) de time fora do mapa"

É o comportamento esperado quando aparece um time novo. Veja a
[seção 3](#se-aparecer-um-time-desconhecido).

### "ATENCAO: N divergencia(s) entre o disco e o manifesto"

O site reescreveu algum arquivo depois que você baixou. Para adotar a versão nova:

```powershell
python scripts/baixar_dados.py --forcar
```

Só saiba que, ao fazer isso, os números dos relatórios anteriores deixam de ser
reproduzíveis — por isso o projeto avisa em vez de atualizar sozinho.

### Os acentos aparecem errados no PowerShell

O terminal do Windows não usa UTF-8 por padrão. Não afeta nada: os arquivos gravados estão
corretos. Se incomodar, rode `chcp 65001` antes.

---

## 9. Como saber que está tudo certo

Marque cada item:

- [ ] `python scripts/baixar_dados.py --conferir` diz **OK**
- [ ] `python scripts/preparar_dados.py` termina com "Tabela gravada"
- [ ] O arquivo `data/processed/jogos.parquet` existe
- [ ] `python scripts/relatorio_cobertura.py` termina com "Relatorio gravado"
- [ ] `pytest` mostra **125 passed**
- [ ] `ruff check .` mostra **All checks passed!**
- [ ] `git tag` mostra `fase-1`

Se todos estiverem marcados, **a Fase 1 está concluída**.

---

## O que foi criado nesta fase

| Arquivo | Para que serve |
|---|---|
| `src/futebol/dados/download.py` | Baixa os CSVs seguindo redirecionamento, sem rebaixar o que já existe |
| `src/futebol/dados/manifesto.py` | Anota URL, data, linhas e impressão digital de cada arquivo |
| `src/futebol/dados/formatos.py` | Conhece os três formatos do site e traduz as colunas |
| `src/futebol/dados/nomes_times.py` | Padroniza os nomes dos times com o mapa versionado |
| `src/futebol/dados/mapa_times.csv` | A lista de nomes conhecidos, revisada por você |
| `src/futebol/dados/limpeza.py` | Junta tudo na tabela única de jogos |
| `src/futebol/dados/cobertura.py` | Mede em quantos jogos existe odd, por liga e mercado |
| `docs/dicionario_dados.md` | O que cada coluna dos arquivos originais significa |
| `docs/relatorios/cobertura_fase1.md` | O relatório de cobertura desta fase |
| `data/manifesto.json` | A prova de quais arquivos geraram estes números |

### Versão Mac/Linux dos comandos

Só a ativação do ambiente muda; o resto é idêntico:

```bash
source .venv/bin/activate
python scripts/baixar_dados.py
python scripts/preparar_dados.py
python scripts/relatorio_cobertura.py
pytest
```

---

## Próximo passo

A **Fase 2** olha para essa tabela e mede **quão bom é o mercado**: qual a margem embutida em
cada liga, quanto as odds acertam sozinhas (isso é a "linha de base" que os modelos vão ter
que superar) e quais ligas passam no filtro de qualidade para valer a pena apostar.

É a fase que responde à pergunta incômoda do projeto: *será que dá para ganhar das casas?* —
começando por medir o quanto elas já acertam.

**Me avise quando quiser começar a Fase 2.**
