# Dicionário de dados

> Documento **gerado** por `scripts/gerar_dicionario.py` a partir dos arquivos reais da fonte. Não edite à mão — rode o script de novo.

Gerado em: 16/09/2026 12:44 UTC
Fonte: <https://www.football-data.co.uk>

## 1. Os três formatos encontrados

| Arquivo inspecionado | Formato | Colunas | Essenciais faltando |
|---|:---:|---:|---|
| `2425/E0.csv` | A | 120 | nenhuma |
| `2425/SP1.csv` | A | 119 | nenhuma |
| `1920/D1.csv` | A | 105 | nenhuma |
| `1819/E0.csv` | B | 62 | nenhuma |
| `1718/E0.csv` | B | 65 | nenhuma |
| `new/BRA.csv` | C | 25 | nenhuma |
| `new/RUS.csv` | C | 19 | nenhuma |
| `new/ARG.csv` | C | 25 | nenhuma |
| `new/JPN.csv` | C | 25 | nenhuma |

O número de colunas varia dentro do mesmo formato (ligas diferentes têm casas de aposta diferentes). O que importa não é a contagem, e sim se as colunas **essenciais** estão presentes.

## 2. Colunas padrão e de onde cada uma vem

Todo arquivo, seja qual for o formato, vira esta mesma tabela. Onde a odd não existe na fonte, a coluna fica **vazia** — nunca é preenchida com estimativa.

### Formato A — ligas principais, 2019/20 em diante

| Coluna padrão | Coluna de origem |
|---|---|
| `data` | `Date` |
| `liga` | _(vem do nome do arquivo)_ |
| `temporada` | _(vem do nome do arquivo)_ |
| `mandante` | `HomeTeam` |
| `visitante` | `AwayTeam` |
| `gols_mandante` | `FTHG` |
| `gols_visitante` | `FTAG` |
| `resultado` | `FTR` |
| `odd_pre_H` | `AvgH` |
| `odd_pre_D` | `AvgD` |
| `odd_pre_A` | `AvgA` |
| `odd_pre_over25` | `Avg>2.5` |
| `odd_pre_under25` | `Avg<2.5` |
| `odd_fech_H` | `AvgCH` |
| `odd_fech_D` | `AvgCD` |
| `odd_fech_A` | `AvgCA` |
| `odd_fech_over25` | `AvgC>2.5` |
| `odd_fech_under25` | `AvgC<2.5` |

### Formato B — ligas principais, até 2018/19

| Coluna padrão | Coluna de origem |
|---|---|
| `data` | `Date` |
| `liga` | _(vem do nome do arquivo)_ |
| `temporada` | _(vem do nome do arquivo)_ |
| `mandante` | `HomeTeam` |
| `visitante` | `AwayTeam` |
| `gols_mandante` | `FTHG` |
| `gols_visitante` | `FTAG` |
| `resultado` | `FTR` |
| `odd_pre_H` | `BbAvH` |
| `odd_pre_D` | `BbAvD` |
| `odd_pre_A` | `BbAvA` |
| `odd_pre_over25` | `BbAv>2.5` |
| `odd_pre_under25` | `BbAv<2.5` |
| `odd_fech_H` | `PSCH` |
| `odd_fech_D` | `PSCD` |
| `odd_fech_A` | `PSCA` |
| `odd_fech_over25` | **vazia** — não existe neste formato |
| `odd_fech_under25` | **vazia** — não existe neste formato |

### Formato C — Grupo 2 (arquivo único por país)

