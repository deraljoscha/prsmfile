"""NONLINEAR_REGRESSION (docs/format.md 2.5)."""
from __future__ import annotations

from ..report import Section
from ..values import PValue, ci, entries, label, num
from . import register
from .common import parameters_section

_BEST_COLUMNS = ["Data set", "Model", "Parameter", "Estimate", "SE", "CI lower", "CI upper",
                 "CI level", "Status"]
_GOF_COLUMNS = ["Data set", "Model", "Fit status", "df", "R squared", "Adj R squared", "Sy.x", "RMSE",
                "AICc", "X analyzed", "Y analyzed"]
_CMP_COLUMNS = ["Data set", "Simpler model", "Complex model", "Run", "Status", "Preferred",
                "F", "DFn", "DFd", "P"]


def _dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def _str(x) -> str | None:
    return x if isinstance(x, str) and x.strip() else None


def scalar(node):
    """The value of a scalar wrapper {<h0>: {id: {}, value: X}}; any other node unchanged."""
    if isinstance(node, dict) and len(node) == 1:
        (only,) = node.values()
        if isinstance(only, dict) and "value" in only and only.get("id") == {}:
            return only["value"]
    return node


def dataset_label(id_) -> str:
    """Label of the data set (column) of an id that may also carry a model."""
    if isinstance(id_, list):
        id_ = id_[0] if id_ else {}
    id_ = _dict(id_)
    return label({"col": id_["col"]}) if "col" in id_ else ""


def _model_name(id_) -> str | None:
    model = _dict(_dict(id_).get("model"))
    return _str(model.get("title")) or _str(model.get("name"))


def _col_uid(id_):
    return _dict(_dict(id_).get("col")).get("uid")


def _best_fit_rows(models) -> list[list]:
    rows = []
    for id_, value in models:
        ds, model = dataset_label(id_), _model_name(id_)
        for name, node in _dict(_dict(value).get("parameters")).items():
            p = _dict(scalar(node))
            lo, hi, level = ci(p.get("ci"))
            rows.append([ds, model, str(name), num(p.get("estimate")), num(p.get("se")), lo, hi, level,
                         _str(p.get("status"))])
    return rows


def _goodness_rows(models, summaries) -> list[list]:
    counts = {}
    for id_, value in summaries:
        uid = _col_uid(id_)
        if uid is not None:
            counts[uid] = _dict(value)
    rows = []
    for id_, value in models:
        v = _dict(value)
        g = _dict(v.get("goodnessOfFit") or {})
        c = counts.get(_col_uid(id_), {})
        rows.append([dataset_label(id_), _model_name(id_), _str(v.get("status")), num(g.get("df")),
                     num(scalar(g.get("r2"))), num(scalar(g.get("adjR2"))), num(scalar(g.get("syx"))),
                     num(scalar(g.get("rmse"))), num(scalar(g.get("aicc"))),
                     num(c.get("xValuesAnalyzed")), num(c.get("yValuesAnalyzed"))])
    return rows


def _comparison_rows(coll) -> list[list]:
    rows = []
    for id_, value in entries(coll):
        ft = _dict(_dict(value).get("fTest"))
        s = _dict(ft.get("summary"))
        run = ft.get("isRun")
        rows.append([
            dataset_label(id_), _str(_dict(ft.get("simpleModel")).get("name")),
            _str(_dict(ft.get("complexModel")).get("name")), run if isinstance(run, bool) else None,
            _str(ft.get("status")), _str(ft.get("preferredModelName")), num(s.get("f")),
            num(s.get("dfNumerator")), num(s.get("dfDenominator")), PValue.from_obj(s.get("pValue")),
        ])
    return rows


@register("NONLINEAR_REGRESSION")
def read_nonlinear(pf, a, warn):
    results = a.results
    models = entries(results.get("models"))
    if not isinstance(results.get("models"), dict):
        raise KeyError("models")
    equation = _dict(_dict(_dict(a.parameters).get("model")).get("equation"))
    sections = []
    params = parameters_section([("Equation", _str(equation.get("name")))])
    if params.rows:
        sections.append(params)
    best = _best_fit_rows(models)
    if best:
        sections.append(Section("Best-fit values", list(_BEST_COLUMNS), best))
    gof = _goodness_rows(models, entries(results.get("dataSummary")))
    if gof:
        sections.append(Section("Goodness of fit", list(_GOF_COLUMNS), gof))
    cmp_rows = _comparison_rows(results.get("modelComparison"))
    if cmp_rows:
        sections.append(Section("Model comparison", list(_CMP_COLUMNS), cmp_rows))
    return sections
