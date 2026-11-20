"""Read the championship-history PDF: per-page text and the table of contents."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

INDEX_TITLE = "ÍNDICE"
INDEX_ENTRY = re.compile(
    r"^\s*(?P<edition>\d{1,3})\s*[º°]\s+(?P<year>\d{4})\s+(?P<venue>.+?)\s+(?P<page>\d{1,4})\s*$"
)
INDEX_BOUNDARY = re.compile(r"^\s*(?P<label>\S.*?)\s{2,}(?P<page>\d{1,4})\s*$")
CITY_UF = re.compile(r"^(?P<city>.+?)\s*[-–]\s*(?P<uf>[A-Z]{2})$")


@dataclass(frozen=True)
class Championship:
    """One edition of the championship (from the PDF index or the official tables)."""

    year: int
    edition: int | None
    city: str | None
    uf: str | None
    first_page: int
    last_page: int
    start_date: date | None = None
    end_date: date | None = None


def read_pages(pdf_path: Path) -> list[str]:
    """Extract the text of every page, keeping the visual column layout.

    Uses poppler's ``pdftotext -layout``, which keeps table cells on the same
    line separated by runs of spaces (the row parser relies on that).

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List where item ``i`` is the text of page ``i + 1``.

    Raises:
        FileNotFoundError: If ``pdftotext`` (poppler-utils) is not installed.
        subprocess.CalledProcessError: If the PDF cannot be read.
    """
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    pages = result.stdout.split("\f")
    return pages[:-1] if pages and not pages[-1].strip() else pages


def find_championships(pages: list[str]) -> list[Championship]:
    """Read the PDF index and return each edition with its page range.

    The page range of an edition goes from its index page up to the page
    before the next index entry (including non-championship entries such as
    "2020 e 2021" or "Colaboradores & Fontes Consultadas").

    Args:
        pages: Page texts as returned by :func:`read_pages`.

    Returns:
        Championships ordered by year. Empty if the PDF has no index.
    """
    index_lines = _index_lines(pages)
    entries = [m for m in map(INDEX_ENTRY.match, index_lines) if m]
    boundaries = sorted(_boundary_pages(index_lines) | {len(pages) + 1})
    return [_championship_from_entry(entry, boundaries) for entry in entries]


def _index_lines(pages: list[str]) -> list[str]:
    """Lines of the first page that contains the index title."""
    for page in pages:
        if INDEX_TITLE in page:
            return page.splitlines()
    return []


def _boundary_pages(index_lines: list[str]) -> set[int]:
    """Start page of every index entry, championship or not."""
    return {int(m["page"]) for m in map(INDEX_BOUNDARY.match, index_lines) if m}


def _championship_from_entry(entry: re.Match, boundaries: list[int]) -> Championship:
    first_page = int(entry["page"])
    next_start = next(page for page in boundaries if page > first_page)
    city, uf = split_city_uf(entry["venue"])
    return Championship(
        year=int(entry["year"]),
        edition=int(entry["edition"]),
        city=city,
        uf=uf,
        first_page=first_page,
        last_page=next_start - 1,
    )


def split_city_uf(text: str) -> tuple[str | None, str | None]:
    """Split ``"São Paulo - SP"`` / ``"Curitiba-PR"`` into city and UF."""
    match = CITY_UF.match(text.strip())
    if not match:
        return text.strip() or None, None
    return match["city"].strip(), match["uf"]
