import pandas as pd
import pytest

from futmesa.export import merge_years
from futmesa.extraction import merge_wrapped_name_cells
from futmesa.rows import parse_ranking_line
from futmesa.sections import division_level, parse_section_title, parse_table_header

STATS_2006 = ["jogos", "vitorias", "empates", "derrotas", "gols_pro", "gols_contra", "saldo_gols", "pontos"]
STATS_2002 = ["pontos", "vitorias", "gols_pro", "gols_contra", "saldo_gols"]


@pytest.mark.parametrize(
    ("line", "category", "division"),
    [
        ("            OURO", "Adulto", "Ouro"),
        ("ADULTO – Ouro", "Adulto", "Ouro"),
        ("MASTER -Ouro", "Master", "Ouro"),
        ("ADULTO – Copa Santos", "Adulto", "Copa"),
        ("ADULTO - 1ª DIVISÃO", "Adulto", "1ª Divisão"),
        ("SUB-18", "Sub-18", "Única"),
        ("SUB-18 - 2ª Divisão", "Sub-18", "2ª Divisão"),
        ("INFANTIL", "Infantil", "Única"),
    ],
)
def test_section_titles(line, category, division):
    section = parse_section_title(line)
    assert (section.category, section.division) == (category, division)


@pytest.mark.parametrize("line", ["Podium Adulto Ouro", "Adulto - 1ª Divisão", "Na categoria dos ADULTOS"])
def test_captions_are_not_section_titles(line):
    assert parse_section_title(line) is None


def test_table_header_translates_columns_and_fixes_repeated_gc():
    assert parse_table_header("CF TÉCNICOS J V GP GC SG PG") == [
        "jogos", "vitorias", "gols_pro", "gols_contra", "saldo_gols", "pontos"
    ]
    assert parse_table_header("CF TÉCNICOS J V E D GF GC GC PG")[-2] == "saldo_gols"


def test_early_layout_with_club_city_and_nickname():
    row = parse_ranking_line('   5º   RUBENS LOPES CINTRA "Rubinho" (ADC Carbocloro - Santos)    SP', None)
    assert (row.posicao, row.botonista, row.apelido) == (5, "RUBENS LOPES CINTRA", "Rubinho")
    assert (row.clube, row.cidade_botonista, row.uf_botonista) == ("ADC Carbocloro", "Santos", "SP")


def test_early_layout_without_state():
    row = parse_ranking_line("11º   ALEX", None)
    assert (row.botonista, row.uf_botonista) == ("ALEX", None)


def test_2008_layout_with_club_after_dash():
    row = parse_ranking_line("1º   THIAGO PENNA – Vasco da Gama      RJ", None)
    assert (row.botonista, row.clube, row.uf_botonista) == ("THIAGO PENNA", "Vasco da Gama", "RJ")


def test_row_without_ordinal_needs_a_state():
    assert parse_ranking_line("31   THI          SC", None).posicao == 31
    assert parse_ranking_line("15 na Sub-15, disputaram, de 19 a 22 de junho", None) is None


def test_modern_layout_with_statistics():
    row = parse_ranking_line(" 3º   THIAGO PENNA-RJ   26   20   3   3   141   91   50   63", STATS_2006)
    assert (row.botonista, row.uf_botonista) == ("THIAGO PENNA", "RJ")
    assert row.stats == dict(zip(STATS_2006, [26, 20, 3, 3, 141, 91, 50, 63]))


@pytest.mark.parametrize(
    ("line", "name", "uf"),
    [
        ("1º   GABRIEL GODOY-PR)   18 11 3 4 84 68 16 36", "GABRIEL GODOY", "PR"),
        ("1º   JOAO PEDRO GALL-SP-   14 7 3 4 59 44 15 24", "JOAO PEDRO GALL", "SP"),
        ("1º   LÉO LIMA (SP)   18 17 1 0 134 37 97 52", "LÉO LIMA", "SP"),
        ("1º   FERNANDO-PR-PR   11 10 0 1 50 20 30 30", "FERNANDO", "PR"),
        ("3º   VINÍCIUS ·SP   27 18 2 7 204 162 42 56", "VINÍCIUS", "SP"),
    ],
)
def test_state_typos_in_modern_layout(line, name, uf):
    row = parse_ranking_line(line, STATS_2006)
    assert (row.botonista, row.uf_botonista) == (name, uf)


