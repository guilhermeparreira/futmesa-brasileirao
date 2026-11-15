"""Give every player a person id that survives name variants and changes of state."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

YOUTH = {"Sub-15", "Sub-18", "Sub-20", "Infantil"}
MASTER = "Master"
ADULT = "Adulto"
UNKNOWN_UF = "xx"
MAX_YOUTH_CAREER_YEARS = 10
MIN_YEARS_FROM_YOUTH_TO_MASTER = 25
MAX_GAP_TO_ADOPT_ROW_WITHOUT_UF = 3
MIN_FULL_NAMES_TO_BE_A_COMMON_FIRST_NAME = 2
MAX_GAP_BETWEEN_STATES_SINGLE_NAME = 4
GENERIC_SINGLE_NAMES = frozenset(
    """ADILSON ADRIANO ALEX ALFREDO ALISSON ANDERSON ANTONIO ARTUR BERNARDO BETO BRUNO CARIOCA
    DIGAO DUDU EDU ELCIO ERICK FLAVINHO GIOVANNI GUGU HENRIQUE HIAGO HUGO IVAN JEAN JULINHO JULIO
    JUNINHO KADU KEVIN LEO LUAN LUCIANO LUQUINHA MARCELINHO MARCO MARCOS MARIO MAURICIO MILTON
    MURILO NETO NILTON OSWALDO PABLO PEDRINHO RONY RUBINHO SANDRO SERGIO TONINHO VELHO VITINHO
    WAGNER WALLACE WASHINGTON WELLINGTON WILL WILLIAM""".split()
)
MAX_GAP_BETWEEN_STATES_FULL_NAME = 8


@dataclass
class Person:
    """Rows of the ranking table believed to be one human being."""

    name_key: str
    rows: list[int] = field(default_factory=list)
    appearances: list[tuple[int, str, str | None]] = field(default_factory=list)

    @property
    def years(self) -> set[int]:
        return {year for year, _, _ in self.appearances}

    @property
    def first_uf(self) -> str | None:
        known = [(year, uf) for year, _, uf in self.appearances if uf]
        return min(known)[1] if known else None

    def add(self, row: int, year: int, category: str, uf: str | None) -> None:
        self.rows.append(row)
        self.appearances.append((year, category, uf))

    def absorb(self, other: "Person") -> None:
        self.rows += other.rows
        self.appearances += other.appearances


def assign_person_ids(rankings: pd.DataFrame, overrides_csv: Path | None = None) -> pd.Series:
    """Person id of every row (``robertinho-pr``, ``alessandro-sp``...).

    People are identified in three steps, always inside one standard name:

    1. Within a state, rows are split when they cannot be one career (Adulto
       and Master in the same year, youth categories more than ten years
       apart, Master less than 25 years after a youth category).
    2. Careers in different states are joined when they never share a year,
       are at most a few years apart, are age-compatible and the name is
       distinctive (two or more words, or a single word that is not a common
       first name). This is what keeps
       ``ROBERTINHO`` one person when he moves from PR to SP while
       ``ALESSANDRO`` of RJ, SC and SP stay apart.
    3. Rows without UF are adopted by the only compatible career within
       three years.

    The id is the name slug plus the state of the first appearance, so it is
    readable and stable; ``-2``, ``-3`` distinguish homonyms of one state.
    ``overrides_csv`` (``botonista_padronizado``, ``uf_botonista``,
    ``id_botonista``) forces the id of a name + state.

    Args:
        rankings: Ranking table with ``botonista_padronizado``.
        overrides_csv: Manual decisions, or ``None``.

    Returns:
        Series of ids aligned with ``rankings`` (missing for unnamed rows).
    """
    name_keys = rankings["botonista_padronizado"].map(_name_key)
    common_first_names = _common_first_names(name_keys.dropna().unique())
    ids = pd.Series(pd.NA, index=rankings.index, dtype="string")
    for name_key, rows in rankings[name_keys.notna()].groupby(name_keys):
        people = _people_with_name(name_key, rows, name_key in common_first_names)
        for person, person_id in zip(people, _ids_for(people)):
            ids.loc[person.rows] = person_id
    return _apply_overrides(ids, rankings, overrides_csv)


def build_people_table(rankings: pd.DataFrame) -> pd.DataFrame:
    """One row per person: display name, states, span and number of appearances."""
    named = rankings[rankings["id_botonista"].notna()]
    return (
        named.groupby("id_botonista")
        .agg(
            botonista=("botonista_padronizado", _most_frequent),
            ufs=("uf_botonista", _unique_in_order),
            categorias=("categoria", _unique_in_order),
            primeiro_ano=("ano", "min"),
            ultimo_ano=("ano", "max"),
            campeonatos=("ano", "nunique"),
            nomes_impressos=("botonista", _unique_in_order),
        )
        .reset_index()
        .astype({"botonista": "string", "ufs": "string", "categorias": "string",
                 "nomes_impressos": "string"})
    )


def _people_with_name(name_key: str, rows: pd.DataFrame, is_common_name: bool) -> list[Person]:
    with_uf = rows[rows["uf_botonista"].notna()]
    people = [
        person
        for _, state_rows in with_uf.groupby("uf_botonista", sort=True)
        for person in _split_into_careers(name_key, state_rows)
    ]
    if not is_common_name:
        people = _join_careers_across_states(people)
    return _adopt_rows_without_uf(name_key, people, rows[rows["uf_botonista"].isna()])


def _split_into_careers(name_key: str, state_rows: pd.DataFrame) -> list[Person]:
    """Greedy split of one state's rows into age-compatible careers."""
    careers: list[Person] = []
    for row in state_rows.sort_values("ano").itertuples():
        appearance = (row.ano, row.categoria, row.uf_botonista)
        career = next((c for c in careers if _compatible(c.appearances + [appearance])), None)
        if career is None:
            career = Person(name_key)
            careers.append(career)
        career.add(row.Index, *appearance)
    return careers


