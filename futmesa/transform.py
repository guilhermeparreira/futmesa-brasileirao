"""Turn extracted rows into the typed, documented ranking table."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

from .pdf_text import Championship
from .people import assign_person_ids
from .sections import division_level
from .standardisation import standardise_clubs, standardise_players

PRIMARY_KEY = ["ano", "categoria", "divisao", "posicao"]

CHAMPIONSHIP_COLUMNS = [
    "ano",
    "edicao",
    "cidade_campeonato",
    "uf_campeonato",
    "local_campeonato",
    "data_inicio",
    "data_fim",
]
STAT_COLUMNS = [
    "jogos",
    "vitorias",
    "empates",
    "derrotas",
    "gols_pro",
    "gols_contra",
    "saldo_gols",
    "pontos",
]
RANKING_COLUMNS = [
    *CHAMPIONSHIP_COLUMNS,
    "categoria",
    "divisao",
    "divisao_nivel",
    "secao_original",
    "posicao",
    "botonista",
    "apelido",
    "botonista_chave",
    "botonista_padronizado",
    "id_botonista",
    "clube",
    "clube_padronizado",
    "cidade_botonista",
    "uf_botonista",
    "wo",
    *STAT_COLUMNS,
    "observacao",
    "pagina_pdf",
    "linha_original",
]
INTEGER_COLUMNS = ["ano", "edicao", "divisao_nivel", "posicao", "pagina_pdf", *STAT_COLUMNS]
DATE_COLUMNS = ["data_inicio", "data_fim"]
CATEGORY_ORDER = ["Adulto", "Master", "Sub-20", "Sub-18", "Sub-15", "Infantil"]
LOWERCASE_PARTICLES = {"de", "da", "do", "das", "dos", "e"}
UNREAD_STATS_NOTE = "Estatísticas não lidas: "


def build_championships_table(
    championships: list[Championship], metadata_csv: Path | None
) -> pd.DataFrame:
    """One row per edition: index data completed by the curated metadata CSV.

    Values in the CSV (venue, dates, reported number of players) take
    precedence; edition, city and UF fall back to the PDF index.

    Args:
        championships: Editions found in the PDF index.
        metadata_csv: ``dados/campeonatos.csv`` or ``None``.

    Returns:
        Championship table indexed by nothing, sorted by year.
    """
    from_index = pd.DataFrame(
        {
            "ano": [c.year for c in championships],
            "edicao": [c.edition for c in championships],
            "cidade_campeonato": [c.city for c in championships],
            "uf_campeonato": [c.uf for c in championships],
        }
    ).set_index("ano")
    curated = _read_metadata(metadata_csv)
    combined = curated.combine_first(from_index) if not curated.empty else from_index
    for column in CHAMPIONSHIP_COLUMNS[1:] + ["participantes_informados"]:
        if column not in combined:
            combined[column] = pd.NA
    table = combined.reset_index()
    return _apply_types(table).sort_values("ano", ignore_index=True)


def _read_metadata(metadata_csv: Path | None) -> pd.DataFrame:
    if metadata_csv is None or not metadata_csv.exists():
        return pd.DataFrame()
    return pd.read_csv(metadata_csv, dtype={"uf_campeonato": "string"}).set_index("ano")


def build_ranking_table(
    records: list[dict],
    championships: pd.DataFrame,
    player_depara_csv: Path | None = None,
    club_depara_csv: Path | None = None,
    people_overrides_csv: Path | None = None,
) -> pd.DataFrame:
    """Build the final ranking table from the extracted rows.

    Adds the championship columns, the division level and the normalised
    player key, applies nullable types and sorts by year, category,
    division level and position.

    Args:
        records: Rows returned by ``extraction.extract_championship``.
        championships: Table from :func:`build_championships_table`.
        player_depara_csv: Reviewed de-para of player names.
        club_depara_csv: Reviewed de-para of club names.
        people_overrides_csv: Manual person ids for a name + state.

    Returns:
        DataFrame with exactly :data:`RANKING_COLUMNS`.
    """
    rankings = pd.DataFrame.from_records(records)
    for column in STAT_COLUMNS + ["observacao"]:
        if column not in rankings:
            rankings[column] = pd.NA
    rankings = reinterpret_uf_in_club_sections(rankings)
    rankings["clube"] = rankings["clube"].map(normalise_club_case)
    rankings = note_unnamed_walkovers(rankings)
    rankings = note_unread_statistics(rankings)
    rankings = rankings.merge(championships[CHAMPIONSHIP_COLUMNS], on="ano", how="left")
    rankings["divisao_nivel"] = _division_levels(rankings)
    rankings["botonista_chave"] = rankings["botonista"].map(player_key)
    rankings["botonista_padronizado"] = standardise_players(rankings, player_depara_csv)
    rankings["clube_padronizado"] = standardise_clubs(rankings["clube"], club_depara_csv)
    rankings["id_botonista"] = pd.NA
    rankings = _apply_types(rankings[RANKING_COLUMNS])
    return sort_rankings(rankings)


def reinterpret_uf_in_club_sections(rankings: pd.DataFrame) -> pd.DataFrame:
    """In tables that put a club acronym after the dash, read ``- SC`` as a club too.

    The 2002 Sub-18 and Sub-15 tables print ``NAME - CLUB`` (``PEDREIRA -
    AFC``, ``CARUSO - SCCP``). One acronym there, ``SC``, is also a UF code
    and would be read as the player's state. When most rows of a section
    carry a club and no UF, a UF that came after a dash is moved to ``clube``.

    Args:
        rankings: Extracted rows (one per placing).

    Returns:
        The rows with those UFs reinterpreted and an ``observacao`` added.
    """
    fixed = rankings.copy()
    section_keys = ["ano", "categoria", "divisao"]
    club_without_uf = fixed["clube"].notna() & fixed["uf_botonista"].isna()
    club_section = club_without_uf.groupby([fixed[k] for k in section_keys]).transform("mean") > 0.5
    lone_uf = fixed["clube"].isna() & fixed["uf_botonista"].notna()
    after_dash = [
        isinstance(uf, str) and isinstance(line, str) and bool(re.search(rf"[-–]\s*{uf}\b", line))
        for uf, line in zip(fixed["uf_botonista"], fixed["linha_original"])
    ]
    to_fix = club_section & lone_uf & pd.Series(after_dash, index=fixed.index)
    fixed.loc[to_fix, "clube"] = fixed.loc[to_fix, "uf_botonista"]
    fixed.loc[to_fix, "uf_botonista"] = pd.NA
    fixed.loc[to_fix, "observacao"] = (
        "Nesta tabela o texto após o traço é sigla de clube; lido como clube, não como UF"
    )
    return fixed


def normalise_club_case(club: object) -> object:
    """``CÍRCULO MILITAR`` -> ``Círculo Militar``; short acronyms (``SCCP``) are kept."""
    if not isinstance(club, str) or club != club.upper() or (len(club) <= 6 and " " not in club):
        return club
    words = club.lower().split()
    return " ".join(
        word if index and word in LOWERCASE_PARTICLES else word.capitalize()
        for index, word in enumerate(words)
    )


def note_unnamed_walkovers(rankings: pd.DataFrame) -> pd.DataFrame:
    """Explain rows that are only a ``(WO)`` placeholder without a player name."""
    noted = rankings.copy()
    unnamed = noted["botonista"].isna() & noted["wo"]
    noted.loc[unnamed, "observacao"] = "Posição impressa só como (WO), sem nome de botonista"
    return noted


def note_unread_statistics(rankings: pd.DataFrame) -> pd.DataFrame:
    """Turn parser alerts (numbers that did not fit the header) into observations."""
    noted = rankings.copy()
    has_alert = noted["alerta"].notna()
    noted.loc[has_alert, "observacao"] = UNREAD_STATS_NOTE + noted.loc[has_alert, "alerta"]
    return noted


def _division_levels(rankings: pd.DataFrame) -> pd.Series:
    """Level of each row's division among its year and category divisions."""
    divisions = rankings.groupby(["ano", "categoria"])["divisao"].unique().map(list)
    return pd.Series(
        [
            division_level(row.divisao, divisions[(row.ano, row.categoria)])
            for row in rankings.itertuples()
        ],
        index=rankings.index,
    )


