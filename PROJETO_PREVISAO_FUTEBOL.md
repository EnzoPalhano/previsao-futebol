# Projeto: Previsão Probabilística de Futebol (Projeto de ML + Backtest)

> **Para o Claude Code:** este documento é a especificação completa do projeto.
> Leia tudo antes de começar. Siga as **Regras do Projeto** (seção 2) em todas as fases.
> O dono do projeto é o **Enzo**, estudante de Engenharia de Software. Ele conhece o básico
> de lógica e está estudando machine learning. Explique as decisões de forma didática.

> **Revisão de 15/09/2026:** documento revisado após **inspeção real dos arquivos de dados**
> (não por suposição). As adições estão marcadas com 🔎 (achado verificado nos dados baixados)
> e ⚠️ (regra de honestidade estatística).
>
> **Escopo definido pelo Enzo:** todas as ligas do mundo cobertas pela fonte que tenham apostas
> de qualidade — são **38 competições**, catalogadas na seção 4.2, com a medição de margem por
> liga na seção 4.3 e o inventário técnico de colunas na seção 4.4.
> **Leia a 4.2 e a 4.4 antes de escrever qualquer parser.**

---

## 1. Visão geral

### 1.1 O que é
Um sistema em Python que:
1. Coleta dados históricos de jogos de futebol **e as odds das casas de aposta**.
2. Treina modelos estatísticos que calculam a **probabilidade** de cada resultado (vitória/empate/derrota, mais/menos de 2,5 gols, ambos marcam).
3. Compara essas probabilidades com as probabilidades implícitas nas odds.
4. Faz **backtest**: simula apostas em temporadas passadas para medir, com honestidade, se o modelo teria lucro ou prejuízo.
5. Simula **apostas múltiplas** e **cash out** para medir o efeito da margem da casa.
6. Mostra tudo num app web simples (Streamlit).

### 1.2 Objetivo real
- **Objetivo principal:** aprender e demonstrar machine learning aplicado (projeto de portfólio para GitHub e currículo).
- **Objetivo secundário:** descobrir, com dados, se existe alguma vantagem sobre as casas. A hipótese padrão é que **não existe**, e o projeto precisa provar o contrário com evidência forte antes de qualquer uso com dinheiro real.

### 1.3 Fora do escopo
- Automatizar apostas em sites (bots que apostam sozinhos).
- Scraping de sites de apostas que proíbem isso nos termos de uso.
- Usar LLM para **calcular probabilidades** (LLM não é a ferramenta certa para dados tabulares).
  - *Observação:* a Fase 10 usa LLM, mas para outra tarefa, legítima: **ler o texto de uma notícia
    e devolver JSON estruturado**. Ler texto é exatamente o que um LLM faz bem; estimar
    probabilidade a partir de tabela não é. As duas coisas não se contradizem.

### 1.4 Conceitos-chave (glossário para o Enzo)
| Conceito | Explicação simples |
|---|---|
| Lei dos Grandes Números | Quanto mais repetições, mais a frequência real se aproxima da probabilidade verdadeira. |
| Probabilidade implícita | `1 / odd`. Odd 2,00 = 50%. |
| Overround (margem) | Soma das probabilidades implícitas passa de 100%. O excesso é o lucro da casa. |
| Valor esperado (EV) | `prob_modelo × odd − 1`. Positivo = aposta com "valor" segundo o modelo. |
| Poisson | Distribuição que modela contagem de eventos raros, como gols. |
| Dixon-Coles | Ajuste do Poisson que corrige placares baixos (0x0, 1x0, 0x1, 1x1). |
| Log loss / Brier | Métricas que medem se as probabilidades previstas são boas (menor = melhor). |
| Calibração | Se o modelo diz 70%, o evento deve acontecer ~70% das vezes. |
| Data leakage | Usar, sem querer, informação do futuro para prever o passado. Invalida o backtest. |
| Walk-forward | Treinar só com jogos anteriores à data prevista, avançando no tempo. |
| Closing line | Odd no momento do início do jogo. É a estimativa mais precisa do mercado. |
| CLV (Closing Line Value) | Pegar odds melhores que a de fechamento. Melhor indicador de vantagem real. |
| ROI | Lucro ÷ total apostado. |
| Drawdown | Maior queda da banca do pico até o fundo. |
| **Erro-padrão** | Quanto uma média medida "balança" por puro acaso. Quanto maior a amostra, menor. |
| **Poder estatístico** | Chance de detectar um efeito que existe de verdade. Amostra pequena = poder baixo. |
| **p-hacking** | Testar muitas combinações e reportar só a que deu certo. Produz descoberta falsa. |

---

## 2. Regras do Projeto (OBRIGATÓRIAS)

### 2.1 Arquivo CLAUDE.md
- Criar `CLAUDE.md` na raiz **na Fase 0**, usando o modelo da seção 7.
- Manter atualizado: ao fim de cada fase, atualizar a seção "Status atual" e "Decisões tomadas".
- Sempre ler o `CLAUDE.md` no início de cada sessão.

### 2.2 Git
- Repositório Git inicializado na Fase 0.
- **Commitar ao fim de cada subtarefa concluída** (não acumular muitas mudanças num commit só).
- Mensagens no padrão Conventional Commits, em português:
  - `feat: adiciona modelo de Poisson`
  - `fix: corrige vazamento de dados no backtest`
  - `docs: adiciona guia da fase 2`
  - `test: adiciona testes do cálculo de overround`
  - `refactor:`, `chore:`, `data:` quando fizer sentido
- Ao fim de cada fase, criar uma tag: `git tag fase-1`, `git tag fase-2`, etc.
- **Nunca commitar:** a pasta `data/raw/`, `data/processed/`, arquivos `.env`, chaves de API, ambientes virtuais (`.venv/`), arquivos grandes (> 5 MB).
- Antes de cada commit, rodar os testes (`pytest`). Não commitar com testes quebrando.

### 2.3 Guia para leigos ao fim de cada fase
Ao terminar qualquer fase, o Claude Code deve:
1. Criar o arquivo `docs/guias/GUIA_FASE_X.md`.
2. Escrever como se o leitor **nunca tivesse programado**:
   - Cada comando em um bloco próprio, com explicação do que ele faz.
   - O que deve aparecer na tela se deu certo (exemplo da saída esperada).
   - Erros comuns e como resolver.
   - Instruções para **Windows** (PowerShell) e, quando diferente, para Mac/Linux.
   - Uma seção final "Como saber que está tudo certo" com um checklist.
3. Mostrar o guia também no chat.
4. **Parar e esperar a confirmação do Enzo** antes de começar a próxima fase.

### 2.4 Qualidade
- Python 3.11 ou superior.
- Código com type hints e docstrings em português.
- Testes com `pytest` para toda função de cálculo (odds, probabilidades, métricas, backtest).
- Formatação com `ruff`.
- Semente aleatória fixa (`SEED = 42`) para resultados reproduzíveis.
- Configurações centralizadas em `config.yaml` (ligas, temporadas, parâmetros).
- 🔎 **Empacotamento com `pyproject.toml`.** Usar `pyproject.toml` declarando o pacote e instalar
  em modo editável (`pip install -e .`).
  *Por quê:* com o layout `src/futebol/`, o `pytest` **não encontra** o módulo `futebol` sem isso.
  Seria o primeiro erro a aparecer, logo na Fase 0. O `pyproject.toml` ainda centraliza a
  configuração do `ruff` e do `pytest` num arquivo só. O `requirements.txt` pode continuar
  existindo para quem preferir, mas o `pyproject.toml` é a fonte da verdade.
- **Integração contínua:** workflow do GitHub Actions rodando `pytest` + `ruff check` a cada push.
  Para um projeto de portfólio de Engenharia de Software, o selo verde no README vale muito.
- **Dicionário de dados:** manter `docs/dicionario_dados.md` descrevendo cada coluna da tabela
  final — nome, tipo, unidade, origem e o que significa quando está vazia.

### 2.5 Regra de ouro contra data leakage
Em qualquer previsão para um jogo na data D, o modelo só pode usar jogos com data **estritamente anterior** a D. Toda função de feature e todo backtest deve ter um teste automatizado que verifica isso.

### 2.6 Honestidade nos resultados

Estas regras existem para impedir que o projeto conclua algo falso.
São tão obrigatórias quanto as regras de código.

#### a) Qual odd usar para apostar 🔎⚠️
- A odd padrão de toda simulação de aposta é a **média do mercado pré-jogo**
  (`Avg*` no formato moderno, `BbAv*` no formato legado — ver seção 4.4).
- **Nunca usar `Max*` como cenário principal.** `Max` é o maior valor entre ~20 casas: quase
  sempre uma casa pequena, uma odd digitada errada, ou uma aposta com limite de R$ 50.
  Backtest feito na `Max` dá ROI positivo com quase qualquer modelo — é o erro clássico que
  invalida a maior parte dos projetos de aposta que se encontram na internet.