def _join_careers_across_states(people: list[Person]) -> list[Person]:
    """Join careers of different states whenever the choice is unambiguous.

    Two careers are joined when they can be one person and every other
    candidate partner of either one is also compatible with both, so a
    player seen in three states (PE, CE, AL) becomes one person, while a
    career that could belong to two rival homonyms is left alone.
    """
    people = list(people)
    while True:
        pair = next(
            (
                (one, other)
                for one in people
                for other in people
                if one is not other and _is_unambiguous_join(one, other, people)
            ),
            None,
        )
        if pair is None:
            return people
        pair[0].absorb(pair[1])
        people.remove(pair[1])


def _is_unambiguous_join(one: Person, other: Person, people: list[Person]) -> bool:
    if not _can_join(one, other):
        return False
    rivals = [p for p in people if p is not one and p is not other]
    return all(_can_join(one, rival) == _can_join(other, rival) for rival in rivals)


def _can_join(one: Person, other: Person) -> bool:
    """Whether two careers in different states can be the same person."""
    return (
        not (one.years & other.years)
        and _years_apart(one, other) <= _max_gap_between_states(one.name_key)
        and not _returns_to_adult_after_master(one.appearances + other.appearances)
        and _compatible(one.appearances + other.appearances)
    )


def _years_apart(one: Person, other: Person) -> int:
    return min(abs(a - b) for a in one.years for b in other.years)


def _max_gap_between_states(name_key: str) -> int:
    is_full_name = len(name_key.split()) > 1
    return MAX_GAP_BETWEEN_STATES_FULL_NAME if is_full_name else MAX_GAP_BETWEEN_STATES_SINGLE_NAME


def _returns_to_adult_after_master(appearances: list[tuple[int, str, str | None]]) -> bool:
    master = [year for year, category, _ in appearances if category == MASTER]
    adult = [year for year, category, _ in appearances if category == ADULT]
    return bool(master and adult and max(adult) > min(master))