| Coluna padrão | Coluna de origem |
|---|---|
| `data` | `Date` |
| `liga` | `League` |
| `temporada` | `Season` |
| `mandante` | `Home` |
| `visitante` | `Away` |
| `gols_mandante` | `HG` |
| `gols_visitante` | `AG` |
| `resultado` | `Res` |
| `odd_pre_H` | **vazia** — não existe neste formato |
| `odd_pre_D` | **vazia** — não existe neste formato |
| `odd_pre_A` | **vazia** — não existe neste formato |
| `odd_pre_over25` | **vazia** — não existe neste formato |
| `odd_pre_under25` | **vazia** — não existe neste formato |
| `odd_fech_H` | `AvgCH` |
| `odd_fech_D` | `AvgCD` |
| `odd_fech_A` | `AvgCA` |
| `odd_fech_over25` | **vazia** — não existe neste formato |
| `odd_fech_under25` | **vazia** — não existe neste formato |

## 3. O que cada formato permite

| Capacidade | A | B | C |
|---|:---:|:---:|:---:|
| Resultado e placar | ✅ | ✅ | ✅ |
| Odd pré-jogo de 1X2 (é nela que se aposta) | ✅ | ✅ | ❌ |
| Odd pré-jogo de Over/Under 2,5 | ✅ | ✅ | ❌ |
| Odd de fechamento de 1X2 | ✅ | ⚠️ | ✅ |
| Odd de fechamento de Over/Under 2,5 | ✅ | ❌ | ❌ |
| Backtest de apostas | ✅ | ✅ | ❌ |
| Medição de CLV | ✅ | ⚠️ | ❌ |

⚠️ **Formato B:** No formato B (até 2018/19) a única odd de fechamento disponível é a da Pinnacle (PSC*), enquanto a odd pré-jogo é a média do mercado (BbAv*). A Pinnacle costuma pagar acima da média, então um CLV calculado assim mistura duas coisas: o ganho real de timing e a diferença entre casas. CLV do formato B não pode ser somado ao CLV do formato A sem ressalva.

## 4. Armadilhas confirmadas na inspeção

### 4.1 Os arquivos do Grupo 2 começam com BOM

Três bytes invisíveis (`EF BB BF`) antes da primeira coluna. Lidos sem cuidado, `Country` vira `\ufeffCountry` e o acesso pelo nome estoura. Tratado em `formatos.ler_cabecalho` com `utf-8-sig`.

### 4.2 `Season` tem dois formatos — dentro do mesmo arquivo

A especificação dizia que no Grupo 2 `Season` é o ano civil. É verdade para uns países e falso para outros — e há arquivos que misturam os dois, porque o país mudou de calendário no meio do período:

- **BRA**: 15 temporadas, 0 no formato `2012/2013` e 15 no formato `2012`. Exemplos: 2012, 2013, 2014, 2015…
- **RUS**: 15 temporadas, 15 no formato `2012/2013` e 0 no formato `2012`. Exemplos: 2012/2013, 2013/2014, 2014/2015, 2015/2016…
- **ARG**: 16 temporadas, 6 no formato `2012/2013` e 10 no formato `2012`. Exemplos: 2012/2013, 2013/2014, 2014, 2015…
- **JPN**: 15 temporadas, 1 no formato `2012/2013` e 14 no formato `2012`. Exemplos: 2012, 2013, 2014, 2015…

Consequência: a normalização de temporada precisa decidir linha a linha, não arquivo a arquivo.

### 4.3 Nem todo país tem todas as casas de aposta

`RUS` traz 19 colunas em vez de 25: não tem B365 nem Betfair. Continua utilizável porque as `AvgC*`, que são as que o projeto usa, estão lá. Por isso o inventário separa colunas **essenciais** de **opcionais**.

## 5. Inventário completo das colunas encontradas

<details><summary><code>2425/E0.csv</code> — formato A, 120 colunas</summary>

