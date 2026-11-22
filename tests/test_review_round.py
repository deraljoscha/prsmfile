"""Pre-release review round: values that were dropped or shown inconsistently."""
import json

import prsmfile
from prsmfile import PValue, read_analysis
from tests import test_auc, test_nonlinear, test_oneway, test_ttest, test_twoway
from tests.builder import PrismBuilder
from tests.helpers import assert_sections_well_formed

OK = {"error": "VALID", "warning": []}


def paths(section):
    return [row[0] for row in section.rows]


def sec(r, title):
    (s,) = [s for s in r.sections if s.title == title]
    return s


def build_one(tmp_path, cls, results, params=None, **kw):
    b = PrismBuilder()
    b.add_analysis("X", cls, params or {}, results, inputs=(("A", "a"), ("B", "b")), **kw)
    with prsmfile.open(b.save(tmp_path / "x.prism")) as pf:
        r = read_analysis(pf, pf.analyses()[0])
    assert_sections_well_formed(r)
    return r


# ---- unread model keys end up in "Other values" ----

def test_ttest_paired_pearson_and_letters_not_dropped(tmp_path):
    m = {"status": "VALID",
         "pairedTTest": {"status": "VALID", "t": 2.0, "df": 5.0, "pValue": test_ttest.pobj(0.1)},
         "pearsonTest": {"r": 0.91, "pValue": test_ttest.pobj(0.01)}}
    res = {"status": OK, "pairedTTestModel": m,
           "compactLetterDisplay": {"status": "VALID", "letterCount": 2, "sampleCount": 2, "samples": {}}}
    r = test_ttest.run(tmp_path, res, {"experimentalDesign": "PAIRED_T_TEST"})
    p = paths(sec(r, "Other values"))
    assert "pearsonTest.r" in p and "pearsonTest.pValue" in p
    assert "compactLetterDisplay.letterCount" in p
    assert r.kind == "structured"


def test_ttest_wilcoxon_spearman_not_dropped(tmp_path):
    m = {"wilcoxonTest": {"signedRanksSum": 3.0, "pValue": test_ttest.pobj(0.2)},
         "medianOfDifferences": {"median": 1.0}, "spearmanTest": {"r": 0.5}}
    r = test_ttest.run(tmp_path, {"status": OK, "wilcoxonTestModel": m}, {"experimentalDesign": "WILCOXON_TEST"})
    assert "spearmanTest.r" in paths(sec(r, "Other values"))


def test_oneway_data_summary_and_unknown_keys_shown(tmp_path):
    m = test_oneway.model(dataSummary={"levelCount": 3, "pointCount": 12}, extraThing={"x": 1})
    r = test_oneway.run(tmp_path, test_oneway.res(m))
    ds = sec(r, "Data summary")
    assert ds.rows == [["Level count", 3], ["Point count", 12]]
    assert ["extraThing.x", 1] in sec(r, "Other values").rows


def test_nonlinear_outliers_not_dropped(tmp_path):
    params = {"K": test_nonlinear.par(1.0)}
    res = test_nonlinear.res([(test_nonlinear.mid(0, "276A"), test_nonlinear.fit(params))],
                             [test_nonlinear.summary(0, "276A")], outliers={"o": {"q": 1.0}})
    r = test_nonlinear.run(tmp_path, res)
    assert ["outliers.o.q", 1.0] in sec(r, "Other values").rows


def test_auc_extra_field_with_empty_samples_is_not_dropped(tmp_path):
    r = test_auc.run(tmp_path, {"status": OK, "samples": {}, "extra": {"v": 5}})
    assert any(row == ["extra.v", 5] for s in r.sections for row in s.rows)


def test_reader_without_sections_falls_back_to_generic(tmp_path):
    r = build_one(tmp_path, "AREA_UNDER_CURVE", {"status": OK, "samples": {}}, {"calc": {}})
    assert r.kind == "generic"


def test_twoway_unknown_model_key_shown(tmp_path):
    res = test_twoway.res({"status": "VALID", "anovaTable": {"rowFactor": test_twoway.node(1, 1, 1)},
                           "mystery": {"a": 1}})
    r = test_twoway.run(tmp_path, res)
    assert ["mystery.a", 1] in sec(r, "Other values").rows


# ---- one-way repeated measures ----