- `Max` pode ser reportada, mas **sempre rotulada como "cenário otimista / não realizável"**.
- 🔎 **Atenção:** o football-data.co.uk **não fornece odd de abertura.** O que existe é um
  snapshot pré-jogo e o fechamento. Onde o documento antigo dizia "odds de abertura", leia
  "média do mercado pré-jogo".

#### b) O que decide qual modelo é melhor ⚠️
- O critério de seleção de modelo é **log loss no walk-forward do conjunto de validação**.
- **ROI e lucro do backtest NUNCA são critério de seleção** — são consequências reportadas.
  O ROI é dominado por ruído (ver seção 8), e escolher modelo por ROI é a forma mais rápida
  de se enganar.

#### c) Intervalo de confiança ⚠️
- Reportar **ROI e CLV** sempre com intervalo de confiança por bootstrap. Nunca um número seco.
- Reportar junto o **número de apostas** e o **erro-padrão**.

#### d) Comparação obrigatória com o mercado
- Todo modelo é comparado com as probabilidades das **odds de fechamento sem margem**.
- Comparar também com uma **estratégia aleatória** de mesmo número de apostas.

#### e) Multiplicidade — proteção contra p-hacking ⚠️
- Ao longo da validação você vai testar dezenas de configurações (liga × mercado × limite de EV
  × estratégia de stake × modelo). **Uma delas vai parecer lucrativa por puro acaso.**
- Todo relatório de backtest deve registrar **quantas configurações foram testadas**.
- A configuração levada ao teste final deve ser **registrada no CLAUDE.md antes** de abrir o
  conjunto de teste (pré-registro).
- Comparando `k` configurações, aplicar correção de Bonferroni (nível `0,05 / k`) ou justificar
  por escrito por que não é necessário.

#### f) Nunca ajustar olhando o teste final
- As temporadas de teste final são abertas **uma única vez**, na Fase 9.

#### g) Resultado negativo é resultado
- Se não houver vantagem, reportar isso com clareza e destaque. O projeto continua completo e
  valioso como portfólio. **Um backtest honesto que dá negativo vale mais, tecnicamente, que um
  backtest positivo mal feito.**

---

## 3. Divisão de tarefas

| Quem | Faz o quê |
|---|---|
| **Claude Code** | Todo o código, testes, estrutura de pastas, documentação, commits, guias. |
| **Enzo** | Instalar Python e Git; criar o repositório no GitHub (EnzoPalhano); rodar os comandos dos guias; conferir os resultados; tomar decisões (quais ligas, quais mercados); aprovar cada fase; fazer `git push`. |
| **Enzo (aprendizado)** | Ler os notebooks de análise e tentar modificar parâmetros sozinho para entender o efeito. |

---

## 4. Stack técnica

| Área | Ferramenta |
|---|---|
| Linguagem | Python 3.11+ |
| Ambiente | `venv` (ou `uv`, se o Enzo preferir) |
| Empacotamento | `pyproject.toml` + `pip install -e .` |
| Dados | `pandas`, `numpy`, `pyarrow` (Parquet) |
| Estatística | `scipy`, `statsmodels` |
| ML | `scikit-learn`, `lightgbm` |
| Gráficos | `matplotlib`, `plotly` |
| App | `streamlit` |
| Download | `requests` |
| Config | `pyyaml` |
| Testes / lint | `pytest`, `ruff` |
| CI | GitHub Actions |
| Notebooks | `jupyter` (para análises exploratórias) |

### 4.1 Fontes de dados
- **football-data.co.uk** (principal, gratuita): resultados + odds históricas de várias casas.
  - Ligas europeias principais: um arquivo por liga **por temporada**
    (`https://www.football-data.co.uk/mmz4281/<TEMPORADA>/<LIGA>.csv`, ex.: `.../2425/E0.csv`).
  - Ligas "extras", incluindo o **Brasileirão**: um arquivo único com todas as temporadas
    (`https://www.football-data.co.uk/new/BRA.csv`).
  - 🔎 **O site redireciona (HTTP 302).** O downloader precisa seguir redirecionamentos
    (`requests` faz isso por padrão; `curl` precisa de `-L`) e enviar um `User-Agent` comum.
  - 🔎 **Existem TRÊS formatos de coluna, não dois.** Ver seção 4.4. Inspecione sempre as
    colunas reais e o `notes.txt` do site antes de escrever o parser.
- **Opcional (fases avançadas):** FBref (xG), StatsBomb Open Data (eventos detalhados).
  Respeitar termos de uso e limites de requisição.

### 4.2 Escopo: todas as ligas disponíveis 🔎

**Decisão do Enzo (15/09/2026): usar todas as ligas do mundo que a fonte cobrir e que tenham
apostas de qualidade aceitável.** Esta seção registra o que existe de fato.

O football-data.co.uk cobre **38 competições**, verificadas uma a uma. Elas se dividem em dois
grupos com capacidades **muito diferentes** — e essa diferença decide o que cada liga pode fazer
no projeto.

#### Grupo 1 — 22 ligas com dados completos (formato A/B)

Têm odds pré-jogo **e** de fechamento, para 1X2 **e** Over/Under 2,5.
**São as únicas que podem entrar no backtest de apostas e na medição de CLV.**

| País | Códigos |
|---|---|
| Inglaterra | E0, E1, E2, E3, EC (5 divisões) |
| Escócia | SC0, SC1, SC2, SC3 (4 divisões) |
| Alemanha | D1, D2 |
| Itália | I1, I2 |
| Espanha | SP1, SP2 |
| França | F1, F2 |
| Holanda | N1 |
| Bélgica | B1 |
| Portugal | P1 |
| Turquia | T1 |
| Grécia | G1 |

**Volume:** ~7.680 jogos por temporada somando as 22.
Com as temporadas 2019/20 em diante (formato moderno) → **~53.800 jogos**.

#### Grupo 2 — 16 países só com odds de fechamento (formato C)

Arquivo único por país, com todas as temporadas desde ~2012.
**Só têm fechamento de 1X2**: servem para treinar e avaliar calibração, **mas não para backtest
nem para CLV** — exatamente a mesma limitação do Brasileirão.

| País | Jogos | País | Jogos |
|---|---:|---|---:|
| Argentina (ARG) | 6.370 | Noruega (NOR) | 3.542 |
| Estados Unidos (USA) | 6.188 | Rússia (RUS) | 3.416 |
| **Brasil (BRA)** | **5.586** | China (CHN) | 3.015 |
| México (MEX) | 4.724 | Dinamarca (DNK) | 3.000 |
| Japão (JPN) | 4.593 | Suíça (SWZ) | 2.720 |
| Romênia (ROU) | 4.253 | Irlanda (IRL) | 2.716 |
| Polônia (POL) | 4.149 | Áustria (AUT) | 2.674 |
| Suécia (SWE) | 3.551 | Finlândia (FIN) | 2.688 |

**Volume:** ~63.200 jogos.

#### Total do projeto

| Uso | Jogos |
|---|---:|
| Backtest de apostas + CLV (Grupo 1, 2019/20+) | ~53.800 |
| Treino e calibração apenas (Grupo 2) | ~63.200 |
| **Total** | **~117.000** |

Isso resolve com folga o problema de tamanho de amostra da seção 8: os ~5.000 apostas
necessárias passam a ser facilmente alcançáveis.

> ⚠️ **"Todas as ligas do mundo" tem um limite.** Estas 38 competições são as que **esta fonte**
> cobre — e elas incluem praticamente todos os campeonatos com mercado de aposta relevante.
> Ligas fora dessa lista (Sul-Americanas menores, africanas, asiáticas além de China e Japão,
> divisões inferiores do Brasil) **não existem nesta fonte** e exigiriam uma API paga.
> Fora do escopo por enquanto.

#### ⚠️ O custo real dessa decisão: nomes de times

Ampliar de 2 para 38 competições **não aumenta quase nada o código de download**, mas aumenta
muito o trabalho de **padronização de nomes de times**: são ~1.500 clubes, em vários idiomas,
com acentuação, abreviações inconsistentes e clubes homônimos em países diferentes
(há "Nacional", "River Plate", "Racing" e "Independiente" em mais de um lugar).

Por isso a Fase 1 ganhou uma estratégia específica para isso (ver Fase 1, item 1c). O plano é:
- chave de time **sempre composta com o país/liga** (`BRA:Palmeiras`), nunca o nome sozinho;
- construção incremental do `mapa_times.csv`, liga por liga;
- teste que falha em nome desconhecido, para nada passar despercebido.

#### Configuração em camadas

