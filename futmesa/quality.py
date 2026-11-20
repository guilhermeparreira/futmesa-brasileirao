"""Data-quality checks on the ranking table.

Each check returns the offending rows with a ``verificacao`` label and a
human-readable ``detalhe``. Inconsistent statistics usually come from typos
in the source PDF; they are reported, never silently changed.
"""

from __future__ import annotations

import pandas as pd

from .official_tables import SHIFTED_COLUMNS_NOTE
from .transform import PRIMARY_KEY, UNREAD_STATS_NOTE

ISSUE_COLUMNS = ["verificacao", "ano", "secao_original", "posicao", "botonista", "detalhe"]


def run_quality_checks(rankings: pd.DataFrame, expected_years: list[int]) -> pd.DataFrame:
    """Run every check and stack the findings in one table.

    Args:
        rankings: Final ranking table.
        expected_years: Years listed in the PDF index (or requested).

    Returns:
        One row per finding, with :data:`ISSUE_COLUMNS`.
    """
    findings = [
        _years_without_rows(rankings, expected_years),
        _duplicated_keys(rankings),
        _position_gaps(rankings),
        _overall_position_gaps(rankings),
        _same_player_twice(rankings),
        _missing_state(rankings),
        _unread_statistics(rankings),
        _shifted_columns(rankings),
        _games_mismatch(rankings),
        _goal_difference_mismatch(rankings),
        _points_mismatch(rankings),
    ]
    non_empty = [finding for finding in findings if not finding.empty]
    if not non_empty:
        return pd.DataFrame(columns=ISSUE_COLUMNS)
    return pd.concat(non_empty, ignore_index=True)[ISSUE_COLUMNS]


def summarise(issues: pd.DataFrame) -> pd.Series:
    """Number of findings per check."""
    return issues["verificacao"].value_counts().sort_index()


def _label(rows: pd.DataFrame, check: str, detail: pd.Series | str) -> pd.DataFrame:
    labelled = rows.assign(verificacao=check, detalhe=detail)
    return labelled.reindex(columns=ISSUE_COLUMNS)


def _years_without_rows(rankings: pd.DataFrame, expected_years: list[int]) -> pd.DataFrame:
    missing = sorted(set(expected_years) - set(rankings["ano"].dropna().astype(int)))
    rows = pd.DataFrame({"ano": missing})
    return _label(rows, "ano_sem_classificacao", "ano listado no índice sem nenhuma linha extraída")


def _duplicated_keys(rankings: pd.DataFrame) -> pd.DataFrame:
    ranked = rankings[rankings["posicao"].notna()]
    duplicated = ranked[ranked.duplicated(PRIMARY_KEY, keep=False)]
    return _label(duplicated, "chave_duplicada", f"chave {PRIMARY_KEY} repetida")


def _same_player_twice(rankings: pd.DataFrame) -> pd.DataFrame:
    """Same standard name and UF twice in a year/category: a de-para rule merged two people."""
    ranked = rankings[rankings["posicao"].notna() & rankings["id_botonista"].notna()]
    person = ["ano", "categoria", "id_botonista"]
    repeated = ranked[ranked.duplicated(person, keep=False)]
    detail = "'" + repeated["botonista_padronizado"] + "' aparece mais de uma vez na categoria"
    return _label(repeated, "botonista_repetido_no_ano", detail)


def _position_gaps(rankings: pd.DataFrame) -> pd.DataFrame:
    gaps = [
        {
            "ano": year,
            "secao_original": section["secao_original"].iloc[0],
            "detalhe": f"posições {positions}",
        }
        for (year, _, _), section in rankings.groupby(["ano", "categoria", "divisao"], sort=False)
        if (positions := sorted(section["posicao"].dropna().astype(int)))
        != list(range(1, len(positions) + 1))
    ]
    rows = pd.DataFrame(gaps, columns=["ano", "secao_original", "detalhe"])
    return rows.assign(verificacao="posicoes_descontinuas").reindex(columns=ISSUE_COLUMNS)


def _overall_position_gaps(rankings: pd.DataFrame) -> pd.DataFrame:
    """``posicao_geral`` must run 1..N in every category that has it."""
    gaps = [
        {
            "ano": year,
            "secao_original": category,
            "detalhe": f"posições gerais {positions}",
        }
        for (year, category), rows in rankings.groupby(["ano", "categoria"], sort=False)
        if (positions := sorted(rows["posicao_geral"].dropna().astype(int)))
        and positions != list(range(1, len(positions) + 1))
    ]
    rows = pd.DataFrame(gaps, columns=["ano", "secao_original", "detalhe"])
    return rows.assign(verificacao="posicao_geral_descontinua").reindex(columns=ISSUE_COLUMNS)


def _shifted_columns(rankings: pd.DataFrame) -> pd.DataFrame:
    shifted = rankings[rankings["observacao"].fillna("").str.contains(SHIFTED_COLUMNS_NOTE, regex=False)]
    return _label(shifted, "colunas_deslocadas", SHIFTED_COLUMNS_NOTE)


def _missing_state(rankings: pd.DataFrame) -> pd.DataFrame:
    missing = rankings[rankings["uf_botonista"].isna() & rankings["botonista"].notna()]
    return _label(missing, "uf_ausente", "UF do botonista não informada no PDF")


def _unread_statistics(rankings: pd.DataFrame) -> pd.DataFrame:
    unread = rankings[rankings["observacao"].fillna("").str.startswith(UNREAD_STATS_NOTE)]
    return _label(unread, "estatisticas_nao_lidas", unread["observacao"])


def _games_mismatch(rankings: pd.DataFrame) -> pd.DataFrame:
    total = rankings["vitorias"] + rankings["empates"] + rankings["derrotas"]
    wrong = rankings[(total != rankings["jogos"]).fillna(False)]
    detail = (
        "J=" + wrong["jogos"].astype("string") + " mas V+E+D="
        + total[wrong.index].astype("string")
    )
    return _label(wrong, "jogos_diferente_de_v_e_d", detail)


def _goal_difference_mismatch(rankings: pd.DataFrame) -> pd.DataFrame:
    difference = rankings["gols_pro"] - rankings["gols_contra"]
    wrong = rankings[(difference != rankings["saldo_gols"]).fillna(False)]
    detail = (
        "SG=" + wrong["saldo_gols"].astype("string") + " mas GF-GC="
        + difference[wrong.index].astype("string")
    )
    return _label(wrong, "saldo_diferente_de_gf_menos_gc", detail)


def _points_mismatch(rankings: pd.DataFrame) -> pd.DataFrame:
    expected = 3 * rankings["vitorias"] + rankings["empates"]
    wrong = rankings[(expected != rankings["pontos"]).fillna(False)]
    detail = (
        "PG=" + wrong["pontos"].astype("string") + " mas 3V+E="
        + expected[wrong.index].astype("string")
    )
    return _label(wrong, "pontos_diferente_de_3v_mais_e", detail)
