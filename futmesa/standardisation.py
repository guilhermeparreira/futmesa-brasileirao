"""Apply the reviewed de-para files to player and club names."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

APPLY = "sim"
ANY_UF = ""


def standardise_players(rankings: pd.DataFrame, depara_csv: Path | None) -> pd.Series:
    """Standard name of each row's player.

    A de-para row matches on ``botonista_chave`` and, when ``de_uf`` is
    filled, on the player's UF too. Only rows marked ``aplicar = sim`` are
    used; a specific-UF rule wins over an any-UF rule. Unmatched players
    keep the printed name.

    Args:
        rankings: Table with ``botonista``, ``botonista_chave``, ``uf_botonista``.
        depara_csv: ``dados/depara_botonistas.csv`` or ``None``.

    Returns:
        Series aligned with ``rankings``.
    """
    rules = _approved_rules(depara_csv)
    if rules.empty:
        return rankings["botonista"]
    by_key_and_uf = rules.set_index(["de_botonista_chave", "de_uf"])["para_botonista"].to_dict()
    standard = [
        by_key_and_uf.get((key, uf if isinstance(uf, str) else None))
        or by_key_and_uf.get((key, ANY_UF))
        or name
        for key, uf, name in zip(
            rankings["botonista_chave"], rankings["uf_botonista"], rankings["botonista"]
        )
    ]
    return pd.Series(standard, index=rankings.index, dtype="string")


def standardise_clubs(clubs: pd.Series, depara_csv: Path | None) -> pd.Series:
    """Standard name of each club; clubs without an approved rule are kept."""
    rules = _approved_rules(depara_csv)
    if rules.empty:
        return clubs
    return clubs.replace(rules.set_index("de_clube")["para_clube"].to_dict())


def _approved_rules(depara_csv: Path | None) -> pd.DataFrame:
    if depara_csv is None or not depara_csv.exists():
        return pd.DataFrame()
    rules = pd.read_csv(depara_csv, dtype="string", keep_default_na=False)
    return rules[rules["aplicar"].str.lower() == APPLY]
