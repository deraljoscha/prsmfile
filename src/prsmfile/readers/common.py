"""Helpers shared by the typed readers."""
from __future__ import annotations

from typing import Callable

from ..report import Cell, Section
from ..values import PValue, ci, entries, label, num


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


def _dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def anova_columns(variation: bool, epsilon: bool = False) -> list[str]:
    """variation=False: ... "R squared"; variation=True: "% of total" instead.
    epsilon=True appends "GG epsilon" (Greenhouse-Geisser, stored as ggEpsilon)."""
    if variation:
        cols = ["Source", "SS", "df", "MS", "% of total", "F", "DFn", "DFd", "P"]
    else:
        cols = ["Source", "SS", "df", "MS", "F", "DFn", "DFd", "P", "R squared"]
    return cols + ["GG epsilon"] if epsilon else cols


def anova_row(source: str, node: dict, variation: bool, epsilon: bool = False) -> list[Cell]:
    """One ANOVA table row; every field via .get and num. `variation` is Prism's percent of total."""
    node = _dict(node)
    f = _dict(node.get("fTest"))
    head = [source, num(node.get("ss")), num(node.get("df")), num(node.get("ms"))]
    test = [num(f.get("f")), num(f.get("dfNumerator")), num(f.get("dfDenominator")),
            PValue.from_obj(f.get("pValue"))]
    row = head + [num(node.get("variation"))] + test if variation else head + test + [num(node.get("r2"))]
    return row + [num(node.get("ggEpsilon"))] if epsilon else row


COMPARISON_COLUMNS = ["Comparison", "Mean 1", "n 1", "Mean 2", "n 2", "Mean diff", "SE", "CI lower", "CI upper", "CI level",
                      "Statistic", "df", "P adjusted", "P individual"]


def comparisons_section(mc: dict) -> Section:
    """Pairwise multiple comparisons. Columns: Comparison, Mean 1, n 1, Mean 2, n 2 (sample1 and
    sample2 mean and n), Mean diff (stored sample1 - sample2), SE, CI lower/upper/level, Statistic,
    df, P adjusted, P individual."""
    mc = _dict(mc)
    method = mc.get("method")
    title = f"Multiple comparisons ({method})" if isinstance(method, str) and method.strip() \
        else "Multiple comparisons"
    rows: list[list[Cell]] = []
    for id1, inner in entries(mc.get("tests")):
        for id2, value in entries(inner):
            if not isinstance(value, dict):
                continue
            lo, hi, level = ci(value.get("meansDifferenceCI"))
            s1 = _dict(_dict(value.get("sample1")).get("value"))
            s2 = _dict(_dict(value.get("sample2")).get("value"))
            rows.append([
                f"{label(id1)} vs {label(id2)}",
                num(s1.get("mean")), num(s1.get("n")), num(s2.get("mean")), num(s2.get("n")),
                num(value.get("meansDifference")), num(value.get("meansDifferenceSE")),
                lo, hi, level, num(value.get("statistic")), num(value.get("df")),
                PValue.from_obj(value.get("pValueAdjusted")),
                PValue.from_obj(value.get("pValueIndividual")),
            ])
    return Section(title, list(COMPARISON_COLUMNS), rows)


def family_rows(mc: dict) -> list[tuple[str, Cell]]:
    """Parameters rows from multipleComparisons.familyCount and comparisonPerFamilyCount."""
    mc = _dict(mc)
    return [("Comparison families", num(mc.get("familyCount"))),
            ("Comparisons per family", num(mc.get("comparisonPerFamilyCount")))]


def letters_section(cld) -> Section | None:
    """Compact letter display: one row per sample, Group = the stored letters."""
    rows: list[list[Cell]] = []
    for id_, value in entries(_dict(_dict(cld).get("samples"))):
        if isinstance(value, str) and value.strip():
            rows.append([label(id_), value])
    return Section("Compact letter display", ["Cell", "Group"], rows) if rows else None
