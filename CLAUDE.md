# futmesa-brasileirao

Pipeline de dados do Campeonato Brasileiro Individual de Futebol de Mesa (12 Toques), 1989 em diante.
Gera a base em `saida/` (Parquet + Excel) a partir de duas fontes: as tabelas oficiais de cada ano
(`dados/<ano>/*.pdf`, um por categoria, via markitdown — **modo padrão de atualização**, 2026+) e o
PDF do histórico (1989–2025). Detalhes em `README.md`.

## Comandos

```bash
make instalar                              # precisa também de poppler-utils (pdftotext)
make atualizar PASTA=dados/2027            # anexa/substitui um ano (padrão; falha se a qualidade quebrar)
make reconstruir                           # histórico + todas as pastas dados/<ano>/
make testes
```

O PDF do histórico fica fora do git (cópia local em `~/Downloads/HISTORICO-DO-CAMPEONATO-BRASILEIRO_12-Toques_3a-edicao_compressed.pdf`).
`make reconstruir` usa esse caminho por padrão (`HISTORICO=...` para trocar).

## Onde mexer

- Regra de leitura das tabelas oficiais (markdown): `futmesa/official_tables.py`.
- Regra de leitura do PDF do histórico: `futmesa/sections.py`, `rows.py`, `extraction.py`.
- Erro de digitação do PDF (as duas fontes) e atleta estrangeiro: `dados/correcoes_texto.csv`
  (nunca corrigir no código).
- Nome de botonista/clube: `dados/depara_botonistas.csv`, `dados/depara_clubes.csv` (só `aplicar = sim` vale).
- Pessoa errada (homônimo ou mudança de estado): `dados/pessoas_manual.csv`; regras em `futmesa/people.py`.
- Local/datas de cada edição: `dados/campeonatos.csv`.
- Participante citado sem colocação: `dados/participantes_sem_classificacao.csv`.

## Regras do projeto

- O que o PDF não traz fica vazio; nada é imputado (única exceção: `posicao_geral` nos anos do
  histórico, calculada com a regra das tabelas oficiais). Inconsistências do PDF são reportadas na
  aba `qualidade`, não corrigidas.
- Depois de qualquer mudança: `make reconstruir` (roda os testes e o pipeline; sai com erro se
  `qualidade` ganhar `chave_duplicada`, `posicoes_descontinuas`, `posicao_geral_descontinua` ou
  `botonista_repetido_no_ano` — ver `BLOCKING_CHECKS` em `futmesa/quality.py`).
- Nomes de colunas e textos para o usuário em português; código e docstrings em inglês.
- Código: Clean Code, funções pequenas com nome descritivo no lugar de comentários, docstrings no
  estilo Google (seções completas só em funções públicas não triviais).

## Decisões já tomadas

- `MAURO` = Mauro Michilin e `MICHILIN` = Paulo César Michilin (aparecem juntos no mesmo ano/categoria).
- `DULEBA` (Master, PR) = Paulo Duleba. `S. E. Palmeiras`/`SEP` = Palmeiras.
- Robertinho é uma pessoa só (PR, depois SP): `robertinho-pr`.
- As 185 sugestões originais do de-para de botonistas foram aprovadas em bloco, sem revisão individual.
- Tabelas oficiais: `posicao` = DIV. (na divisão), `posicao_geral` = POS. (acumulada na categoria;
  Campeão/Vice = logo após as divisões de cima). Nova divisão quando DIV. volta a 1º.
  Nos anos do histórico `posicao_geral` é calculada com a mesma regra (divisões empilhadas por
  `divisao_nivel`; 1991 fica subestimado porque só traz os primeiros de cada série).
- Estrangeiro: sigla do país + `*` em `uf_botonista` (`HU*`, `JP*`), via `correcoes_texto.csv`.
- Sub-18 2026: números impressos uma coluna à direita dos rótulos; lidos com o deslocamento
  (`colunas_deslocadas` na `qualidade`), SG vazio.

## Próximos passos

- Automação: Action que dispara a publicação do site quando `saida/` muda.
- Revisar o de-para e os IDs conforme os botonistas apontarem erros. Só DULEBA e as 3 regras
  de 2026 (SCHUMAQUER, MELLI JR, BRANQUINHO) têm `confianca = confirmado`; as demais 184 foram
  aprovadas em bloco (122 alta, 59 média, 3 baixa) — as de média/baixa são as primeiras a revisar.
