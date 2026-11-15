"""End-to-end pipeline: PDF -> typed tables -> Parquet + Excel."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .corrections import load_corrections
from .export import PEOPLE_PARQUET, merge_years, read_base, save_base
from .extraction import extract_championship
from .people import assign_person_ids, build_people_table
from .pdf_text import Championship, find_championships, read_pages
from .quality import run_quality_checks, summarise
from .transform import build_championships_table, build_ranking_table
from .unranked import load_unranked_participants

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_METADATA = PROJECT_DIR / "dados" / "campeonatos.csv"
DEFAULT_CORRECTIONS = PROJECT_DIR / "dados" / "correcoes_texto.csv"
DEFAULT_UNRANKED = PROJECT_DIR / "dados" / "participantes_sem_classificacao.csv"
DEFAULT_PLAYER_DEPARA = PROJECT_DIR / "dados" / "depara_botonistas.csv"
DEFAULT_CLUB_DEPARA = PROJECT_DIR / "dados" / "depara_clubes.csv"
DEFAULT_PEOPLE_OVERRIDES = PROJECT_DIR / "dados" / "pessoas_manual.csv"


@dataclass(frozen=True)
class SingleYearPdf:
    """Identifies a PDF that holds only one championship and has no index."""

    year: int
    city: str | None = None
    uf: str | None = None


@dataclass(frozen=True)
class PipelineResult:
    """Tables produced by a run and the files written."""

    rankings: pd.DataFrame
    championships: pd.DataFrame
    issues: pd.DataFrame
    files: list[Path]


def run_pipeline(
    pdf_path: Path,
    output_dir: Path,
    years: list[int] | None = None,
    single_year_pdf: SingleYearPdf | None = None,
    metadata_csv: Path | None = DEFAULT_METADATA,
    corrections_csv: Path | None = DEFAULT_CORRECTIONS,
    unranked_csv: Path | None = DEFAULT_UNRANKED,
    player_depara_csv: Path | None = DEFAULT_PLAYER_DEPARA,
    club_depara_csv: Path | None = DEFAULT_CLUB_DEPARA,
    people_overrides_csv: Path | None = DEFAULT_PEOPLE_OVERRIDES,
) -> PipelineResult:
    """Extract the rankings from the PDF and save the base.

    Without ``years`` the whole base is rebuilt from the PDF. With ``years``
    only those championships are extracted and they replace the same years
    in the base already saved in ``output_dir`` (the other years are kept),
    which is how a new championship is appended each year.

    Args:
        pdf_path: Championship-history PDF (or a PDF with a single edition).
        output_dir: Folder where the base is read from and written to.
        years: Years to extract and replace; ``None`` rebuilds everything.
        single_year_pdf: Use when the PDF has no index and holds one edition.
        metadata_csv: Curated venue/dates per edition.
        corrections_csv: Manual fixes for typos in the PDF text.
        unranked_csv: Participants cited without a final position.
        player_depara_csv: Reviewed de-para of player names.
        club_depara_csv: Reviewed de-para of club names.
        people_overrides_csv: Manual person ids for a name + state.

    Returns:
        The final tables and the paths of the files written.

    Raises:
        ValueError: If a requested year is not in the PDF, or the PDF has no
            index and ``single_year_pdf`` was not given.
    """
    pages = read_pages(pdf_path)
    championships = _select_championships(pages, years, single_year_pdf)
    corrections = load_corrections(corrections_csv)
    records = [
        record
        for championship in championships
        for record in extract_championship(championship, pages, corrections)
    ]
    records += load_unranked_participants(unranked_csv, [c.year for c in championships])
    championship_table = build_championships_table(championships, metadata_csv)
    championship_table = championship_table[
        championship_table["ano"].isin([c.year for c in championships])
    ].reset_index(drop=True)
    rankings = build_ranking_table(
        records, championship_table, player_depara_csv, club_depara_csv
    )
    if years or single_year_pdf:
        rankings, championship_table = _merge_with_saved_base(
            output_dir, rankings, championship_table
        )
    rankings["id_botonista"] = assign_person_ids(rankings, people_overrides_csv)
    issues = run_quality_checks(rankings, championship_table["ano"].astype(int).tolist())
    depara_sheets = _read_depara_sheets(player_depara_csv, club_depara_csv)
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