def _adopt_rows_without_uf(name_key: str, people: list[Person], rows: pd.DataFrame) -> list[Person]:
    orphans = Person(name_key)
    for row in rows.sort_values("ano").itertuples():
        appearance = (row.ano, row.categoria, None)
        candidates = [p for p in people if _is_near_and_compatible(p, appearance)]
        target = candidates[0] if len(candidates) == 1 else orphans
        target.add(row.Index, *appearance)
    return people + ([orphans] if orphans.rows else [])


def _is_near_and_compatible(person: Person, appearance: tuple[int, str, None]) -> bool:
    year = appearance[0]
    gap = min(abs(year - other) for other in person.years)
    return (
        gap <= MAX_GAP_TO_ADOPT_ROW_WITHOUT_UF
        and year not in person.years
        and _compatible(person.appearances + [appearance])
    )


def _compatible(appearances: list[tuple[int, str, str | None]]) -> bool:
    """Whether a set of (year, category) could be a single person's career."""
    youth = [year for year, category, _ in appearances if category in YOUTH]
    master = [year for year, category, _ in appearances if category == MASTER]
    adult = [year for year, category, _ in appearances if category == ADULT]
    if set(master) & set(adult):
        return False
    if not youth:
        return True
    if max(youth) - min(youth) > MAX_YOUTH_CAREER_YEARS:
        return False
    if master and min(master) - max(youth) < MIN_YEARS_FROM_YOUTH_TO_MASTER:
        return False
    return not adult or min(adult) >= min(youth) - 1


def _common_first_names(name_keys) -> set[str]:
    """Single words that start several different full names (ANDRE, CARLOS, THIAGO...)."""
    full_names_by_first_word: dict[str, set[str]] = {}
    for name_key in name_keys:
        words = name_key.split()
        if len(words) > 1:
            full_names_by_first_word.setdefault(words[0], set()).add(name_key)
    frequent = {
        first_word
        for first_word, full_names in full_names_by_first_word.items()
        if len(full_names) >= MIN_FULL_NAMES_TO_BE_A_COMMON_FIRST_NAME
    }
    return frequent | GENERIC_SINGLE_NAMES


def _ids_for(people: list[Person]) -> list[str]:
    """``slug-uf`` for each person, numbering homonyms of the same state by debut."""
    ordered = sorted(people, key=lambda person: min(person.years))
    seen: dict[str, int] = {}
    ids: dict[int, str] = {}
    for person in ordered:
        base = f"{_slug(person.name_key)}-{(person.first_uf or UNKNOWN_UF).lower()}"
        seen[base] = seen.get(base, 0) + 1
        ids[id(person)] = base if seen[base] == 1 else f"{base}-{seen[base]}"
    return [ids[id(person)] for person in people]


def _apply_overrides(ids: pd.Series, rankings: pd.DataFrame, overrides_csv: Path | None) -> pd.Series:
    if overrides_csv is None or not overrides_csv.exists():
        return ids
    overrides = pd.read_csv(overrides_csv, dtype="string", keep_default_na=False)
    forced = ids.copy()
    for rule in overrides.itertuples():
        matches = (rankings["botonista_padronizado"].map(_name_key) == _name_key(rule.botonista_padronizado)) & (
            rankings["uf_botonista"].fillna("") == rule.uf_botonista
        )
        forced.loc[matches] = rule.id_botonista
    return forced


def _name_key(name: object) -> object:
    """Accent-free upper-case name used to compare standard names."""
    if not isinstance(name, str):
        return pd.NA
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Za-z0-9]+", " ", ascii_name).upper().split()) or pd.NA


def _slug(name_key: str) -> str:
    return name_key.lower().replace(" ", "-")


def _most_frequent(values: pd.Series) -> str:
    return values.value_counts().index[0]


def _unique_in_order(values: pd.Series) -> str:
    return ", ".join(dict.fromkeys(values.dropna()))
