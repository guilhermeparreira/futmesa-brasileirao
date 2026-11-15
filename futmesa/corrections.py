"""Manual, documented fixes for typos in the source PDF text.

Corrections are keyed by championship year (not by page), so they keep
working when a new edition of the PDF shifts the page numbers.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TextCorrection:
    """Replace ``original`` with ``corrected`` in the pages of one championship."""

    year: int
    original: str
    corrected: str
    note: str

    @property
    def pattern(self) -> re.Pattern:
        """``original`` matched regardless of how many spaces separate words."""
        return _whitespace_insensitive(self.original)


def load_corrections(csv_path: Path | None) -> dict[int, list[TextCorrection]]:
    """Read the corrections file, grouped by year.

    The CSV has the columns ``ano``, ``texto_original``, ``texto_corrigido``
    and ``observacao``. A missing file means no corrections.

    Args:
        csv_path: Path to the CSV, or ``None``.

    Returns:
        Mapping from championship year to its corrections.
    """
    by_year: dict[int, list[TextCorrection]] = defaultdict(list)
    if csv_path is None or not csv_path.exists():
        return by_year
    with csv_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            correction = TextCorrection(
                year=int(row["ano"]),
                original=row["texto_original"],
                corrected=row["texto_corrigido"],
                note=row["observacao"],
            )
            by_year[correction.year].append(correction)
    return by_year


def apply_corrections(
    text: str, corrections: list[TextCorrection]
) -> tuple[str, set[TextCorrection]]:
    """Apply the corrections that occur in this page text.

    Args:
        text: Text of one page.
        corrections: Corrections registered for the page's championship.

    Returns:
        The corrected text and the corrections that were applied.
    """
    applied: set[TextCorrection] = set()
    for correction in corrections:
        if correction.pattern.search(text):
            text = correction.pattern.sub(lambda _: correction.corrected, text)
            applied.add(correction)
    return text, applied


def ensure_all_applied(
    year: int, corrections: list[TextCorrection], applied: set[TextCorrection]
) -> None:
    """Fail loudly when a correction no longer matches the PDF text.

    Raises:
        ValueError: If any correction of the year was not applied, which
            means the PDF changed and the correction must be reviewed.
    """
    missing = [c.original for c in corrections if c not in applied]
    if missing:
        raise ValueError(f"Correções de {year} não encontradas no PDF: {missing}")


def note_for_line(line: str, corrections: list[TextCorrection]) -> str | None:
    """Observation of the correction applied to this line, if any."""
    notes = [
        c.note
        for c in corrections
        if c.corrected.strip() and _whitespace_insensitive(c.corrected).search(line)
    ]
    return "; ".join(notes) or None


def _whitespace_insensitive(snippet: str) -> re.Pattern:
    return re.compile(r"\s+".join(map(re.escape, snippet.split())))
