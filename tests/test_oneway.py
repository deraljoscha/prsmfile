import prsmfile
from prsmfile import PValue, read_analysis
from tests.builder import PrismBuilder
from tests.helpers import assert_sections_well_formed

CLS = "ONE_WAY_ANOVA"
OK = {"error": "VALID", "warning": []}


def pobj(v, sig=True):
    return {"value": v, "level": 0.05, "isSignificant": sig, "state": "P_VALUE_EQUAL"}


def pv(v, sig=True):
    return PValue(value=v, alpha=0.05, significant=sig, bound=False)


def colid(idx, title):
    c = {"uid": f"U{idx}", "idx": idx}
    if title is not None:
        c["title"] = title
    return {"col": c}


def run(tmp_path, results, params=None, **kw):
    params = {"experimentalDesign": "ORDINARY_ANOVA",
              "postTests": {"type": "PAIRWISE_TESTS",
                            "pairwiseTests": {"pairwiseDesign": {"type": "ALL_VS_ALL"}}},
              **(params or {})}
    b = PrismBuilder()
    b.add_analysis("O", CLS, params, results, inputs=(("A", "ctrl"), ("B", "asp")), **kw)
    with prsmfile.open(b.save(tmp_path / "o.prism")) as pf:
        r = read_analysis(pf, pf.analyses()[0])
    assert_sections_well_formed(r)
    return r


def sec(r, title):
    (s,) = [s for s in r.sections if s.title == title]
    return s


def ftest(f, dfn, dfd, p):
    return {"status": "VALID", "f": f, "dfNumerator": dfn, "dfDenominator": dfd, "pValue": pobj(p)}


def table():
    return {"colFactor": {"ss": 52.4, "df": 3.0, "ms": 17.47, "r2": 0.49,
                          "fTest": ftest(3.84, 3.0, 12.0, 0.0386)},
            "residual": {"ss": 54.53, "df": 12.0, "ms": 4.544},
            "total": {"ss": 106.9, "df": 15.0}}


def pair(diff, p_adj=None, p_ind=None, ci=True):
    v = {"status": "VALID", "meansDifference": diff, "meansDifferenceSE": 1.5, "statistic": 4.0, "df": 12.0,
         "sample1": {"value": {"mean": 3.0, "n": 4}}, "sample2": {"value": {"mean": 7.0, "n": 4}}}
    if ci:
        v["meansDifferenceCI"] = {"lower": -8.0, "upper": 0.1, "level": 95.0}
    if p_adj is not None:
        v["pValueAdjusted"] = pobj(p_adj)
    if p_ind is not None:
        v["pValueIndividual"] = pobj(p_ind)
    return v


def mc(method, pairs):
    """pairs: [((idx1, title1), (idx2, title2), value)] grouped by the first column."""
    outer = {}
    for c1, c2, value in pairs:
        o = outer.setdefault(c1, {"id": colid(*c1), "value": {}})
        o["value"][f"h{c2[0]}"] = {"id": colid(*c2), "value": value}
    m = {"status": "VALID", "tests": {f"k{c[0]}": v for c, v in outer.items()}}
    if method is not None:
        m["method"] = method
    return m


def model(**kw):
    m = {"status": "VALID", "anovaTable": table()}
    m.update(kw)
    return m


def res(m=None, key="ordinaryAnovaModel", stats=True):
    out = {"status": OK, key: m if m is not None else model()}
    if stats:
        out["descriptiveStatistics"] = {
            "d0": {"id": colid(1, "asp"), "value": {"n": 4, "mean": 7.0}},
            "d1": {"id": colid(0, "ctrl"), "value": {"n": 4, "mean": 3.0}},
        }
    return out


def test_anova_table(tmp_path):
    r = run(tmp_path, res())
    assert r.kind == "structured" and r.warnings == []
    assert [s.title for s in r.sections] == ["Parameters", "ANOVA", "Descriptive statistics"]
    t = sec(r, "ANOVA")
    assert t.columns == ["Source", "SS", "df", "MS", "F", "DFn", "DFd", "P", "R squared"]
    assert t.rows[0] == ["Treatment", 52.4, 3.0, 17.47, 3.84, 3.0, 12.0, pv(0.0386), 0.49]
    assert t.rows[1] == ["Residual", 54.53, 12.0, 4.544, None, None, None, None, None]
    assert t.rows[2] == ["Total", 106.9, 15.0, None, None, None, None, None, None]
    p = sec(r, "Parameters")
    assert p.rows == [["Design", "ORDINARY_ANOVA"], ["Post test design", "ALL_VS_ALL"]]
    d = sec(r, "Descriptive statistics")
    assert [row[0] for row in d.rows] == ["A:ctrl", "B:asp"]


