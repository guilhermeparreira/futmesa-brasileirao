# Base histórica — Campeonato Brasileiro Individual de Futebol de Mesa (12 Toques)

Extrai do PDF *Histórico do Campeonato Brasileiro Individual 12 Toques* todas as
classificações finais (1989–2025, 35 edições; não houve campeonato em 2020 e 2021)
e gera uma base tabular em **Parquet** e **Excel**.

## Saídas (`saida/`)

| Arquivo | Conteúdo |
|---|---|
| `classificacao.parquet` | 1 linha por botonista × campeonato × categoria × divisão |
| `botonistas.parquet` | 1 linha por pessoa (`id_botonista`) |
| `campeonatos.parquet` | 1 linha por edição (sede, local, datas, participantes citados) |
| `campeonato_brasileiro_12_toques.xlsx` | abas `classificacao`, `campeonatos`, `qualidade` e `dicionario` |

Chave de `classificacao`: `ano + categoria + divisao + posicao` (posição vazia só para
participantes citados sem colocação).
A descrição de cada coluna está na aba `dicionario` do Excel.

## Regras de tratamento

- **Categoria × divisão.** `ADULTO – Ouro` → categoria `Adulto`, divisão `Ouro`.
  - 1989–1992: só havia a categoria aberta, separada em séries Ouro/Prata/Bronze
    → categoria `Adulto`; a Sub-18 aparece em 1990.
  - A partir de 1993: Adulto, Master, Sub-18; Sub-15 a partir de 1996; `Infantil`
    (1994) e `Sub-20` (2008) mantidos como impressos.
  - Copas (`Copa Santos`, `Copa Blumenau`…) → divisão `Copa`; o título exato fica em
    `secao_original`.
  - Categoria sem divisões (ex.: `SUB-18`) → divisão `Única`.
  - `divisao_nivel`: 1 = principal. Ouro > Prata > Bronze > Extra > Copa (contando só
    as que existiram no ano); `Nª Divisão` = N.
- **Botonista × clube × UF.**
  - Anos iniciais: `NOME (Clube – Cidade)   UF` → `botonista`, `clube`,
    `cidade_botonista`, `uf_botonista`.
  - 2008: `NOME – Clube   UF`.
  - Anos recentes: `NOME-UF` / `NOME - UF`, seguidos das estatísticas.
  - Apelidos entre aspas (`"Rubinho"`) vão para `apelido`.
  - Nomes de clube em caixa alta são padronizados (`CÍRCULO MILITAR` → `Círculo Militar`);
    siglas curtas ficam como estão.
- **Estatísticas** (`jogos`, `vitorias`, `empates`, `derrotas`, `gols_pro`, `gols_contra`,
  `saldo_gols`, `pontos`) são lidas pelo cabeçalho de cada tabela (`CF TÉCNICOS J V E D…`),
  porque a ordem e o conjunto de colunas mudam ao longo dos anos (2002 não tem J; 2003–2005
  não têm E/D). O que o PDF não traz fica **missing**: nada é calculado ou imputado.
- **`botonista_chave`**: nome sem acento e pontuação, em maiúsculas — ponto de partida
  para unificar o mesmo botonista entre anos (ainda não há ID de pessoa).

## Como rodar

Requisitos: Python ≥ 3.10, `poppler-utils` (fornece `pdftotext`; já vem no Ubuntu
desktop) e as bibliotecas de `requirements.txt`.

```bash
pip install -r requirements.txt
python -m futmesa --pdf HISTORICO.pdf --saida saida          # reconstrói a base inteira
python -m pytest -q tests                                     # testes do parser
```

## Adicionar o campeonato do próximo ano

1. Acrescente uma linha em `dados/campeonatos.csv` (ano, edição, cidade, UF, local,
   datas, participantes) — opcional, mas é de lá que vêm local e datas.
2. Rode **um** dos comandos:

```bash
# PDF do histórico atualizado (com o novo ano no índice): extrai só 2026 e anexa
python -m futmesa --pdf HISTORICO_ATUALIZADO.pdf --saida saida --anos 2026

# PDF avulso só com o novo campeonato (sem índice)
python -m futmesa --pdf BRASILEIRO_2026.pdf --saida saida --ano-unico 2026 --cidade "Recife" --uf PE

# ou simplesmente reconstruir tudo a partir do PDF atualizado
python -m futmesa --pdf HISTORICO_ATUALIZADO.pdf --saida saida
```

Com `--anos`/`--ano-unico`, os anos informados **substituem** os mesmos anos da base e os
demais são mantidos — rodar de novo não duplica nada.

O novo PDF precisa manter o padrão de tabela (`CATEGORIA - Divisão`, cabeçalho
`CF TÉCNICOS …`, linhas `1º NOME-UF …`). Depois de rodar, confira a aba `qualidade`.

