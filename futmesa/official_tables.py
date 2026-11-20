"""Read a championship from the official result tables (one PDF per category).

The organisers publish each category as a PDF whose last pages hold the
final classification::

    POS.     DIV.   ATLETA            PG  J   V  E  D  GP   GC   SG  IA%
    Campeão  1º     NANDO-RJ          61  27  19 4  4  148  105  43  75,3%
    ...
    Campeão  1º     RENAN-PR          56  27  18 2  7  133  96   37  69,1%
    Vice     2º     ALBARELLO-SP      51  27  16 3  8  131  111  20  63,0%
    19º      3º     ROBERTINHO-SP     52  26  16 4  6  155  122  33  66,7%

``POS.`` is the overall position in the category (``Campeão``/``Vice`` for
the top two of every division) and ``DIV.`` the position inside the
division, which restarts at 1º whenever a new division begins. Each PDF is
converted to Markdown with markitdown, and that Markdown is what is parsed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from .corrections import TextCorrection, apply_corrections, ensure_all_applied, note_for_line
from .pdf_text import Championship
from .rows import RankingRow, parse_ranking_line
from .sections import STAT_COLUMNS, SINGLE_DIVISION, parse_section_title

FINAL_TABLE_TITLE = "CLASSIFICAÇÃO FINAL"
PAGE_FOOTER = re.compile(r"^\s*Página\s+\d+\s+de\s+\d+\s*$")
CATEGORY_LINE = re.compile(r"^\s*CATEGORIA:\s*(?P<category>\S.*?)\s*$", re.IGNORECASE)
EDITION = re.compile(r"(?P<edition>\d{1,3})\s*[º°]\s*CAMPEONATO BRASILEIRO INDIVIDUAL")
VENUE = re.compile(r"^(?P<city>[A-ZÀ-Ý][A-ZÀ-Ý .'-]*?)\s*/\s*(?P<uf>[A-Z]{2})$")
DIVISION_POSITION = re.compile(r"^(?P<position>\d{1,3})\s*[º°]")
OVERALL_POSITION = re.compile(r"^(?P<position>\d{1,3})\s*[º°]?$")
TOP_OF_DIVISION = {"CAMPEÃO": 1, "CAMPEAO": 1, "VICE": 2}
PERCENTAGE = re.compile(r"\s+-?[\d.,]+\s*%\s*$")
TABLE_SEPARATOR = re.compile(r"^[\s|:-]+$")
MONTHS = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
    "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}
MONTH = "|".join(MONTHS)
DATE_RANGE = re.compile(
    rf"\b(?P<first_day>\d{{1,2}})(?:\s+(?:DE\s+)?(?P<first_month>{MONTH}))?"
    rf"\s+A\s+(?P<last_day>\d{{1,2}})\s+(?:DE\s+)?(?P<last_month>{MONTH})\b",
    re.IGNORECASE,
)
SHIFTED_COLUMNS_NOTE = (
    "Colunas deslocadas no PDF: cada número está uma coluna à direita do seu rótulo "
    "(só assim J=V+E+D e PG=3V+E fecham em todas as linhas); lido com o deslocamento "
    "corrigido, SG não impresso e 1º número da linha descartado"
)
LOWERCASE_PARTICLES = {"de", "da", "do", "das", "dos", "e"}


@dataclass(frozen=True)
class FinalTableRow:
    """One line of a final-classification table, before it is split into fields."""

    category: str
    page: int
    overall_label: str
    division_position: int
    parsed: RankingRow
    original_line: str


def convert_pdf_to_markdown(pdf_path: Path) -> Path:
    """Convert one official-table PDF to Markdown with markitdown.

    The Markdown is saved next to the PDF (same name, ``.md``) so it can be
    audited and is what the parser reads.

    Args:
        pdf_path: PDF of one category.

    Returns:
        Path of the Markdown file written.

    Raises:
        ImportError: If ``markitdown[pdf]`` is not installed.
    """
    from markitdown import MarkItDown

    markdown_path = pdf_path.with_suffix(".md")
    markdown_path.write_text(MarkItDown().convert(str(pdf_path)).text_content, encoding="utf-8")
    return markdown_path


def read_official_tables(
    tables_dir: Path, year: int, corrections: dict[int, list[TextCorrection]] | None = None
) -> tuple[Championship, list[dict]]:
    """Convert and read every category PDF of one championship.

    Args:
        tables_dir: Folder with one PDF per category (e.g. ``dados/2026``).
        year: Championship year.
        corrections: Manual text fixes by year (see ``corrections.py``).

    Returns:
        The championship (edition, venue, dates) and one record per placing.

    Raises:
        ValueError: If the folder has no PDF, a PDF has no final table, the
            PDFs disagree on edition/venue/dates or a correction was not used.
    """
    pdf_paths = sorted(tables_dir.glob("*.pdf"))
    if not pdf_paths:
        raise ValueError(f"Nenhum PDF em {tables_dir}.")
    year_corrections = (corrections or {}).get(year, [])
    applied: set[TextCorrection] = set()
    championships: list[Championship] = []
    records: list[dict] = []
    for pdf_path in pdf_paths:
        markdown = convert_pdf_to_markdown(pdf_path).read_text(encoding="utf-8")
        markdown, applied_here = apply_corrections(markdown, year_corrections)
        applied |= applied_here
        championship, file_records = parse_official_markdown(markdown, year, pdf_path.name)
        for record in file_records:
            record["observacao"] = _join_notes(
                note_for_line(record["linha_original"], list(applied_here)), record["observacao"]
            )
        championships.append(championship)
        records += file_records
    ensure_all_applied(year, year_corrections, applied)
    return _single_championship(championships), records


def parse_official_markdown(
    markdown: str, year: int, source_name: str
) -> tuple[Championship, list[dict]]:
    """Read the championship header and the final classification of one category.

    Args:
        markdown: Markdown produced by markitdown from one category PDF.
        year: Championship year.
        source_name: File name stored in ``arquivo_fonte``.

    Returns:
        The championship described in the header and one record per placing.

    Raises:
        ValueError: If there is no final-classification table, or its number
            of divisions differs from the division titles found in the file.
    """
    lines = markdown.splitlines()
    rows = _final_table_rows(lines)
    if not rows:
        raise ValueError(f"{source_name}: tabela '{FINAL_TABLE_TITLE}' não encontrada.")
    announced = _announced_divisions(lines)
    records = [
        record
        for category in dict.fromkeys(row.category for row in rows)
        for record in _category_records(
            [row for row in rows if row.category == category],
            announced.get(category, {}),
            year,
            source_name,
        )
    ]
    return _championship_header(markdown, year, _page_count(lines)), records


def _final_table_rows(lines: list[str]) -> list[FinalTableRow]:
    """Rows of every final-classification table, in file order."""
    rows: list[FinalTableRow] = []
    page, category = 1, None
    stat_columns: tuple[str, ...] | None = None
    expecting_header = in_table = False
    for line in lines:
        if PAGE_FOOTER.match(line):
            page, in_table, expecting_header = page + 1, False, False
        elif category_match := CATEGORY_LINE.match(line):
            category = _category_name(category_match["category"])
        elif line.strip() == FINAL_TABLE_TITLE:
            expecting_header = True
        elif not line.lstrip().startswith("|"):
            in_table = False
        elif expecting_header and _cells(line)[0].upper().startswith("POS"):
            stat_columns, expecting_header, in_table = _header_columns(_cells(line)), False, True
        elif in_table and category and stat_columns:
            row = _table_row(line, category, page, stat_columns)
            rows += [row] if row else []
    return rows


def _cells(line: str) -> list[str]:
    """Cells of a Markdown table line, without the outer pipes."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _category_name(raw: str) -> str:
    """``SUB-18`` -> ``Sub-18``, using the same rule as the history PDF."""
    section = parse_section_title(raw.upper())
    return section.category if section else raw.strip().capitalize()