def test_matching_r_squared(tmp_path):
    m = model()
    m["anovaTable"]["matchedFactor"] = {"ss": 5.0, "df": 3.0, "ms": 1.7, "r2": 0.1006,
                                         "fTest": ftest(2.0, 3.0, 9.0, 0.2)}
    r = run(tmp_path, res(m, "repeatedMeasuresGlmAnovaModel"),
            {"experimentalDesign": "REPEATED_MEASURES_ANOVA"})
    t = sec(r, "ANOVA")
    assert [row[0] for row in t.rows] == ["Treatment", "Matching", "Residual", "Total"]
    assert t.rows[1][-1] == 0.1006 and t.rows[1][7] == pv(0.2)
    assert sec(r, "Parameters").rows[0] == ["Design", "REPEATED_MEASURES_ANOVA"]


def test_tukey_comparisons(tmp_path):
    m = model(multipleComparisons=mc("Tukey", [((0, "ctrl"), (1, "asp"), pair(-4.3125, p_adj=0.06))]))
    r = run(tmp_path, res(m))
    s = sec(r, "Multiple comparisons (Tukey)")
    assert s.columns == ["Comparison", "Mean diff", "SE", "CI lower", "CI upper", "CI level",
                         "Statistic", "df", "P adjusted", "P individual"]
    assert s.rows == [["A:ctrl vs B:asp", -4.3125, 1.5, -8.0, 0.1, 95.0, 4.0, 12.0, pv(0.06), None]]
    assert ["Method", "Tukey"] in sec(r, "Parameters").rows


def test_same_title_comparisons(tmp_path):
    cols = [(0, "0nM"), (1, "0nM"), (2, "0nM")]
    pairs = [(cols[0], cols[1], pair(1.0, p_adj=0.5)), (cols[0], cols[2], pair(2.0, p_adj=0.5)),
             (cols[1], cols[2], pair(3.0, p_adj=0.5))]
    r = run(tmp_path, res(model(multipleComparisons=mc("Tukey", pairs))))
    labels = [row[0] for row in sec(r, "Multiple comparisons (Tukey)").rows]
    assert labels == ["A:0nM vs B:0nM", "A:0nM vs C:0nM", "B:0nM vs C:0nM"]
    assert len(set(labels)) == 3


def test_no_correction_individual_p(tmp_path):
    m = model(multipleComparisons=mc("No correction", [((0, "ctrl"), (1, "asp"), pair(-4.0, p_ind=0.03, ci=False))]))
    r = run(tmp_path, res(m))
    s = sec(r, "Multiple comparisons (No correction)")
    assert s.rows == [["A:ctrl vs B:asp", -4.0, 1.5, None, None, None, 4.0, 12.0, None, pv(0.03)]]


def test_comparisons_without_method(tmp_path):
    m = model(multipleComparisons=mc(None, [((0, "ctrl"), (1, "asp"), pair(-4.0, p_adj=0.5))]))
    r = run(tmp_path, res(m))
    assert len(sec(r, "Multiple comparisons").rows) == 1
    assert "Method" not in [row[0] for row in sec(r, "Parameters").rows]


def test_bartlett_not_valid(tmp_path):
    m = model(bartlettTest={"status": "TOO_FEW_POINTS"},
              brownForsytheTest=ftest(0.7, 2.0, 12.0, 0.51))
    r = run(tmp_path, res(m))
    s = sec(r, "Assumption tests")
    assert s.columns == ["Test", "Statistic", "DFn", "DFd", "P", "Status"]
    assert s.rows == [["Brown-Forsythe test", 0.7, 2.0, 12.0, pv(0.51), "VALID"],
                      ["Bartlett's test", None, None, None, None, "TOO_FEW_POINTS"]]


def test_bartlett_valid(tmp_path):
    m = model(bartlettTest={"status": "VALID", "statistic": 1.2, "pValue": pobj(0.4, False)})
    s = sec(run(tmp_path, res(m)), "Assumption tests")
    assert s.rows == [["Bartlett's test", 1.2, None, None, pv(0.4, False), "VALID"]]


def test_model_without_anova_table(tmp_path):
    r = run(tmp_path, res({"status": "VALID"}))
    assert r.kind == "structured"
    assert [s.title for s in r.sections] == ["Parameters", "Descriptive statistics"]


def test_invalid_data_no_model(tmp_path):
    r = run(tmp_path, {"status": {"error": "INVALID_DATA_TOO_FEW_COLUMNS", "warning": []}})
    assert r.kind == "generic"
    assert "Prism reported INVALID_DATA_TOO_FEW_COLUMNS" in r.warnings


def test_missing_model_key_falls_back(tmp_path):
    r = run(tmp_path, {"status": OK, "descriptiveStatistics": {}})
    assert r.kind == "generic"
    assert "Structured reader failed (KeyError), showing generic values." in r.warnings


def test_non_dict_model_falls_back(tmp_path):
    r = run(tmp_path, {"status": OK, "ordinaryAnovaModel": 3})
    assert r.kind == "generic"


def test_garbage_values_do_not_raise(tmp_path):
    m = {"status": "VALID",
         "anovaTable": {"colFactor": {"ss": "undefined", "fTest": "x"}, "residual": 3},
         "multipleComparisons": {"method": 7, "tests": {"k": {"id": {}, "value": {"h": {"id": {}, "value": 5}}}}}}
    r = run(tmp_path, res(m))
    assert r.kind == "structured"
