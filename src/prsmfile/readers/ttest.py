"""T_TESTS_AND_NONPARAMETRIC: t tests, Mann-Whitney and Wilcoxon (docs/format.md 2.2)."""
from __future__ import annotations

from ..values import PValue, ci, entries, int_idx, label, letter, num
from . import register
from .common import (
    DIFFERENCES,
    derive_direction,
    descriptive_section,
    desc_shapes,
    letters_leftovers,
    letters_section,
    other_rows,
    other_section,
    parameters_section,
)
from ..report import Section

_MODELS = {
    "WELCH_T_TEST": "welchTTestModel",
    "UNPAIRED_T_TEST": "unpairedTTestModel",
    "PAIRED_T_TEST": "pairedTTestModel",
    "MANN_WHITNEY_TEST": "mannWhitneyTestModel",
    "WILCOXON_TEST": "wilcoxonTestModel",
}
_TAILS = {"P_VALUE_TWO_TAILED": "two", "P_VALUE_ONE_TAILED": "one"}
_TEST_COLUMNS = ["Test", "Statistic name", "Statistic", "df", "DFn", "DFd", "P"]
_P = ("pValue",)
_READ_VARIANCE = [("varianceTest", n) for n in ("f", "dfNumerator", "dfDenominator", "pValue")]
_READ_DIFF_MEANS = [("differenceOfMeans", n) for n in (
    "n1", "mean1", "n2", "mean2", "difference", "stdErrorOfDifference",
    "confidenceIntervalOfDifference", "rSquared")]
# Leaves each model reader reads (shapes below the model dict); everything else of the model is
# listed under "Other values".
_TEST_KEYS = {
    "welchTTestModel": [("welchTTest", n) for n in ("t", "df", "pValue")] + _READ_VARIANCE + _READ_DIFF_MEANS,
    "unpairedTTestModel": [("unpairedTTest", n) for n in ("t", "df", "pValue")] + _READ_VARIANCE
    + _READ_DIFF_MEANS,
    "pairedTTestModel": [("pairedTTest", n) for n in ("t", "df", "pValue")] + [
        ("meanOfDifferences", n) for n in ("mean", "confidenceIntervalOfDifferences",
                                           "stdDeviationOfDifferences", "stdErrorOfDifferences",
                                           "rSquared")],
    "mannWhitneyTestModel": [("mannWhitneyTest", n) for n in ("U", "pValue")] + [
        ("differenceOfMedians", n) for n in ("n1", "n2", "median1", "median2",
                                             "hodgesLehmannDifference", "actualDifference")],
    "wilcoxonTestModel": [("wilcoxonTest", n) for n in ("signedRanksSum", "pValue")] + [
        ("medianOfDifferences", "median")],
}
_VARIANCE = "F test to compare variances"


def _dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def _model_key(design, results: dict) -> str:
    if design in _MODELS:
        return _MODELS[design]
    if design is None:  # no design stored: use the one model key present
        found = [k for k in _MODELS.values() if k in results]
        if len(found) == 1:
            return found[0]
    raise KeyError(design)


def _p(obj):
    return PValue.from_obj(obj)


def _labelled(stats: dict, name: str):
    """(label, value dict) of a named descriptive entry, or (None, {})."""
    e = _dict(_dict(stats).get(name))
    id_ = e.get("id")
    return (label(id_) or None if isinstance(id_, (dict, list)) else None), _dict(e.get("value"))


def _raw_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _identity(id_, text: str):
    """Column identity of a stored id: the column letter, else the formatted label."""
    col = id_.get("col") if isinstance(id_, dict) else None
    idx = int_idx(_dict(col).get("idx"))
    return letter(idx) if idx is not None and idx >= 0 else text


def _match_label(stats: dict, n, key: str, val) -> list[tuple[str, object]]:
    """(label, identity) of the non-`differences` entries whose (n, key) equals (n, val):
    the raw stored values, exact =="""
    if not (_raw_num(n) and _raw_num(val)):
        return []
    out = []
    for id_, value in entries({k: v for k, v in _dict(stats).items() if k != DIFFERENCES}):
        v = _dict(value)
        if _raw_num(v.get("n")) and _raw_num(v.get(key)) and v["n"] == n and v[key] == val:
            text = label(id_)
            out.append((text, _identity(id_, text)))
    return out


def _input_label(ltr: str, title: str | None) -> str:
    """Formatted exactly like values.label: a blank title gives the bare letter."""
    return f"{ltr}:{title}" if title else ltr


