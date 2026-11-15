"""Parse one ranking line into player, club, state and statistics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BRAZILIAN_UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)

RANKING_LINE = re.compile(r"^\s*(?P<position>\d{1,3})\s*(?P<ordinal>[º°])?\s+(?P<body>\S.*?)\s*$")
WALKOVER = re.compile(r"\(\s*W\s*\.?\s*O\s*\.?\s*\)", re.IGNORECASE)
INTEGER = re.compile(r"^-?\d+$")
UF_AFTER_DASH = re.compile(r"^(?P<name>.*?)\s*[-–·]\s*(?P<uf>[A-Z]{2})\s*[)\-–]?$")
UF_IN_PARENTHESES = re.compile(r"^(?P<name>.*?)\s*\((?P<uf>[A-Z]{2})\)$")
UF_AFTER_GAP = re.compile(r"^(?P<name>.*\S)\s{2,}(?P<uf>[A-Z]{2})$")
CLUB_IN_PARENTHESES = re.compile(r"^(?P<name>[^()]*?)\s*\((?P<club>[^()]+)\)\s*$")
CLUB_AFTER_DASH = re.compile(r"^(?P<name>.+?)\s+[-–]\s+(?P<club>.+)$")
CLUB_AND_CITY = re.compile(r"^(?P<club>.+?)\s*[-–]\s*(?P<city>.+)$")
NICKNAME = re.compile(r"[\"“”](?P<nickname>[^\"“”]+)[\"“”]")


@dataclass
class RankingRow:
    """A player's final placing in one section, as printed in the PDF."""

    posicao: int
    botonista: str | None
    apelido: str | None
    clube: str | None
    cidade_botonista: str | None
    uf_botonista: str | None
    wo: bool
    stats: dict[str, int] = field(default_factory=dict)
    linha_original: str = ""
    alerta: str | None = None


def parse_ranking_line(line: str, stat_columns: list[str] | None) -> RankingRow | None:
    """Parse a ranking line from any era of the PDF.

    Supported layouts::

        1º   JOÃO LUIZ GIL (S. E. Palmeiras)        SP          # 1989-2001
        1º   THIAGO PENNA – Vasco da Gama           RJ          # 2008
        1º   SÍLVIO PAIVA - SP   36   10   109 ...              # 2002-2015
        1º   ROBERTINHO-SP   27   18   4   5 ...                # 2012-2025
        31   THI                                    SC          # ordinal missing

    A line without the ordinal sign is accepted only when it still looks like
    a table row (a valid UF or exactly the expected number of statistics), so
    narrative text that happens to start with a number is ignored.

    Args:
        line: One line of page text.
        stat_columns: Statistic columns announced by the section's table
            header, or ``None`` when the section has no statistics.

    Returns:
        The parsed row, or ``None`` if the line is not a ranking row.
    """
    match = RANKING_LINE.match(line)
    if not match:
        return None
    body, walkover = _remove_walkover_flag(match["body"])
    expected = len(stat_columns or [])
    text, numbers = _split_trailing_integers(body, expected)
    name_text, uf = _split_uf(text)
    if not match["ordinal"] and not _looks_like_unmarked_row(uf, numbers, expected):
        return None
    name_text, club_text = _split_club(name_text)
    name, nickname = _split_nickname(name_text)
    club, club_city = _split_club_city(club_text)
    stats, alert = _map_stats(numbers, stat_columns or [])
    return RankingRow(
        posicao=int(match["position"]),
        botonista=name,
        apelido=nickname,
        clube=club,
        cidade_botonista=club_city,
        uf_botonista=uf,
        wo=walkover,
        stats=stats,
        linha_original=" ".join(line.split()),
        alerta=alert,
    )


def is_numbers_only_row(line: str) -> bool:
    """True for a row whose name cell was wrapped onto the lines around it."""
    match = RANKING_LINE.match(line)
    if not match or not match["ordinal"]:
        return False
    return all(INTEGER.match(token) for token in match["body"].split())


def _looks_like_unmarked_row(uf: str | None, numbers: list[int], expected: int) -> bool:
    return uf is not None or (expected > 0 and len(numbers) == expected)


def _remove_walkover_flag(body: str) -> tuple[str, bool]:
    """Drop a ``(WO)`` marker and report whether it was there."""
    cleaned, count = WALKOVER.subn(" ", body)
    return cleaned.strip(), count > 0


def _split_trailing_integers(body: str, expected: int) -> tuple[str, list[int]]:
    """Separate the statistics (trailing integers) from the text cells.

    When there are more trailing integers than statistic columns, the extra
    leading ones belong to the name cell (e.g. ``THIAGO P. - 2004``, where
    2004 is the club).
    """
    tokens = re.split(r"(\s+)", body)
    taken: list[str] = []
    while tokens and (INTEGER.match(tokens[-1]) or not tokens[-1].strip()):
        taken.insert(0, tokens.pop())
    while expected and len([t for t in taken if t.strip()]) > expected:
        tokens.append(taken.pop(0))
    numbers = [int(token) for token in taken if token.strip()]
    return "".join(tokens).strip(), numbers


def _split_uf(text: str) -> tuple[str, str | None]:
    """Take the player's state from ``NAME - UF``, ``NAME (UF)`` or ``NAME    UF``.

    A UF printed twice (``FERNANDO-PR-PR``, 2013) is removed from the name.
    """
    for pattern in (UF_AFTER_DASH, UF_IN_PARENTHESES, UF_AFTER_GAP):
        match = pattern.match(text)
        if match and match["uf"] in BRAZILIAN_UFS:
            return _drop_repeated_uf(match["name"].strip(), match["uf"]), match["uf"]
    return text.strip(), None


def _drop_repeated_uf(name: str, uf: str) -> str:
    repeated = UF_AFTER_DASH.match(name)
    return repeated["name"].strip() if repeated and repeated["uf"] == uf else name


def _split_club(text: str) -> tuple[str, str | None]:
    """Take the club from ``NAME (Club)`` or, as in 2008, ``NAME – Club``."""
    for pattern in (CLUB_IN_PARENTHESES, CLUB_AFTER_DASH):
        match = pattern.match(text)
        if match:
            return match["name"].strip(), " ".join(match["club"].split())
    return text, None


def _split_nickname(text: str) -> tuple[str | None, str | None]:
    """``RUBENS LOPES CINTRA "Rubinho"`` -> (``RUBENS LOPES CINTRA``, ``Rubinho``)."""
    match = NICKNAME.search(text)
    nickname = match["nickname"].strip() if match else None
    name = NICKNAME.sub(" ", text)
    name = " ".join(name.replace(")", " ").split()).strip(" -–")
    return name or None, nickname


def _split_club_city(club_text: str | None) -> tuple[str | None, str | None]:
    """``ADC Carbocloro - Santos`` -> (``ADC Carbocloro``, ``Santos``)."""
    if not club_text:
        return None, None
    match = CLUB_AND_CITY.match(club_text)
    if not match:
        return club_text, None
    return match["club"].strip(), match["city"].strip()


def _map_stats(numbers: list[int], columns: list[str]) -> tuple[dict[str, int], str | None]:
    """Pair statistics with the header columns, flagging count mismatches."""
    if not numbers:
        return {}, None
    if len(numbers) != len(columns):
        return {}, f"{len(numbers)} números para colunas {columns}"
    return dict(zip(columns, numbers)), None