def player_key(name: object) -> object:
    """Accent-free, punctuation-free upper-case name, to help match players across years."""
    if not isinstance(name, str):
        return pd.NA
    without_accents = "".join(
        char for char in unicodedata.normalize("NFKD", name) if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^A-Za-z0-9]+", " ", without_accents).upper().split()) or pd.NA


def sort_rankings(rankings: pd.DataFrame) -> pd.DataFrame:
    """Sort by year, category (Adulto first), division level and position."""
    category_rank = rankings["categoria"].map(
        {name: order for order, name in enumerate(CATEGORY_ORDER)}
    )
    return (
        rankings.assign(_categoria_ordem=category_rank.fillna(len(CATEGORY_ORDER)))
        .sort_values(["ano", "_categoria_ordem", "divisao_nivel", "posicao"], ignore_index=True)
        .drop(columns="_categoria_ordem")
    )


def _apply_types(table: pd.DataFrame) -> pd.DataFrame:
    """Nullable integers, real dates, booleans and strings."""
    typed = table.copy()
    for column in typed.columns:
        if column in INTEGER_COLUMNS or column == "participantes_informados":
            typed[column] = pd.to_numeric(typed[column], errors="coerce").astype("Int64")
        elif column in DATE_COLUMNS:
            typed[column] = pd.to_datetime(typed[column], errors="coerce")
        elif column == "wo":
            typed[column] = typed[column].fillna(False).astype(bool)
        else:
            typed[column] = typed[column].astype("string")
    return typed
