# Base histórica — Campeonato Brasileiro Individual de Futebol de Mesa (12 Toques)

Gera uma base tabular em **Parquet** e **Excel** com todas as classificações finais
(1989 em diante; não houve campeonato em 2020 e 2021), a partir de duas fontes:

| Fonte | Anos | Uso |
|---|---|---|
| **Tabelas oficiais** do campeonato: um PDF por categoria (`dados/<ano>/*.pdf`), baixado em [documentos oficiais da CBFM](https://www.cbfm.com.br/documentos-oficiais/) → *12 Toques* → *Tabela*, e convertido para markdown com [markitdown](https://github.com/microsoft/markitdown) | 2026 em diante | **padrão** para acrescentar um ano novo: sai direto das tabelas, sem esperar o histórico |
| PDF *Histórico do Campeonato Brasileiro Individual 12 Toques* | 1989–2025 | reconstruir a base inteira |

## Saídas (`saida/`)

| Arquivo | Conteúdo |
|---|---|
| `classificacao.parquet` | 1 linha por botonista × campeonato × categoria × divisão |
| `botonistas.parquet` | 1 linha por pessoa (`id_botonista`) |
| `campeonatos.parquet` | 1 linha por edição (sede, local, datas, participantes citados) |
| `campeonato_brasileiro_12_toques.xlsx` | abas `classificacao`, `campeonatos`, `qualidade` e `dicionario` |

Chave de `classificacao`: `ano + categoria + divisao + posicao` (posição vazia só para
participantes citados sem colocação).

Duas classificações por linha:

- `posicao`: dentro da divisão (coluna **DIV.** das tabelas oficiais; no histórico, a
  posição impressa em cada tabela);
- `posicao_geral`: acumulada na categoria — cada divisão começa logo após a última posição
  das divisões de cima (ordem de `divisao_nivel`); não volta a 1 a cada divisão. Nas tabelas
  oficiais é a coluna **POS.**; nos anos do histórico, que não a trazem, é **calculada** com a
  mesma regra. Em 1991 o histórico só publicou os primeiros de cada série, então a posição
  geral da Prata e do Bronze desse ano fica subestimada.

`arquivo_fonte` diz de qual arquivo cada linha veio.
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
desktop) e as bibliotecas de `requirements.txt` (inclui `markitdown[pdf]`).

```bash
make instalar                       # pip install -r requirements.txt
make atualizar PASTA=dados/2027     # acrescenta/substitui um ano (tabelas oficiais)
make reconstruir                    # histórico (1989–2025) + todas as pastas dados/<ano>/
make testes                         # testes dos parsers
```

Sem `make`: `python -m futmesa --tabelas dados/2027 --saida saida` e
`python -m futmesa --pdf HISTORICO.pdf --saida saida`.

## Adicionar o campeonato do próximo ano (padrão: tabelas oficiais)

Roteiro (exemplo para 2027):

1. Crie `dados/2027/` e coloque lá os PDFs oficiais, um por categoria — os arquivos
   `..._br_individual_OFICIAL.pdf` de https://www.cbfm.com.br/documentos-oficiais/
   (*12 Toques* → *Tabela*). O nome da pasta é o ano.
2. Rode:

   ```bash
   make atualizar PASTA=dados/2027
   ```

   Roda os testes, converte os PDFs, lê a classificação final e anexa 2027 à base
   (`saida/`). Equivale a `python -m futmesa --tabelas dados/2027 --saida saida`.
3. Confira o resumo impresso. O comando **termina com erro** se aparecer alguma
   verificação que precisa ficar zerada (`chave_duplicada`, `posicoes_descontinuas`,
   `posicao_geral_descontinua`, `botonista_repetido_no_ano`, `ano_sem_classificacao`);
   as demais (`uf_ausente`, `saldo_diferente…`) são inconsistências do PDF, só reportadas.
4. Se precisar, ajuste os CSVs de `dados/` e rode o mesmo comando de novo (substitui o
   ano, não duplica):
   - local da disputa → `dados/campeonatos.csv` (sede e datas já vêm do PDF);
   - erro de digitação ou estrangeiro (`NOME-XX` → `NOME-XX*`) → `dados/correcoes_texto.csv`;
   - mesmo botonista com outra grafia → `dados/depara_botonistas.csv` (`aplicar = sim`).