def _groups(a, stats, n1, v1, n2, v2, key, warn):
    """Group labels per group: a unique non-empty exact (n, value) match, else the
    input at that position (with a warning), else None. Columns are compared by identity
    (the letter), never by the formatted label."""
    m1, m2 = _match_label(stats, n1, key, v1), _match_label(stats, n2, key, v2)
    ok1, ok2 = len(m1) == 1 and bool(m1[0][0]), len(m2) == 1 and bool(m2[0][0])
    if ok1 and ok2 and m1[0][1] == m2[0][1]:
        ok1 = ok2 = False
    out: list[str | None] = [m1[0][0] if ok1 else None, m2[0][0] if ok2 else None]
    ids: list[object] = [m1[0][1] if ok1 else None, m2[0][1] if ok2 else None]
    inferred = False
    usable = len(a.inputs) >= 2
    titles = list(a.input_titles) + [None] * (len(a.inputs) - len(a.input_titles))
    cands = [(ltr, _input_label(ltr, titles[i])) for i, (ltr, _t) in enumerate(a.inputs)]
    for i, ok in enumerate((ok1, ok2)):
        if ok:
            continue
        inferred = True
        if not usable:
            continue
        other = ids[1 - i]
        pick = cands[i] if i < len(cands) else None
        if pick is not None and other is not None and pick[0] == other:
            rest = [c for c in cands if c[0] != other]
            pick = rest[0] if len(rest) == 1 else None
        out[i] = pick[1] if pick is not None else None
        ids[i] = pick[0] if pick is not None else None
    if inferred and usable:
        warn("Group labels inferred from input order.")
    return out[0], out[1]


def _variance_row(model: dict, warn):
    vt = model.get("varianceTest")
    if not isinstance(vt, dict):
        return None
    f = num(vt.get("f"))
    if f is None:
        warn(f"{_VARIANCE}: {vt.get('status')}")
        return [_VARIANCE, "F", None, None, None, None, None]
    return [_VARIANCE, "F", f, None, num(vt.get("dfNumerator")), num(vt.get("dfDenominator")),
            _p(vt.get("pValue"))]


def _effect_two_means(a, model, stats, warn) -> Section:
    d = _dict(model.get("differenceOfMeans"))
    n1, n2 = d.get("n1"), d.get("n2")
    g1, g2 = _groups(a, stats, n1, d.get("mean1"), n2, d.get("mean2"), "mean", warn)
    m1, m2 = num(d.get("mean1")), num(d.get("mean2"))
    diff = num(d.get("difference"))
    lo, hi, level = ci(d.get("confidenceIntervalOfDifference"))
    return Section(
        "Effect",
        ["Group 1", "Mean 1", "n 1", "Group 2", "Mean 2", "n 2", "Difference", "Difference is",
         "SE", "CI lower", "CI upper", "CI level", "R squared"],
        [[g1, m1, num(n1), g2, m2, num(n2), diff,
          derive_direction(diff, m1, m2, g1, g2, warn),
          num(d.get("stdErrorOfDifference")), lo, hi, level, num(d.get("rSquared"))]],
    )


def _effect_paired(model, stats, warn) -> Section:
    d = _dict(model.get("meanOfDifferences"))
    l1, s1 = _labelled(stats, "sample1")
    l2, s2 = _labelled(stats, "sample2")
    mean = num(d.get("mean"))
    lo, hi, level = ci(d.get("confidenceIntervalOfDifferences"))
    return Section(
        "Effect",
        ["Mean of differences", "Difference is", "SD", "SE", "CI lower", "CI upper", "CI level",
         "R squared"],
        [[mean, derive_direction(mean, num(s2.get("mean")), num(s1.get("mean")), l2, l1, warn),
          num(d.get("stdDeviationOfDifferences")), num(d.get("stdErrorOfDifferences")),
          lo, hi, level, num(d.get("rSquared"))]],
    )


def _effect_mann_whitney(a, model, stats, warn) -> Section:
    d = _dict(model.get("differenceOfMedians"))
    n1, n2 = d.get("n1"), d.get("n2")
    g1, g2 = _groups(a, stats, n1, d.get("median1"), n2, d.get("median2"), "median", warn)
    m1, m2 = num(d.get("median1")), num(d.get("median2"))
    return Section(
        "Effect",
        ["Group 1", "Median 1", "n 1", "Group 2", "Median 2", "n 2",
         "Hodges-Lehmann difference", "Difference is"],
        [[g1, m1, num(n1), g2, m2, num(n2), num(d.get("hodgesLehmannDifference")),
          derive_direction(num(d.get("actualDifference")), m1, m2, g1, g2, warn)]],
    )


