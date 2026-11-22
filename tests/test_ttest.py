import json

import prsmfile
from prsmfile import PValue, read_analysis
from tests.builder import PrismBuilder
from tests.helpers import assert_sections_well_formed

CLS = "T_TESTS_AND_NONPARAMETRIC"
OK = {"error": "VALID", "warning": []}
DIRW = "Direction of difference could not be verified."


def pobj(v, sig=True):
    return {"value": v, "level": 0.05, "isSignificant": sig, "state": "P_VALUE_EQUAL"}


def colid(idx, title, uid=None):
    c = {"uid": uid or f"U{idx}", "idx": idx}
    if title is not None:
        c["title"] = title
    return {"col": c}


def stats(n, mean, **kw):
    v = {"n": n, "mean": mean, "sd": 1.0, "meanSE": 0.5, "minimum": 0.0, "median": mean, "maximum": 9.0}
    v.update(kw)
    return v


def desc(*items):
    return {name: {"id": id_, "value": value} for name, id_, value in items}


def run(tmp_path, results, params=None, inputs=(("A", "Ctl"), ("B", "Drug")), **kw):
    design = (params or {}).get("experimentalDesign", "WELCH_T_TEST")
    params = {"experimentalDesign": design, "options": {"pValueTailType": "P_VALUE_TWO_TAILED",
              "swapDirection": True}, **(params or {})}
    b = PrismBuilder()
    b.add_analysis("T", CLS, params, results, inputs=inputs, **kw)
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        r = read_analysis(pf, pf.analyses()[0])
    assert_sections_well_formed(r)
    return r


def sec(r, title):
    (s,) = [s for s in r.sections if s.title == title]
    return s


def welch(n1, m1, n2, m2, d, model="welchTTestModel", test="welchTTest", variance=None):
    inner = {test: {"status": "VALID", "t": 2.5, "df": 17.0, "pValue": pobj(0.02)},
             "differenceOfMeans": {"n1": n1, "mean1": m1, "n2": n2, "mean2": m2, "difference": d,
                                   "stdErrorOfDifference": 0.4,
                                   "confidenceIntervalOfDifference": {"lower": 1.0, "upper": 2.0, "level": 95.0},
                                   "rSquared": 0.3}}
    if variance is not None:
        inner["varianceTest"] = variance
    return {"status": OK, model: inner}


def welch_results(m1, m2, d, ids=((0, "Ctl"), (1, "Drug")), **kw):
    """Group 1 is input A (idx 0); Prism lists sample1 as the SECOND column."""
    (i1, t1), (i2, t2) = ids
    res = welch(10, m1, 12, m2, d, **kw)
    res["descriptiveStatistics"] = desc(
        ("sample1", colid(i2, t2), stats(12, m2)),
        ("sample2", colid(i1, t1), stats(10, m1)),
    )
    return res


def test_welch_labels_and_direction(tmp_path):
    r = run(tmp_path, welch_results(5.0, 7.0, 2.0, variance={
        "status": "VALID", "f": 1.5, "dfNumerator": 11.0, "dfDenominator": 9.0, "pValue": pobj(0.4, False)}))
    assert r.kind == "structured" and r.warnings == []
    assert [s.title for s in r.sections] == ["Parameters", "Test", "Effect", "Descriptive statistics"]
    assert sec(r, "Parameters").rows == [["Design", "WELCH_T_TEST"], ["Tails", "two"], ["Swap direction", True]]
    t = sec(r, "Test")
    assert t.columns == ["Test", "Statistic name", "Statistic", "df", "DFn", "DFd", "P"]
    assert t.rows[0][:6] == ["Welch's t test", "t", 2.5, 17.0, None, None] and isinstance(t.rows[0][6], PValue)
    assert t.rows[1][:6] == ["F test to compare variances", "F", 1.5, None, 11.0, 9.0]
    e = sec(r, "Effect")
    assert e.columns == ["Group 1", "Mean 1", "n 1", "Group 2", "Mean 2", "n 2", "Difference",
                         "Difference is", "SE", "CI lower", "CI upper", "CI level", "R squared"]
    assert e.rows == [["A:Ctl", 5.0, 10, "B:Drug", 7.0, 12, 2.0, "B:Drug - A:Ctl", 0.4, 1.0, 2.0, 95.0, 0.3]]
    d = sec(r, "Descriptive statistics")
    assert d.columns == ["Column", "n", "Mean", "SD", "SEM", "Minimum", "Median", "Maximum"]
    assert [row[0] for row in d.rows] == ["A:Ctl", "B:Drug"]
    json.dumps(r.to_dict(), allow_nan=False)