5. Faça o commit de `saida/`, dos CSVs e dos `.md` de `dados/2027/` (os PDFs ficam fora
   do git pelo `.gitignore`).

Outros alvos: `make reconstruir` refaz a base inteira (PDF do histórico + todas as pastas
`dados/<ano>/`, em ordem; caminho do histórico em `HISTORICO=...`), `make testes`,
`make instalar`.

O que acontece na leitura:

- cada PDF é convertido com markitdown para `dados/<ano>/<mesmo nome>.md` (fica salvo
  para auditoria);
- do markdown é lida só a tabela **CLASSIFICAÇÃO FINAL** (últimas páginas):
  - `POS.` → `posicao_geral`. `Campeão`/`Vice` são o 1º/2º da divisão; na posição geral
    ficam logo depois das divisões de cima (Campeão da 2ª divisão com 16 na 1ª = 17º);
  - `DIV.` → `posicao`. Toda vez que DIV. volta a 1º começa a divisão seguinte
    (1ª, 2ª, …); o nome é conferido com os títulos de mata-mata do próprio PDF
    (`ADULTO - 3ª DIVISÃO`) e o pipeline para com erro se a contagem não bater;
  - `ATLETA` (`NOME-UF`) e as estatísticas, pelo cabeçalho `PG J V E D GP GC SG IA%`
    (IA% não é guardado: é PG / 3J);
- edição, sede e datas vêm do cabeçalho das páginas (`36º CAMPEONATO…`, `CAMPINAS/SP`,
  `18 A 21 ABRIL`); `dados/campeonatos.csv` continua valendo por cima (ex.: para o local);
- o ano substitui o mesmo ano da base e os demais são mantidos — rodar de novo não duplica.

Erros de digitação e atletas estrangeiros vão em `dados/correcoes_texto.csv`, como no
histórico. Estrangeiro: a sigla do país vai em `uf_botonista` seguida de `*`
(`ANDRAS HICZ-HU` → `ANDRAS HICZ-HU*`, `uf_botonista = HU*`); o `*` não entra no `id_botonista`.

**Colunas deslocadas.** Na tabela Sub-18 de 2026 os números estão uma coluna à direita
dos rótulos (`PG J …` sobre `23 35 14 11 2 1 68 36`): lida como impressa, nenhuma linha
fecha (J=35, mas V+E+D=27); deslocada, todas fecham (J=14, V=11, E=2, D=1, PG=35). Quando
isso acontece em **todas** as linhas de uma categoria, o pipeline lê com o deslocamento,
deixa `saldo_gols` vazio (não impresso) e marca as linhas na `observacao` e na
verificação `colunas_deslocadas`.

### Alternativa: PDF do histórico

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

O PDF do histórico precisa manter o padrão de tabela (`CATEGORIA - Divisão`, cabeçalho
`CF TÉCNICOS …`, linhas `1º NOME-UF …`). Para os anos que já vieram das tabelas oficiais,
não rode `--anos` com o histórico: ele trocaria a tabela oficial pelo texto do histórico.
Em qualquer caso, confira a aba `qualidade` depois de rodar.

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
  - posições descontínuas (na divisão e, `posicao_geral_descontinua`, na categoria) e
    chaves duplicadas (hoje: nenhuma);
  - `colunas_deslocadas`: tabela oficial lida com o deslocamento de colunas corrigido
    (Sub-18 de 2026);
  - `uf_ausente`: linhas sem UF no PDF (estrangeiros têm a sigla do país com `*`, não entram aqui) (1997, tabelas Sub-18/15 de 2002 que trazem sigla
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
Makefile          atualizar / reconstruir / testes / instalar
futmesa/
  official_tables.py  tabelas oficiais: PDF → markdown (markitdown) → classificação final
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
  <ano>/                 PDFs oficiais do campeonato (um por categoria) e o markdown gerado
  campeonatos.csv        local, datas e participantes por edição (curadoria do texto do PDF)
  correcoes_texto.csv    correções manuais
```