O `config.yaml` organiza as ligas em camadas, para o Enzo poder começar pequeno enquanto aprende
e ligar tudo quando for rodar o backtest de verdade:

```yaml
ligas:
  camada_aprendizado:      # rápido de rodar, para estudar
    - E0
  camada_principal:        # margens baixas, mercados mais eficientes
    - E0, SP1, D1, I1, F1, N1, P1, B1
  camada_completa_backtest: # todas do Grupo 1
    - E0, E1, E2, E3, EC, SC0, SC1, SC2, SC3, D1, D2, I1, I2,
      SP1, SP2, F1, F2, N1, B1, P1, T1, G1
  camada_treino_apenas:    # Grupo 2 — sem backtest, sem CLV
    - ARG, AUT, BRA, CHN, DNK, FIN, IRL, JPN, MEX, NOR, POL, ROU, RUS, SWE, SWZ, USA
ativa: camada_aprendizado
```

### 4.3 🔎 O que é uma liga com "apostas boas"

O Enzo pediu as ligas "em que tem apostas boas". Isso merece uma resposta com número, porque a
intuição aqui engana.

#### A margem medida, liga por liga

Margem média da casa no 1X2 de fechamento (quanto menor, melhor para o apostador).
Medido nos dados reais: temporada 2024/25 para o Grupo 1, todas as temporadas para o Grupo 2.

| Liga | Margem | Liga | Margem |
|---|---:|---|---:|
| **E0** Inglaterra 1ª | **4,19%** | SWE Suécia | 6,51% |
| **SP1** Espanha 1ª | **4,59%** | USA Estados Unidos | 6,58% |
| **D1** Alemanha 1ª | **4,59%** | RUS Rússia | 6,59% |
| **I1** Itália 1ª | **4,71%** | NOR Noruega | 6,63% |
| **F1** França 1ª | **4,82%** | G1 Grécia | 6,72% |
| N1 Holanda | 5,40% | SP2 Espanha 2ª | 6,72% |
| E1 Inglaterra 2ª | 5,42% | **BRA Brasil** | **6,79%** |
| P1 Portugal | 5,67% | F2 França 2ª | 6,83% |
| SC0 Escócia 1ª | 5,94% | E2/E3 Inglaterra 3ª/4ª | 6,86% |
| B1 Bélgica | 5,99% | AUT Áustria | 6,87% |
| D2 Alemanha 2ª | 6,00% | JPN Japão | 7,06% |
| T1 Turquia | 6,11% | ARG Argentina | 7,08% |
| I2 Itália 2ª | 6,61% | SWZ Suíça | 7,10% |
| POL Polônia | 7,25% | FIN Finlândia | 7,27% |
| MEX México | 7,47% | IRL Irlanda | 7,74% |
| SC1 Escócia 2ª | 7,90% | CHN China | 8,03% |
| EC Inglaterra 5ª | 8,31% | ROU Romênia | 8,36% |
| SC3 Escócia 4ª | 8,55% | SC2 Escócia 3ª | 8,58% |

**O padrão é nítido:** as cinco grandes ligas europeias cobram ~4,2 a 4,8%. As divisões
inferiores e as ligas menores cobram 7 a 8,6% — **o dobro**.

#### ⚠️ Mas margem baixa NÃO quer dizer "fácil de ganhar"

Este é o ponto mais importante desta seção, e é contraintuitivo:

- Nas **grandes ligas**, a margem é baixa **porque o mercado é muito eficiente**. Milhões de
  reais e dezenas de modelos profissionais apontam para os mesmos jogos. A "taxa" é barata,
  mas a linha é quase impossível de bater.
- Nas **ligas menores**, a margem é alta, mas as casas têm **menos informação** e as linhas são
  mais "moles". Há mais espaço para um modelo achar erro — só que ele precisa achar um erro
  **maior que 8%** para valer a pena.

A conta que importa é sempre a mesma:

```
para lucrar, a vantagem do modelo precisa ser MAIOR que a margem da casa
```

Qual dos dois efeitos ganha **é exatamente uma das perguntas que este projeto existe para
responder** — e com 38 competições dá para responder com dados, não com opinião.

#### Regra de inclusão orientada por dados (decidida na Fase 2, não agora)

Em vez de escolher as ligas "boas" no chute, o projeto mede e deixa o dado decidir.
A Fase 2 calcula, por liga:
1. margem média (1X2 e Over/Under, pré-jogo e fechamento);
2. cobertura de odds (% de jogos com odd disponível);
3. calibração do mercado (o mercado daquela liga é confiável?);
4. número de jogos disponíveis.

E o `config.yaml` guarda os limites de corte, ajustáveis:

```yaml
filtro_qualidade_mercado:
  margem_maxima: 0.08          # descarta ligas acima de 8% de margem
  cobertura_minima_odds: 0.90  # pelo menos 90% dos jogos com odds
  jogos_minimos: 1000          # histórico suficiente para treinar
```

⚠️ O relatório da Fase 6 deve apresentar o resultado **por liga**, não só o total agregado.
Uma média geral pode esconder que o lucro veio de uma liga só — o que quase sempre é sorte.
O critério de consistência entre ligas da seção 8 depende disso.

### 4.4 🔎 Inventário de dados verificado (inspeção de 15/09/2026)

**Esta seção é resultado de download e inspeção real dos arquivos, não de suposição.**
Ela deve ser reconferida na Fase 1 (o site atualiza os arquivos) e virar teste automatizado.

