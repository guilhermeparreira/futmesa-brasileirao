"""Command line.

``python -m futmesa --tabelas dados/2026``      adds a year from the official tables (default)
``python -m futmesa --pdf HISTORICO.pdf``        rebuilds the base from the history PDF
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import (
    DEFAULT_CORRECTIONS,
    DEFAULT_METADATA,
    PipelineResult,
    ReferenceFiles,
    SingleYearPdf,
    describe,
    run_official_tables,
    run_pipeline,
)


def parse_arguments() -> argparse.Namespace:
    """Read the command-line options."""
    parser = argparse.ArgumentParser(
        prog="python -m futmesa",
        description="Constrói/atualiza a base do Campeonato Brasileiro Individual 12 Toques.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--tabelas",
        type=Path,
        help="pasta com os PDFs oficiais de um campeonato, um por categoria (ex.: dados/2026); "
        "é o modo padrão de atualização",
    )
    source.add_argument("--pdf", type=Path, help="PDF do histórico")
    parser.add_argument("--saida", type=Path, default=Path("saida"), help="pasta da base")
    parser.add_argument(
        "--ano", type=int, help="ano do campeonato (com --tabelas; padrão: nome da pasta)"
    )
    parser.add_argument(
        "--anos",
        type=int,
        nargs="+",
        help="com --pdf: extrai só estes anos e os substitui na base (os demais são mantidos)",
    )
    parser.add_argument("--ano-unico", type=int, help="PDF sem índice com um único campeonato")
    parser.add_argument("--cidade", help="cidade-sede (com --ano-unico)")
    parser.add_argument("--uf", help="UF da sede (com --ano-unico)")
    parser.add_argument("--campeonatos", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--correcoes", type=Path, default=DEFAULT_CORRECTIONS)
    return parser.parse_args()


def main() -> None:
    """Run the pipeline with the command-line options and print a summary."""
    arguments = parse_arguments()
    reference = ReferenceFiles(
        metadata_csv=arguments.campeonatos, corrections_csv=arguments.correcoes
    )
    result = (
        _run_official_tables(arguments, reference)
        if arguments.tabelas
        else _run_history_pdf(arguments, reference)
    )
    print(describe(result))


def _run_official_tables(arguments: argparse.Namespace, reference: ReferenceFiles) -> PipelineResult:
    year = arguments.ano or _year_from_folder(arguments.tabelas)
    return run_official_tables(arguments.tabelas, arguments.saida, year, reference)


def _run_history_pdf(arguments: argparse.Namespace, reference: ReferenceFiles) -> PipelineResult:
    single_year_pdf = (
        SingleYearPdf(arguments.ano_unico, arguments.cidade, arguments.uf)
        if arguments.ano_unico
        else None
    )
    return run_pipeline(
        pdf_path=arguments.pdf,
        output_dir=arguments.saida,
        years=arguments.anos,
        single_year_pdf=single_year_pdf,
        reference=reference,
    )


def _year_from_folder(folder: Path) -> int:
    name = folder.resolve().name
    if not (name.isdigit() and len(name) == 4):
        raise SystemExit(f"Não deu para tirar o ano do nome da pasta '{name}': informe --ano.")
    return int(name)


if __name__ == "__main__":
    main()
