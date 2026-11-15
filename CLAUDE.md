# futmesa-brasileirao

Pipeline de dados do Campeonato Brasileiro Individual de Futebol de Mesa (12 Toques), 1989–2025.
Lê o PDF do histórico e gera a base em `saida/` (Parquet + Excel). Detalhes em `README.md`.

## Comandos

```bash
pip install -r requirements.txt            # precisa também de poppler-utils (pdftotext)
python -m futmesa --pdf HISTORICO.pdf --saida saida              # reconstrói tudo
python -m futmesa --pdf NOVO.pdf --saida saida --anos 2026       # anexa/substitui um ano
python -m pytest -q tests
```

O PDF fica fora do git.

## Onde mexer

- Regra de leitura do PDF: `futmesa/sections.py`, `rows.py`, `extraction.py`.
- Erro de digitação do PDF: `dados/correcoes_texto.csv` (nunca corrigir no código).
- Nome de botonista/clube: `dados/depara_botonistas.csv`, `dados/depara_clubes.csv` (só `aplicar = sim` vale).
- Pessoa errada (homônimo ou mudança de estado): `dados/pessoas_manual.csv`; regras em `futmesa/people.py`.
- Local/datas de cada edição: `dados/campeonatos.csv`.
- Participante citado sem colocação: `dados/participantes_sem_classificacao.csv`.

## Regras do projeto

- O que o PDF não traz fica vazio; nada é imputado. Inconsistências do PDF são reportadas na aba `qualidade`, não corrigidas.
- Depois de qualquer mudança: rodar os testes e o pipeline e conferir que `qualidade` não ganhou
  `chave_duplicada`, `posicoes_descontinuas` nem `botonista_repetido_no_ano`.
- Nomes de colunas e textos para o usuário em português; código e docstrings em inglês.
- Código: Clean Code, funções pequenas com nome descritivo no lugar de comentários, docstrings no
  estilo Google (seções completas só em funções públicas não triviais).

## Decisões já tomadas

- `MAURO` = Mauro Michilin e `MICHILIN` = Paulo César Michilin (aparecem juntos no mesmo ano/categoria).
- `DULEBA` (Master, PR) = Paulo Duleba. `S. E. Palmeiras`/`SEP` = Palmeiras.
- Robertinho é uma pessoa só (PR, depois SP): `robertinho-pr`.
- Todas as 185 sugestões do de-para de botonistas foram aprovadas em bloco, sem revisão individual.

## Próximos passos

- Automação: Action que dispara a publicação do site quando `saida/` muda.
- Revisar o de-para e os IDs conforme os botonistas apontarem erros.
