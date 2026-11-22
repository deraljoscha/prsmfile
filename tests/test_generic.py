import json

import pytest

import prsmfile
from prsmfile import PValue, Report, Section, read_analysis
from prsmfile.readers import generic_sections, register
from prsmfile.readers import REGISTRY
from prsmfile.readers.generic import flatten
from tests.builder import PrismBuilder
from tests.helpers import assert_sections_well_formed

OK = {"status": {"error": "VALID", "warning": []}}
NOT_CALC = "Not calculated when saved: open the file in Prism, view this analysis's results and save again."


def run(tmp_path, build, **save):
    """Build a file with one analysis and return (report, pf-warnings) of it."""
    b = PrismBuilder()
    build(b)
    with prsmfile.open(b.save(tmp_path / "t.prism", **save)) as pf:
        a = pf.analyses()[0]
        r = read_analysis(pf, a)
    assert_sections_well_formed(r)
    return r


def pobj(v, state="P_VALUE_EQUAL", sig=True):
    return {"value": v, "level": 0.05, "isSignificant": sig, "state": state}


def test_not_calculated(tmp_path):
    r = run(tmp_path, lambda b: b.add_analysis("A", "ONE_WAY_ANOVA", {}, None, is_calculated=False))
    assert r.kind == "not_calculated" and r.sections == []
    assert r.warnings == [NOT_CALC]


def test_stub_uses_rendered_tables(tmp_path):
    def build(b):
        b.add_analysis("A", "T_TESTS_AND_NONPARAMETRIC", {}, None, is_calculated=None, views=[
            ("Tabular results", [["Mean", "1.5"], ["", ""]], "text"),
            ("Numbers", [["1", "2"]], "y_single"),
            ("Empty", [["", " "]], "text"),
            ("Gone", None),
        ])

    r = run(tmp_path, build, prism_version="10.0.2", )
    assert r.kind == "generic"
    assert [s.title for s in r.sections] == ["Tabular results", "Numbers"]
    assert r.sections[0].note == "Rounded values from Prism's rendered table."
    assert r.sections[1].note is None
    assert r.warnings[0].startswith("No stored results")
    assert "10.0.2" in r.warnings[0]


def test_status_only_content(tmp_path):
    def build(b):
        b.add_analysis("A", "ONE_WAY_ANOVA", {}, {"status": {"error": "INVALID_DATA_TOO_FEW_COLUMNS", "warning": []}},
                       views=[("V", [["x", "y"]])])

    r = run(tmp_path, build)
    assert r.kind == "generic"
    assert "Prism reported INVALID_DATA_TOO_FEW_COLUMNS" in r.warnings
    assert not any(w.startswith("No stored results") for w in r.warnings)
    assert not any("reader failed" in w for w in r.warnings)
    assert [s.title for s in r.sections] == ["V"]


def test_unknown_class_generic_values(tmp_path):
    res = {**OK, "pearsonTestModel": {"r": 0.5, "p": pobj(0.01)}}
    r = run(tmp_path, lambda b: b.add_analysis("A", "CORRELATION", {}, res))
    assert r.kind == "generic"
    (s,) = r.sections
    assert s.title == "Values" and s.columns == ["Path", "Value"]
    rows = dict((p, v) for p, v in s.rows)
    assert rows["pearsonTestModel.r"] == 0.5
    assert rows["pearsonTestModel.p"] == PValue(0.01, 0.05, True, False)
    assert not any(p.startswith("status") for p, _ in s.rows)


def keyed_results(ids_values):
    return {**OK, "x": PrismBuilder.keyed(ids_values)}


def test_hash_keys_labelled(tmp_path):
    ids = [({"col": {"idx": i, "title": "aCSF"}}, float(i)) for i in (4, 0, 2)]
    r = run(tmp_path, lambda b: b.add_analysis("A", "CORRELATION", {}, keyed_results(ids)))
    paths = [p for p, _ in r.sections[0].rows]
    assert paths == ["x[A:aCSF]", "x[C:aCSF]", "x[E:aCSF]"]


def test_hash_keys_nested_and_empty_label(tmp_path):
    res = {**OK, "x": PrismBuilder.keyed([({}, {"n": 3, "q": pobj(0.2, "P_VALUE_GREATER", False)})])}
    r = run(tmp_path, lambda b: b.add_analysis("A", "CORRELATION", {}, res))
    rows = r.sections[0].rows
    assert [p for p, _ in rows] == ["x.n", "x.q"]
    assert rows[0][1] == 3 and rows[1][1].bound is True


def test_list_id_labelled(tmp_path):
    ids = [([{"col": {"idx": 0, "title": "x"}}, {"col": {"idx": 1, "title": "y"}}], 1.0)]
    r = run(tmp_path, lambda b: b.add_analysis("A", "CORRELATION", {}, keyed_results(ids)))
    assert r.sections[0].rows == [["x[A:x vs B:y]", 1.0]]