def test_oneway_rm_epsilon_and_matching_test(tmp_path):
    t = test_oneway.table()
    t["colFactor"]["ggEpsilon"] = 0.7448
    t["matchedFactor"] = {"ss": 1.0, "df": 2.0, "ms": 0.5}
    m = {"status": "VALID", "anovaTable": t,
         "matchingTest": {"status": "VALID", "f": 1.32, "dfNumerator": 2.0, "dfDenominator": 4.0,
                          "pValue": test_oneway.pobj(0.36, False)}}
    r = test_oneway.run(tmp_path, test_oneway.res(m, key="repeatedMeasuresGlmAnovaModel"),
                        {"experimentalDesign": "REPEATED_MEASURES"})
    a = sec(r, "ANOVA")
    assert a.columns[-1] == "GG epsilon" and a.rows[0][-1] == 0.7448
    mt = sec(r, "Matching test")
    assert mt.columns == ["F", "DFn", "DFd", "P"]
    assert mt.rows == [[1.32, 2.0, 4.0, PValue(0.36, 0.05, False, False)]]


# ---- status-only content ----

def test_status_only_keeps_warning_codes(tmp_path):
    r = build_one(tmp_path, "ONE_WAY_ANOVA",
                  {"status": {"error": "VALID", "warning": ["MISSING_VALUES"]}})
    assert "Prism reported MISSING_VALUES" in r.warnings


def test_warning_codes_use_prism_reported_wording(tmp_path):
    r = build_one(tmp_path, "UNKNOWN_CLASS",
                  {"status": {"error": "INVALID_X", "warning": ["INCOMPLETE_CI"]}, "v": 1})
    assert "Prism reported INCOMPLETE_CI" in r.warnings
    assert "Prism reported INVALID_X" in r.warnings


def test_one_wording_for_unverifiable_direction(tmp_path):
    import inspect
    from prsmfile.readers import ttest
    assert "unverified" not in inspect.getsource(ttest)


# ---- naming ----

def test_ttest_test_table_columns_and_split_df(tmp_path):
    var = {"status": "VALID", "f": 1.5, "dfNumerator": 5.0, "dfDenominator": 16.0, "pValue": test_ttest.pobj(0.8)}
    r = test_ttest.run(tmp_path, test_ttest.welch(3, 1.0, 3, 2.0, -1.0, variance=var))
    t = sec(r, "Test")
    assert t.columns == ["Test", "Statistic name", "Statistic", "df", "DFn", "DFd", "P"]
    assert t.rows[0][:6] == ["Welch's t test", "t", 2.5, 17.0, None, None]
    assert t.rows[1][:6] == ["F test to compare variances", "F", 1.5, None, 5.0, 16.0]


def test_twoway_data_summary_names_humanised(tmp_path):
    res = test_twoway.res({"status": "VALID", "anovaTable": {"rowFactor": test_twoway.node(1, 1, 1)},
                           "dataSummary": {"rowCount": 2, "colCount": 3, "isBalancedDesign": True,
                                           "matchedCount": 4}})
    d = sec(test_twoway.run(tmp_path, res), "Data summary")
    assert d.rows == [["Row count", 2], ["Column count", 3], ["Balanced design", True], ["Matched count", 4]]


# ---- numbers ----

def test_num_keeps_ints_exact():
    from prsmfile.values import num
    assert num(6) == 6 and isinstance(num(6), int) and not isinstance(num(6), bool)
    assert num(9007199254740993) == 9007199254740993
    assert num(True) is None and isinstance(num(6.0), float)
    assert num(10 ** 400) is None


def test_json_shows_integers_without_fraction(tmp_path):
    r = build_one(tmp_path, "UNKNOWN_CLASS", {"status": OK, "n": 6, "big": 9007199254740993})
    text = json.dumps(r.to_dict())
    assert '"n", 6]' in text and "9007199254740993]" in text and "9007199254740992" not in text


# ---- generic p-value ----

def test_generic_p_value_without_state_is_one_cell(tmp_path):
    r = build_one(tmp_path, "UNKNOWN_CLASS",
                  {"status": OK, "pValueAdjusted": {"value": 0.7974, "isSignificant": False}})
    rows = sec(r, "Values").rows
    assert rows == [["pValueAdjusted", PValue(0.7974, None, False, False)]]


# ---- corpus comparison helper binds p to the p cell ----

def test_corpus_effect_check_does_not_take_f_cell_as_p():
    from tests.test_corpus import _effect_cells_ok
    cells = ["28.4", "5", "5.69", "F (5, 18) = 0.04", "P=0.85"]
    assert _effect_cells_ok(cells, 0.04, 0.85)
    assert not _effect_cells_ok(cells, 0.04, 0.04)  # 0.04 as p would only match the F cell
    assert _effect_cells_ok(cells, None, 0.85)
    assert not _effect_cells_ok(cells, None, 0.04)