def _header_columns(cells: list[str]) -> tuple[str, ...]:
    """Statistic columns after ``ATLETA`` (``PG J V E D GP GC SG``), without ``IA%``."""
    labels = " ".join(cells).split()
    after_athlete = labels[[label.upper() for label in labels].index("ATLETA") + 1 :]
    return tuple(STAT_COLUMNS.get(label.upper(), label.lower()) for label in after_athlete
                 if not label.endswith("%"))


def _table_row(
    line: str, category: str, page: int, stat_columns: tuple[str, ...]
) -> FinalTableRow | None:
    """Split a table line into the ``POS.`` label and the ``DIV. ATLETA numbers`` body."""
    if TABLE_SEPARATOR.match(line):
        return None
    cells = [cell for cell in _cells(line) if cell]
    if len(cells) < 2:
        return None
    body = PERCENTAGE.sub("", " ".join(cells[1:]))
    division_position = DIVISION_POSITION.match(body)
    parsed = parse_ranking_line(body, list(stat_columns)) if division_position else None
    if not parsed:
        return None
    return FinalTableRow(
        category=category,
        page=page,
        overall_label=cells[0],
        division_position=int(division_position["position"]),
        parsed=parsed,
        original_line=" ".join(" ".join(cells).split()),
    )


def _announced_divisions(lines: list[str]) -> dict[str, dict[int, str]]:
    """Division titles printed in the knockout pages, by category and number.

    Example: ``| ADULTO - 3ª DIVISÃO | ...`` -> ``{"Adulto": {3: "ADULTO - 3ª DIVISÃO"}}``.
    """
    announced: dict[str, dict[int, str]] = {}
    for line in lines:
        for cell in _cells(line) if line.lstrip().startswith("|") else [line.strip()]:
            section = parse_section_title(cell)
            number = re.match(r"^(\d)ª Divisão$", section.division) if section else None
            if number:
                announced.setdefault(section.category, {})[int(number[1])] = section.title
    return announced


