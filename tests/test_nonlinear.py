import prsmfile
from prsmfile import PValue, read_analysis
from tests.builder import PrismBuilder
from tests.helpers import assert_sections_well_formed

CLS = "NONLINEAR_REGRESSION"
OK = {"error": "VALID", "warning": []}
H0 = "d571a627-1d57-538c-9727-83a878cf55f1"


def wrap(x):
    return {H0: {"id": {}, "value": x}}


def pobj(v, sig=True):
    return {"value": v, "level": 0.05, "isSignificant": sig, "state": "P_VALUE_EQUAL"}


def mid(idx, title, model="Model 1", mtitle="Top unconstrained"):
    col = {"uid": f"U{idx}", "idx": idx}
    if title is not None:
        col["title"] = title
    return {"col": col, "model": {"name": model, "title": mtitle}}


def par(est, status="REGULAR", se=0.1, lo=0.5, hi=1.5):
    return wrap({"status": status, "estimate": est, "se": se,
                 "ci": {"lower": lo, "upper": hi, "level": 95.0}})


def fit(parameters, gof=True, status="COMPLETED"):
    v = {"status": status, "iterationCount": 10, "parameters": parameters}
    if gof is True:
        v["goodnessOfFit"] = {"df": 27.0, "r2": wrap(0.98), "adjR2": 0.97, "syx": 0.03,
                              "rmse": 0.029, "aicc": -195.6}
    elif gof:
        v["goodnessOfFit"] = gof
    return v


def summary(idx, title, x=30, y=29):
    c = {"uid": f"U{idx}", "idx": idx}
    if title is not None:
        c["title"] = title
    return {"id": {"col": c}, "value": {"xValuesAnalyzed": x, "yValuesAnalyzed": y, "yValuesSkipped": 1}}


def run(tmp_path, results, params=None):
    params = {"model": {"equation": {"name": "Sigmoidal 4PL, X is concentration"}}, **(params or {})}
    b = PrismBuilder()
    b.add_analysis("N", CLS, params, results, inputs=(("A", "276A"), ("B", "B2")))
    with prsmfile.open(b.save(tmp_path / "n.prism")) as pf:
        r = read_analysis(pf, pf.analyses()[0])
    assert_sections_well_formed(r)
    return r


def sec(r, title):
    (s,) = [s for s in r.sections if s.title == title]
    return s


def res(models, summaries, **kw):
    out = {"status": OK,
           "models": PrismBuilder.keyed(models),
           "dataSummary": PrismBuilder.keyed((s["id"], s["value"]) for s in summaries)}
    out.update(kw)
    return out


def test_nlr_best_fit_constant_param(tmp_path):
    params = {"Bottom": par(0.0, "CONSTANT", "undefined", "undefined", "undefined"),
              "IC50": par(1.2e-6, se=1.3e-7, lo=9.4e-7, hi=1.6e-6)}
    r = run(tmp_path, res([(mid(0, "276A"), fit(params))], [summary(0, "276A")]))
    assert r.kind == "structured" and r.warnings == []
    assert [s.title for s in r.sections] == ["Parameters", "Best-fit values", "Goodness of fit", "Other values"]
    assert sec(r, "Other values").rows == [
        ["models[A:276A:Top unconstrained].iterationCount", 10], ["dataSummary[A:276A].yValuesSkipped", 1]]
    assert sec(r, "Parameters").rows == [["Equation", "Sigmoidal 4PL, X is concentration"]]
    t = sec(r, "Best-fit values")
    assert t.columns == ["Data set", "Model", "Parameter", "Estimate", "SE", "CI lower", "CI upper",
                         "CI level", "Status"]
    assert t.rows[0] == ["A:276A", "Top unconstrained", "Bottom", 0.0, None, None, None, 95.0, "CONSTANT"]
    assert t.rows[1] == ["A:276A", "Top unconstrained", "IC50", 1.2e-6, 1.3e-7, 9.4e-7, 1.6e-6, 95.0, "REGULAR"]