```
Div, Date, Time, HomeTeam, AwayTeam, FTHG, FTAG, FTR, HTHG, HTAG, HTR, Referee, HS, AS, HST, AST, HF, AF, HC, AC, HY, AY, HR, AR, B365H, B365D, B365A, BWH, BWD, BWA, BFH, BFD, BFA, PSH, PSD, PSA, WHH, WHD, WHA, 1XBH, 1XBD, 1XBA, MaxH, MaxD, MaxA, AvgH, AvgD, AvgA, BFEH, BFED, BFEA, B365>2.5, B365<2.5, P>2.5, P<2.5, Max>2.5, Max<2.5, Avg>2.5, Avg<2.5, BFE>2.5, BFE<2.5, AHh, B365AHH, B365AHA, PAHH, PAHA, MaxAHH, MaxAHA, AvgAHH, AvgAHA, BFEAHH, BFEAHA, B365CH, B365CD, B365CA, BWCH, BWCD, BWCA, BFCH, BFCD, BFCA, PSCH, PSCD, PSCA, WHCH, WHCD, WHCA, 1XBCH, 1XBCD, 1XBCA, MaxCH, MaxCD, MaxCA, AvgCH, AvgCD, AvgCA, BFECH, BFECD, BFECA, B365C>2.5, B365C<2.5, PC>2.5, PC<2.5, MaxC>2.5, MaxC<2.5, AvgC>2.5, AvgC<2.5, BFEC>2.5, BFEC<2.5, AHCh, B365CAHH, B365CAHA, PCAHH, PCAHA, MaxCAHH, MaxCAHA, AvgCAHH, AvgCAHA, BFECAHH, BFECAHA
```
</details>

<details><summary><code>2425/SP1.csv</code> — formato A, 119 colunas</summary>

```
Div, Date, Time, HomeTeam, AwayTeam, FTHG, FTAG, FTR, HTHG, HTAG, HTR, HS, AS, HST, AST, HF, AF, HC, AC, HY, AY, HR, AR, B365H, B365D, B365A, BWH, BWD, BWA, BFH, BFD, BFA, PSH, PSD, PSA, WHH, WHD, WHA, 1XBH, 1XBD, 1XBA, MaxH, MaxD, MaxA, AvgH, AvgD, AvgA, BFEH, BFED, BFEA, B365>2.5, B365<2.5, P>2.5, P<2.5, Max>2.5, Max<2.5, Avg>2.5, Avg<2.5, BFE>2.5, BFE<2.5, AHh, B365AHH, B365AHA, PAHH, PAHA, MaxAHH, MaxAHA, AvgAHH, AvgAHA, BFEAHH, BFEAHA, B365CH, B365CD, B365CA, BWCH, BWCD, BWCA, BFCH, BFCD, BFCA, PSCH, PSCD, PSCA, WHCH, WHCD, WHCA, 1XBCH, 1XBCD, 1XBCA, MaxCH, MaxCD, MaxCA, AvgCH, AvgCD, AvgCA, BFECH, BFECD, BFECA, B365C>2.5, B365C<2.5, PC>2.5, PC<2.5, MaxC>2.5, MaxC<2.5, AvgC>2.5, AvgC<2.5, BFEC>2.5, BFEC<2.5, AHCh, B365CAHH, B365CAHA, PCAHH, PCAHA, MaxCAHH, MaxCAHA, AvgCAHH, AvgCAHA, BFECAHH, BFECAHA
```
</details>

<details><summary><code>1920/D1.csv</code> — formato A, 105 colunas</summary>

```
Div, Date, Time, HomeTeam, AwayTeam, FTHG, FTAG, FTR, HTHG, HTAG, HTR, HS, AS, HST, AST, HF, AF, HC, AC, HY, AY, HR, AR, B365H, B365D, B365A, BWH, BWD, BWA, IWH, IWD, IWA, PSH, PSD, PSA, WHH, WHD, WHA, VCH, VCD, VCA, MaxH, MaxD, MaxA, AvgH, AvgD, AvgA, B365>2.5, B365<2.5, P>2.5, P<2.5, Max>2.5, Max<2.5, Avg>2.5, Avg<2.5, AHh, B365AHH, B365AHA, PAHH, PAHA, MaxAHH, MaxAHA, AvgAHH, AvgAHA, B365CH, B365CD, B365CA, BWCH, BWCD, BWCA, IWCH, IWCD, IWCA, PSCH, PSCD, PSCA, WHCH, WHCD, WHCA, VCCH, VCCD, VCCA, MaxCH, MaxCD, MaxCA, AvgCH, AvgCD, AvgCA, B365C>2.5, B365C<2.5, PC>2.5, PC<2.5, MaxC>2.5, MaxC<2.5, AvgC>2.5, AvgC<2.5, AHCh, B365CAHH, B365CAHA, PCAHH, PCAHA, MaxCAHH, MaxCAHA, AvgCAHH, AvgCAHA
```
</details>

