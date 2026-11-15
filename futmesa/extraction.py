"""Walk the pages of each championship and collect its ranking rows."""

from __future__ import annotations

import re
from dataclasses import asdict

from .corrections import TextCorrection, apply_corrections, ensure_all_applied, note_for_line
from .pdf_text import Championship
from .rows import RankingRow, is_numbers_only_row, parse_ranking_line
from .sections import Section, parse_section_title, parse_table_header

NAME_FRAGMENT = re.compile(r"^[A-ZÀ-Ý0-9 .'\"“”()\-–]+$")
PAGE_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")


def extract_championship(
    championship: Championship,
    pages: list[str],
    corrections: dict[int, list[TextCorrection]] | None = None,
) -> list[dict]:
    """Extract every ranking row of one championship.

    Lines are read in page order. A section title opens a new ranking table
    and resets the statistic columns; a ``CF TÉCNICOS ...`` header sets them.
    Lines that do not belong to a table (narrative, photo captions, page
    numbers) are skipped.

    Args:
        championship: Edition and page range, from the PDF index.
        pages: Text of every page of the PDF.
        corrections: Manual text fixes by year (see ``corrections.py``).

    Returns:
        One dict per ranking row with year, section, page and row fields.
    """
    year_corrections = (corrections or {}).get(championship.year, [])
    applied: set[TextCorrection] = set()
    records: list[dict] = []
    section: Section | None = None
    stat_columns: list[str] | None = None
    for page_number in range(championship.first_page, championship.last_page + 1):
        page_text, applied_here = apply_corrections(pages[page_number - 1], year_corrections)
        applied |= applied_here
        for line in merge_wrapped_name_cells(page_text.splitlines()):
            new_section = parse_section_title(line)
            if new_section:
                section, stat_columns = new_section, None
                continue
            header = parse_table_header(line)
            if header:
                stat_columns = header
                continue
            row = parse_ranking_line(line, stat_columns) if section else None
            if row:
                record = _record(championship, section, page_number, row)
                record["observacao"] = note_for_line(line, list(applied_here))
                records.append(record)
    ensure_all_applied(championship.year, year_corrections, applied)
    return records


def merge_wrapped_name_cells(lines: list[str]) -> list[str]:
    """Rebuild rows whose name cell pdftotext split above and below the numbers.

    Example (2013, Sub-15)::

        LEONARDO GONÇALVES-
        7º   16   12   2   2   81   48   33   38
        PR

    becomes ``7º   LEONARDO GONÇALVES-PR   16   12 ...``. The fragment lines
    are removed so they are not read again.

    Args:
        lines: Lines of one page.

    Returns:
        The lines with wrapped rows merged.
    """
    merged = list(lines)
    for index, line in enumerate(lines):
        if not is_numbers_only_row(line):
            continue
        before = _neighbour_fragment(merged, index, step=-1)
        after = _neighbour_fragment(merged, index, step=1)
        name = _join_fragments(merged[before].strip() if before is not None else "",
                               merged[after].strip() if after is not None else "")
        position, numbers = line.strip().split(maxsplit=1)
        merged[index] = f"{position}   {name}   {numbers}"
        for fragment_index in (before, after):
            if fragment_index is not None:
                merged[fragment_index] = ""
    return merged


def _neighbour_fragment(lines: list[str], index: int, step: int) -> int | None:
    """Index of the nearest non-blank line in ``step`` direction if it is a name piece."""
    neighbour = index + step
    while 0 <= neighbour < len(lines) and not lines[neighbour].strip():
        neighbour += step
    if not 0 <= neighbour < len(lines):
        return None
    return neighbour if _is_name_fragment(lines[neighbour]) else None


def _is_name_fragment(line: str) -> bool:
    text = line.strip()
    return bool(
        NAME_FRAGMENT.match(text)
        and not PAGE_NUMBER.match(text)
        and not parse_section_title(text)
        and not parse_table_header(text)
        and not parse_ranking_line(text, None)
    )


def _join_fragments(before: str, after: str) -> str:
    """Glue ``"NAME-"`` + ``"PR"`` without a space, otherwise with one."""
    if not before or not after:
        return before or after
    separator = "" if before.endswith(("-", "–")) else " "
    return f"{before}{separator}{after}"


def _record(championship: Championship, section: Section, page: int, row: RankingRow) -> dict:
    row_fields = asdict(row)
    stats = row_fields.pop("stats")
    return {
        "ano": championship.year,
        "categoria": section.category,
        "divisao": section.division,
        "secao_original": section.title,
        "pagina_pdf": page,
        **row_fields,
        **stats,
    }
