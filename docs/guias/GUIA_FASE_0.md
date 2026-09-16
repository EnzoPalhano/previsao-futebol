# Guia da Fase 0 — Preparando o computador para o projeto

> **Para quem é este guia:** para alguém que nunca programou. Cada comando está explicado,
> junto com o que deve aparecer na tela quando dá certo e o que fazer quando dá errado.
> Se você já sabe usar terminal e Git, pule direto para a seção 5.

**O que a Fase 0 faz:** ela não analisa nenhum jogo ainda. Ela só deixa o computador pronto
para receber o código das próximas fases. É como arrumar a bancada antes de cozinhar.

**Tempo estimado:** 20 a 40 minutos na primeira vez.

---

## Índice

1. [Instalar o Python](#1-instalar-o-python)
2. [Instalar o Git](#2-instalar-o-git)
3. [Abrir o terminal na pasta certa](#3-abrir-o-terminal-na-pasta-certa)
4. [Criar o ambiente virtual](#4-criar-o-ambiente-virtual)
5. [Instalar o projeto](#5-instalar-o-projeto)
6. [Rodar os testes](#6-rodar-os-testes)
7. [Colocar no GitHub](#7-colocar-no-github)
8. [Erros comuns](#8-erros-comuns)
9. [Como saber que está tudo certo](#9-como-saber-que-está-tudo-certo)

---

## 1. Instalar o Python

O Python é a linguagem em que o projeto é escrito.

**Como saber se você já tem.** Abra o **PowerShell** (aperte a tecla Windows, digite
`powershell`, aperte Enter) e digite:

```powershell
python --version
```

**Se deu certo**, aparece algo assim:

```
Python 3.14.0
```

Qualquer número **3.11 ou maior** serve. Se apareceu isso, pule para a etapa 2.

**Se não deu certo** (apareceu "não é reconhecido como um cmdlet" ou abriu a Microsoft Store):

1. Vá em [python.org/downloads](https://www.python.org/downloads/).
2. Clique no botão amarelo "Download Python".
3. Abra o arquivo baixado.
4. ⚠️ **MUITO IMPORTANTE:** na primeira tela, marque a caixinha
   **"Add python.exe to PATH"**, lá embaixo. Se você esquecer disso, o computador não vai
   achar o Python e nada mais vai funcionar.
5. Clique em "Install Now" e espere.
6. **Feche e abra o PowerShell de novo** (ele só enxerga programas novos depois de reiniciar).
7. Rode `python --version` outra vez.

---

## 2. Instalar o Git

O Git guarda o histórico do projeto: cada mudança fica registrada e dá para voltar atrás.

**Como saber se você já tem:**

```powershell
git --version
```

**Se deu certo**, aparece algo assim:

```
git version 2.53.0.windows.2
```

**Se não deu certo:** baixe em [git-scm.com/download/win](https://git-scm.com/download/win),
abra o instalador e clique em "Next" em todas as telas (as opções padrão estão certas).
Depois **feche e abra o PowerShell**.

### Dizer ao Git quem é você

Só precisa fazer isso **uma vez na vida**. Troque pelos seus dados:

```powershell
git config --global user.name "Enzo Palhano"
```

```powershell
git config --global user.email "enzo.palhano@gmail.com"
```

Esses dados vão aparecer no histórico de cada mudança que você salvar.

---

## 3. Abrir o terminal na pasta certa

O terminal sempre está "dentro" de alguma pasta. Você precisa estar dentro da pasta do projeto.

```powershell
cd "C:\Users\Usuario\Documents\Jogos_Probabilidade"
```

O `cd` quer dizer *change directory* — mudar de pasta.

**Para conferir que você está no lugar certo:**

```powershell
ls
```

**Deve aparecer** uma lista com `config.yaml`, `pyproject.toml`, `src`, `tests`, entre outros.
Se aparecer vazio ou der erro, você está na pasta errada.

> 💡 **Atalho:** abra a pasta no Explorer, clique com o botão direito em um espaço vazio e
> escolha "Abrir no Terminal". Ele já abre no lugar certo.

---

## 4. Criar o ambiente virtual

### O que é isso, em português

Imagine que cada projeto Python precisa de um conjunto de ferramentas com versões específicas.
Se você instalar tudo "no computador inteiro", um projeto começa a atrapalhar o outro.

O **ambiente virtual** é uma caixa separada, dentro da pasta do projeto, onde ficam só as
ferramentas deste projeto. É uma pasta chamada `.venv`.

### Criar a caixa

```powershell
py -3 -m venv .venv
```

Isso demora uns 10 segundos e **não mostra nada na tela** quando dá certo. Silêncio é sucesso.

### Ativar a caixa

```powershell
.venv\Scripts\Activate.ps1
```

**Se deu certo**, o começo da sua linha de comando muda e passa a mostrar `(.venv)`:

```
(.venv) PS C:\Users\Usuario\Documents\Jogos_Probabilidade>
```

Esse `(.venv)` é a confirmação de que você está dentro da caixa.

> ⚠️ **Você precisa ativar o ambiente toda vez que abrir um terminal novo.** Não é uma
> instalação permanente — é mais parecido com acender a luz da sala ao entrar.

**No Mac ou Linux**, o comando de ativação é outro:

```bash
source .venv/bin/activate
```

---

## 5. Instalar o projeto

Com o `(.venv)` aparecendo na linha:

```powershell
pip install -e ".[dev]"
```

### O que esse comando faz

- `pip` é o instalador de bibliotecas do Python.
- `install` instala.
- `-e` quer dizer **editável**: em vez de copiar o código para outro lugar, o Python passa a
  ler direto da pasta `src/`. Assim, quando o código mudar, não precisa reinstalar nada.
- `".[dev]"` quer dizer "este projeto aqui, mais as ferramentas de desenvolvimento"
  (o `pytest`, que roda os testes, e o `ruff`, que confere o estilo do código).

> 💡 **Por que isso importa:** o código deste projeto fica dentro da pasta `src/`. Sem esse
> comando, o Python simplesmente não encontra o código e todos os testes falham com
> `ModuleNotFoundError: No module named 'futebol'`. Esse é o erro número 1 de quem pula
> esta etapa.

**Vai demorar de 2 a 5 minutos** e passar muito texto na tela. É normal.

**Se deu certo**, a última linha começa com:

```
Successfully installed ... previsao-futebol-0.1.0 ...
```

---

## 6. Rodar os testes

Este é o momento da verdade.

```powershell
pytest
```

**Se deu certo**, você vê algo assim:

```
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.1.1
collected 12 items

tests/test_ambiente.py::test_pytest_funciona PASSED                      [  8%]
tests/test_ambiente.py::test_versao_minima_do_python PASSED              [ 16%]
tests/test_ambiente.py::test_pacote_futebol_importavel PASSED            [ 25%]
tests/test_ambiente.py::test_subpacotes_existem PASSED                   [ 33%]
tests/test_ambiente.py::test_config_carrega PASSED                       [ 41%]
tests/test_ambiente.py::test_camada_ativa_existe PASSED                  [ 50%]
tests/test_ambiente.py::test_camada_inexistente_da_erro_claro PASSED     [ 58%]
tests/test_ambiente.py::test_secao_obrigatoria_faltando_da_erro PASSED   [ 66%]
tests/test_ambiente.py::test_grupo2_nunca_entra_em_backtest PASSED       [ 75%]
tests/test_ambiente.py::test_backtest_nao_usa_odd_maxima PASSED          [ 83%]
tests/test_ambiente.py::test_selecao_de_modelo_e_por_log_loss PASSED     [ 91%]
tests/test_ambiente.py::test_uma_selecao_por_jogo_nas_multiplas PASSED   [100%]

============================= 12 passed in 0.08s ==============================
```

**`12 passed` em verde = Fase 0 funcionando.**

### O que esses testes estão conferindo

Os quatro primeiros são checagens de ambiente. Mas os quatro últimos são diferentes e vale
entender, porque eles são uma ideia central do projeto:

| Teste | O que protege |
|---|---|
| `test_grupo2_nunca_entra_em_backtest` | Impede que Brasil, Argentina, EUA etc. entrem no backtest. Essas ligas só têm odd de fechamento — apostar nelas no simulador seria apostar sabendo o preço final, o que é trapaça sem querer. |
| `test_backtest_nao_usa_odd_maxima` | Impede usar a *melhor* odd do mercado. Isso infla o lucro artificialmente e é o erro que invalida a maioria dos backtests amadores. |
| `test_selecao_de_modelo_e_por_log_loss` | Impede escolher o modelo pelo lucro do backtest, que é quase todo sorte. |
| `test_uma_selecao_por_jogo_nas_multiplas` | Impede juntar dois mercados do mesmo jogo numa múltipla, porque eles são correlacionados e a conta ficaria errada. |

A ideia é simples: **as regras que evitam auto-engano viraram código**. Se alguém (inclusive
eu, em uma sessão futura) mudar o `config.yaml` violando uma delas, o `pytest` falha na hora.
Regra que está só escrita na documentação é esquecida; regra que quebra o teste, não.

### Conferir o estilo do código

```powershell
ruff check .
```

**Deve aparecer:**

```
All checks passed!
```

---

## 7. Colocar no GitHub

### 7.1 Criar o repositório no site

1. Entre em [github.com](https://github.com) e faça login.
2. Clique no **+** no canto superior direito → **New repository**.
3. Em *Repository name*, escreva: `previsao-futebol`
4. Escolha **Public** (é um projeto de portfólio — a graça é poder mostrar).
5. ⚠️ **NÃO marque** nenhuma das caixinhas ("Add a README", "Add .gitignore", "Choose a
   license"). O projeto já tem esses arquivos, e marcar causa conflito.
6. Clique em **Create repository**.

### 7.2 Conectar e enviar

O GitHub vai mostrar uma tela com comandos. Use estes, trocando `EnzoPalhano` pelo seu usuário:

```powershell
git remote add origin https://github.com/EnzoPalhano/previsao-futebol.git
```

```powershell
git branch -M main
```

```powershell
git push -u origin main
```

```powershell
git push origin --tags
```

O último comando envia a etiqueta `fase-0`, que marca este ponto do histórico.

**Na primeira vez**, o Git vai abrir uma janela pedindo login no GitHub. Faça o login pelo
navegador que ele abrir.

**Se deu certo**, atualize a página do GitHub: os arquivos aparecem lá.

### 7.3 Conferir a integração contínua

Na página do seu repositório, clique na aba **Actions**. Deve aparecer uma execução chamada
"CI" com um ✅ verde ao lado.

Isso quer dizer que o GitHub baixou o projeto numa máquina limpa, instalou tudo do zero e
rodou os testes — e passou. É a prova de que o projeto funciona não só no seu computador.

---

## 8. Erros comuns

### `python não é reconhecido como um cmdlet`
O Python não foi instalado, ou foi instalado sem marcar **"Add python.exe to PATH"**.
Reinstale marcando a caixinha, e depois feche e abra o PowerShell.

### `O arquivo Activate.ps1 não pode ser carregado porque a execução de scripts foi desabilitada`
O Windows bloqueia scripts por padrão. Rode uma vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Digite `S` e Enter quando ele perguntar. Depois tente ativar o ambiente de novo.
Isso libera scripts só para o seu usuário, não para o computador inteiro.

### `ModuleNotFoundError: No module named 'futebol'`
O erro mais comum de todos. Quer dizer uma destas duas coisas:

1. Você esqueceu de **ativar o ambiente** (não aparece `(.venv)` na linha). Rode
   `.venv\Scripts\Activate.ps1`.
2. Você esqueceu de rodar `pip install -e ".[dev]"`.

### `pytest não é reconhecido`
O ambiente não está ativado, ou a instalação da etapa 5 não terminou. Confira se aparece
`(.venv)` no início da linha.

### O terminal abriu na pasta errada
Rode `cd "C:\Users\Usuario\Documents\Jogos_Probabilidade"` e depois `ls` para conferir.

### `fatal: not a git repository`
Você está fora da pasta do projeto. Use o `cd` acima.

### `error: remote origin already exists`
Você já rodou o `git remote add` antes. Para corrigir:

```powershell
git remote set-url origin https://github.com/EnzoPalhano/previsao-futebol.git
```

---

## 9. Como saber que está tudo certo

Marque cada item:

- [ ] `python --version` mostra 3.11 ou maior
- [ ] `git --version` mostra alguma versão
- [ ] Estou na pasta `Jogos_Probabilidade` (o `ls` mostra `config.yaml` e `pyproject.toml`)
- [ ] Aparece `(.venv)` no começo da linha do terminal
- [ ] `pip install -e ".[dev]"` terminou com "Successfully installed"
- [ ] `pytest` mostra **12 passed**
- [ ] `ruff check .` mostra **All checks passed!**
- [ ] `git log --oneline` mostra 5 mudanças salvas
- [ ] `git tag` mostra `fase-0`
- [ ] Os arquivos aparecem no GitHub
- [ ] A aba **Actions** do GitHub mostra ✅ verde

Se todos estiverem marcados, **a Fase 0 está concluída**.

---

## O que foi criado nesta fase

| Arquivo | Para que serve |
|---|---|
| `pyproject.toml` | Diz quais bibliotecas o projeto usa e onde o código mora |
| `config.yaml` | Tudo que dá para ajustar sem mexer em código: ligas, temporadas, parâmetros |
| `README.md` | A página de apresentação do projeto no GitHub |
| `.gitignore` | A lista do que **não** deve ir para o GitHub (dados, senhas, o `.venv`) |
| `.env.exemplo` | Modelo de onde as chaves de API vão ficar (só a partir da Fase 10) |
| `.github/workflows/ci.yml` | Faz o GitHub rodar os testes sozinho a cada mudança |
| `src/futebol/config.py` | O primeiro código de verdade: lê o `config.yaml` |
| `tests/test_ambiente.py` | Os 12 testes que você acabou de rodar |

---

## Próximo passo

A **Fase 1** baixa os dados de verdade: resultados e odds das ligas, limpa tudo e junta
numa tabela só.

O plano é começar com **uma liga só** (a Premier League) para validar que o processo inteiro
funciona, e só depois ligar as 38 competições. O motivo é prático: são cerca de 1.500 clubes
em vários idiomas para padronizar, e é melhor descobrir os problemas com 20 times do que
com 1.500.

**Me avise quando quiser começar a Fase 1.**