def test_club_acronym_that_looks_like_a_number():
    row = parse_ranking_line("7º   THIAGO P. - 2004   34   10   83   79   4", STATS_2002)
    assert (row.botonista, row.clube, row.stats["pontos"]) == ("THIAGO P.", "2004", 34)


def test_walkover_flag():
    row = parse_ranking_line("29º   NICOLAZZI-PR (WO)   14 0 0 14 0 42 -42 0", STATS_2006)
    assert row.wo and row.botonista == "NICOLAZZI"


def test_wrapped_name_cell_is_merged():
    lines = ["   LEONARDO GONÇALVES-", "7º   16   12   2   2   81   48   33   38", "   PR"]
    merged = [line for line in merge_wrapped_name_cells(lines) if line.strip()]
    row = parse_ranking_line(merged[0], STATS_2006)
    assert (row.posicao, row.botonista, row.uf_botonista, row.stats["pontos"]) == (
        7, "LEONARDO GONÇALVES", "PR", 38
    )


def test_division_levels():
    named = ["Ouro", "Prata", "Bronze", "Copa"]
    assert division_level("Copa", named) == 4
    assert division_level("3ª Divisão", []) == 3
    assert division_level("Única", []) == 1
    mixed_2011 = ["1ª Divisão", "2ª Divisão", "3ª Divisão", "Extra", "Copa"]
    assert [division_level(name, mixed_2011) for name in mixed_2011] == [1, 2, 3, 4, 5]


def test_merge_years_replaces_only_the_new_years():
    existing = pd.DataFrame({"ano": [2024, 2025], "valor": [1, 2]})
    new = pd.DataFrame({"ano": [2025, 2026], "valor": [20, 30]})
    merged = merge_years(existing, new)
    assert merged.to_dict("list") == {"ano": [2024, 2025, 2026], "valor": [1, 20, 30]}


def _rankings(rows):
    columns = ["ano", "categoria", "botonista_padronizado", "uf_botonista"]
    return pd.DataFrame(rows, columns=columns)


def test_player_who_changes_state_keeps_one_id():
    from futmesa.people import assign_person_ids

    rankings = _rankings(
        [(2023, "Adulto", "ROBERTINHO", "PR"), (2024, "Adulto", "ROBERTINHO", "PR"),
         (2025, "Adulto", "ROBERTINHO", "SP")]
    )
    assert assign_person_ids(rankings).unique().tolist() == ["robertinho-pr"]


def test_homonyms_in_the_same_year_are_different_people():
    from futmesa.people import assign_person_ids

    rankings = _rankings(
        [(2014, "Adulto", "DENIS", "PR"), (2014, "Adulto", "DENIS", "SP"),
         (2015, "Adulto", "DENIS", "SP")]
    )
    assert assign_person_ids(rankings).tolist() == ["denis-pr", "denis-sp", "denis-sp"]


def test_youth_and_master_with_same_name_are_split():
    from futmesa.people import assign_person_ids

    rankings = _rankings([(2000, "Sub-18", "JUNINHO", "SP"), (2024, "Master", "JUNINHO", "SP")])
    assert assign_person_ids(rankings).tolist() == ["juninho-sp", "juninho-sp-2"]


def test_foreign_country_marked_with_star_is_kept_as_uf():
    row = parse_ranking_line("11º ANDRAS HICZ-HU* 30 24 8 6 10 99 91 8", ["pontos", "jogos", "vitorias", "empates", "derrotas", "gols_pro", "gols_contra", "saldo_gols"])
    assert (row.botonista, row.uf_botonista) == ("ANDRAS HICZ", "HU*")


def test_unmarked_foreign_code_is_not_a_uf():
    row = parse_ranking_line("11º ANDRAS HICZ-HU", None)
    assert row.uf_botonista is None


def test_overall_position_stacks_divisions_by_level():
    from futmesa.transform import fill_overall_positions

    rankings = pd.DataFrame(
        {
            "ano": [2025] * 5 + [2026],
            "categoria": ["Adulto", "Adulto", "Adulto", "Adulto", "Master", "Adulto"],
            "divisao_nivel": [1, 1, 2, 2, 1, 1],
            "posicao": pd.array([1, 2, 1, 2, 1, 1], dtype="Int64"),
            "posicao_geral": pd.array([None] * 5 + [7], dtype="Int64"),
        }
    )
    filled = fill_overall_positions(rankings)
    assert filled["posicao_geral"].tolist() == [1, 2, 3, 4, 1, 7]