<details><summary><code>1819/E0.csv</code> — formato B, 62 colunas</summary>

```
Div, Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR, HTHG, HTAG, HTR, Referee, HS, AS, HST, AST, HF, AF, HC, AC, HY, AY, HR, AR, B365H, B365D, B365A, BWH, BWD, BWA, IWH, IWD, IWA, PSH, PSD, PSA, WHH, WHD, WHA, VCH, VCD, VCA, Bb1X2, BbMxH, BbAvH, BbMxD, BbAvD, BbMxA, BbAvA, BbOU, BbMx>2.5, BbAv>2.5, BbMx<2.5, BbAv<2.5, BbAH, BbAHh, BbMxAHH, BbAvAHH, BbMxAHA, BbAvAHA, PSCH, PSCD, PSCA
```
</details>

<details><summary><code>1718/E0.csv</code> — formato B, 65 colunas</summary>

```
Div, Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR, HTHG, HTAG, HTR, Referee, HS, AS, HST, AST, HF, AF, HC, AC, HY, AY, HR, AR, B365H, B365D, B365A, BWH, BWD, BWA, IWH, IWD, IWA, LBH, LBD, LBA, PSH, PSD, PSA, WHH, WHD, WHA, VCH, VCD, VCA, Bb1X2, BbMxH, BbAvH, BbMxD, BbAvD, BbMxA, BbAvA, BbOU, BbMx>2.5, BbAv>2.5, BbMx<2.5, BbAv<2.5, BbAH, BbAHh, BbMxAHH, BbAvAHH, BbMxAHA, BbAvAHA, PSCH, PSCD, PSCA
```
</details>

<details><summary><code>new/BRA.csv</code> — formato C, 25 colunas</summary>

```
Country, League, Season, Date, Time, Home, Away, HG, AG, Res, PSCH, PSCD, PSCA, MaxCH, MaxCD, MaxCA, AvgCH, AvgCD, AvgCA, BFECH, BFECD, BFECA, B365CH, B365CD, B365CA
```
</details>

<details><summary><code>new/RUS.csv</code> — formato C, 19 colunas</summary>

```
Country, League, Season, Date, Time, Home, Away, HG, AG, Res, PSCH, PSCD, PSCA, MaxCH, MaxCD, MaxCA, AvgCH, AvgCD, AvgCA
```
</details>

<details><summary><code>new/ARG.csv</code> — formato C, 25 colunas</summary>

```
Country, League, Season, Date, Time, Home, Away, HG, AG, Res, PSCH, PSCD, PSCA, MaxCH, MaxCD, MaxCA, AvgCH, AvgCD, AvgCA, BFECH, BFECD, BFECA, B365CH, B365CD, B365CA
```
</details>

<details><summary><code>new/JPN.csv</code> — formato C, 25 colunas</summary>

```
Country, League, Season, Date, Time, Home, Away, HG, AG, Res, PSCH, PSCD, PSCA, MaxCH, MaxCD, MaxCA, AvgCH, AvgCD, AvgCA, BFECH, BFECD, BFECA, B365CH, B365CD, B365CA
```
</details>

Amostras inspecionadas: 9 arquivos (3 do formato A, 2 do B, 4 do C).
