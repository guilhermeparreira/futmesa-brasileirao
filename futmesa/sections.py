"""Recognise section titles (category/division) and table headers."""

from __future__ import annotations

import re
from dataclasses import dataclass

SINGLE_DIVISION = "Única"
NAMED_DIVISION_ORDER = ("Ouro", "Prata", "Bronze", "Extra", "Copa")
EARLY_YEARS_SERIES = {"OURO": "Ouro", "PRATA": "Prata", "BRONZE": "Bronze"}

SECTION_TITLE = re.compile(
    r"^(?P<category>ADULTO|MASTER|SUB\s*-?\s*\d{2}|INFANTIL|JUVENIL|OURO|PRATA|BRONZE)"
    r"(?:\s*[-–]\s*(?P<division>\S.*))?$"
)
NUMBERED_DIVISION = re.compile(r"^(?P<number>\d)\s*[ªa°º]?\s*DIVIS[ÃA]O$", re.IGNORECASE)
TABLE_HEADER = re.compile(r"^CF\s+T[ÉE]CNICOS\s+(?P<columns>.+)$")

STAT_COLUMNS = {
    "J": "jogos",
    "V": "vitorias",
    "E": "empates",
    "D": "derrotas",
    "GF": "gols_pro",
    "GP": "gols_pro",
    "GC": "gols_contra",
    "SG": "saldo_gols",
    "PG": "pontos",
}


@dataclass(frozen=True)
class Section:
    """A ranking table: category + division, as titled in the PDF."""

    category: str
    division: str
    title: str


def parse_section_title(line: str) -> Section | None:
    """Return the section a title line opens, or ``None`` if it is not a title.

    Handles every layout found in the PDF: ``OURO`` (1989-1992 series, which
    belong to the single open category, here called Adulto), ``ADULTO – Ouro``,
    ``ADULTO – Copa Santos``, ``MASTER - 3ª Divisão``, ``SUB-18`` and
    ``SUB-18 - 1ª Divisão``.

    Args:
        line: One line of page text.

    Returns:
        The parsed section, or ``None``.
    """
    title = " ".join(line.split())
    match = SECTION_TITLE.match(title)
    if not match:
        return None
    raw_category = match["category"]
    if raw_category in EARLY_YEARS_SERIES:
        return Section("Adulto", EARLY_YEARS_SERIES[raw_category], title)
    return Section(_normalise_category(raw_category), _normalise_division(match["division"]), title)


def _normalise_category(raw: str) -> str:
    """``SUB - 18`` -> ``Sub-18``; ``ADULTO`` -> ``Adulto``."""
    compact = re.sub(r"\s|-", "", raw)
    if compact.startswith("SUB"):
        return f"Sub-{compact[3:]}"
    return compact.capitalize()


def _normalise_division(raw: str | None) -> str:
    """``Copa Santos`` -> ``Copa``; ``1ª DIVISÃO`` -> ``1ª Divisão``; none -> Única."""
    if not raw:
        return SINGLE_DIVISION
    text = raw.strip()
    numbered = NUMBERED_DIVISION.match(text)
    if numbered:
        return f"{numbered['number']}ª Divisão"
    first_word = text.split()[0].capitalize()
    return first_word if first_word in NAMED_DIVISION_ORDER else text


def parse_table_header(line: str) -> list[str] | None:
    """Return the stat columns of a ``CF TÉCNICOS J V E D ...`` header line.

    Column labels are translated to dataset names (``GP`` and ``GF`` both
    become ``gols_pro``). A repeated ``GC`` — a typo found in the 2015 Sub-15
    table, where the last-but-one column is the goal difference — is read as
    ``saldo_gols``.

    Args:
        line: One line of page text.

    Returns:
        Dataset column names in table order, or ``None`` if the line is not a
        table header.
    """
    match = TABLE_HEADER.match(line.strip())
    if not match:
        return None
    columns: list[str] = []
    for label in match["columns"].split():
        column = STAT_COLUMNS.get(label.upper(), label.lower())
        if column in columns and column == "gols_contra":
            column = "saldo_gols"
        columns.append(column)
    return columns


def division_level(division: str, divisions_in_category: list[str]) -> int | None:
    """Rank of a division inside its category/year (1 = top tier).

    Numbered divisions use their number. Named divisions follow
    Ouro > Prata > Bronze > Extra > Copa, counting only the ones that existed
    that year (so Copa is level 4 when there was no Extra), and come below any
    numbered division of the same year (2011: 1ª, 2ª, 3ª, Extra = 4, Copa = 5).
    A single division is level 1.
    """
    if division == SINGLE_DIVISION:
        return 1
    if _division_number(division):
        return _division_number(division)
    present = [name for name in NAMED_DIVISION_ORDER if name in divisions_in_category]
    if division not in present:
        return None
    numbers = [_division_number(name) for name in divisions_in_category]
    lowest_numbered = max((number for number in numbers if number), default=0)
    return lowest_numbered + present.index(division) + 1


def _division_number(division: str) -> int | None:
    """``3ª Divisão`` -> 3; anything else -> None."""
    numbered = re.match(r"^(\d)ª Divisão$", division)
    return int(numbered[1]) if numbered else None