#### Formato A — ligas principais, moderno (2019/20 em diante)
- **~105 a 120 colunas.** Verificado em E0, E1, SP1, I1, D1, F1, N1, P1.
- Resultado: `Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, `FTR`
- 1X2 pré-jogo: `B365H/D/A`, `PSH/D/A`, `MaxH/D/A`, **`AvgH/D/A`**
- 1X2 fechamento: `B365CH/D/A`, `PSCH/D/A`, `MaxCH/D/A`, **`AvgCH/D/A`**
- Over/Under 2,5 pré-jogo: `B365>2.5`, `B365<2.5`, `Max>2.5`, **`Avg>2.5`**
- Over/Under 2,5 fechamento: `B365C>2.5`, `B365C<2.5`, `MaxC>2.5`, **`AvgC>2.5`**
- ✅ **Tudo o que o projeto precisa:** baseline de mercado, CLV e os dois mercados.

#### Formato B — ligas principais, legado (até 2018/19)
- **62 a 65 colunas**, com prefixo `Bb` (Betbrain). Verificado em E0 1516, 1617, 1718, 1819.
- 🔎 **A quebra de formato é exatamente entre 2018/19 e 2019/20.**
- 1X2 pré-jogo: `B365H/D/A`, `PSH/D/A`, `BbMxH/D/A`, **`BbAvH/D/A`**
- Over/Under 2,5 pré-jogo: `BbMx>2.5`, **`BbAv>2.5`**, `BbMx<2.5`, `BbAv<2.5`
- Fechamento: **apenas `PSCH/PSCD/PSCA`** (Pinnacle, 1X2)
- ⚠️ **Não existe odd de fechamento de Over/Under antes de 2019/20.**
- Consequência: nessas temporadas dá para medir CLV de 1X2 (`BbAv*` → `PSC*`), mas o baseline
  de mercado e o CLV de Over/Under **não existem**.

#### Formato C — arquivo extra (Brasileirão, `BRA.csv`)
- **25 colunas. 5.586 jogos, temporadas 2012 a 2026** (2026 em andamento, 266 jogos).
- Colunas: `Country`, `League`, `Season`, `Date`, `Time`, `Home`, `Away`, `HG`, `AG`, `Res`
  (note: nomes **diferentes** do formato A — `Home` e não `HomeTeam`, `HG` e não `FTHG`).
- `Season` é o **ano civil** (2024), não "2425".
- Odds disponíveis: `PSCH/D/A`, `MaxCH/D/A`, `AvgCH/D/A`, `BFECH/D/A`, `B365CH/D/A`
- 🔎 **Todas terminam em "C": são TODAS odds de fechamento.**
- ✅ Cobertura do fechamento de 1X2: **100%** (`AvgCH` não está vazia em nenhuma temporada).
- ❌ **Não existe nenhuma odd pré-fechamento** → **CLV é impossível de medir.**
- ❌ **Não existe nenhuma coluna de Over/Under** → **o mercado de 2,5 gols não existe.**

> **A expectativa do Enzo estava correta:** o Brasileirão tem fechamento de 1X2, mas não tem
> Over/Under nem odds pré-fechamento, e é justamente a falta das pré-fechamento que impede
> medir CLV.

🔎 **O mesmo vale para os outros 15 países do formato C** (ARG, AUT, CHN, DNK, FIN, IRL, JPN,
MEX, NOR, POL, ROU, RUS, SWE, SWZ, USA): todos têm 25 colunas, todas de fechamento
(exceção: RUS tem 19 colunas, com menos casas de aposta). Nenhum tem odd pré-jogo nem
Over/Under. Ou seja: **os ~63.200 jogos do Grupo 2 servem para treino e calibração, e nenhum
deles pode entrar no backtest de apostas ou na medição de CLV.**

#### Resumo do que cada formato permite

| Capacidade | A (moderno) | B (legado) | C (Grupo 2: BRA, ARG, USA…) |
|---|:---:|:---:|:---:|
| Resultado e placar | ✅ | ✅ | ✅ |
| Baseline de mercado 1X2 (fechamento) | ✅ | ✅ | ✅ |
| Baseline de mercado O/U 2,5 | ✅ | ❌ | ❌ |
| Backtest 1X2 (apostar na média pré-jogo) | ✅ | ✅ | ❌ |
| Backtest O/U 2,5 | ✅ | ✅ | ❌ |
| **CLV de 1X2** | ✅ | ✅ | ❌ |
| **CLV de O/U 2,5** | ✅ | ❌ | ❌ |

---

## 5. Estrutura de pastas

```
previsao-futebol/
├── CLAUDE.md
├── README.md
├── pyproject.toml          # pacote, ruff e pytest configurados aqui
├── requirements.txt        # opcional, espelha as dependências
├── config.yaml
├── .gitignore
├── .env.exemplo
├── .github/
│   └── workflows/
│       └── ci.yml          # pytest + ruff a cada push
├── data/
│   ├── manifesto.json      # VAI pro Git: url, data, linhas, sha256 de cada arquivo
│   ├── raw/                # CSVs baixados (NÃO vai pro Git)
│   └── processed/          # Parquet limpo (NÃO vai pro Git)
├── docs/
│   ├── dicionario_dados.md
│   ├── guias/              # GUIA_FASE_0.md, GUIA_FASE_1.md, ...
│   └── relatorios/         # resultados de cada fase
├── notebooks/              # análises exploratórias
├── src/
│   └── futebol/
│       ├── __init__.py
│       ├── config.py
│       ├── dados/
│       │   ├── download.py
│       │   ├── formatos.py        # detecta e mapeia os formatos A, B e C
│       │   ├── limpeza.py
│       │   ├── manifesto.py       # registra e confere sha256 dos arquivos
│       │   └── nomes_times.py     # padroniza nomes de times
│       │   └── mapa_times.csv     # mapeamento versionado (VAI pro Git)
│       ├── odds/
│       │   └── mercado.py         # prob. implícita, overround, remoção de margem
│       ├── modelos/
│       │   ├── base.py            # interface comum dos modelos
│       │   ├── baseline.py
│       │   ├── poisson.py
│       │   ├── dixon_coles.py
│       │   ├── elo.py
│       │   └── gbm.py             # LightGBM
│       ├── features/
│       │   └── construtor.py
│       ├── avaliacao/
│       │   ├── metricas.py        # log loss, Brier, calibração, tamanho de amostra
│       │   └── validacao.py       # walk-forward
│       ├── backtest/
│       │   ├── estrategias.py     # stake fixa, Kelly fracionado
│       │   ├── simulador.py
│       │   ├── multiplas.py
│       │   ├── montador.py
│       │   └── cash_out.py
│       └── app/
│           └── streamlit_app.py
├── scripts/            # comandos de linha: baixar, treinar, backtest
└── tests/
```

---

## 6. Fases do projeto

Cada fase termina com: testes passando → commit → tag → atualização do CLAUDE.md → guia para leigos → **pausa para aprovação do Enzo**.

### Fase 0 — Configuração do ambiente
**Objetivo:** projeto pronto para receber código.
- Criar estrutura de pastas da seção 5.
- Criar `CLAUDE.md` (modelo da seção 7), `README.md`, `.gitignore`, `config.yaml`, `.env.exemplo`.
- 🔎 Criar **`pyproject.toml`** declarando o pacote `futebol` (layout `src/`), com as configurações
  do `ruff` e do `pytest`. Instalar com `pip install -e .`.
  **Explicar ao Enzo o que é instalação editável e por que sem ela o `pytest` não acha o código.**
- Criar ambiente virtual e instalar dependências.
- Criar `.github/workflows/ci.yml` rodando `pytest` e `ruff check`.
- `git init`, primeiro commit, instruções para conectar ao GitHub.
- Um teste bobo (`test_ambiente.py`) para confirmar que o `pytest` funciona **e que o pacote
  `futebol` é importável** (este segundo é o que prova que o `pyproject.toml` está certo).

**Guia deve ensinar:** instalar Python e Git no Windows, abrir o terminal, criar e ativar o venv, instalar dependências, rodar `pytest`, criar repositório no GitHub e fazer o primeiro `git push`.

**Pronto quando:** `pytest` passa, `import futebol` funciona, o CI está verde e o código está no GitHub.

---

### Fase 1 — Coleta e limpeza de dados
**Objetivo:** uma tabela limpa e padronizada com todos os jogos.

#### 1a. Conferência do inventário (fazer primeiro) 🔎
- Baixar um arquivo de cada formato (A, B e C) e **conferir se o inventário de colunas da seção 4.4 ainda vale**.
  O site atualiza os arquivos, então isso não é opcional.
- Gerar `docs/dicionario_dados.md` a partir das colunas reais encontradas.
- Teste automatizado: se uma coluna esperada sumir, o teste **falha** com mensagem clara.

#### 1b. Download
- `download.py`: baixa os CSVs das ligas/temporadas do `config.yaml`, salva em `data/raw/`,
  não baixa de novo se já existir.
- 🔎 Seguir redirecionamentos (HTTP 302) e enviar `User-Agent`.
- `manifesto.py`: para cada arquivo baixado, registrar em `data/manifesto.json` a **URL, a data
  do download, o número de linhas e o SHA-256**. Esse arquivo **vai para o Git**.
  *Por quê:* `data/raw/` não é versionado, e o football-data **reescreve** os CSVs (corrige
  placares, adiciona odds). Sem o manifesto, nem você daqui a seis meses consegue reproduzir
  um número do relatório. Um teste avisa quando um arquivo mudou desde o último registro.

#### 1c. Parsers dos três formatos
- `formatos.py`: detecta qual formato o arquivo usa e mapeia para os nomes padrão.
  Os três mapeamentos devem ser **dados declarativos** (dicionários), não `if` espalhado.
- `limpeza.py`: unifica tudo numa tabela com colunas padrão:
  `data, liga, temporada, mandante, visitante, gols_mandante, gols_visitante, resultado,`
  `odd_pre_H, odd_pre_D, odd_pre_A, odd_pre_over25, odd_pre_under25,`
  `odd_fech_H, odd_fech_D, odd_fech_A, odd_fech_over25, odd_fech_under25`
  - As colunas `odd_pre_*` vêm de `Avg*` (formato A) ou `BbAv*` (formato B), e ficam **vazias**
    no formato C.
  - As colunas de Over/Under ficam **vazias** nos formatos B (fechamento) e C (tudo).
  - 🔎 Nomes antigos `odd_casa_*` foram renomeados para `odd_pre_*`, porque "abertura" não existe
    na fonte (ver regra 2.6a).
- `nomes_times.py`: padroniza nomes usando **`mapa_times.csv` versionado no Git**.
  ⚠️ Se aparecer um nome de time que não está no mapa, o teste **falha**. Falhar em silêncio
  aqui significa perder jogos na junção sem ninguém perceber.
- 🔎 **Estratégia de nomes para 38 competições (este é o maior custo da Fase 1).**
  Com todas as ligas ligadas são ~1.500 clubes, em vários idiomas. Regras obrigatórias:
  - **A chave de um time é sempre `LIGA:nome_padrao`** (ex.: `BRA:Palmeiras`, `ARG:River Plate`),
    nunca o nome sozinho. Existem clubes homônimos em países diferentes — "Nacional", "River
    Plate", "Racing", "Independiente", "Everton" (há um no Chile) — e juntar dois deles por
    engano corrompe silenciosamente o Elo e as médias móveis.
  - **Normalização automática antes do mapa:** remover acentos, baixar para minúsculas, remover
    pontuação e sufixos comuns (`FC`, `CF`, `AFC`, `SC`, `AC`, `CD`, `SV`, `BK`). Só o que
    sobrar ambíguo vai para o mapa manual.
  - **Construção incremental:** o script processa liga por liga e, ao encontrar nomes novos,
    grava-os em `data/nomes_pendentes.csv` com uma sugestão de correspondência. O Enzo revisa
    e move para `mapa_times.csv`. Nada entra no mapa automaticamente sem revisão.
  - **Times que mudam de nome ou de divisão** (subidas e descidas) devem apontar para a mesma
    chave, senão o histórico do time se parte em dois.
- Tratar datas em formatos diferentes, jogos sem odds, linhas vazias, jogos adiados.
- Salvar em `data/processed/jogos.parquet`.
- Script `scripts/baixar_dados.py`.

#### 1d. Relatório de cobertura
Resumo obrigatório, por liga e temporada:
- número de jogos;
- **% de odds faltando, separado por mercado e por pré/fechamento**;
- ⚠️ **viés de seleção:** jogos sem odds não são aleatórios (times pequenos, jogos adiados,
  ligas menores). O relatório deve dizer quantos são e a Fase 6 deve declarar o que faz com eles.

#### 1e. ⚠️ TAREFA DE DECISÃO DO ENZO — o papel das ligas do Grupo 2 🔎

Os dados confirmam: o `BRA.csv` — e os outros 15 arquivos do Grupo 2 — têm **fechamento de 1X2
com cobertura praticamente total**, mas **nenhuma odd pré-fechamento** e **nenhum Over/Under**.
Isso significa que o Brasileirão (e Argentina, México, EUA, Japão…):

- ✅ **pode** entrar no treino dos modelos (tem resultados e placares desde 2012);
- ✅ **pode** servir para avaliar log loss e Brier contra o mercado de 1X2;
- ❌ **não pode** entrar no backtest de apostas (não há odd pré-jogo para simular a aposta);
- ❌ **não pode** medir CLV;
- ❌ **não pode** contribuir com o mercado de Over/Under.

O Claude Code deve apresentar esta tabela ao Enzo e pedir a escolha:

| Opção | O que faz | Consequência |
|---|---|---|
| **1 (recomendada)** | Todo o Grupo 2 entra como **treino e avaliação de calibração**; o backtest de apostas roda só no Grupo 1 | Aproveita ~63.200 jogos (5.586 só do Brasil) sem contaminar o backtest. Exige marcar claramente no relatório quais ligas entram em qual análise. |
| **2** | Grupo 2 fica só na análise exploratória (Fase 2) | Mais simples, aproveita muito menos. |
| **3** | Ignorar o Grupo 2 | Projeto mais leve e homogêneo, mas joga fora mais da metade dos dados e o campeonato nacional do Enzo. |

⚠️ **Se a opção 1 for escolhida (recomendado), a regra é inegociável:** toda tabela de resultado
precisa dizer **quais ligas entraram naquela análise**. Misturar, num mesmo número, ligas que
podem apostar com ligas que só treinam é o tipo de erro que passa despercebido e invalida
o relatório inteiro.

A decisão deve ser **registrada no CLAUDE.md** em "Decisões tomadas", com a data.

#### Testes da fase
Sem duplicatas, datas válidas, gols não negativos, resultado coerente com o placar, nome de
time desconhecido faz falhar, colunas esperadas presentes por formato, manifesto confere.

**Pronto quando:** o Parquet existe, o relatório de cobertura mostra jogos e % de odds faltando por liga/temporada/mercado, o `mapa_times.csv` cobre todas as ligas ativas sem pendências, e a decisão sobre o Grupo 2 está registrada no CLAUDE.md.

---

### Fase 2 — Análise exploratória e o "mercado"
**Objetivo:** entender os dados e medir quão bom é o mercado.
- `mercado.py`:
  - probabilidade implícita (`1/odd`);
  - overround;
  - remoção de margem (método proporcional **e** método de Shin ou "power", comparando os dois).
- Notebook `01_exploracao.ipynb`:
  - distribuição de gols por jogo (comparar com Poisson);
  - **vantagem de mando de campo por liga E por temporada** 🔎
    *Por quê:* em 2020 e 2021, com estádios vazios, a vantagem de mando caiu muito em quase
    todas as ligas. Um modelo que trata o fator casa como constante ao longo de 10 temporadas
    fica errado num pedaço grande do treino. Este gráfico é uma das análises mais interessantes
    do projeto e justifica o fator casa variável da Fase 3;
  - frequência de mais de 2,5 gols por liga;
  - margem média das casas por liga e mercado (comparar pré-jogo × fechamento);
  - calibração do mercado: quando a odd diz 60%, acontece ~60%?
  - 🔎 **ranking de margem por liga**, reproduzindo e atualizando a tabela da seção 4.3 com
    todas as temporadas (a tabela da especificação usou só 2024/25 para o Grupo 1);
  - 🔎 **a margem cobrada por uma liga mudou ao longo dos anos?** O mercado ficou mais eficiente?
- **Baseline do mercado:** log loss e Brier das odds de fechamento sem margem. Esta é a meta a ser batida.
  - ⚠️ Calcular separadamente por liga e por formato, já que o formato B não tem fechamento de O/U.
- 🔎 **Aplicar o filtro de qualidade de mercado** (seção 4.3): calcular margem, cobertura de
  odds, calibração e número de jogos por liga, e produzir a **lista final de ligas aprovadas
  para o backtest**. Gravar essa lista no `config.yaml` e registrar no CLAUDE.md quais ligas
  foram reprovadas e por quê.
  ⚠️ Esta é a resposta com dados para o pedido "quero as ligas em que tem apostas boas" —
  a decisão sai da medição, não do chute.
- Relatório em `docs/relatorios/fase2.md`, com uma tabela **por liga**.

**Pronto quando:** o Enzo sabe responder "qual é a margem média da casa em cada liga?", "o mercado é bem calibrado?", "a vantagem de jogar em casa mudou ao longo dos anos?" e "quais ligas passaram no filtro de qualidade?".

---

### Fase 3 — Modelos de Poisson e Dixon-Coles
**Objetivo:** primeiro modelo próprio.
- Interface comum em `base.py`: `treinar(jogos_ate_data)` e `prever(jogo) -> dict de probabilidades`.
- `baseline.py`: probabilidades médias históricas da liga (modelo "burro" de referência).
- `poisson.py`: força de ataque e defesa por time + fator casa.
- 🔎 **Fator casa não constante:** estimar o fator casa **por liga** e deixá-lo variar no tempo
  (o decaimento temporal do Dixon-Coles já ajuda bastante). Testar contra a versão de fator fixo
  e reportar a diferença — é um experimento pequeno e didático.
- `dixon_coles.py`: correção de placares baixos + **decaimento temporal** (jogos antigos pesam menos; parâmetro `xi` no config).
  - ⚠️ O `xi` deve ser **escolhido por validação** (walk-forward no conjunto de validação),
    nunca chutado nem ajustado olhando o teste final.
- A partir da matriz de placares (0–10 gols cada lado), derivar: 1X2, Over/Under 2,5, ambos marcam, placar mais provável.
- **Times recém-promovidos:** usar encolhimento (*shrinkage*) para a média da liga quando o time
  tem poucos jogos. Documentar a fórmula no CLAUDE.md.
- Testes: probabilidades somam 1, sem valores negativos, matriz de placares correta, shrinkage
  aplicado a time novo.

**Pronto quando:** dá para rodar `scripts/prever.py --mandante "Arsenal" --visitante "Chelsea"` e ver as probabilidades.

---

### Fase 4 — Avaliação honesta (walk-forward)
**Objetivo:** saber se o modelo presta.
- `validacao.py`: walk-forward — para cada rodada, treinar só com jogos anteriores e prever a rodada.
- `metricas.py`: log loss, Brier score, acurácia, curva de calibração.
- Comparar: baseline × Poisson × Dixon-Coles × **mercado de fechamento**.
- ⚠️ **O log loss no walk-forward de validação é o critério oficial de escolha de modelo**
  (regra 2.6b).
- Separar dados em:
  - **Treino/validação:** temporadas antigas (para escolher parâmetros);
  - **Teste final:** as 2 temporadas mais recentes, **usadas uma única vez** na Fase 9.
- Gráficos de calibração salvos em `docs/relatorios/`.
- Teste automatizado contra data leakage.

**Pronto quando:** existe uma tabela comparando os modelos com o mercado. Esperado: o mercado ganha. Isso é normal e não é fracasso.

---

### Fase 5 — Features e modelo de machine learning
**Objetivo:** tentar melhorar com ML.
- `elo.py`: rating Elo por time, atualizado jogo a jogo.
- `construtor.py` — features (todas calculadas só com jogos anteriores):
  - Elo de cada time e diferença;
  - média móvel de gols feitos/sofridos (últimos 5 e 10 jogos), separando casa/fora;
  - pontos nos últimos 5 jogos;
  - dias de descanso desde o último jogo;
  - probabilidades do Dixon-Coles como feature;
  - indicador de temporada com estádio vazio (2020/21) 🔎;
  - (opcional) xG, se a fonte for adicionada.
- `gbm.py`: LightGBM multiclasse (1X2) e binário (Over 2,5).
- Calibrar as probabilidades (isotonic ou Platt) se necessário.
- Mostrar importância das features (explicar ao Enzo o que cada uma significa).
- Avaliar com o mesmo walk-forward da Fase 4.

**Pronto quando:** tabela da Fase 4 atualizada com o LightGBM.

---

### Fase 6 — Backtest de apostas
**Objetivo:** responder "teria dado lucro?".

- `estrategias.py`:
  - **Stake fixa** (ex.: 1% da banca inicial por aposta);
  - **Kelly fracionado** (1/4 de Kelly), com teto por aposta;
  - ⚠️ **Definir e reportar as DUAS variantes de banca:** *banca fixa* (stake calculada sempre
    sobre a banca inicial) e *banca composta* (stake recalculada a cada aposta sobre a banca
    atual). A escolha muda ROI e drawdown de forma enorme, e omitir qual foi usada é uma das
    formas mais comuns de relatório enganoso.
- `simulador.py`:
  - aposta só quando `EV > limite` (limite configurável, ex.: 5%);
  - 🔎 **aposta na odd média pré-jogo (`odd_pre_*`)** e usa a de fechamento (`odd_fech_*`)
    só para medir CLV (regra 2.6a). Nunca apostar na `Max`;
  - ⚠️ pular automaticamente jogos sem `odd_pre_*` (ex.: todo o Brasileirão) e **reportar
    quantos foram pulados**;
  - registrar cada aposta (data, jogo, mercado, odd, prob. modelo, EV, resultado, lucro, CLV).
- Métricas: nº de apostas, taxa de acerto, ROI, lucro, drawdown máximo, CLV médio,
  **intervalo de confiança do ROI e do CLV via bootstrap**, erro-padrão de cada um.
- ⚠️ **Relatório de poder estatístico obrigatório:** junto com o ROI, reportar
  "com N apostas, o menor ROI detectável a 95% é X%" (função `tamanho_amostra` em `metricas.py`,
  fórmula na seção 8). Sem isso, o número do ROI não quer dizer nada.
- ⚠️ Registrar **quantas configurações foram testadas** (regra 2.6e).
- Comparação obrigatória: estratégia aleatória com o mesmo número de apostas.
- Gráfico da evolução da banca.
- Script `scripts/backtest.py` com parâmetros por linha de comando.

**Pronto quando:** relatório `docs/relatorios/fase6.md` com os números, o poder estatístico e uma conclusão clara: "há evidência de vantagem", "não há", ou **"a amostra é pequena demais para decidir"** — esta terceira é uma conclusão legítima e provavelmente a mais honesta.

---

### Fase 7 — Simulador de múltiplas e cash out
**Objetivo:** medir, com dados, o efeito das múltiplas e do cash out.

#### 7.1 ⚠️ Independência entre seleções — limitação assumida e como lidar

Este é o ponto conceitualmente mais delicado da fase. Leia antes de codar.

**O que o projeto faz:** a probabilidade de uma múltipla acertar é calculada como o **produto
das probabilidades das seleções**.

**Por que isso é parcialmente errado:**
1. **Dentro do mesmo jogo** os mercados são fortemente correlacionados (se o mandante vence,
   é mais provável que tenha saído mais de 2,5 gols). → **Resolvido** pela restrição de
   **no máximo uma seleção por jogo**.
2. **Entre jogos diferentes** ainda existe correlação, menor mas real: rodadas com muitos gols,
   efeitos de calendário e clima, e principalmente **erro compartilhado do próprio modelo**
   (se o modelo está subestimando gols naquele mês, erra na mesma direção em todos os jogos).
   → **Não resolvido.** O produto simples **superestima** a chance de acertar múltiplas grandes.

**⚠️ O que NÃO resolve isso:** simular por Monte Carlo a partir das matrizes de placar de cada
jogo **de forma independente**. Se os jogos são sorteados independentemente, a simulação apenas
reproduz o produto das probabilidades, com ruído amostral a mais. **Não é um conserto** —
é o mesmo número por um caminho mais caro.
*(O Monte Carlo continua útil para outra coisa: obter a **distribuição do número de acertos**
de uma múltipla, que é o que a análise de cash out precisa. Só não serve para corrigir a
correlação entre jogos.)*

**O que o projeto faz então (obrigatório):**
- **Documentar a limitação** de forma explícita no relatório da fase **e na tela do app**:
  "a chance de ganhar mostrada assume independência entre jogos; a chance real tende a ser
  um pouco menor, especialmente em múltiplas grandes."
- **Medir o tamanho do erro empiricamente** (ver validação histórica em 7.4): comparar
  **taxa de acerto real × taxa prevista, por tamanho de múltipla**. Se o desvio crescer com o
  número de seleções, está vendo a correlação em ação — e isso vira um dos resultados mais
  interessantes do projeto.

**Item OPCIONAL (só se sobrar tempo, e só depois de 7.4 funcionar):**
modelar a correlação com um **efeito compartilhado por rodada**: multiplicar todos os λ (lambdas)
dos jogos da mesma rodada por `exp(ε)`, com `ε ~ Normal(0, σ²)` sorteado uma vez por rodada.
Estimar `σ` a partir da dispersão histórica de gols por rodada (comparando a variância real com
a variância que o Poisson prevê). Validar medindo se o descasamento real × previsto de 7.4
diminui. Se não diminuir, descartar e reportar isso.

#### 7.2 `multiplas.py`
- montar múltiplas de 2 a 10 seleções (ex.: as "mais prováveis" de cada rodada, segundo o modelo);
- calcular a odd combinada e a margem acumulada;
- simular milhares de múltiplas nos dados históricos e mostrar ROI por nº de seleções.

#### 7.3 `cash_out.py`
- dado uma múltipla em andamento, calcular o **valor justo**: `prob_restante × prêmio`;
- simular uma oferta da casa com margem (parâmetro configurável, ex.: 5–10% abaixo do justo);
- comparar estratégias: nunca sacar, sempre sacar após X acertos, sacar só quando a oferta >
  valor justo do modelo;
- usar o Monte Carlo para a **distribuição do número de acertos** (ver nota em 7.1).

#### 7.4 `montador.py` — montador flexível de múltiplas (número de jogos NÃO é fixo)
- **Entradas do usuário:** valor apostado; e UMA destas opções:
  - número de seleções desejado (qualquer valor de 1 a N, configurável), ou
  - prêmio alvo (ex.: "quero ganhar R$ 200 com R$ 10"), ou
  - faixa de seleções (ex.: "entre 3 e 6 jogos") para comparar as opções.
- **Candidatos:** todos os mercados dos jogos da rodada (1X2, Over/Under 2,5, e outros que existirem), com a odd informada e a probabilidade do modelo (já com o ajuste de desfalques da Fase 10, quando existir).
- **Otimização:** para cada tamanho de múltipla, encontrar a combinação que:
  1. atinge o prêmio alvo (se informado);
  2. maximiza a **probabilidade real de ganhar** segundo o modelo;
  3. como critério de desempate e alerta, calcula o **valor esperado (EV)**.
  Usar busca eficiente (ex.: ordenar candidatos e busca em feixe / beam search), não força bruta em todas as combinações.
- **Restrições:**
  - no máximo **uma seleção por jogo** (mercados do mesmo jogo são correlacionados; a multiplicação simples de probabilidades seria errada);
  - odd mínima e máxima por seleção configuráveis;
  - descartar seleções em que o modelo tem poucos dados (ex.: times recém-promovidos).
- **Saída para cada opção (ex.: 4 jogos, 6 jogos, 10 jogos):**
  - lista das seleções, com odd e probabilidade do modelo de cada uma;
  - odd total e prêmio potencial;
  - **chance real de ganhar** (produto das probabilidades do modelo), em % e em "1 em X",
    ⚠️ **acompanhada do aviso de independência de 7.1**;
  - chance que a casa atribui (produto das probabilidades implícitas);
  - margem acumulada da casa;
  - EV da aposta em R$ (quanto se ganha ou perde em média por aposta);
  - aviso visual quando o EV for negativo (o caso mais comum).
- **Tabela comparativa** entre tamanhos: mostra lado a lado como a chance de ganhar cai e a margem sobe à medida que se adicionam jogos.
- **⚠️ Validação histórica (obrigatória, é o coração da fase):** rodar o montador nas rodadas
  passadas (walk-forward) para **cada tamanho de múltipla** e reportar, lado a lado:
  - **taxa de acerto real × taxa de acerto prevista** (com intervalo de confiança);
  - o **desvio entre as duas, em função do número de seleções** — a evidência empírica da
    correlação discutida em 7.1;
  - ROI por tamanho, com intervalo de confiança.
- Testes: probabilidades entre 0 e 1, uma seleção por jogo, prêmio calculado corretamente, resultado igual com a mesma semente.

**Pronto quando:** o relatório mostra, com números, (a) como a margem cresce com o número de jogos, (b) **o quanto a taxa de acerto real fica abaixo da prevista conforme a múltipla cresce**, e (c) se alguma regra de cash out muda o resultado.

---

### Fase 8 — Aplicativo Streamlit
**Objetivo:** interface visual.
Páginas:
1. **Início:** explicação do projeto e aviso de jogo responsável.
2. **Prever jogo:** escolher liga e times → probabilidades de cada modelo, odds justas (`1/prob`) e placares mais prováveis.
3. **Comparar com odds:** o usuário digita as odds que viu → app mostra EV de cada mercado.
4. **Backtest:** escolher modelo, estratégia, limite de EV, período → gráfico da banca e métricas,
   **sempre com o intervalo de confiança e o número de apostas visíveis**.
5. **Montador de múltiplas:** o usuário informa o valor e o número de jogos (ou o prêmio alvo, ou uma faixa de jogos) → o app sugere as melhores combinações da rodada, com chance real de ganhar, margem acumulada, EV e a tabela comparativa entre tamanhos. Também permite montar uma múltipla manualmente e avaliá-la.
   ⚠️ Exibir o aviso de independência de 7.1 junto da "chance de ganhar".
6. **Cash out:** informar uma múltipla em andamento e a oferta da casa → app mostra o valor justo e se a oferta está acima ou abaixo dele.
7. **Desempenho dos modelos:** tabelas e gráficos da Fase 4/5.

**Pronto quando:** `streamlit run src/futebol/app/streamlit_app.py` abre o app no navegador.

---

### Fase 9 — Teste final e próximos jogos
- ⚠️ **Antes de abrir o teste final:** registrar no CLAUDE.md a configuração escolhida
  (modelo, mercado, limite de EV, estratégia de stake) e quantas configurações foram testadas
  na validação (regra 2.6e). Depois disso, rodar **uma única vez** a avaliação e o backtest
  nas temporadas de teste final.
- Relatório final `docs/relatorios/final.md` aplicando o critério de parada da seção 8, e README
  atualizado para portfólio (com prints do app).
- 🔎 **Preparar o deploy (decidir na Fase 8, executar aqui):** o app depende de
  `data/processed/jogos.parquet`, que **não está no Git** — um deploy ingênuo sobe e quebra.
  Escolher uma das duas saídas:
  - **(a)** gerar um Parquet reduzido (só as colunas que o app usa, provavelmente < 5 MB) e
    versioná-lo; ou
  - **(b)** o app baixa e processa os dados no primeiro boot, com cache.
- Opcional: baixar a lista de próximos jogos (arquivo de fixtures do football-data) e gerar previsões da rodada.
- Opcional: deploy do app (Streamlit Community Cloud).

---

### Fase 10 — Notícias, desfalques e escalações (informação do mundo real)
**Objetivo:** ajustar as probabilidades com base em desfalques e notícias **somente dos times que vão jogar**.

**Pré-requisito:** Fases 3 a 9 concluídas (o modelo base precisa existir e estar avaliado).

> ⚠️ **Enquadramento honesto desta fase (leia primeiro).**
> Esta fase é uma **demonstração de engenharia de dados e de uso correto de LLM** — pipeline de
> coleta filtrada, extração estruturada e ajuste parametrizado. **Ela não é, e não pode ser,
> uma hipótese validada estatisticamente dentro do prazo do projeto.**
> Motivo: "algumas semanas" de jogos são ~50 a 150 previsões. Detectar uma melhora de log loss
> dessa magnitude com essa amostra é impossível — a diferença fica enterrada no ruído.
> Se você olhar um log loss levemente melhor depois de 6 semanas e concluir que o ajuste
> funciona, vai concluir errado. Avalie por **CLV** (converge mais rápido, ver seção 8) e,
> ainda assim, trate o resultado como **indício**, nunca como prova.

**Pipeline (sempre nesta ordem, para filtrar antes de buscar):**
1. **Jogos alvo:** buscar os jogos dos próximos N dias (N no `config.yaml`) das ligas escolhidas.
2. **Times alvo:** extrair a lista de times desses jogos. Nenhuma busca acontece fora dessa lista.
3. **Dados estruturados (fonte principal):** consultar uma API de futebol que forneça lesões, suspensões e escalações prováveis/confirmadas por time e por jogo (ex.: API-Football / api-sports.io). **Confirmar endpoints, limites do plano gratuito e termos de uso atuais antes de implementar.**
4. **Notícias (fonte complementar):** buscar notícias apenas com o nome de cada time alvo, das últimas 48–72h, via RSS de portais esportivos, Google News RSS ou uma API de notícias. Deduplicar por título/URL.
5. **Extração com LLM:** enviar cada notícia filtrada para a API da Anthropic (Claude) com instrução de responder **somente JSON**:
   `{"time": "", "jogador": "", "status": "fora|duvida|volta", "motivo": "", "confianca": 0-1, "fonte": "", "data": ""}`
   Notícias sem informação sobre desfalques são descartadas. (Este é o uso correto de LLM no projeto: ler texto, não calcular probabilidade.)
6. **Importância do jogador:** calcular um peso por jogador com dados históricos (minutos jogados, participação em gols, titularidade). Um reserva fora pesa quase nada; o artilheiro fora pesa muito.
7. **Ajuste do modelo:** reduzir a força de ataque/defesa do time proporcionalmente ao peso dos desfalques confirmados (dúvidas pesam metade). Fórmula e limites no `config.yaml`, documentados no CLAUDE.md.
8. **Saída:** mostrar no app, para cada jogo, a probabilidade **antes e depois** do ajuste, com a lista de desfalques e links das fontes.

**Arquivos novos:**
```
src/futebol/noticias/
├── jogos_alvo.py
├── api_futebol.py        # lesões, suspensões, escalações
├── coletor_noticias.py   # RSS / API de notícias, filtrado por time
├── extrator_llm.py       # Claude -> JSON estruturado
├── importancia.py        # peso de cada jogador
└── ajuste.py             # aplica os desfalques no modelo
```

**Regras específicas desta fase:**
- Chaves de API **somente** no arquivo `.env` (nunca no código, nunca no Git). Criar `.env.exemplo` sem valores.
- Cache local das respostas (não repetir requisições) e controle de limite diário de chamadas.
- Registrar em log cada previsão ajustada com data/hora, para avaliação futura.
- Testes com respostas de API e notícias **falsas** (mocks), sem chamar a internet.

**Como avaliar (importante):** não dá para fazer backtest confiável com notícias do passado, porque é muito difícil saber o que era conhecido *antes* de cada jogo. Por isso a avaliação é **para frente** (paper trading):
- Registrar as previsões ajustadas e não ajustadas antes de cada jogo.
- Comparar **CLV** (métrica primária, converge mais rápido) e log loss das duas versões.
- ⚠️ Reportar sempre o número de jogos acumulados e o intervalo de confiança. Enquanto o IC
  cruzar zero, a resposta honesta é **"ainda não dá para saber"**.
- Só manter o ajuste se ele melhorar as métricas de forma consistente e com amostra suficiente.

**Guia para leigos deve ensinar:** criar conta e chave nas APIs, preencher o `.env`, rodar a coleta dos próximos jogos e ler o resultado no app.

**Pronto quando:** o app mostra, para os jogos da próxima rodada, os desfalques encontrados e as probabilidades antes/depois do ajuste, **com o aviso de que o efeito ainda não está validado**.

---

## 7. Modelo do CLAUDE.md

```markdown
# CLAUDE.md — Previsão Probabilística de Futebol