def _category_records(
    rows: list[FinalTableRow], announced: dict[int, str], year: int, source_name: str
) -> list[dict]:
    """Records of one category: divisions split where ``DIV.`` restarts at 1º."""
    divisions = _split_divisions(rows)
    if announced and sorted(announced) != list(range(1, len(divisions) + 1)):
        raise ValueError(
            f"{source_name}: {len(divisions)} divisões na classificação final, mas os títulos "
            f"do arquivo citam {sorted(announced)}."
        )
    records: list[dict] = []
    offset = 0
    for number, division_rows in enumerate(divisions, start=1):
        division, title = _division_name(number, len(divisions), announced, rows[0].category)
        records += [
            _record(row, division, title, offset, year, source_name) for row in division_rows
        ]
        offset += len(division_rows)
    return _realign_shifted_columns(records)


def _split_divisions(rows: list[FinalTableRow]) -> list[list[FinalTableRow]]:
    divisions: list[list[FinalTableRow]] = []
    for row in rows:
        if row.division_position == 1 or not divisions:
            divisions.append([])
        divisions[-1].append(row)
    return divisions


def _division_name(
    number: int, total: int, announced: dict[int, str], category: str
) -> tuple[str, str]:
    """``(divisao, secao_original)`` of the ``number``-th block of the table."""
    if number in announced:
        return f"{number}ª Divisão", announced[number]
    if total == 1:
        return SINGLE_DIVISION, f"{category.upper()} - {FINAL_TABLE_TITLE}"
    return f"{number}ª Divisão", f"{category.upper()} - {number}ª Divisão"


def _record(
    row: FinalTableRow, division: str, title: str, offset: int, year: int, source_name: str
) -> dict:
    parsed = row.parsed
    return {
        "ano": year,
        "categoria": row.category,
        "divisao": division,
        "secao_original": title,
        "pagina_pdf": row.page,
        "posicao": row.division_position,
        "posicao_geral": _overall_position(row, offset),
        "botonista": parsed.botonista,
        "apelido": parsed.apelido,
        "clube": parsed.clube,
        "cidade_botonista": parsed.cidade_botonista,
        "uf_botonista": parsed.uf_botonista,
        "wo": parsed.wo,
        "linha_original": row.original_line,
        "alerta": parsed.alerta,
        "observacao": None,
        "arquivo_fonte": source_name,
        **parsed.stats,
    }


def _overall_position(row: FinalTableRow, offset: int) -> int | None:
    """``POS.``: printed number, or (``Campeão``/``Vice``) the place after the divisions above."""
    label = row.overall_label.strip().upper()
    if label in TOP_OF_DIVISION:
        return offset + TOP_OF_DIVISION[label]
    number = OVERALL_POSITION.match(label)
    return int(number["position"]) if number else None


