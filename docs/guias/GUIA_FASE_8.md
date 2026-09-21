# Guia da Fase 8 — O aplicativo: o projeto que dá para clicar

Este guia é para quem nunca programou. Os comandos são do **Windows
(PowerShell)** primeiro; a versão Mac/Linux está no fim.

Até agora o projeto era um monte de arquivos de texto. Esta fase transforma tudo
em **sete telas de navegador**: escolher dois times e ver as probabilidades,
digitar as odds que você viu e ver o valor esperado, montar um bilhete de
múltipla, conferir se uma oferta de cash out é justa.

E esta fase tem uma responsabilidade que nenhuma outra teve. Um relatório é lido
por quem quer conferir; um app é usado por quem quer uma resposta. É a primeira
entrega do projeto que alguém pode usar **sem ler nada** — e por isso tudo o que
as Fases 6 e 7 mediram de ruim precisa estar na tela, não numa nota de rodapé.

---

## Índice

1. [Abrir o app](#1-abrir-o-app)
2. [As sete telas, uma por uma](#2-as-sete-telas-uma-por-uma)
3. [A parte mais importante: os avisos](#3-a-parte-mais-importante-os-avisos)
4. [Duas limitações que a tela admite](#4-duas-limitações-que-a-tela-admite)
5. [Por que o app não pode discordar dos relatórios](#5-por-que-o-app-não-pode-discordar-dos-relatórios)
6. [A decisão de deploy](#6-a-decisão-de-deploy)
7. [Erros comuns](#7-erros-comuns)
8. [Como saber que está tudo certo](#8-como-saber-que-está-tudo-certo)

---

## 1. Abrir o app

```powershell
.venv\Scripts\Activate.ps1
streamlit run src\futebol\app\streamlit_app.py
```

O navegador abre sozinho em `http://localhost:8501`. Se não abrir, copie esse
endereço na barra do navegador.

Para **fechar**, volte ao PowerShell e aperte `Ctrl + C`.

⚠️ **A primeira vez que você clica em "Backtest" demora** — uns segundos, às
vezes meio minuto. O app está percorrendo cem mil apostas candidatas. Depois
disso fica instantâneo, porque o resultado fica guardado em memória por uma hora.

⚠️ **O app precisa dos dados prontos.** Se aparecer uma tela vermelha dizendo que
a tabela de jogos não existe, rode antes:

```powershell
python scripts\baixar_dados.py
python scripts\preparar_dados.py
python scripts\validar.py
```

O terceiro é o demorado (cerca de uma hora na primeira vez). Ele é necessário
para as telas de Backtest, Múltiplas e Desempenho: elas mostram medições, e
medição não se inventa na hora do clique.

---

## 2. As sete telas, uma por uma

O menu fica na barra da esquerda.

### 🏠 Início

A explicação do projeto e o **resultado** — inclusive o ruim, logo de cara: ROI
de −12,92%, CLV de −7,82%, zero de 18 ligas com lucro.

Isso é de propósito. Um app de previsão de futebol que abre com gráficos bonitos
e esconde "o modelo perde do mercado" na sétima aba é um app que engana por
omissão. Aqui o veredito vem **antes** da ferramenta.

### 🔮 Prever jogo

Escolha competição, mandante, visitante e data → as probabilidades de cada
mercado, as odds justas e os placares mais prováveis.

Repare que a tela mostra **três modelos lado a lado**, e que eles discordam. Isso
também é de propósito: um número sozinho ("68% para o mandante") parece um fato;
três números diferentes para a mesma pergunta lembram que isto é uma
**estimativa**.

⚠️ **Mudar a data muda a previsão, e é assim que tem de ser.** O modelo é
treinado só com jogos **anteriores** àquela data (é a regra 6 do projeto, contra
olhar o futuro). Pedir uma previsão para 2019 dá um resultado diferente de pedir
para 2024, porque em 2019 se sabia menos.

### ⚖️ Comparar com odds

Você digita as odds que viu no site da casa → o app calcula o valor esperado de
cada aposta.

**Esta é a tela mais perigosa do app**, e o próprio app diz isso. "Valor esperado
+9%" lê-se como "aposte" — e o projeto mediu, em 21.682 apostas, que seguir
exatamente esse número perde 12,9%. Por isso o aviso fica **antes** da conta, em
vermelho, e a tela nunca chama nada de "oportunidade".

Ela também mostra a **comissão da casa** naquelas odds que você digitou: quanto
as probabilidades implícitas somam acima de 100%. É o tamanho da desvantagem com
que todo apostador começa.

### 📉 Backtest

Escolha modelo, limite de valor esperado, estratégia de dinheiro e período → o
que teria acontecido com a banca.

Três coisas que esta tela faz e quase nenhum backtest da internet faz:

- **nenhum número aparece sem o intervalo de confiança e o número de apostas ao
  lado.** Não é estilo: é um componente de código que não sabe desenhar um número
  sozinho;
- **compara com apostar no chute.** Uma linha da tabela é "sorteio, mesmo número
  de apostas". Um modelo que não fica acima do sorteio não está acrescentando
  informação;
- **avisa quando a amostra é pequena.** Abaixo de 5.000 apostas aparece uma caixa
  dizendo que a conclusão correta é *amostra insuficiente* — nem "há vantagem"
  nem "não há".

⚠️ O limite de valor esperado é uma **lista de quatro opções** (0%, 2%, 5%, 10%),
e não um campo para digitar. Campo livre seria um convite a procurar o número que
deixa o gráfico bonito, que é exatamente a armadilha que a regra 11 do projeto
existe para conter.

### 🎟️ Múltiplas

Quatro modos, nas abas de cima:

| Aba | O que faz |
|---|---|
| **Por número de jogos** | "Quero um bilhete de 5 jogos" → o mais provável com 5 |
| **Por prêmio alvo** | "Quero ganhar R$ 500" → o bilhete mais provável que chega lá |
| **Montar na mão** | Você escolhe seleção por seleção, como no site da casa |
| **Comparar tamanhos** | A tabela de 1 a 10 jogos, lado a lado |

Em todas elas aparecem a chance de ganhar, o prêmio e a **comissão acumulada** —
que é o número que a casa nunca mostra. Num bilhete de dez jogos ela chega a 54%.

### 💸 Cash out

Você informa o bilhete em andamento, as chances do que falta e a oferta da casa →
o app diz o valor justo e se a oferta está acima ou abaixo dele.

A conta é simples (chance do que falta × prêmio). O que a tela acrescenta é o
contexto: **a taxa do cash out é a mesma em qualquer momento**. Sacar depois de um
acerto ou depois de nove dá a mesma conta — o que muda é só o tamanho do susto.

### 📊 Desempenho

As tabelas de log loss das Fases 4 e 5, a calibração do modelo e a distância para
o mercado competição por competição.

---

## 3. A parte mais importante: os avisos

Esta é a parte da fase que menos parece código e mais importa.

Todos os avisos do app moram num arquivo só: `src\futebol\app\avisos.py`. Não
estão espalhados pelas telas. São três motivos:

1. **para serem testáveis.** Existe um teste que exige que cada tela que mostra
   probabilidade importe o aviso que lhe corresponde. Se alguém apagar um aviso
   numa reescrita, o `pytest` fica vermelho — em vez de o aviso simplesmente
   desaparecer sem ninguém notar;
2. **para ficarem consistentes.** O mesmo resultado não pode aparecer como
   −12,9% numa tela e −13% em outra;
3. **para serem fáceis de auditar.** Quem quiser conferir se o app esconde algo
   lê **um** arquivo, não sete telas.

E cada aviso carrega um campo `origem`, que diz de qual relatório o número saiu.
Um aviso que cita número sem dizer onde ele foi medido é indistinguível de um
aviso inventado — e este projeto inteiro é sobre essa diferença.

Há até um teste que abre `docs\relatorios\fase6.md` e confere que os números
citados nos avisos **aparecem lá**. Se um relatório for regerado com outro valor,
o teste avisa antes de o app passar a mentir.

Os oito avisos:

| Aviso | Onde aparece |
|---|---|
| Jogo responsável (com o CVV — 188) | No pé de **todas** as telas |
| Este modelo perde do mercado | Prever jogo, Desempenho |
| Valor esperado positivo não quer dizer aposta boa | Comparar com odds (em vermelho) |
| A odd justa não é uma odd que você vá encontrar | Prever jogo |
| Olhe o intervalo, não o número | Backtest |
| A chance supõe jogos independentes | Múltiplas |
| E a chance mostrada é do modelo, que exagera | Múltiplas |
| O cash out cobra a mesma taxa sempre | Cash out |

---

## 4. Duas limitações que a tela admite

Um app honesto diz o que não faz. Estas duas aparecem escritas na própria tela,
não só aqui.

**1. Não há jogos futuros.** A fonte do projeto é um histórico de partidas já
jogadas. Então "a rodada" da tela de múltiplas é uma **data do passado** que você
escolhe. Inventar uma rodada futura seria inventar os dados dela. (Buscar jogos
que ainda vão acontecer é item da Fase 9.)

**2. No cash out, as chances são digitadas por você.** Se você usar as do modelo
deste projeto, elas carregam o exagero de ~4% por seleção que a Fase 7 mediu; se
usar `1 ÷ odd` da casa, elas carregam a comissão dela. A tela diz qual é qual, em
vez de fingir que existe um número neutro.

---

## 5. Por que o app não pode discordar dos relatórios

O app **não tem matemática própria**. Nenhuma.

Todo número que aparece na tela vem do mesmo código que gerou os relatórios. A
tela de Desempenho, por exemplo, não copia os valores do `fase5.md`: ela lê o
**mesmo arquivo de previsões** que o relatório leu e refaz as contas na hora.

O motivo é o tipo de erro que isso evita. Se a tela tivesse os números copiados à
mão, bastaria alguém regerar um relatório para que os dois passassem a discordar —
e essa divergência apareceria meses depois, quando ninguém mais lembrasse qual dos
dois estava velho.

A mesma ideia organiza o arquivo `dados.py`: as funções que **calculam** são puras
e não sabem que o Streamlit existe (são elas que os testes chamam), e as que
**guardam em memória** são casquinhas finas por cima. Lógica escondida dentro de
uma função com cache é lógica que só roda com um servidor no ar — ou seja, lógica
sem teste.

---

## 6. A decisão de deploy

A especificação manda **decidir nesta fase** (e executar na Fase 9) como o app
funcionaria publicado na internet, porque existe um problema: o app depende de
arquivos de dados que **não vão para o Git**. Um deploy ingênuo sobe e quebra.

As duas saídas possíveis eram:

- **(a)** versionar um arquivo de dados reduzido, só com o que o app usa;
- **(b)** o app baixar e processar os dados sozinho no primeiro boot.

**Escolhida a (a).** E o motivo é que os arquivos foram **medidos**, e são
pequenos:

| Arquivo | Tamanho |
|---|---|
| `jogos.parquet` (as 116.514 partidas) | **1,73 MB** |
| previsões do modelo oficial (36.446 jogos) | **2,87 MB** |
| **total** | **4,60 MB** |

Ou seja: nem precisa reduzir nada. Os dois arquivos caem abaixo do limite de 5 MB
por arquivo que o projeto se impôs (regra 4) e podem ser versionados numa pasta
própria, sem desligar o `.gitignore` de `data/`.

A opção (b) foi descartada por dois motivos, e o segundo é decisivo:

1. um app que baixa 170 arquivos e processa cem mil jogos no primeiro acesso faz
   o primeiro visitante esperar minutos;
2. o download **já falha** em rede com filtro de domínio — é um problema conhecido
   e registrado no projeto. Um deploy que depende dele é um deploy que quebra sem
   avisar, e a causa ficaria escondida no servidor.

---

## 7. Erros comuns

### `streamlit : O termo 'streamlit' não é reconhecido...`

O ambiente não está ligado. Rode `.venv\Scripts\Activate.ps1` — deve aparecer
`(.venv)` no começo da linha.

### `ModuleNotFoundError: No module named 'futebol'`

```powershell
pip install -e ".[dev]"
```

### A tela abre vermelha dizendo que falta a tabela de jogos

Rode `python scripts\preparar_dados.py`. A mensagem na tela diz exatamente os
comandos — um app que só estoura com "arquivo não encontrado" deixa quem abriu
sem saber o que fazer.

### "Nenhum modelo tem walk-forward gravado"

Falta `python scripts\validar.py`. Ele demora cerca de uma hora na primeira vez e
depois lê o que já está no disco.

### O app diz `AttributeError: module 'streamlit' has no attribute 'navigation'`

Sua versão do Streamlit é antiga. O app usa recursos que existem a partir da
1.64:

```powershell
pip install -e ".[dev]" --upgrade
```

### O navegador ofereceu "traduzir esta página" — ou traduziu sozinho

Pode aceitar? **Não.** O texto já está em português, e o tradutor automático
reescreve o que já está escrito: "Apostas envolvem risco real de perda" vira
"Apostas de envolvimento risco real de perda", e "Início" vira "Não se trata de
uma questão de". Os avisos obrigatórios saem adulterados.

O app declara o idioma sozinho para que isso não aconteça. Se mesmo assim o seu
navegador insistir, clique em "Mostrar original".

### A porta 8501 já está em uso

Outro app está aberto. Feche a outra janela do PowerShell, ou rode:

```powershell
streamlit run src\futebol\app\streamlit_app.py --server.port 8502
```

### Mudei um arquivo e a tela não mudou

Aperte `R` no navegador (ou clique em "Rerun", no canto superior direito). Se for
um número de dado, o cache dura uma hora — reinicie o app com `Ctrl + C` e rode
de novo.

---

## 8. Como saber que está tudo certo

- [ ] `streamlit run src\futebol\app\streamlit_app.py` abre o app no navegador
- [ ] as **sete** telas aparecem no menu da esquerda e todas abrem sem erro
- [ ] a tela de **Início** mostra "não há vantagem" e o ROI de −12,92%
- [ ] a tela de **Comparar com odds** mostra o aviso vermelho **antes** da conta
- [ ] no **Backtest**, nenhum número aparece sem o intervalo de confiança e o
      número de apostas embaixo
- [ ] em **Múltiplas**, toda chance de ganhar vem com os **dois** avisos
- [ ] o pé de **todas** as telas traz o aviso de jogo responsável com o CVV
- [ ] o `config.yaml` **não mudou** — a Fase 8 não mexe em modelo nenhum
      (regra 9)
- [ ] `pytest` mostra **615 passed** (ou 614 passed + 1 skipped, se a sua rede
      bloquear o site da fonte — o teste de rede vira *skip*, e isso é esperado)
- [ ] `ruff check .` mostra **All checks passed!**
- [ ] `git tag` mostra `fase-8`

⚠️ Se você clonou o projeto num computador novo e ainda não rodou
`preparar_dados.py`, **9 dos 25 testes do app aparecem como `skipped`** em vez de
falhar. Isso é esperado: eles precisam da tabela de jogos, que não vai para o
Git. Os outros 16 não dependem de dado nenhum e rodam sempre.

Se todos estiverem marcados, **a Fase 8 está concluída**.

---

## O que foi criado nesta fase

| Arquivo | Para que serve |
|---|---|
| `src/futebol/app/streamlit_app.py` | Só a navegação entre as sete telas |
| `src/futebol/app/avisos.py` | Os avisos obrigatórios, com a origem de cada número |
| `src/futebol/app/dados.py` | O que o app carrega, e o cache que o torna usável |
| `src/futebol/app/paginas/comum.py` | Os pedaços de tela usados por mais de uma página |
| `src/futebol/app/paginas/inicio.py` | 🏠 O projeto e o resultado |
| `src/futebol/app/paginas/prever.py` | 🔮 As probabilidades de um confronto |
| `src/futebol/app/paginas/comparar.py` | ⚖️ As odds que você viu × o modelo |
| `src/futebol/app/paginas/backtest.py` | 📉 A banca ao longo do tempo |
| `src/futebol/app/paginas/multiplas.py` | 🎟️ O montador de bilhetes |
| `src/futebol/app/paginas/cash_out.py` | 💸 A oferta da casa × o valor justo |
| `src/futebol/app/paginas/desempenho.py` | 📊 As tabelas das Fases 4 e 5 |
| `tests/test_app.py` | As telas rodam, e os avisos continuam lá |

### Versão Mac/Linux dos comandos

```bash
source .venv/bin/activate
streamlit run src/futebol/app/streamlit_app.py
pytest
```

---

## Próximo passo

A **Fase 9** é o teste final — e é a fase mais séria do projeto, porque ela só
pode ser feita **uma vez**.

Desde o começo, três temporadas de dados estão **trancadas**: nenhum modelo as
viu, nenhum backtest as usou, e há código que impede o acesso a elas. Elas
existem para responder uma única pergunta, uma única vez: *o que está escrito no
`CLAUDE.md` se sustenta em dados que o projeto nunca tocou?*

O que a Fase 9 faz:

1. confere que a configuração escolhida está registrada **antes** de abrir os
   dados (já está: Dixon-Coles com `xi = 0,003`, e 108 configurações testadas até
   aqui, contadas uma por uma);
2. destranca as temporadas de teste e roda a avaliação e o backtest **uma vez**;
3. escreve `docs/relatorios/final.md` aplicando o critério de parada do projeto;
4. executa a decisão de deploy tomada nesta fase;
5. põe o README em forma de portfólio, com prints do app.

⚠️ **Por que "uma vez" é tão importante:** se fosse permitido rodar o teste final,
não gostar do resultado, mexer num parâmetro e rodar de novo, as temporadas
trancadas deixariam de ser um teste e virariam mais um conjunto de validação — e
o número final não significaria nada. O valor delas está inteiro na promessa de
não repetir.

Pelo que as Fases 6 e 7 mediram, o resultado esperado é **negativo**. E isso é
uma previsão, não um medo: se o teste final vier positivo, a suspeita correta
será de que algo vazou, não de que o modelo é bom.

**Me avise quando quiser começar a Fase 9.**
