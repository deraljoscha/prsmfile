"""Helpers shared by the typed readers."""
from __future__ import annotations

from typing import Callable

from ..report import Cell, Section
from ..values import entries, label, num


def parameters_section(rows: list[tuple[str, Cell]]) -> Section:
    """The "Parameters" section; rows whose value is None are dropped."""
    return Section(
        "Parameters", ["Name", "Value"], [[k, v] for k, v in rows if v is not None]
    )


_DESC_COLUMNS = ["Column", "n", "Mean", "SD", "SEM", "Minimum", "Median", "Maximum"]
_DESC_FIELDS = ["n", "mean", "sd", "meanSE", "minimum", "median", "maximum"]
DIFFERENCES = "differences"


def _desc_row(name: str, value) -> list[Cell]:
    v = value if isinstance(value, dict) else {}
    return [name] + [num(v.get(f)) for f in _DESC_FIELDS]


def descriptive_section(stats: dict) -> Section:
    """Descriptive statistics by position; the literal key `differences` goes last."""
    stats = stats if isinstance(stats, dict) else {}
    rest = {k: v for k, v in stats.items() if k != DIFFERENCES}
    rows = [_desc_row(label(id_), value) for id_, value in entries(rest)]
    diff = stats.get(DIFFERENCES)
    if isinstance(diff, dict):
        rows.append(_desc_row("Differences", diff.get("value")))
    return Section("Descriptive statistics", list(_DESC_COLUMNS), rows)


def _tol(*xs: float) -> float:
    return max(1e-12, 1e-9 * max(abs(x) for x in xs))


def derive_direction(d, a1, a2, l1, l2, warn: Callable[[str], None]) -> str | None:
    """Name the sign of a stored difference d by comparing it with a2 - a1 and a1 - a2."""
    if d is None or a1 is None or a2 is None or not l1 or not l2:
        return None
    e_fwd = abs(d - (a2 - a1))
    e_rev = abs(d - (a1 - a2))
    tol = _tol(a1, a2, d)
    if e_fwd > tol and e_rev > tol:
        warn("Direction of difference could not be verified.")
        return None
    if e_rev < e_fwd:
        return f"{l1} - {l2}"
    return f"{l2} - {l1}"  # forward, or an exact tie
