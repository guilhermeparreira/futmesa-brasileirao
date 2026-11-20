"""End-to-end pipeline: source PDFs -> typed tables -> Parquet + Excel.

Two sources feed the same base:

* the official result tables of one championship (one PDF per category,
  read through markitdown) — the default way to add a new year;
* the championship-history PDF — used to rebuild the whole base.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .corrections import load_corrections
from .export import PEOPLE_PARQUET, merge_years, read_base, save_base
from .extraction import extract_championship
from .official_tables import read_official_tables
from .people import assign_person_ids, build_people_table
from .pdf_text import Championship, find_championships, read_pages
from .quality import run_quality_checks, summarise
from .transform import build_championships_table, build_ranking_table, fill_overall_positions
from .unranked import load_unranked_participants

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "dados"
DEFAULT_METADATA = DATA_DIR / "campeonatos.csv"
DEFAULT_CORRECTIONS = DATA_DIR / "correcoes_texto.csv"
DEFAULT_UNRANKED = DATA_DIR / "participantes_sem_classificacao.csv"
DEFAULT_PLAYER_DEPARA = DATA_DIR / "depara_botonistas.csv"
DEFAULT_CLUB_DEPARA = DATA_DIR / "depara_clubes.csv"
DEFAULT_PEOPLE_OVERRIDES = DATA_DIR / "pessoas_manual.csv"


@dataclass(frozen=True)
class SingleYearPdf:
    """Identifies a PDF that holds only one championship and has no index."""

    year: int
    city: str | None = None
    uf: str | None = None


@dataclass(frozen=True)
class ReferenceFiles:
    """Curated CSVs in ``dados/`` that complete and correct the source PDFs."""

    metadata_csv: Path | None = DEFAULT_METADATA
    corrections_csv: Path | None = DEFAULT_CORRECTIONS
    unranked_csv: Path | None = DEFAULT_UNRANKED
    player_depara_csv: Path | None = DEFAULT_PLAYER_DEPARA
    club_depara_csv: Path | None = DEFAULT_CLUB_DEPARA
    people_overrides_csv: Path | None = DEFAULT_PEOPLE_OVERRIDES


@dataclass(frozen=True)
class PipelineResult:
    """Tables produced by a run and the files written."""

    rankings: pd.DataFrame
    championships: pd.DataFrame
    issues: pd.DataFrame
    files: list[Path]


def run_official_tables(
    tables_dir: Path,
    output_dir: Path,
    year: int,
    reference: ReferenceFiles = ReferenceFiles(),
) -> PipelineResult:
    """Add (or replace) one championship read from its official result tables.

    Every PDF in ``tables_dir`` (one per category) is converted to Markdown
    with markitdown and its final classification is read. The year replaces
    the same year in the base saved in ``output_dir``; the other years are kept.

    Args:
        tables_dir: Folder with the category PDFs (e.g. ``dados/2026``).
        output_dir: Folder where the base is read from and written to.
        year: Championship year.
        reference: Curated CSVs (metadata, corrections, de-para, ids).

    Returns:
        The final tables and the paths of the files written.
    """
    corrections = load_corrections(reference.corrections_csv)
    championship, records = read_official_tables(tables_dir, year, corrections)
    return _build_and_save(records, [championship], output_dir, reference, merge=True)


def run_pipeline(
    pdf_path: Path,
    output_dir: Path,
    years: list[int] | None = None,
    single_year_pdf: SingleYearPdf | None = None,
    reference: ReferenceFiles = ReferenceFiles(),
) -> PipelineResult:
    """Extract the rankings from the history PDF and save the base.

    Without ``years`` the whole base is rebuilt from the PDF. With ``years``
    only those championships are extracted and they replace the same years
    in the base already saved in ``output_dir`` (the other years are kept).

    Args:
        pdf_path: Championship-history PDF (or a PDF with a single edition).
        output_dir: Folder where the base is read from and written to.
        years: Years to extract and replace; ``None`` rebuilds everything.
        single_year_pdf: Use when the PDF has no index and holds one edition.
        reference: Curated CSVs (metadata, corrections, de-para, ids).

    Returns:
        The final tables and the paths of the files written.

    Raises:
        ValueError: If a requested year is not in the PDF, or the PDF has no
            index and ``single_year_pdf`` was not given.
    """
    pages = read_pages(pdf_path)
    championships = _select_championships(pages, years, single_year_pdf)
    corrections = load_corrections(reference.corrections_csv)
    records = [
        {**record, "arquivo_fonte": pdf_path.name}
        for championship in championships
        for record in extract_championship(championship, pages, corrections)
    ]
    merge = bool(years or single_year_pdf)
    return _build_and_save(records, championships, output_dir, reference, merge)


def _build_and_save(
    records: list[dict],
    championships: list[Championship],
    output_dir: Path,
    reference: ReferenceFiles,
    merge: bool,
) -> PipelineResult:
    """Common tail of both sources: type, merge, identify people, check and save."""
    years = [c.year for c in championships]
    records = records + load_unranked_participants(reference.unranked_csv, years)
    championship_table = build_championships_table(championships, reference.metadata_csv)
    championship_table = championship_table[
        championship_table["ano"].isin(years)
    ].reset_index(drop=True)
    rankings = build_ranking_table(
        records, championship_table, reference.player_depara_csv, reference.club_depara_csv
    )
    if merge:
        rankings, championship_table = _merge_with_saved_base(
            output_dir, rankings, championship_table
        )
    rankings = fill_overall_positions(rankings)
    rankings["id_botonista"] = assign_person_ids(rankings, reference.people_overrides_csv)
    issues = run_quality_checks(rankings, championship_table["ano"].astype(int).tolist())
    depara_sheets = _read_depara_sheets(reference.player_depara_csv, reference.club_depara_csv)
    people = build_people_table(rankings)
    extra_sheets = {"botonistas": people, **depara_sheets}
    files = save_base(output_dir, rankings, championship_table, issues, extra_sheets)
    people.to_parquet(output_dir / PEOPLE_PARQUET, index=False)
    files.append(output_dir / PEOPLE_PARQUET)
    return PipelineResult(rankings, championship_table, issues, files)


def _read_depara_sheets(player_csv: Path | None, club_csv: Path | None) -> dict[str, pd.DataFrame]:
    """De-para files as workbook sheets, skipping the ones that do not exist."""
    files = {"depara_botonistas": player_csv, "depara_clubes": club_csv}
    return {
        name: pd.read_csv(path, dtype="string", keep_default_na=False)
        for name, path in files.items()
        if path is not None and path.exists()
    }


def _select_championships(
    pages: list[str], years: list[int] | None, single_year_pdf: SingleYearPdf | None
) -> list[Championship]:
    if single_year_pdf:
        return [
            Championship(
                year=single_year_pdf.year,
                edition=None,
                city=single_year_pdf.city,
                uf=single_year_pdf.uf,
                first_page=1,
                last_page=len(pages),
            )
        ]
    championships = find_championships(pages)
    if not championships:
        raise ValueError("O PDF não tem índice: informe --ano-unico (e, se quiser, --cidade/--uf).")
    if not years:
        return championships
    missing = sorted(set(years) - {c.year for c in championships})
    if missing:
        raise ValueError(f"Ano(s) {missing} não encontrado(s) no índice do PDF.")
    return [c for c in championships if c.year in years]


def _merge_with_saved_base(
    output_dir: Path, rankings: pd.DataFrame, championships: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    saved = read_base(output_dir)
    if saved is None:
        return rankings, championships
    saved_rankings, saved_championships = saved
    return (
        merge_years(saved_rankings, rankings),
        merge_years(saved_championships, championships),
    )


def describe(result: PipelineResult) -> str:
    """Short text report of a run, for the command line."""
    rankings = result.rankings
    per_year = rankings.groupby("ano").size()
    lines = [
        f"{len(rankings)} classificações | {rankings['ano'].nunique()} campeonatos "
        f"({per_year.index.min()}–{per_year.index.max()})",
        "Verificações de qualidade:",
        *(f"  {check}: {count}" for check, count in summarise(result.issues).items()),
        "Arquivos:",
        *(f"  {path}" for path in result.files),
    ]
    return "\n".join(lines)