def _effect_wilcoxon(model, stats, warn) -> Section:
    median = num(_dict(model.get("medianOfDifferences")).get("median"))
    diff = _dict(_dict(stats).get(DIFFERENCES))
    ids = diff.get("id")
    direction = None
    if isinstance(ids, list) and len(ids) >= 2:
        l1, l2 = label(ids[0]), label(ids[1])
        dm = num(_dict(diff.get("value")).get("mean"))
        s1 = num(_dict(_dict(_dict(stats).get("sample1")).get("value")).get("mean"))
        s2 = num(_dict(_dict(_dict(stats).get("sample2")).get("value")).get("mean"))
        # the label is only shown when the stored mean difference confirms its sign
        direction = derive_direction(dm, s2, s1, l2, l1, warn)
    return Section("Effect", ["Median of differences", "Difference is"], [[median, direction]])


def _has_number(row) -> bool:
    return any(_raw_num(c) or isinstance(c, PValue) and c.value is not None for c in row)


def _test_row(block, name, stat, stat_key):
    b = _dict(block)
    row = [name, stat, num(b.get(stat_key)), num(b.get("df")), None, None, _p(b.get("pValue"))]
    return row if _has_number(row[2:]) else None


@register("T_TESTS_AND_NONPARAMETRIC")
def read_ttest(pf, a, warn):
    results = a.results
    params = _dict(a.parameters)
    design = params.get("experimentalDesign")
    design = design if isinstance(design, str) else None
    key = _model_key(design, results)
    model = results[key]
    if not isinstance(model, dict):
        raise KeyError(key)
    stats = results.get("descriptiveStatistics")
    opts = _dict(params.get("options"))
    swap = opts.get("swapDirection")
    tails = opts.get("pValueTailType")
    parameters = parameters_section([
        ("Design", design),
        ("Tails", _TAILS.get(tails) if isinstance(tails, str) else None),
        ("Swap direction", swap if isinstance(swap, bool) else None),
    ])
    test_rows = []
    effect = None
    if key in ("welchTTestModel", "unpairedTTestModel"):
        welch = key == "welchTTestModel"
        row = _test_row(model.get("welchTTest" if welch else "unpairedTTest"),
                        "Welch's t test" if welch else "Unpaired t test", "t", "t")
        if row:
            test_rows.append(row)
        vrow = _variance_row(model, warn)
        if vrow is not None:
            test_rows.append(vrow)
        if _dict(model.get("differenceOfMeans")):
            effect = _effect_two_means(a, model, stats, warn)
    elif key == "pairedTTestModel":
        row = _test_row(model.get("pairedTTest"), "Paired t test", "t", "t")
        if row:
            test_rows.append(row)
        if _dict(model.get("meanOfDifferences")):
            effect = _effect_paired(model, stats, warn)
    elif key == "mannWhitneyTestModel":
        b = _dict(model.get("mannWhitneyTest"))
        row = ["Mann-Whitney test", "U", num(b.get("U")), None, None, None, _p(b.get("pValue"))]
        if _has_number(row[2:]):
            test_rows.append(row)
        if _dict(model.get("differenceOfMedians")):
            effect = _effect_mann_whitney(a, model, stats, warn)
    else:
        b = _dict(model.get("wilcoxonTest"))
        row = ["Wilcoxon signed-rank test", "W", num(b.get("signedRanksSum")), None, None, None,
               _p(b.get("pValue"))]
        if _has_number(row[2:]):
            test_rows.append(row)
        effect = _effect_wilcoxon(model, stats, warn)
    sections = []
    if parameters.rows:
        sections.append(parameters)
    if test_rows:
        sections.append(Section("Test", list(_TEST_COLUMNS), test_rows))
    if effect is not None and (_has_number(effect.rows[0]) or (key == "wilcoxonTestModel" and effect.rows[0][1] is not None)):
        sections.append(effect)
    desc = descriptive_section(stats)
    if desc.rows:
        sections.append(desc)
    letters = letters_section(results.get("compactLetterDisplay"))
    if letters is not None:
        sections.append(letters)
    other = other_rows(results, desc_shapes(("descriptiveStatistics",))
                       + [("compactLetterDisplay",), (key,)])
    other += other_rows(model, _TEST_KEYS[key])
    other += letters_leftovers(results.get("compactLetterDisplay"))
    extra = other_section(other)
    if extra is not None:
        sections.append(extra)
    return sections
