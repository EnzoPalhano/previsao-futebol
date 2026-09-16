# Guia da Fase 2 — Medindo o adversário

> **Para quem é este guia:** para alguém que nunca programou. Cada comando está
> explicado, junto com o que deve aparecer na tela. Os comandos são para o
> **PowerShell do Windows**; no fim há a versão Mac/Linux.

**O que a Fase 2 faz:** ela ainda não treina nenhum modelo. Ela mede **o adversário** —
as casas de aposta — e responde quatro perguntas:

1. quanto a casa cobra em cada liga?
2. o mercado é bem calibrado, ou seja, quando a odd diz 60%, acontece 60%?
3. a vantagem de jogar em casa mudou ao longo dos anos?
4. em quais ligas vale a pena apostar?

É a fase que transforma "quero apostar nas ligas boas" numa lista com nome e número.

**Tempo estimado:** 15 minutos para rodar tudo (a maior parte é download).

---

## Índice

1. [O que mudou desde a Fase 1](#1-o-que-mudou-desde-a-fase-1)
2. [Baixar as 38 competições](#2-baixar-as-38-competições)
3. [Montar a tabela e o relatório](#3-montar-a-tabela-e-o-relatório)
4. [Escolher as ligas por dados](#4-escolher-as-ligas-por-dados)
5. [Gerar o relatório da fase](#5-gerar-o-relatório-da-fase)
6. [As quatro respostas](#6-as-quatro-respostas)
7. [O caderno de gráficos](#7-o-caderno-de-gráficos)
8. [Uma ideia que vale a pena entender: tirar a margem](#8-uma-ideia-que-vale-a-pena-entender-tirar-a-margem)
9. [Erros comuns](#9-erros-comuns)
10. [Como saber que está tudo certo](#10-como-saber-que-está-tudo-certo)

---

## 1. O que mudou desde a Fase 1

Na Fase 1 o projeto rodava com **uma liga só** (a Premier League), de propósito, para
validar o processo. Agora ele roda com **as 38 competições**: 116.514 jogos.

A mudança está numa linha do `config.yaml`:

```yaml
ligas:
  ativa: camada_tudo     # antes era camada_aprendizado
```

Junto com isso, o `mapa_times.csv` passou de 28 para **1.026 clubes**. A parte
trabalhosa foi descobrir onde duas grafias diferentes são o **mesmo** clube — veja a
[seção 9](#quando-dois-nomes-são-o-mesmo-clube).

---

## 2. Baixar as 38 competições

```powershell
cd C:\Users\Usuario\Documents\Jogos_Probabilidade
.venv\Scripts\Activate.ps1
python scripts/baixar_dados.py
```

São 170 arquivos (22 ligas × 7 temporadas + 16 países). O comando **não rebaixa** o que
já está no disco, então rodar de novo é rápido e seguro.

**Deve terminar com:**

```
170 arquivo(s): 0 baixado(s), 170 reaproveitado(s) do disco.
Manifesto atualizado: data\manifesto.json
```

---

## 3. Montar a tabela e o relatório

```powershell
python scripts/preparar_dados.py
python scripts/relatorio_cobertura.py
```

O primeiro junta tudo numa tabela só; o segundo mede em quantos jogos existe odd.

**Deve aparecer, entre outras linhas:**

```
Jogos por grupo:
  grupo1:   53330 jogos  - backtest de apostas + CLV
  grupo2:   63184 jogos  - treino e calibracao apenas (regra 12)
```

Uma curiosidade que o relatório de cobertura mostrou: dos 53.330 jogos do Grupo 1,
apenas **60** estão sem odd pré-jogo — e 29 deles são da Turquia em 2022/23,
concentrados em dois clubes, Hatayspor e Gaziantep. São os times da região atingida
pelo terremoto de fevereiro de 2023. O buraco nos dados tinha um motivo no mundo real.

---

## 4. Escolher as ligas por dados

```powershell
python scripts/filtro_ligas.py
```

Este é o comando que responde ao seu pedido original — "quero as ligas em que tem
apostas boas" — **medindo**, em vez de escolhendo no chute.

Ele avalia cada liga em quatro critérios, todos ajustáveis no `config.yaml`:

| Critério | Corte | Por quê |
|---|---|---|
| Margem da casa (1X2 pré-jogo) | no máximo **8%** | é a barreira que o modelo tem que vencer antes de lucrar um centavo |
| Cobertura de odds | pelo menos **90%** | liga boa sem odd registrada não serve |
| Jogos disponíveis | pelo menos **1.000** | histórico curto não dá para treinar nem para medir |
| Calibração | até **2×** o piso de ruído | mercado que erra de forma sistemática é sinal de dado ruim |

**O resultado:**

```
APROVADAS (18): B1, D1, D2, E0, E1, E2, E3, F1, F2, G1, I1, I2, N1, P1, SC0, SP1, SP2, T1

REPROVADAS (4):
  SC1: margem alta (8.45% > 8%)
  EC: margem alta (8.62% > 8%)
  SC2: margem alta (9.19% > 8%)
  SC3: margem alta (9.33% > 8%)
```

As quatro reprovadas são as divisões mais baixas da Escócia e a quinta divisão
inglesa. Para lucrar nelas, o modelo precisaria de uma vantagem de **mais de 8%**
sobre o mercado — o que seria extraordinário.

A lista aprovada fica gravada no `config.yaml`, em `ligas_aprovadas_backtest`. A partir
da Fase 6, só ela entra no backtest de apostas.

### 🔎 Uma sutileza que vale o parágrafo

O critério de calibração quase reprovou a **Grécia** — e pelo motivo errado. Medir
calibração com o número cru pune liga pequena: com 1.669 jogos, o erro de calibração é
alto **mesmo num mercado perfeito**, só por acaso. O projeto passou a comparar cada
liga com o *piso de ruído dela mesma*: quanto de erro apareceria se aquele mercado
fosse impecável, estimado por simulação. Com isso, nenhuma liga foi reprovada por
calibração — as quatro que caíram, caíram por margem.

⚠️ Isso foi decidido **depois** de olhar os números, e está registrado como tal no
`CLAUDE.md`. Mudar um critério depois de ver o resultado é o tipo de coisa que precisa
ficar escrita, mesmo quando a mudança é justificada.

---

## 5. Gerar o relatório da fase

```powershell
python scripts/relatorio_fase2.py
```

Escreve [`docs/relatorios/fase2.md`](../relatorios/fase2.md), com todas as tabelas.
O texto do relatório é **gerado a partir dos dados**: se você baixar mais uma
temporada e rodar de novo, todos os números se atualizam juntos, inclusive os que
aparecem no meio das frases.

---

## 6. As quatro respostas

### Quanto a casa cobra?

De **4,3%** na Premier League a **9,3%** na quarta divisão escocesa. As cinco grandes
ligas europeias cobram cerca de metade do que cobram as divisões menores.

⚠️ **Margem baixa não quer dizer "fácil de ganhar"**, e este é o ponto mais
contraintuitivo do projeto. Na Premier League a taxa é barata *porque o mercado é
eficiente*: milhões de reais e dezenas de modelos profissionais apontam para os mesmos
jogos, e a linha é quase impossível de bater. Na quarta divisão escocesa a taxa é cara,
mas a casa tem menos informação. Qual dos dois efeitos ganha é **a pergunta que este
projeto existe para responder**, e ela só será respondida na Fase 6.

### O mercado é bem calibrado?

**Sim, notavelmente.** Agrupando todas as afirmações de probabilidade do mercado de
fechamento: quando ele diz 25%, acontece 25,8%; quando diz 44,6%, acontece 44,9%. O
erro médio é de menos de um quarto de ponto percentual.

Mas sobra um padrão, e ele tem nome: os **favoritos vencem um pouco mais** do que a odd
dizia, e os **azarões um pouco menos**. É o *viés favorito-azarão*, o efeito mais
replicado em mercados de aposta. Quem aposta em azarão paga caro duas vezes: na
comissão maior e na probabilidade inflada.

### A vantagem de jogar em casa mudou?

**Mudou muito, e há um motivo claro.** Em 2020 e 2021, com os estádios vazios, o
mandante caiu de 1,567 para **1,497 pontos por jogo**, e o saldo de gols caiu de 0,296
para **0,194** — uma queda de um terço. Depois, com a torcida de volta, subiu de novo.

O mando caiu em **29 das 38 competições** ao mesmo tempo. Isso é um experimento natural
raro: o mundo inteiro tirou a torcida de campo no mesmo ano.

**Consequência prática:** um modelo que trate o fator casa como uma constante ao longo
de sete temporadas vai errar num pedaço grande do treino. A Fase 3 vai precisar de um
fator casa que muda no tempo.

### Qual é a meta dos modelos?

O mercado de fechamento acerta com **log loss de 0,9984**. Quem chuta "33% para cada"
tira 1,0986. Essa distância é tudo que existe entre não saber nada e ser o mercado —
e é o espaço em que os modelos da Fase 3 vão ter que se encaixar.

---

## 7. O caderno de gráficos

```powershell
jupyter notebook notebooks/01_exploracao.ipynb
```

O caderno é a versão visual do relatório. Aperte `Shift+Enter` em cada célula para
rodar. Ele é gravado **sem os gráficos dentro** de propósito: imagem salva no arquivo
faria ele pesar dezenas de MB e ficaria impossível de acompanhar no Git.

O gráfico mais interessante é o segundo: a queda do mando com os estádios vazios,
com o período da pandemia marcado em vermelho.

---

## 8. Uma ideia que vale a pena entender: tirar a margem

Uma odd de 2,00 parece dizer "50% de chance". **Não diz.** Ela diz "50% mais a minha
comissão".

Some as três probabilidades de um jogo de 1X2 e o total não dá 100%: dá 104%, 107%.
Esses pontos a mais são a margem da casa. Comparar a previsão de um modelo com um
número que embute comissão é comparar coisas diferentes — o modelo pareceria pior do
que é.

O problema é que **tirar a margem não tem uma resposta única**. É preciso supor *como*
a casa distribuiu a comissão entre as três opções, e há três hipóteses:

| Método | O que supõe | Resultado |
|---|---|---|
| **proporcional** | a casa cobrou a mesma fatia de todos | o mais simples, e o que mais erra no azarão |
| **power** | o azarão paga comissão maior | erro de calibração **3,4 vezes menor** |
| **shin** | idem, com uma história sobre apostadores informados | fica no meio |

O projeto calculou os três e comparou, em vez de escolher um no escuro. O **power**
venceu, e essa é uma evidência interessante por si só: se supor que o azarão paga mais
comissão descreve melhor a realidade, é porque **a casa de fato cobra mais caro no
azarão**.

### Quando dois nomes são o mesmo clube

Ao ligar as 38 competições, apareceram 1.025 nomes de clube. O risco não é o nome
desconhecido — esse faz o programa parar. O risco é **duas grafias do mesmo clube**
virarem dois times diferentes, partindo o histórico dele em dois sem dar erro nenhum.

Foram 14 casos, de dois tipos:

- **grafia mudou na fonte**: `Colon Santa FE` e `Colon Santa Fe`, `Ham-Kam` e `HamKam`;
- **o clube foi renomeado**: `Shandong Luneng` virou `Shandong Taishan` em 2021, junto
  com metade do futebol chinês, por causa de uma regra da federação que proibiu nome de
  patrocinador.

E o contrário também existe: `Reggiana` e `Reggina` são clubes **diferentes** (um em
Reggio Emilia, outro em Reggio Calabria), assim como `Atletico-MG`, `Atletico-GO` e
`Athletico-PR`.

Como saber quem está certo? O projeto ganhou uma trava que dá uma resposta objetiva:
**um clube não pode jogar contra si mesmo**. Se duas grafias fossem clubes diferentes,
elas teriam se enfrentado em algum momento — e depois da fusão esse jogo viraria um
time contra ele mesmo, o que não existe. As 14 fusões passaram nessa prova.

---

## 9. Erros comuns

### "data\processed\jogos.parquet não existe ainda"

Rode `python scripts/preparar_dados.py` primeiro.

### "PAROU: N nome(s) de time fora do mapa"

Apareceu um clube novo (subiu de divisão, ou a fonte mudou a grafia). Abra
`data/nomes_pendentes.csv`, confira a coluna `nome_padrao` e mova as linhas revisadas
para `src/futebol/dados/mapa_times.csv`.

### "N jogo(s) ficaram com o mesmo time nos dois lados"

É a trava da seção anterior: o `mapa_times.csv` está juntando dois clubes diferentes
sob o mesmo nome. A mensagem diz qual clube e em que data — separe os dois.

### O `filtro_ligas.py` demora

Ele simula o piso de ruído de cada liga 200 vezes. Para uma rodada rápida:

```powershell
python scripts/filtro_ligas.py --so-ver --repeticoes 30
```

### Os acentos aparecem errados no PowerShell

Não afeta os arquivos gravados. Se incomodar, rode `chcp 65001` antes.

---

## 10. Como saber que está tudo certo

- [ ] `python scripts/baixar_dados.py --conferir` diz **OK** para 170 arquivos
- [ ] `python scripts/preparar_dados.py` termina com **116.514 jogos**
- [ ] `python scripts/filtro_ligas.py` mostra **APROVADAS (18)**
- [ ] `config.yaml` tem a lista em `ligas_aprovadas_backtest`
- [ ] `docs/relatorios/fase2.md` existe
- [ ] `pytest` mostra **200 passed**
- [ ] `ruff check .` mostra **All checks passed!**
- [ ] `git tag` mostra `fase-2`

Se todos estiverem marcados, **a Fase 2 está concluída**.

---

## O que foi criado nesta fase

| Arquivo | Para que serve |
|---|---|
| `src/futebol/odds/mercado.py` | Transforma odd em probabilidade e tira a margem (3 métodos) |
| `src/futebol/avaliacao/metricas.py` | Log loss, Brier, calibração e o piso de ruído |
| `src/futebol/avaliacao/exploracao.py` | Gols, mando de campo, margem por liga e por temporada |
| `src/futebol/avaliacao/filtro.py` | O filtro de qualidade que escolhe as ligas |
| `src/futebol/avaliacao/relatorio_fase2.py` | Monta o relatório a partir dos dados |
| `src/futebol/relatorio.py` | Formatação de tabelas em Markdown |
| `src/futebol/terminal.py` | Impede que nome estrangeiro derrube o script no Windows |
| `docs/relatorios/fase2.md` | O relatório da fase |
| `notebooks/01_exploracao.ipynb` | Os gráficos |

### Versão Mac/Linux dos comandos

```bash
source .venv/bin/activate
python scripts/baixar_dados.py
python scripts/preparar_dados.py
python scripts/filtro_ligas.py
python scripts/relatorio_fase2.py
pytest
```

---

## Próximo passo

A **Fase 3** constrói o primeiro modelo próprio: Poisson e Dixon-Coles. A ideia é
estimar, para cada time, uma força de ataque e uma de defesa, e a partir delas calcular
a probabilidade de cada placar possível.

Três coisas que esta fase deixou prontas para lá:

1. **a meta**: log loss de 0,9984 — abaixo disso o modelo é útil, acima é enfeite;
2. **um alerta**: a Poisson simples erra nos placares de poucos gols, e é exatamente
   isso que o ajuste de Dixon-Coles corrige;
3. **um requisito**: o fator casa precisa variar no tempo.

**Me avise quando quiser começar a Fase 3.**
