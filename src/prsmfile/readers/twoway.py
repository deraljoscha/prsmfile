"""TWO_WAY_ANOVA: ordinary, repeated-measures GLM and mixed model REML (docs/format.md 2.4)."""
from __future__ import annotations

from ..report import Cell, Section
from ..values import PValue, num
from . import register
from .common import (
    anova_columns,
    anova_row,
    comparisons_section,
    data_summary_section,
    family_rows,
    letters_leftovers,
    letters_section,
    anova_shapes,
    comparison_shapes,
    other_rows,
    test_shapes,
    other_section,
    parameters_section,
)

_MODELS = ("ordinaryAnovaModel", "repeatedMeasuresGlmAnovaModel", "repeatedMeasuresRemlAnovaModel")
_GLM = "repeatedMeasuresGlmAnovaModel"
_REML = "repeatedMeasuresRemlAnovaModel"
_ANOVA_ROWS = (
    ("rowFactorVsColFactor", "Interaction"),
    ("rowFactor", "Row factor"),
    ("colFactor", "Column factor"),
    ("matchedFactor", "Subjects"),
    ("matchedFactorVsRowFactor", "Subjects x Row factor"),
    ("matchedFactorVsColFactor", "Subjects x Column factor"),
    ("residual", "Residual"),
    ("total", "Total"),
)
_FIXED_ROWS = (("rowFactor", "Row factor"), ("colFactor", "Column factor"),
               ("rowFactorVsColFactor", "Interaction"))
_RANDOM_NAMES = {"matchedFactor": "Subject", "residual": "Residual"}


def _dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def _str(x) -> str | None:
    return x if isinstance(x, str) and x.strip() else None


def _bool(x) -> bool | None:
    return x if isinstance(x, bool) else None


def _anova_section(table: dict) -> Section | None:
    known = {k for k, _ in _ANOVA_ROWS}
    eps = any("ggEpsilon" in v for v in table.values() if isinstance(v, dict))
    rows = [anova_row(name, table[key], True, eps) for key, name in _ANOVA_ROWS if key in table]
    rows += [anova_row(str(k), v, True, eps) for k, v in table.items() if k not in known]
    return Section("ANOVA", anova_columns(True, eps), rows) if rows else None


def _fixed_section(fixed: dict) -> Section | None:
    rows = []
    for key, name in _FIXED_ROWS:
        if key not in fixed:
            continue
        f = _dict(_dict(fixed[key]).get("fTest"))
        rows.append([name, num(f.get("f")), num(f.get("dfNumerator")), num(f.get("dfDenominator")),
                     PValue.from_obj(f.get("pValue"))])
    return Section("Fixed effects", ["Source", "F", "DFn", "DFd", "P"], rows) if rows else None


def _random_section(random: dict) -> Section | None:
    keys = [k for k in _RANDOM_NAMES if k in random] + [k for k in random if k not in _RANDOM_NAMES]
    rows = []
    for k in keys:
        v = _dict(random[k])
        rows.append([_RANDOM_NAMES.get(k, str(k)), num(v.get("sd")), num(v.get("variance"))])
    return Section("Random effects", ["Source", "SD", "Variance"], rows) if rows else None


def _matching_section(test) -> Section | None:
    t = _dict(test)
    row = [num(t.get("chiSquared")), num(t.get("df")), PValue.from_obj(t.get("pValue"))]
    if all(c is None or (isinstance(c, PValue) and c.value is None) for c in row):
        return None
    return Section("Matching", ["Chi-square", "df", "P"], [row])


@register("TWO_WAY_ANOVA")
def read_twoway(pf, a, warn):
    results = a.results
    found = [k for k in _MODELS if k in results]
    if not found:
        raise KeyError("two-way ANOVA model")
    key = found[0]
    model = results[key]
    if not isinstance(model, dict):
        raise KeyError(key)
    params = _dict(a.parameters)
    rm = _dict(params.get("repeatedMeasures"))
    post = _dict(_dict(params.get("postTests")).get("pairwiseTests"))
    names = _dict(model.get("factorNames"))
    mc = _dict(model.get("multipleComparisons"))
    sections: list[Section] = []
    parameters = parameters_section([
        ("Design", _str(params.get("experimentalDesign"))),
        ("Repeated measures method", _str(rm.get("method"))),
        ("Assume sphericity", _bool(rm.get("assumeSphericity"))),
        ("Post test design", _str(post.get("meansDesignType"))),
        ("Method", _str(mc.get("method"))),
        *family_rows(mc),
        ("Row factor", _str(names.get("rowFactor"))),
        ("Column factor", _str(names.get("colFactor"))),
    ])
    if parameters.rows:
        sections.append(parameters)
    if key == _REML:
        parts = [_fixed_section(_dict(model.get("fixedEffects"))),
                 _random_section(_dict(model.get("randomEffects"))),
                 _matching_section(model.get("matchingTest")) if "matchingTest" in model else None]
    else:
        table = _dict(model.get("anovaTable"))
        parts = [_anova_section(table)]
        if key == _GLM and "matchedFactor" not in table:
            warn("Subjects row only in Prism's rendered table (view ANOVA results).")
    sections.extend(s for s in parts if s is not None)
    comparisons = comparisons_section(mc)
    if comparisons.rows:
        sections.append(comparisons)
    letters = letters_section(model.get("compactLetterDisplay"))
    if letters is not None:
        sections.append(letters)
    summary = data_summary_section(model.get("dataSummary"))
    if summary is not None:
        sections.append(summary)
    consumed = comparison_shapes() + test_shapes(("factorNames",), "rowFactor", "colFactor")
    consumed += [("compactLetterDisplay",), ("dataSummary",)]
    if key == _REML:
        for k, _ in _FIXED_ROWS:
            consumed += test_shapes(("fixedEffects", k, "fTest"), "f", "dfNumerator", "dfDenominator",
                                    "pValue")
        for k in _dict(model.get("randomEffects")):
            consumed += test_shapes(("randomEffects", k), "sd", "variance")
        consumed += test_shapes(("matchingTest",), "chiSquared", "df", "pValue")
    else:
        table = _dict(model.get("anovaTable"))
        consumed += anova_shapes(table, list(table), True)
    other = other_rows(results, (key,))
    other += other_rows(model, consumed)
    other += letters_leftovers(model.get("compactLetterDisplay"))
    extra = other_section(other)
    if extra is not None:
        sections.append(extra)
    return sections