def test_list_indices(tmp_path):
    res = {**OK, "v": [1, "txt", {"a": True}]}
    r = run(tmp_path, lambda b: b.add_analysis("A", "CORRELATION", {}, res))
    assert r.sections[0].rows == [["v[0]", 1], ["v[1]", "txt"], ["v[2].a", True]]


def test_undefined_is_none(tmp_path):
    res = {**OK, "a": "undefined", "b": 2.5, "c": pobj("undefined")}
    r = run(tmp_path, lambda b: b.add_analysis("A", "CORRELATION", {}, res))
    rows = dict((p, v) for p, v in r.sections[0].rows)
    assert rows["a"] is None and rows["b"] == 2.5
    assert rows["c"].value is None


def test_big_int_kept(tmp_path):
    res = {**OK, "n": 10**400}
    r = run(tmp_path, lambda b: b.add_analysis("A", "CORRELATION", {}, res))
    assert r.sections[0].rows == [["n", 10**400]]


def test_deep_nesting_no_recursion_error():
    node = "leaf"
    for _ in range(5000):
        node = {"k": node}
    rows = flatten(node)
    assert len(rows) == 1 and rows[0][1] == "leaf" and rows[0][0].count(".") == 4999


def test_reader_failure_falls_back(tmp_path):
    saved = dict(REGISTRY)
    try:
        for exc in (KeyError("k"), AttributeError("a"), TypeError("t"), ValueError("v"), IndexError("i")):
            @register("BOOM")
            def boom(pf, a, warn, exc=exc):
                warn("half done")
                raise exc

            res = {**OK, "v": 1}
            r = run(tmp_path, lambda b: b.add_analysis("A", "BOOM", {}, res))
            assert r.kind == "generic" and r.sections[0].title == "Values"
            assert f"Structured reader failed ({type(exc).__name__}), showing generic values." in r.warnings
    finally:
        REGISTRY.clear()
        REGISTRY.update(saved)


def test_registered_reader_is_structured(tmp_path):
    saved = dict(REGISTRY)
    try:
        @register("OK_CLASS")
        def fine(pf, a, warn):
            warn("from reader")
            return [Section("S", ["a"], [[1]])]

        res = {**OK, "v": 1}
        r = run(tmp_path, lambda b: b.add_analysis("A", "OK_CLASS", {}, res, alert="Alert text"))
        assert r.kind == "structured" and r.sections[0].title == "S"
        assert r.warnings == ["Alert text", "from reader"]
    finally:
        REGISTRY.clear()
        REGISTRY.update(saved)


def test_major_version_generic(tmp_path):
    saved = dict(REGISTRY)
    try:
        @register("ONE_WAY_ANOVA")
        def never(pf, a, warn):
            raise AssertionError("must not run")

        res = {**OK, "v": 1}
        r = run(tmp_path, lambda b: b.add_analysis("A", "ONE_WAY_ANOVA", {}, res), format_version="2-0-0")
        assert r.kind == "generic" and r.sections[0].title == "Values"
    finally:
        REGISTRY.clear()
        REGISTRY.update(saved)


def test_alerts_in_warnings(tmp_path):
    res = {"status": {"error": "VALID", "warning": ["INCOMPLETE_CI"]}, "v": 1}
    r = run(tmp_path, lambda b: b.add_analysis("A", "CORRELATION", {}, res, alert="Careful", auto_note="Note two"))
    assert r.warnings[:2] == ["Careful", "Note two"]
    assert "INCOMPLETE_CI" in r.warnings


def test_alerts_come_first_even_when_not_calculated(tmp_path):
    r = run(tmp_path, lambda b: b.add_analysis("A", "X", {}, None, is_calculated=False, alert="Al"))
    assert r.warnings == ["Al", NOT_CALC]


def test_nonvalid_error_with_content(tmp_path):
    res = {"status": {"error": "INVALID_DATA_SINGLE_COLUMN", "warning": []}, "v": 1}
    r = run(tmp_path, lambda b: b.add_analysis("A", "CORRELATION", {}, res))
    assert "Prism reported INVALID_DATA_SINGLE_COLUMN" in r.warnings


def test_to_dict_pvalue(tmp_path):
    res = {**OK, "p": pobj(0.01)}
    r = run(tmp_path, lambda b: b.add_analysis("A", "CORRELATION", {}, res))
    d = r.to_dict()
    json.dumps(d)
    assert d["id"] == r.analysis.id and d["title"] == "A" and d["class"] == "CORRELATION"
    assert d["kind"] == "generic" and d["calculated"] is True and isinstance(d["warnings"], list)
    assert d["sections"][0]["rows"] == [["p", {"p": 0.01, "bound": False, "significant": True, "alpha": 0.05}]]
    assert set(d["sections"][0]) == {"title", "columns", "rows", "note"}


def test_generic_sections_direct(tmp_path):
    b = PrismBuilder()
    b.add_analysis("A", "CORRELATION", {}, {**OK, "v": 1})
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        (s,) = generic_sections(pf, pf.analyses()[0])
    assert s.rows == [["v", 1]]