def test_unpaired_uses_unpaired_model(tmp_path):
    res = welch_results(5.0, 7.0, 2.0, model="unpairedTTestModel", test="unpairedTTest")
    r = run(tmp_path, res, {"experimentalDesign": "UNPAIRED_T_TEST"})
    assert r.kind == "structured"
    assert sec(r, "Test").rows[0][0] == "Unpaired t test"
    assert sec(r, "Effect").rows[0][7] == "B:Drug - A:Ctl"


def test_same_title_groups(tmp_path):
    res = welch_results(5.0, 7.0, 2.0, ids=((2, "Ethanol"), (10, "Ethanol")))
    r = run(tmp_path, res, inputs=(("C", "Ethanol"), ("K", "Ethanol")))
    e = sec(r, "Effect").rows[0]
    assert e[0] == "C:Ethanol" and e[3] == "K:Ethanol" and e[7] == "K:Ethanol - C:Ethanol"
    assert r.warnings == []


def test_direction_reverse(tmp_path):
    r = run(tmp_path, welch_results(5.0, 7.0, -2.0))
    assert sec(r, "Effect").rows[0][7] == "A:Ctl - B:Drug"


def test_direction_near_zero(tmp_path):
    r = run(tmp_path, welch_results(1.0, 1.0 - 4e-13, 4e-13))
    assert sec(r, "Effect").rows[0][7] == "A:Ctl - B:Drug"
    assert DIRW not in r.warnings


def test_direction_unverifiable(tmp_path):
    r = run(tmp_path, welch_results(5.0, 7.0, 99.0))
    assert sec(r, "Effect").rows[0][7] is None
    assert DIRW in r.warnings


def test_derive_direction_unit():
    from prsmfile.readers.common import derive_direction
    w = []
    assert derive_direction(0.0, 1.0, 1.0, "a", "b", w.append) == "b - a"  # exact tie
    assert derive_direction(None, 1.0, 2.0, "a", "b", w.append) is None
    assert derive_direction(1.0, None, 2.0, "a", "b", w.append) is None
    assert w == []
    assert derive_direction(5.0, 1.0, 2.0, "a", "b", w.append) is None and w == [DIRW]


