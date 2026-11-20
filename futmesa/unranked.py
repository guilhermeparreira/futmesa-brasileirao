"""Players the PDF only mentions in a note, without a final position."""

from __future__ import annotations

import csv
from pathlib import Path


def load_unranked_participants(csv_path: Path | None, years: list[int]) -> list[dict]:
    """Read the curated list of participants that have no published position.

    Example: the 1996 note listing who else played the Master category
    besides the champion and runner-up. Rows come out in the same shape as
    the extracted ranking rows, with ``posicao`` empty.

    Args:
        csv_path: ``dados/participantes_sem_classificacao.csv`` or ``None``.
        years: Championship years being processed; other years are skipped.

    Returns:
        One record per participant of the requested years.
    """
    if csv_path is None or not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        return [
            _record(row, csv_path.name)
            for row in csv.DictReader(handle)
            if int(row["ano"]) in years
        ]


def _record(row: dict, source_name: str) -> dict:
    return {
        "ano": int(row["ano"]),
        "categoria": row["categoria"],
        "divisao": row["divisao"],
        "secao_original": row["secao_original"],
        "pagina_pdf": None,
        "posicao": None,
        "botonista": row["botonista"],
        "apelido": row["apelido"] or None,
        "clube": None,
        "cidade_botonista": None,
        "uf_botonista": row["uf_botonista"] or None,
        "wo": False,
        "linha_original": None,
        "alerta": None,
        "observacao": row["observacao"],
        "arquivo_fonte": source_name,
    }
