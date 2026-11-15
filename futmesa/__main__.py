"""Command line: ``python -m futmesa --pdf HISTORICO.pdf [--anos 2026]``."""

from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import (
    DEFAULT_CORRECTIONS,
    DEFAULT_METADATA,
    SingleYearPdf,
    describe,
    run_pipeline,
)


def parse_arguments() -> argparse.Namespace:
    """Read the command-line options."""
    parser = argparse.ArgumentParser(
        prog="python -m futmesa",
        description="Constrói/atualiza a base do Campeonato Brasileiro Individual 12 Toques.",
    )
    parser.add_argument("--pdf", type=Path, required=True, help="PDF do histórico")
    parser.add_argument("--saida", type=Path, default=Path("saida"), help="pasta da base")
    parser.add_argument(
        "--anos",
        type=int,
        nargs="+",
        help="extrai só estes anos e os substitui na base existente (os demais são mantidos)",
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
    single_year_pdf = (
        SingleYearPdf(arguments.ano_unico, arguments.cidade, arguments.uf)
        if arguments.ano_unico
        else None
    )
    result = run_pipeline(
        pdf_path=arguments.pdf,
        output_dir=arguments.saida,
        years=arguments.anos,
        single_year_pdf=single_year_pdf,
        metadata_csv=arguments.campeonatos,
        corrections_csv=arguments.correcoes,
    )
    print(describe(result))


if __name__ == "__main__":
    main()