## Sobre o projeto
Projeto de ML que calcula probabilidades de jogos de futebol, compara com as odds
das casas e faz backtest honesto. Especificação completa: PROJETO_PREVISAO_FUTEBOL.md.

## Dono
Enzo — estudante de Engenharia de Software, aprendendo ML. Explicar decisões de forma
didática. Idioma: português do Brasil.

## Regras obrigatórias
1. Ler este arquivo no início de toda sessão.
2. Commitar ao fim de cada subtarefa (Conventional Commits em português).
3. Rodar `pytest` antes de cada commit; não commitar com testes falhando.
4. Nunca commitar data/raw, data/processed, .env, .venv ou arquivos > 5 MB.
5. Ao fim de cada fase: tag `fase-X`, atualizar "Status atual", criar
   docs/guias/GUIA_FASE_X.md para leigos (Windows primeiro), mostrar no chat
   e ESPERAR aprovação do Enzo antes da próxima fase.
6. Sem data leakage: previsões para a data D usam só jogos anteriores a D.
7. Não usar as temporadas de teste final antes da Fase 9.
8. Apostar sempre na odd MÉDIA pré-jogo (Avg/BbAv). Nunca na Max como cenário
   principal. Max só como "cenário otimista", sempre rotulado.
9. Escolha de modelo é por LOG LOSS no walk-forward de validação. Nunca por ROI.
10. Reportar ROI e CLV sempre com intervalo de confiança, nº de apostas e o menor
    efeito detectável naquela amostra.