def _realign_shifted_columns(records: list[dict]) -> list[dict]:
    """Fix a table whose numbers sit one column to the right of their labels.

    The 2026 Sub-18 table prints ``PG J V E D GP GC SG`` over
    ``23 35 14 11 2 1 68 36``: read as labelled, no row closes (J=35 but
    V+E+D=27), while shifted one column (PG=35, J=14, V=11, E=2, D=1,
    GP=68, GC=36) every row does. The shift is applied only when it makes
    every row of the category consistent and none was consistent as printed.
    """
    columns = _stat_columns_in_order(records)
    if not columns or not all(_has_all(record, columns) for record in records):
        return records
    shifted = [dict(zip(columns[:-1], [record[c] for c in columns][1:])) for record in records]
    as_printed = [{column: record[column] for column in columns} for record in records]
    if any(map(_closes, as_printed)) or not all(map(_closes, shifted)):
        return records
    return [
        {
            **{key: value for key, value in record.items() if key not in columns},
            **stats,
            "observacao": _join_notes(record["observacao"], SHIFTED_COLUMNS_NOTE),
        }
        for record, stats in zip(records, shifted)
    ]


def _stat_columns_in_order(records: list[dict]) -> list[str]:
    known = set(STAT_COLUMNS.values())
    return [key for key in records[0] if key in known] if records else []


def _has_all(record: dict, columns: list[str]) -> bool:
    return all(record.get(column) is not None for column in columns)


def _closes(stats: dict) -> bool:
    """True when the games and points add up: J = V+E+D and PG = 3V+E."""
    needed = ("jogos", "vitorias", "empates", "derrotas", "pontos")
    if not all(stats.get(column) is not None for column in needed):
        return False
    wins, draws = stats["vitorias"], stats["empates"]
    return stats["jogos"] == wins + draws + stats["derrotas"] and stats["pontos"] == 3 * wins + draws


def _join_notes(*notes: str | None) -> str | None:
    return "; ".join(note for note in notes if note) or None


def _page_count(lines: list[str]) -> int:
    return sum(1 for line in lines if PAGE_FOOTER.match(line))


def _championship_header(markdown: str, year: int, pages: int) -> Championship:
    """Edition, venue and dates from the page headers (``36º CAMPEONATO ...``, ``CAMPINAS/SP``)."""
    edition = EDITION.search(markdown)
    city, uf = _venue(markdown)
    first_day, last_day = _dates(markdown, year)
    return Championship(
        year=year,
        edition=int(edition["edition"]) if edition else None,
        city=city,
        uf=uf,
        first_page=1,
        last_page=max(pages, 1),
        start_date=first_day,
        end_date=last_day,
    )


def _venue(markdown: str) -> tuple[str | None, str | None]:
    for line in markdown.splitlines():
        for cell in _cells(line):
            match = VENUE.match(cell)
            if match:
                return _title_case(match["city"]), match["uf"]
    return None, None


def _title_case(text: str) -> str:
    """``SÃO JOSÉ DOS CAMPOS`` -> ``São José dos Campos``."""
    words = text.lower().split()
    return " ".join(
        word if index and word in LOWERCASE_PARTICLES else word.capitalize()
        for index, word in enumerate(words)
    )


def _dates(markdown: str, year: int) -> tuple[date | None, date | None]:
    """``18 A 21 ABRIL`` or ``30 DE MAIO A 2 DE JUNHO`` -> first and last day."""
    match = DATE_RANGE.search(markdown)
    if not match:
        return None, None
    last_month = MONTHS[match["last_month"].upper()]
    first_month = MONTHS[match["first_month"].upper()] if match["first_month"] else last_month
    return date(year, first_month, int(match["first_day"])), date(
        year, last_month, int(match["last_day"])
    )


def _single_championship(championships: list[Championship]) -> Championship:
    """The championship all category files describe; they must agree."""
    described = {replace(c, first_page=1, last_page=1) for c in championships}
    if len(described) != 1:
        raise ValueError(f"Os PDFs descrevem campeonatos diferentes: {sorted(map(str, described))}")
    return described.pop()
