# Atualização da base do Campeonato Brasileiro Individual 12 Toques.
#
#   make atualizar PASTA=dados/2027     acrescenta (ou substitui) o ano da pasta
#   make reconstruir                    refaz tudo: histórico + cada dados/<ano>/
#   make testes                         só os testes
#
# Variáveis que podem ser trocadas na linha de comando: PYTHON, SAIDA, HISTORICO.

PYTHON    ?= python
SAIDA     ?= saida
HISTORICO ?= $(HOME)/Downloads/HISTORICO-DO-CAMPEONATO-BRASILEIRO_12-Toques_3a-edicao_compressed.pdf
PASTAS_ANUAIS := $(sort $(wildcard dados/[0-9][0-9][0-9][0-9]))

.DEFAULT_GOAL := ajuda
.PHONY: ajuda instalar testes atualizar reconstruir

ajuda:
	@echo "make atualizar PASTA=dados/2027   acrescenta/substitui o ano da pasta (PDFs oficiais, um por categoria)"
	@echo "make reconstruir                  refaz a base: histórico + $(PASTAS_ANUAIS)"
	@echo "make testes                       roda os testes"
	@echo "make instalar                     instala as dependências (requirements.txt)"

instalar:
	$(PYTHON) -m pip install -r requirements.txt

testes:
	$(PYTHON) -m pytest -q tests

atualizar: testes
	@test -n "$(PASTA)" || { echo "Informe a pasta: make atualizar PASTA=dados/2027"; exit 1; }
	@test -d "$(PASTA)" || { echo "Pasta $(PASTA) não existe."; exit 1; }
	@ls "$(PASTA)"/*.pdf >/dev/null 2>&1 || { echo "Nenhum PDF em $(PASTA)."; exit 1; }
	$(PYTHON) -m futmesa --tabelas "$(PASTA)" --saida "$(SAIDA)"

reconstruir: testes
	@test -f "$(HISTORICO)" || { echo "PDF do histórico não encontrado: $(HISTORICO) (use HISTORICO=...)"; exit 1; }
	$(PYTHON) -m futmesa --pdf "$(HISTORICO)" --saida "$(SAIDA)"
	@for pasta in $(PASTAS_ANUAIS); do \
		echo "== $$pasta"; \
		$(PYTHON) -m futmesa --tabelas "$$pasta" --saida "$(SAIDA)" || exit 1; \
	done