11. Registrar quantas configurações foram testadas; pré-registrar aqui a escolhida
    antes de abrir o teste final.
12. Ligas do GRUPO 2 (BRA, ARG, USA, MEX, JPN, CHN, AUT, DNK, FIN, IRL, NOR,
    POL, ROU, RUS, SWE, SWZ) só têm odds de fechamento: servem para treino e
    calibração, NUNCA para backtest de apostas nem para CLV. Ver seção 4.4.
13. Toda tabela de resultado deve dizer QUAIS ligas entraram naquela análise.
14. Chave de time é sempre LIGA:nome (ex.: BRA:Palmeiras). Nunca o nome sozinho —
    há clubes homônimos em países diferentes.

## Comandos
- Ativar ambiente (Windows): `.venv\Scripts\Activate.ps1`
- Ativar ambiente (Mac/Linux): `source .venv/bin/activate`
- Instalar o projeto: `pip install -e .`
- Testes: `pytest`
- Lint: `ruff check . --fix`
- Baixar dados: `python scripts/baixar_dados.py`
- Backtest: `python scripts/backtest.py`
- App: `streamlit run src/futebol/app/streamlit_app.py`

## Status atual
- Fase atual: 0
- Última tag: —
- Camada de ligas ativa: camada_aprendizado (só E0) — ampliar conforme as fases avançam
- Próximo passo: —

