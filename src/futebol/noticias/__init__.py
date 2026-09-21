"""Fase 10 — desfalques e notícias: informação que o placar não tem.

⚠️ **LEIA ISTO ANTES DE OLHAR QUALQUER NÚMERO QUE ESTA FASE PRODUZIR.**

Esta fase é uma **demonstração de engenharia de dados e de uso correto de LLM**:
coleta filtrada, extração estruturada e ajuste parametrizado. Ela **não é, e não
pode ser, uma hipótese validada estatisticamente** no prazo do projeto — e isso
não é modéstia, é aritmética medida com os dados do próprio projeto.

**O que a amostra desta fase consegue enxergar.** O desvio-padrão da diferença
de log loss entre dois modelos, jogo a jogo, é 0,148 nestes dados. Daí sai o
menor efeito detectável (80% de poder, 5%):

=============  =====================  =================
jogos          log loss detectável    CLV detectável
=============  =====================  =================
50             0,0585                 2,77 pp
150            0,0338                 1,60 pp
600            0,0169                 0,80 pp
=============  =====================  =================

Seis semanas de jogos são ~150 previsões. **A distância inteira do modelo para o
mercado é 0,0212** (teste final, Fase 9). Ou seja: pela log loss, o ajuste teria
de superar o mercado em 60% só para o efeito aparecer como detectável. **A log
loss não consegue responder esta pergunta neste tamanho de amostra**, e é por
isso que a seção 8.3 manda usar CLV.

**O CLV serve, e com limite.** Com 150 apostas ele enxerga 1,60 pp. O CLV medido
no teste final é −9,02%; para ele chegar a zero, o ajuste precisaria mover 9 pp,
o que seria impossível de não ver. Então esta fase responde **"isso ajudou
muito?"** — e não responde "isso ajudou um pouco".

⚠️ Enquanto o intervalo de confiança cruzar zero, a resposta honesta é **"ainda
não dá para saber"**. Não "não funciona", e muito menos "funciona".

**O que esta fase não pode fazer, por construção.** Não há backtest: é
impossível saber, hoje, o que se sabia sobre lesões *antes* de cada jogo de
2021. A avaliação é **para frente** (paper trading) — o projeto registra as duas
previsões, a ajustada e a crua, antes do jogo, e a comparação só existe depois
que os jogos acontecerem.

**Três coisas que o projeto não tem e que esta fase precisa de fora:**

1. **dados de jogador.** A fonte do projeto (football-data.co.uk) traz placar e
   odds, e **nenhuma** informação de elenco. Minutos, gols e titularidade — que
   é o que dá peso a um desfalque — vêm da API de futebol;
2. **jogos futuros.** A fonte é histórica. A lista da próxima rodada vem do
   arquivo de *fixtures* ou da API;
3. **chaves de API**, que moram no `.env` e nunca no código nem no Git.

Sem as chaves, tudo aqui continua rodando com as fontes falsas
(:mod:`futebol.noticias.fontes`) — é assim que os testes rodam, sem tocar a
internet, e é assim que dá para ver a fase funcionando antes de ter conta em
lugar nenhum.
"""
