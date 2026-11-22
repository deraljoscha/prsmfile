"""ONE_WAY_ANOVA: ordinary and repeated-measures GLM (docs/format.md 2.3)."""
from __future__ import annotations

from ..report import Section
from ..values import PValue, num
from . import register
from .common import (
    anova_columns,
    anova_row,
    comparisons_section,
    data_summary_section,
    descriptive_section,
    letters_leftovers,
    letters_section,
    anova_shapes,
    comparison_shapes,
    desc_shapes,
    other_rows,
    test_shapes,
    other_section,
    parameters_section,
)

_MODELS = ("ordinaryAnovaModel", "repeatedMeasuresGlmAnovaModel")
_ASSUMPTION_COLUMNS = ["Test", "Statistic", "DFn", "DFd", "P", "Status"]


def _dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def _str(x) -> str | None:
    return x if isinstance(x, str) and x.strip() else None


def _assumption_rows(model: dict) -> list[list]:
    rows = []
    bf = model.get("brownForsytheTest")
    if isinstance(bf, dict):
        rows.append(["Brown-Forsythe test", num(bf.get("f")), num(bf.get("dfNumerator")),
                     num(bf.get("dfDenominator")), PValue.from_obj(bf.get("pValue")),
                     _str(bf.get("status"))])
    bt = model.get("bartlettTest")
    if isinstance(bt, dict):
        rows.append(["Bartlett's test", num(bt.get("statistic")), None, None,
                     PValue.from_obj(bt.get("pValue")), _str(bt.get("status"))])
    return rows


def _matching_test(test) -> Section | None:
    t = _dict(test)
    row = [num(t.get("f")), num(t.get("dfNumerator")), num(t.get("dfDenominator")),
           PValue.from_obj(t.get("pValue"))]
    if all(c is None or (isinstance(c, PValue) and c.value is None) for c in row):
        return None
    return Section("Matching test", ["F", "DFn", "DFd", "P"], [row])


def _per_family(mc: dict):
    """One-way results store comparisonCount; familyCount and comparisonPerFamilyCount are
    only read when present (not seen in the corpus)."""
    v = num(mc.get("comparisonPerFamilyCount"))
    return v if v is not None else num(mc.get("comparisonCount"))


@register("ONE_WAY_ANOVA")
def read_oneway(pf, a, warn):
    results = a.results
    found = [k for k in _MODELS if k in results]
    if not found:
        raise KeyError("one-way ANOVA model")
    model = results[found[0]]
    if not isinstance(model, dict):
        raise KeyError(found[0])
    params = _dict(a.parameters)
    pairwise = _dict(_dict(_dict(params.get("postTests")).get("pairwiseTests")).get("pairwiseDesign"))
    mc = _dict(model.get("multipleComparisons"))
    sections = []
    parameters = parameters_section([
        ("Design", _str(params.get("experimentalDesign"))),
        ("Post test design", _str(pairwise.get("type"))),
        ("Method", _str(mc.get("method"))),
        ("Comparison families", num(mc.get("familyCount"))),
        ("Comparisons per family", _per_family(mc)),
    ])
    if parameters.rows:
        sections.append(parameters)
    table = _dict(model.get("anovaTable"))
    if table:
        eps = any("ggEpsilon" in v for v in table.values() if isinstance(v, dict))
        rows = [anova_row("Treatment", table["colFactor"], False, eps)] if "colFactor" in table else []
        if "matchedFactor" in table:
            rows.append(anova_row("Matching", table["matchedFactor"], False, eps))
        for key, name in (("residual", "Residual"), ("total", "Total")):
            if key in table:
                rows.append(anova_row(name, table[key], False, eps))
        if rows:
            sections.append(Section("ANOVA", anova_columns(False, eps), rows))
    matching = _matching_test(model.get("matchingTest"))
    if matching is not None:
        sections.append(matching)
    assumptions = _assumption_rows(model)
    if assumptions:
        sections.append(Section("Assumption tests", list(_ASSUMPTION_COLUMNS), assumptions))
    comparisons = comparisons_section(mc)
    if comparisons.rows:
        sections.append(comparisons)
    letters = letters_section(model.get("compactLetterDisplay"))
    if letters is not None:
        sections.append(letters)
    desc = descriptive_section(results.get("descriptiveStatistics"))
    if desc.rows:
        sections.append(desc)
    summary = data_summary_section(model.get("dataSummary"))
    if summary is not None:
        sections.append(summary)
    other = other_rows(results, desc_shapes(("descriptiveStatistics",)) + [(found[0],)])
    read = (anova_shapes(table, ("colFactor", "matchedFactor", "residual", "total"), False)
            + test_shapes(("brownForsytheTest",), "f", "dfNumerator", "dfDenominator", "pValue", "status")
            + test_shapes(("bartlettTest",), "statistic", "pValue", "status")
            + test_shapes(("matchingTest",), "f", "dfNumerator", "dfDenominator", "pValue")
            + comparison_shapes() + [("compactLetterDisplay",), ("dataSummary",)])
    other += other_rows(model, read)
    other += letters_leftovers(model.get("compactLetterDisplay"))
    extra = other_section(other)
    if extra is not None:
        sections.append(extra)
    return sections
