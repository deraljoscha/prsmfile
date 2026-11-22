from __future__ import annotations

from prsmfile.values import PValue, ci, dataset_title, entries, label, letter, num


def test_num():
    assert num(3) == 3 and isinstance(num(3), int) and not isinstance(num(3), bool)
    assert isinstance(num(3.0), float)
    assert num(2.5) == 2.5
    assert num("undefined") is None
    assert num(None) is None
    assert num(True) is None


def test_pvalue():
    p = PValue.from_obj({"value": 0.01, "level": 0.05, "isSignificant": True, "state": "P_VALUE_EQUAL"})
    assert p == PValue(0.01, 0.05, True, False)
    g = PValue.from_obj({"value": 0.1, "level": 0.05, "isSignificant": False, "state": "P_VALUE_GREATER"})
    assert g.bound is True
    u = PValue.from_obj({"value": "undefined", "level": 0.05, "state": "P_VALUE_EQUAL"})
    assert u.value is None and u.significant is None
    assert PValue.from_obj(None) is None


def test_ci():
    assert ci({"lower": 1, "upper": "undefined", "level": 95.0}) == (1.0, None, 95.0)
    assert ci(None) == (None, None, None)


def _col(i, title=None):
    c = {"idx": i}
    if title is not None:
        c["title"] = title
    return {"col": c}


def test_entries_sorted():
    coll = {
        "h1": {"id": _col(2), "value": "c"},
        "h2": {"id": _col(0), "value": "a"},
        "h3": {"id": _col(1), "value": "b"},
    }
    assert [v for _, v in entries(coll)] == ["a", "b", "c"]
    assert entries(None) == []

    coll = {
        "h1": {"id": {"col": {"idx": 0}}, "value": "col"},
        "h2": {"id": {"row": {"idx": 3}}, "value": "row"},
    }
    assert [v for _, v in entries(coll)] == ["row", "col"]

    coll = {
        "h1": {"id": {"col": {"idx": 0}, "model": {"name": "Model 2"}}, "value": 2},
        "h2": {"id": {"col": {"idx": 0}, "model": {"name": "Model 1"}}, "value": 1},
    }
    assert [v for _, v in entries(coll)] == [1, 2]

    coll = {
        "h1": {"id": [_col(1), _col(0)], "value": "x"},
        "h2": {"id": [_col(0), _col(2)], "value": "y"},
    }
    assert [v for _, v in entries(coll)] == ["y", "x"]


def test_label_shapes():
    assert label(_col(0, "WT")) == "A:WT"
    assert label(_col(1)) == "B"
    assert label(_col(1, "  ")) == "B"
    assert label(_col(0, "WT"), with_letter=False) == "WT"
    assert label(_col(1), with_letter=False) == "B"
    assert label({"row": {"idx": 0, "title": "Day 1"}}) == "row 1:Day 1"
    assert label({"row": {"idx": 1}}) == "row 2"
    assert label({"col": {"idx": 0, "title": "WT"}, "row": {"idx": 0, "title": "Day 1"}}) == "row 1:Day 1 A:WT"
    assert label({"col": {"idx": 0, "title": "WT"}, "model": {"name": "Model 1", "title": "Top"}}) == "A:WT:Top"
    assert label({"col": {"idx": 0, "title": "WT"}, "model": {"name": "Model 1"}}) == "A:WT:Model 1"
    assert label({}) == ""
    assert label([_col(0, "a"), _col(1, "b")]) == "A:a vs B:b"
    assert label(_col(0, "aCSF")) == "A:aCSF"
    assert label(_col(2, "aCSF")) == "C:aCSF"


def test_letter():
    assert letter(0) == "A"
    assert letter(25) == "Z"
    assert letter(26) == "AA"
    assert letter(27) == "AB"
    assert letter(701) == "ZZ"
    assert letter(702) == "AAA"


def test_dataset_title():
    assert dataset_title({"title": "Control"}) == "Control"
    assert dataset_title({"title": {"string": "a\rb"}}) == "a\rb"
    assert dataset_title({"title": "  "}) is None
    assert dataset_title({"title": {"string": ""}}) is None
    assert dataset_title({}) is None


def test_pvalue_greater_value():
    g = PValue.from_obj({"value": 0.1, "level": 0.05, "isSignificant": False, "state": "P_VALUE_GREATER"})
    assert g.value == 0.1 and g.bound is True


def test_ci_numeric_upper():
    assert ci({"lower": 1, "upper": 2.5, "level": 95.0}) == (1.0, 2.5, 95.0)


def test_entries_ids_and_float_idx():
    a, b, c = _col(2.0), _col(0.0), _col(1)
    coll = {"h1": {"id": a, "value": 1}, "h2": {"id": b, "value": 2}, "h3": {"id": c, "value": 3}}
    assert [i for i, _ in entries(coll)] == [b, c, a]


def test_entries_row_precedes_col_and_ties_stable():
    r = {"row": {"idx": 5}, "col": {"idx": 0}}
    s = {"row": {"idx": 1}, "col": {"idx": 9}}
    coll = {"h1": {"id": r, "value": 1}, "h2": {"id": s, "value": 2}}
    assert [i for i, _ in entries(coll)] == [s, r]
    t1, t2 = _col(0, "x"), _col(0, "y")
    coll = {"h1": {"id": t1, "value": 1}, "h2": {"id": t2, "value": 2}}
    assert [i for i, _ in entries(coll)] == [t1, t2]


def test_entries_missing_model_name_last():
    m1 = {"col": {"idx": 0}, "model": {"name": "Model 1"}}
    m0 = {"col": {"idx": 0}, "model": {}}
    coll = {"h1": {"id": m0, "value": 0}, "h2": {"id": m1, "value": 1}}
    assert [i for i, _ in entries(coll)] == [m1, m0]


def test_label_float_idx_and_combined():
    assert label({"col": {"idx": 2.0, "title": "x"}}) == "C:x"
    assert label({"row": {"idx": 0.0}}) == "row 1"
    assert label({"col": {"idx": True}}) == ""
    assert label({"row": {"idx": 0, "title": "Day 1"}, "col": {"idx": 0, "title": "WT"},
                  "model": {"name": "Model 1", "title": "Top"}}) == "row 1:Day 1 A:WT:Top"
    assert label({"col": {"idx": 0, "title": "WT"}, "model": {"name": "Model 1", "title": " "}}) == "A:WT:Model 1"


def test_num_huge_int_is_none():
    assert num(10**400) is None