def test_groups_inferred_from_input_order(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    res["descriptiveStatistics"]["sample1"]["value"]["mean"] = 7.5  # no exact (n, mean) match
    r = run(tmp_path, res)
    e = sec(r, "Effect").rows[0]
    assert e[0] == "A:Ctl" and e[3] == "B:Drug" and e[7] == "B:Drug - A:Ctl"
    assert "Group labels inferred from input order." in r.warnings


def test_groups_unknown_without_inputs(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    del res["descriptiveStatistics"]
    r = run(tmp_path, res, inputs=())
    e = sec(r, "Effect").rows[0]
    assert e[0] is None and e[3] is None and e[7] is None
    assert [s.title for s in r.sections] == ["Parameters", "Test", "Effect"]


def paired_results(mean, s1=("B", 1, "x", 8.0), s2=("A", 0, "y", 5.0)):
    return {"status": OK,
            "pairedTTestModel": {
                "pairedTTest": {"status": "VALID", "t": 3.0, "df": 9.0, "pValue": pobj(0.01)},
                "meanOfDifferences": {"mean": mean, "stdDeviationOfDifferences": 1.1,
                                      "stdErrorOfDifferences": 0.3,
                                      "confidenceIntervalOfDifferences": {"lower": 2.0, "upper": 4.0, "level": 95.0},
                                      "rSquared": 0.5}},
            "descriptiveStatistics": desc(
                ("sample1", colid(s1[1], s1[2]), stats(10, s1[3])),
                ("sample2", colid(s2[1], s2[2]), stats(10, s2[3])),
                ("differences", [colid(s1[1], s1[2]), colid(s2[1], s2[2])], stats(10, mean))),
            }


def test_paired(tmp_path):
    r = run(tmp_path, paired_results(3.0), {"experimentalDesign": "PAIRED_T_TEST"})
    assert r.kind == "structured" and r.warnings == []
    assert sec(r, "Test").rows[0][:4] == ["Paired t test", "t", 3.0, 9.0]
    e = sec(r, "Effect")
    assert e.columns == ["Mean of differences", "Difference is", "SD", "SE", "CI lower", "CI upper",
                         "CI level", "R squared"]
    assert e.rows == [[3.0, "B:x - A:y", 1.1, 0.3, 2.0, 4.0, 95.0, 0.5]]
    d = sec(r, "Descriptive statistics")
    assert [row[0] for row in d.rows] == ["A:y", "B:x", "Differences"]  # differences sorts last


def mw_results(med_g1=10.0, med_g2=14.0, actual=4.0):
    return {"status": OK,
            "mannWhitneyTestModel": {
                "mannWhitneyTest": {"status": "VALID", "U": 12.5, "pValue": pobj(0.03)},
                "differenceOfMedians": {"n1": 8, "median1": med_g1, "n2": 9, "median2": med_g2,
                                        "actualDifference": actual, "hodgesLehmannDifference": 3.5}},
            "descriptiveStatistics": desc(
                ("sample1", colid(1, "Drug"), stats(9, 0.0, median=med_g2)),
                ("sample2", colid(0, "Ctl"), stats(8, 0.0, median=med_g1)))}


def test_mann_whitney(tmp_path):
    r = run(tmp_path, mw_results(), {"experimentalDesign": "MANN_WHITNEY_TEST"})
    assert r.kind == "structured" and r.warnings == []
    t = sec(r, "Test")
    assert t.rows[0][:4] == ["Mann-Whitney test", "U", 12.5, None]
    e = sec(r, "Effect")
    assert e.columns == ["Group 1", "Median 1", "n 1", "Group 2", "Median 2", "n 2",
                         "Hodges-Lehmann difference", "Difference is"]
    assert e.rows == [["A:Ctl", 10.0, 8, "B:Drug", 14.0, 9, 3.5, "B:Drug - A:Ctl"]]


def wilcoxon_results(ids, diff_mean=3.0, s1=8.0, s2=5.0):
    a, b = ids
    return {"status": OK,
            "wilcoxonTestModel": {
                "wilcoxonTest": {"status": "VALID", "signedRanksSum": 40.0, "pValue": pobj(0.02)},
                "medianOfDifferences": {"median": 2.5}},
            "descriptiveStatistics": desc(
                ("sample1", colid(1, "x"), stats(10, s1)),
                ("sample2", colid(0, "y"), stats(10, s2)),
                ("differences", [colid(*a), colid(*b)], stats(10, diff_mean)))}


def test_wilcoxon_order(tmp_path):
    r = run(tmp_path, wilcoxon_results([(1, "x"), (0, "y")]), {"experimentalDesign": "WILCOXON_TEST"})
    assert r.kind == "structured" and r.warnings == []
    assert sec(r, "Test").rows[0][:4] == ["Wilcoxon signed-rank test", "W", 40.0, None]
    e = sec(r, "Effect")
    assert e.columns == ["Median of differences", "Difference is"]
    assert e.rows == [[2.5, "B:x - A:y"]]


def test_wilcoxon_order_unverified(tmp_path):
    r = run(tmp_path, wilcoxon_results([(1, "x"), (0, "y")], diff_mean=-3.0), {"experimentalDesign": "WILCOXON_TEST"})
    assert DIRW in r.warnings


def test_variance_status_only(tmp_path):
    res = welch_results(5.0, 7.0, 2.0, variance={"status": "SD_ZERO"})
    r = run(tmp_path, res)
    t = sec(r, "Test")
    assert t.rows[1] == ["F test to compare variances", "F", None, None, None, None, None]
    assert "F test to compare variances: SD_ZERO" in r.warnings


def test_descriptive_missing_fields(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    res["descriptiveStatistics"]["sample1"]["value"] = {"n": 12, "mean": 7.0, "sd": "undefined"}
    res["descriptiveStatistics"]["sample2"]["value"] = {"n": 10, "mean": 5.0}
    r = run(tmp_path, res)
    d = sec(r, "Descriptive statistics")
    assert d.rows == [["A:Ctl", 10, 5.0, None, None, None, None, None],
                      ["B:Drug", 12, 7.0, None, None, None, None, None]]


def test_unknown_design_falls_back(tmp_path):
    res = {"status": OK, "descriptiveStatistics": {}}
    r = run(tmp_path, res, {"experimentalDesign": "KOLMOGOROV_SMIRNOV_TEST"})
    assert r.kind == "generic"
    assert "Structured reader failed (KeyError), showing generic values." in r.warnings


def test_missing_model_falls_back(tmp_path):
    r = run(tmp_path, {"status": OK, "x": 1}, {"experimentalDesign": "WELCH_T_TEST"})
    assert r.kind == "generic"


def test_missing_design_infers_model(tmp_path):
    b = PrismBuilder()
    b.add_analysis("T", CLS, {}, welch_results(5.0, 7.0, 2.0), inputs=(("A", "Ctl"), ("B", "Drug")))
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        r = read_analysis(pf, pf.analyses()[0])
    assert r.kind == "structured"
    assert sec(r, "Test").rows[0][0] == "Welch's t test"
    assert "Parameters" not in [s.title for s in r.sections]  # nothing stored: section omitted


INF = "Group labels inferred from input order."


def test_fallback_per_group(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    res["descriptiveStatistics"]["sample1"]["value"]["mean"] = 7.5  # group 2 unmatched
    r = run(tmp_path, res, inputs=(("A", "In1"), ("B", "In2")))
    e = sec(r, "Effect").rows[0]
    assert e[0] == "A:Ctl" and e[3] == "B:In2"
    assert INF in r.warnings


def test_fallback_per_group_without_inputs(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    res["descriptiveStatistics"]["sample1"]["value"]["mean"] = 7.5
    r = run(tmp_path, res, inputs=())
    e = sec(r, "Effect").rows[0]
    assert e[0] == "A:Ctl" and e[3] is None and e[7] is None


def test_empty_label_match_is_unmatched(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    res["descriptiveStatistics"]["sample1"]["id"] = {}
    r = run(tmp_path, res, inputs=(("A", "In1"), ("B", "In2")))
    e = sec(r, "Effect").rows[0]
    assert e[0] == "A:Ctl" and e[3] == "B:In2" and INF in r.warnings


def test_match_compares_raw_values(tmp_path):
    big = 2**53
    res = welch_results(5.0, 7.0, 2.0)
    res["welchTTestModel"]["differenceOfMeans"]["mean1"] = big + 1
    res["descriptiveStatistics"]["sample2"]["value"]["mean"] = big
    r = run(tmp_path, res, inputs=(("A", "In1"), ("B", "In2")))
    assert sec(r, "Effect").rows[0][0] == "A:In1" and INF in r.warnings


def test_missing_test_block_keeps_effect(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    del res["welchTTestModel"]["welchTTest"]
    r = run(tmp_path, res)
    assert r.kind == "structured"
    assert [s.title for s in r.sections] == ["Parameters", "Effect", "Descriptive statistics"]


def test_missing_effect_block_keeps_test(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    del res["welchTTestModel"]["differenceOfMeans"]
    r = run(tmp_path, res)
    assert r.kind == "structured"
    assert [s.title for s in r.sections] == ["Parameters", "Test", "Descriptive statistics"]


def test_empty_blocks_omit_sections(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    res["welchTTestModel"]["welchTTest"] = {"status": "INVALID"}
    res["welchTTestModel"]["differenceOfMeans"] = {}
    r = run(tmp_path, res)
    assert [s.title for s in r.sections] == ["Parameters", "Descriptive statistics", "Other values"]
    assert sec(r, "Other values").rows == [["welchTTest.status", "INVALID"]]


def test_paired_and_wilcoxon_missing_blocks(tmp_path):
    res = paired_results(3.0)
    del res["pairedTTestModel"]["meanOfDifferences"]
    r = run(tmp_path, res, {"experimentalDesign": "PAIRED_T_TEST"})
    assert "Effect" not in [s.title for s in r.sections] and r.kind == "structured"
    res = wilcoxon_results([(1, "x"), (0, "y")])
    del res["wilcoxonTestModel"]["wilcoxonTest"]
    r = run(tmp_path, res, {"experimentalDesign": "WILCOXON_TEST"})
    assert "Test" not in [s.title for s in r.sections] and r.kind == "structured"


def test_input_label_keeps_equal_title(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    del res["descriptiveStatistics"]
    r = run(tmp_path, res, inputs=(("A", "A"), ("B", "B")))
    e = sec(r, "Effect").rows[0]
    assert e[0] == "A:A" and e[3] == "B:B"


def test_fallback_never_reuses_other_groups_label(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    res["descriptiveStatistics"]["sample1"]["value"]["mean"] = 7.5  # group 2 unmatched
    r = run(tmp_path, res, inputs=(("B", "X"), ("A", "Ctl")))
    e = sec(r, "Effect").rows[0]
    assert e[0] == "A:Ctl" and e[3] == "B:X" and INF in r.warnings


def test_fallback_conflict_ambiguous_gives_none(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    res["descriptiveStatistics"]["sample1"]["value"]["mean"] = 7.5
    r = run(tmp_path, res, inputs=(("B", "X"), ("A", "Ctl"), ("C", "Y")))
    e = sec(r, "Effect").rows[0]
    assert e[0] == "A:Ctl" and e[3] is None and e[7] is None and INF in r.warnings


def test_fallback_needs_two_inputs(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    res["descriptiveStatistics"]["sample2"]["value"]["mean"] = 5.5  # group 1 unmatched
    r = run(tmp_path, res, inputs=(("A", "Solo"),))
    e = sec(r, "Effect").rows[0]
    assert e[0] is None and e[3] == "B:Drug"


def test_wilcoxon_without_median_keeps_direction_and_check(tmp_path):
    res = wilcoxon_results([(1, "x"), (0, "y")], diff_mean=-3.0)
    del res["wilcoxonTestModel"]["medianOfDifferences"]
    r = run(tmp_path, res, {"experimentalDesign": "WILCOXON_TEST"})
    assert sec(r, "Effect").rows == [[None, "B:x - A:y"]]
    assert DIRW in r.warnings


def test_non_dict_model_falls_back(tmp_path):
    r = run(tmp_path, {"status": OK, "welchTTestModel": 5}, {"experimentalDesign": "WELCH_T_TEST"})
    assert r.kind == "generic"
    assert "Structured reader failed (KeyError), showing generic values." in r.warnings


def test_untitled_input_label_is_bare_letter(tmp_path):
    res = welch_results(5.0, 7.0, 2.0)
    del res["descriptiveStatistics"]
    r = run(tmp_path, res, inputs=(("A", None), ("B", "Y")))
    e = sec(r, "Effect").rows[0]
    assert e[0] == "A" and e[3] == "B:Y"


def test_fallback_never_reuses_untitled_column(tmp_path):
    res = welch_results(5.0, 7.0, 2.0, ids=((0, None), (1, "Drug")))
    res["descriptiveStatistics"]["sample1"]["value"]["mean"] = 7.5  # group 2 unmatched
    r = run(tmp_path, res, inputs=(("B", "X"), ("A", None)))
    e = sec(r, "Effect").rows[0]
    assert e[0] == "A" and e[3] == "B:X" and INF in r.warnings