## Padronização de nomes (de-para)

- `dados/depara_botonistas.csv`: `de_botonista_chave` (+ `de_uf`; vazio = qualquer UF) → `para_botonista`,
  com `confianca` (confirmado/alta/média/baixa), `motivo` e `aplicar`.
- `dados/depara_clubes.csv`: `de_clube` → `para_clube`.
- Só as linhas com `aplicar = sim` entram na base, nas colunas `botonista_padronizado` e
  `clube_padronizado` (os nomes impressos continuam em `botonista` e `clube`). Para aprovar
  uma sugestão, troque `revisar` por `sim` e rode o pipeline de novo.
- A verificação `botonista_repetido_no_ano` acusa quando uma regra junta duas pessoas que
  jogaram a mesma categoria no mesmo ano (foi assim que apareceu que `MICHILIN` e `MAURO`
  são pessoas diferentes).
- As duas tabelas também saem como abas do Excel.

## ID da pessoa (`id_botonista`)

Cada linha recebe um `id_botonista` (ex.: `robertinho-pr`): nome padronizado + UF da estreia.
A mesma pessoa mantém o ID quando muda de estado; homônimos recebem IDs diferentes
(`denis-pr`, `denis-sp`, `juninho-sp-2`). Regras, sempre dentro de um mesmo nome padronizado:

1. No mesmo estado, as linhas são separadas quando não cabem em uma só carreira (Adulto e
   Master no mesmo ano; categorias de base com mais de 10 anos de distância; Master menos de
   25 anos depois de uma categoria de base).
2. Carreiras em estados diferentes são unidas quando nunca coincidem no mesmo ano, estão a
   poucos anos uma da outra (4 para nome de uma palavra, 8 para nome composto), não voltam do
   Master para o Adulto e o nome é distintivo (não é um primeiro nome comum como ANDRÉ ou
   CARLOS).
3. Linhas sem UF são adotadas pela única carreira compatível a até 3 anos.

É uma heurística: para corrigir um caso, acrescente uma linha em `dados/pessoas_manual.csv`
(`botonista_padronizado`, `uf_botonista`, `id_botonista`). `saida/botonistas.parquet` (aba
`botonistas` do Excel) tem uma linha por pessoa, com estados, período e nomes impressos.

## Participantes sem classificação

`dados/participantes_sem_classificacao.csv` traz quem o PDF só cita em nota (Master de 1996).
Entram na base com `posicao` vazia e a explicação em `observacao`.

## Correções manuais e qualidade

- `dados/correcoes_texto.csv`: erros de digitação/OCR do próprio PDF (ex.: `o` no lugar
  de `0`, `3S` no lugar de `35`, UF ilegível `se`). Cada correção é por ano + trecho de
  texto e fica registrada na coluna `observacao` da linha afetada. Se o trecho deixar de
  existir no PDF, o pipeline para com erro em vez de ignorar.
- Aba/verificação `qualidade` (não altera dados, só reporta):
  - posições descontínuas e chaves duplicadas (hoje: nenhuma);
  - `uf_ausente`: linhas sem UF no PDF (1997, tabelas Sub-18/15 de 2002 que trazem sigla
    de clube no lugar da UF, etc.);
  - `saldo_diferente_de_gf_menos_gc` / `pontos_diferente_de_3v_mais_e`: inconsistências
    do próprio PDF (ex.: sinal do saldo ausente em 2019; Sub-18 2016–2017 com pontos que
    não batem com 3V+E). Ficam como impressas.

## Limitações conhecidas

- Alguns anos publicam só os primeiros colocados (1991, 1993, 1994, 1999…), então a
  quantidade de linhas não é o número de participantes.
- `clube` está como impresso: `S. E. Palmeiras`, `Palmeiras` e `SEP` ainda são valores
  diferentes; o mesmo vale para nomes de botonistas que variam entre anos.

## Estrutura do código

```
futmesa/
  pdf_text.py     PDF → texto por página (pdftotext -layout) e leitura do índice
  sections.py     títulos de seção (categoria/divisão) e cabeçalhos de tabela
  rows.py         uma linha de classificação → nome, apelido, clube, cidade, UF, estatísticas
  extraction.py   percorre as páginas de cada campeonato; junta nomes quebrados em 2 linhas
  corrections.py  correções manuais do texto do PDF
  transform.py    tipos, nível da divisão, dados do campeonato, ordenação
  quality.py      verificações de qualidade
  export.py       Parquet/Excel e merge de anos novos
  pipeline.py     orquestração;  __main__.py  linha de comando
dados/
  campeonatos.csv        local, datas e participantes por edição (curadoria do texto do PDF)
  correcoes_texto.csv    correções manuais
```