## Decisões tomadas
- 15/09/2026: escopo ampliado para TODAS as 38 competições da fonte — 22 ligas do
  Grupo 1 (backtest completo, ~53.800 jogos desde 2019/20) + 16 países do Grupo 2
  (treino e calibração apenas, ~63.200 jogos). Motivo: pedido do Enzo por todas as
  ligas com apostas boas + tamanho de amostra (seção 8).
- 15/09/2026: a lista final de ligas aprovadas para aposta sai do filtro de
  qualidade de mercado da Fase 2 (margem, cobertura, calibração), não de escolha
  manual.
- (registrar aqui cada decisão importante com data)

## Pré-registro do teste final (preencher antes da Fase 9)
- Configurações testadas na validação: —
- Configuração escolhida: —
- Data do pré-registro: —

## Problemas conhecidos
- (registrar aqui)
```

---

## 8. Critério de parada (importante)

### 8.1 ⚠️ Por que o critério antigo não funcionava

A versão anterior deste documento pedia "ROI positivo com IC todo acima de zero" **e**
"pelo menos 1.000 apostas". Esses dois critérios **brigam entre si**. Veja por quê.

O retorno de uma aposta de 1 unidade em odd `b` é: `b−1` se ganhar, `−1` se perder.
Com probabilidade justa, o desvio-padrão desse retorno é aproximadamente:

```
desvio-padrão por aposta ≈ √(b − 1)
```

- Odd 2,00 → desvio-padrão ≈ **1,0** (ou seja, **100% de volatilidade por aposta**)
- Odd 3,00 → desvio-padrão ≈ **1,41**

Com 1.000 apostas em odds perto de 2,00:

```
erro-padrão do ROI = 1,0 / √1000 ≈ 3,2%
IC 95% = ROI ± 6,2 pontos percentuais
```

**Conclusão:** com 1.000 apostas, o IC só fica todo acima de zero se o ROI observado passar
de ~6%. Um edge real de 2 a 3% — que já seria excelente e realista — **é indetectável**.
E um ROI observado acima de 6% em 1.000 apostas quase sempre significa uma de três coisas:
sorte, data leakage, ou aposta na `Max`. **O critério antigo filtrava a favor de resultados falsos.**

### 8.2 Quantas apostas seriam necessárias

Fórmula (implementar como `tamanho_amostra()` em `metricas.py`, com testes):

```
n ≈ ( 1,96 × desvio_padrão / ROI_verdadeiro )²
```

| ROI verdadeiro | Odd média | Apostas necessárias |
|---|---|---|
| 2% | 2,00 | ~9.600 |
| 2% | 3,00 | ~19.100 |
| 3% | 2,00 | ~4.300 |
| 5% | 2,00 | ~1.500 |

É por isso que o escopo foi ampliado. Com as 2 ligas originais a amostra ficaria na casa das
centenas de apostas e **nenhuma conclusão sobre ROI seria possível**. Com as **22 ligas do
Grupo 1** (~53.800 jogos elegíveis para aposta, seção 4.2), as ~5.000 apostas necessárias
passam a ser **confortavelmente alcançáveis** — o critério secundário de ROI deixa de ser
decorativo e vira mensurável de verdade.

⚠️ **Cuidado com o outro lado da moeda:** amostra grande também torna significativo qualquer
viés sistemático. Com 50 mil jogos, um erro pequeno no parser ou um leakage sutil produz um
"edge" com IC estreitíssimo e totalmente falso. Quanto maior a amostra, **mais** importa o
teste automatizado contra leakage (regra 2.5) e a conferência do manifesto (Fase 1b).

### 8.3 CLV é o critério primário 🔎⚠️

O **CLV é medido comparando a odd que você pegou com a odd de fechamento** — ele **não depende
do resultado do jogo**. Por isso sua variância por observação é uma ordem de grandeza menor que
a do ROI, e ele converge com **centenas** de apostas, não dezenas de milhares.

Na escala deste projeto, **o CLV é o único sinal de vantagem que pode realmente ser medido.**
Por isso ele foi promovido a critério primário.

- O projeto deve **medir empiricamente o desvio-padrão do CLV** nos seus próprios dados
  (não confiar em número de referência) e reportar o tamanho de amostra necessário a partir dele.
- ⚠️ Lembrete: o CLV **não pode ser medido em nenhuma liga do Grupo 2** — Brasileirão incluído
  (seção 4.4). O CLV do projeto vem inteiramente das 22 ligas do Grupo 1.

### 8.4 Critério de parada revisado

Antes de pensar em usar dinheiro real, o projeto precisa mostrar **todos** estes pontos no teste final:

**Critérios primários (obrigatórios):**
1. **CLV médio positivo com intervalo de confiança inteiro acima de zero**, com amostra
   suficiente segundo o cálculo de tamanho de amostra feito nos próprios dados.
2. Desempenho consistente em **mais de uma liga** e **mais de uma temporada**.
   🔎 Com 22 ligas no backtest, "consistente" precisa de definição: o CLV médio deve ser
   positivo na **maioria das ligas com amostra suficiente**, e não pode depender de uma única
   liga. Reportar sempre a tabela por liga junto do número agregado — se o resultado sumir
   ao tirar a melhor liga, era sorte.
3. Configuração **pré-registrada** no CLAUDE.md antes de abrir o teste final (regra 2.6e).

**Critérios secundários (confirmatórios):**
4. ROI positivo com o intervalo de confiança inteiro acima de zero.
5. **Pelo menos 5.000 apostas simuladas** para que o critério 4 tenha qualquer poder
   (ver tabela de 8.2). Com menos que isso, a conclusão correta sobre o ROI é
   **"amostra insuficiente"**, e não "não há vantagem" nem "há vantagem".

**Como ler o resultado:**

| Situação | Conclusão correta |
|---|---|
| CLV positivo com IC acima de zero + consistência | Há **indício** de vantagem. Continuar medindo. |
| CLV com IC cruzando zero | **Sem evidência de vantagem.** |
| ROI positivo mas com menos de 5.000 apostas | **Amostra insuficiente** — não é evidência de nada. |
| ROI muito alto (>6%) com amostra pequena | **Suspeitar de bug**: procurar data leakage ou uso da `Max`. |

Se qualquer critério primário falhar, a conclusão é: **o modelo não tem vantagem demonstrável sobre as casas.** O projeto continua valioso como portfólio de ML — e a análise de poder estatístico que levou a essa conclusão é, tecnicamente, um dos pontos mais fortes dele.

Mesmo com resultado positivo: começar com valores mínimos, apostar só dinheiro que se pode perder, e lembrar que as casas costumam limitar contas lucrativas.

---

## 9. Jogo responsável
O app deve exibir, na página inicial, um aviso curto: apostas envolvem risco de perda, o projeto é educacional, e quem sentir que perdeu o controle pode buscar apoio (ex.: Jogadores Anônimos, CVV — 188).

---

## 10. Primeira mensagem sugerida para o Claude Code

> Leia o arquivo PROJETO_PREVISAO_FUTEBOL.md por completo. Depois execute a Fase 0,
> seguindo todas as Regras do Projeto da seção 2. Ao terminar, me passe o guia para
> leigos e espere minha aprovação antes da Fase 1.
