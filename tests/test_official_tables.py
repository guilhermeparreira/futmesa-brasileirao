from datetime import date

import pytest

from futmesa.official_tables import SHIFTED_COLUMNS_NOTE, parse_official_markdown

HEADER = """36º CAMPEONATO BRASILEIRO INDIVIDUAL
| CAMPINAS/SP |     |     | Categoria: | {category} | 18 A 21 ABRIL |
| ----------- | --- | --- | ---------- | ------ | ------------- |
| {category} - 1ª DIVISÃO |      |     | FINAL    |
| {category} - 2ª DIVISÃO |      |     | FINAL    |
Página 1 de 2

36º CAMPEONATO BRASILEIRO INDIVIDUAL
CAMPINAS/SP
CATEGORIA: {category}
CLASSIFICAÇÃO FINAL
| POS.    | DIV.                   | ATLETA | PG J  | V E  | D GP   | GC SG   | IA%   |
| ------- | ---------------------- | ------ | ----- | ---- | ------ | ------- | ----- |
"""

ADULTO = HEADER.format(category="ADULTO") + """\
| Campeão | 1º NANDO-RJ            |        | 61 27 | 19 4 | 4 148  | 105 43  | 75,3% |
| Vice    | 2º QUINHO-SP           |        | 62 27 | 20 2 | 5 148  | 113 35  | 76,5% |
| 3º      | 3º LEO GONÇALVES-PR    |        | 57 26 | 18 3 | 5 164  | 134 30  | 73,1% |
| Campeão | 1º RENAN-PR            |        | 56 27 | 18 2 | 7 133  | 96 37   | 69,1% |
| Vice    | 2º ALBARELLO-SP        |        | 51 27 | 16 3 | 8 131  | 111 20  | 63,0% |
| 6º      | 3º GARCIA-SP           |        | 36 24 | 11 3 | 10 87  | 95 -8   | 50,0% |
Página 2 de 2
"""

SUB18_SHIFTED = HEADER.format(category="SUB-18") + """\
| Campeão | 1º MANU-SP                |        | 23 35 | 14 11 | 2 1  | 68 36 | 21,9%  |
| Vice    | 2º THIAGO DALLA STELLA-PR |        | 23 35 | 14 11 | 2 1  | 67 32 | 21,9%  |
| Campeão | 1º MARCELINHO-PI          |        | 24 15 | 14 4  | 3 7  | 25 40 | 53,3%  |
| Vice    | 2º ALAMO DE HELD-PR       |        | 24 19 | 14 6  | 1 7  | 34 39 | 42,1%  |
Página 2 de 2
"""


@pytest.fixture
def adulto():
    return parse_official_markdown(ADULTO, 2026, "adulto.pdf")


def test_header_gives_edition_venue_and_dates(adulto):
    championship, _ = adulto
    assert (championship.edition, championship.city, championship.uf) == (36, "Campinas", "SP")
    assert (championship.start_date, championship.end_date) == (date(2026, 4, 18), date(2026, 4, 21))


def test_division_restarts_at_first_place(adulto):
    _, records = adulto
    assert [r["divisao"] for r in records] == ["1ª Divisão"] * 3 + ["2ª Divisão"] * 3
    assert records[3]["secao_original"] == "ADULTO - 2ª DIVISÃO"


def test_division_and_overall_positions(adulto):
    _, records = adulto
    assert [r["posicao"] for r in records] == [1, 2, 3, 1, 2, 3]
    assert [r["posicao_geral"] for r in records] == [1, 2, 3, 4, 5, 6]


def test_player_state_statistics_and_page(adulto):
    _, records = adulto
    nando = records[0]
    assert (nando["botonista"], nando["uf_botonista"], nando["categoria"]) == ("NANDO", "RJ", "Adulto")
    assert (nando["jogos"], nando["vitorias"], nando["gols_pro"], nando["saldo_gols"], nando["pontos"]) == (
        27, 19, 148, 43, 61
    )
    assert (nando["pagina_pdf"], nando["arquivo_fonte"]) == (2, "adulto.pdf")
    assert records[5]["saldo_gols"] == -8


def test_table_with_numbers_shifted_one_column_is_realigned():
    _, records = parse_official_markdown(SUB18_SHIFTED, 2026, "sub18.pdf")
    manu = records[0]
    assert (manu["jogos"], manu["vitorias"], manu["empates"], manu["derrotas"]) == (14, 11, 2, 1)
    assert (manu["gols_pro"], manu["gols_contra"], manu["pontos"]) == (68, 36, 35)
    assert manu.get("saldo_gols") is None
    assert SHIFTED_COLUMNS_NOTE in manu["observacao"]
    assert [r["posicao_geral"] for r in records] == [1, 2, 3, 4]


def test_consistent_table_is_not_realigned(adulto):
    _, records = adulto
    assert all(r["observacao"] is None for r in records)


def test_division_count_must_match_the_titles_in_the_file():
    one_title_only = ADULTO.replace("| ADULTO - 2ª DIVISÃO |      |     | FINAL    |\n", "")
    with pytest.raises(ValueError, match="divisões"):
        parse_official_markdown(one_title_only, 2026, "adulto.pdf")


def test_file_without_final_table_is_rejected():
    with pytest.raises(ValueError, match="CLASSIFICAÇÃO FINAL"):
        parse_official_markdown("36º CAMPEONATO BRASILEIRO INDIVIDUAL\n", 2026, "x.pdf")