def test_nlr_goodness_join(tmp_path):
    p = {"K": par(1.0)}
    r = run(tmp_path, res(
        [(mid(1, "B2"), fit(p)), (mid(0, "276A"), fit(p))],
        [summary(0, "276A", 30, 29), summary(1, "B2", 12, 11)]))
    g = sec(r, "Goodness of fit")
    assert g.columns == ["Data set", "Model", "Fit status", "df", "R squared", "Adj R squared", "Sy.x",
                         "RMSE", "AICc", "X analyzed", "Y analyzed"]
    assert g.rows[0] == ["A:276A", "Top unconstrained", "COMPLETED", 27.0, 0.98, 0.97, 0.03, 0.029,
                         -195.6, 30.0, 29.0]
    assert g.rows[1][0] == "B:B2" and g.rows[1][9:] == [12.0, 11.0]


def test_nlr_not_converged_keeps_counts(tmp_path):
    r = run(tmp_path, res([(mid(0, "276A"), fit({"K": par(1.0)}, gof=False, status="INTERRUPTED"))],
                          [summary(0, "276A", 7, 6)]))
    g = sec(r, "Goodness of fit")
    assert g.rows == [["A:276A", "Top unconstrained", "INTERRUPTED", None, None, None, None, None,
                       None, 7.0, 6.0]]


def cmp_entry(is_run, status, summ=None, pref="Top unconstrained"):
    ft = {"status": status, "isRun": is_run, "preferredModelName": pref,
          "simpleModel": {"status": "REGULAR", "name": "Top = 1", "key": "Model 2", "ss": 0.07, "df": 28.0},
          "complexModel": {"status": "REGULAR", "name": "Top unconstrained", "key": "Model 1",
                           "ss": 0.03, "df": 27.0}}
    if summ is not None:
        ft["summary"] = summ
    return {"id": [mid(0, "276A"), mid(0, "276A", "Model 2", "Top = 1")], "value": {"fTest": ft}}


def base(extra):
    return res([(mid(0, "276A"), fit({"K": par(1.0)}))], [summary(0, "276A")], modelComparison=extra)


def test_nlr_model_comparison_run(tmp_path):
    s = {"f": 31.5, "dfNumerator": 1.0, "dfDenominator": 27.0, "pValue": pobj(5.9e-6)}
    r = run(tmp_path, base({"c0": cmp_entry(True, "CALCULATED", s)}))
    t = sec(r, "Model comparison")
    assert t.columns == ["Data set", "Simpler model", "Complex model", "Run", "Status", "Preferred",
                         "F", "DFn", "DFd", "P"]
    assert t.rows == [["A:276A", "Top = 1", "Top unconstrained", True, "CALCULATED", "Top unconstrained",
                       31.5, 1.0, 27.0, PValue(5.9e-6, 0.05, True, False)]]


def test_nlr_model_comparison_not_run(tmp_path):
    r = run(tmp_path, base({"c0": cmp_entry(False, "NOT_CONVERGED_VS_NOT_CONVERGED", pref="")}))
    t = sec(r, "Model comparison")
    assert t.rows == [["A:276A", "Top = 1", "Top unconstrained", False, "NOT_CONVERGED_VS_NOT_CONVERGED",
                       None, None, None, None, None]]


def test_nlr_comparison_undefined_summary(tmp_path):
    s = {"f": "undefined", "dfNumerator": 1.0, "dfDenominator": 3.0,
         "pValue": {"value": "undefined", "level": 0.05, "isSignificant": False, "state": "P_VALUE_EQUAL"}}
    r = run(tmp_path, base({"c0": cmp_entry(True, "SIMPLE_MODEL_FITS_BETTER", s)}))
    row = sec(r, "Model comparison").rows[0]
    assert row[3] is True and row[6] is None and row[7:9] == [1.0, 3.0]
    assert row[9] == PValue(None, 0.05, False, False)


def test_nlr_garbage_does_not_raise(tmp_path):
    r = run(tmp_path, {"status": OK, "models": {"k": {"id": {}, "value": {"parameters": 5}}},
                       "dataSummary": 3, "modelComparison": {"k": {"id": 1, "value": 2}}})
    assert r.kind == "structured"
