import itertools
import json
import zipfile

import pytest

import prsmfile
from prsmfile.report import is_empty_rows
from prsmfile.tables import read_table
from tests.builder import PrismBuilder


def table_of(tmp_path, b, sid):
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        return read_table(pf, sid)


def test_headers_y_sd_n(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("Ctrl", "y_sd_n", 3), ("B", "y_sd_n", 3)],
                          [list("123456")], row_titles=False)
    t = table_of(tmp_path, b, sid)
    assert t.columns == ["Ctrl Mean", "Ctrl SD", "Ctrl N", "B Mean", "B SD", "B N"]
    assert (t.title, t.table_format, t.data_format) == ("T", "column", "y_sd_n")


def test_headers_with_row_titles(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("Ctrl", "y_sd_n", 3), ("B", "y_sd_n", 3)],
                          [list("r123456")], row_titles=True)
    assert table_of(tmp_path, b, sid).columns[:2] == ["Row title", "Ctrl Mean"]


def test_headers_replicates_and_letters(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("WT", "y_replicates", 3), (None, "y_single", 1)],
                          [list("1234")])
    assert table_of(tmp_path, b, sid).columns == ["WT 1", "WT 2", "WT 3", "B"]


def test_other_formats(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "xy", [("a", "y_se", 2), ("b", "y_plus_minus", 3), ("c", "date_se", 2)],
                          [list("1234567")])
    assert table_of(tmp_path, b, sid).columns == [
        "a Mean", "a SEM", "b Mean", "b Plus", "b Minus", "c 1", "c 2"]


def test_x_series_has_no_column(tmp_path):
    b = PrismBuilder()
    s1 = b.add_raw_table("T", "xy", [("S", "y_single", 1)], [["1"]], x_data_set=(None, "series", 1))
    s2 = b.add_raw_table("T2", "xy", [("S", "y_single", 1)], [["1", "2"]], x_data_set=("Time", "y_single", 1))
    s3 = b.add_raw_table("T3", "xy", [("S", "y_single", 1)], [["1", "2"]], x_data_set=(None, "y_single", 1))
    s4 = b.add_raw_table("T4", "xy", [("S", "y_single", 1)], [list("123")], x_data_set=("D", "y_errorBar", 2))
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        assert read_table(pf, s1).columns == ["S"]
        assert read_table(pf, s2).columns == ["Time", "S"]
        assert read_table(pf, s3).columns == ["X", "S"]
        assert read_table(pf, s4).columns == ["D 1", "D 2", "S"]


def test_subcolumn_titles_nested(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table(
        "T", "column", [("WT", "y_replicates", 3)], [list("123")],
        subcolumn_titles=[{"column": 0, "replicates": [
            {"replicate": 0, "name": "2152"}, {"replicate": 1, "name": {"string": "2153"}}]}])
    assert table_of(tmp_path, b, sid).columns == ["WT 2152", "WT 2153", "WT 3"]


def test_csv_dialect(tmp_path):
    b = PrismBuilder()
    cells = ["WT\r(3 weeks)", "55.00 , 0.000", "Šídák 日本"]
    sid = b.add_raw_table("T", "column", [("a", "text", 1)] * 3, [cells, ["", "", ""]])
    t = table_of(tmp_path, b, sid)
    assert t.rows == [cells, ["", "", ""]]
    sid2 = b.add_raw_table("E", "column", [("a", "text", 1)], [])
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        t = read_table(pf, sid2)
    assert t.rows == []


def test_empty_table_keeps_headers(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("E", "column", [("A", "y_sd", 2), ("B", "y_single", 1)], [])
    t = table_of(tmp_path, b, sid)
    assert t.rows == [] and t.columns == ["A Mean", "A SD", "B"]


def test_width_mismatch(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("W", "column", [("A", "y_single", 1), ("B", "y_single", 1)],
                          [list("12345")])
    assert table_of(tmp_path, b, sid).columns == ["A", "B", "Column 3", "Column 4", "Column 5"]
    sid2 = b.add_raw_table("N", "column", [("A", "y_single", 1), ("B", "y_single", 1)], [["1"]])
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        assert read_table(pf, sid2).columns == ["A"]  # cut to the widest row


def test_raw_vs_result(tmp_path):
    b = PrismBuilder()
    raw = b.add_raw_table("R", "column", [("A", "y_single", 1)], [["1"]])
    b.add_analysis("An", "ONE_WAY_ANOVA", {}, None,
                   views=[("Has", [["a", "b"]]), ("Gone", None), ("Num", [["1", "2", "3"]], "y_sd_n")])
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        assert pf.data_tables() == [raw]
        a = pf.analyses()[0]
        has, gone, num = (pf.result_table(v[1]) for v in a.views)
        assert has.rows == [["a", "b"]] and has.table_format == "view"
        assert has.title == "An:Has" and has.columns == ["A", "B"]
        assert gone is None
        assert num.columns == ["A Mean", "A SD", "A N"]
        assert pf.result_table("nope") is None
        assert read_table(pf, "../x") is None


def test_missing_sheet_and_bad_json(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("R", "column", [("A", "y_single", 1)], [["1"]])
    b.add_member(f"data/sheets/{sid}/sheet.json", b"[1]")
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        assert read_table(pf, sid) is None
        assert any("not a JSON object" in w for w in pf.warnings)


def test_is_empty_rows():
    assert is_empty_rows([]) and is_empty_rows([["", " "], [None]])
    assert not is_empty_rows([["", "x"]]) and not is_empty_rows([[0]])


def rewrite_document(path, fn):
    with zipfile.ZipFile(path) as z:
        items = [(n, z.read(n)) for n in z.namelist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in items:
            if n == "document.json":
                doc = json.loads(d)
                fn(doc)
                d = json.dumps(doc).encode()
            z.writestr(n, d)


def put_json(b, name, **changes):
    obj = json.loads(b._members[name])
    obj.update(changes)
    b.add_member(name, json.dumps(obj).encode())


def test_y_plus_minus_width_two(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("a", "y_plus_minus", 2)], [["1", "2"]])
    assert table_of(tmp_path, b, sid).columns == ["a Mean", "a Plus"]


def test_missing_x_data_set_file_reserves_column(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "xy", [("S", "y_single", 1)], [["1", "2"]], x_data_set=("T", "y_single", 1))
    xuid = json.loads(b._members[f"data/sheets/{sid}/sheet.json"])["table"]["xDataSet"]
    del b._members[f"data/sets/{xuid}.json"]
    assert table_of(tmp_path, b, sid).columns == ["X", "S"]
    b2 = PrismBuilder()
    sid2 = b2.add_raw_table("T", "xy", [("S", "y_single", 1)], [list("123")], x_data_set=("T", "y_errorBar", 2))
    xuid = json.loads(b2._members[f"data/sheets/{sid2}/sheet.json"])["table"]["xDataSet"]
    del b2._members[f"data/sets/{xuid}.json"]
    assert table_of(tmp_path, b2, sid2).columns == ["X 1", "X 2", "S"]


def test_missing_csv_with_folder_warns_empty(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("My table", "column", [("A", "y_single", 1)], [["1"]])
    t_uid = json.loads(b._members[f"data/sheets/{sid}/sheet.json"])["table"]["uid"]
    del b._members[f"data/tables/{t_uid}/data.csv"]
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        t = read_table(pf, sid)
        assert t.rows == [] and t.columns == ["A"]
        assert "Missing data.csv for table My table" in pf.warnings


def test_zero_byte_csv_no_warning(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("E", "column", [("A", "y_single", 1)], [])
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        assert read_table(pf, sid).rows == [] and pf.warnings == []


def test_undecodable_csv_is_none(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("A", "y_single", 1)], [["1"]])
    t_uid = json.loads(b._members[f"data/sheets/{sid}/sheet.json"])["table"]["uid"]
    b.add_member(f"data/tables/{t_uid}/data.csv", b"\xff\xfe,1\n")
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        assert read_table(pf, sid) is None
        assert any("data.csv" in w for w in pf.warnings)


def test_unclosed_quote_is_none(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("A", "y_single", 1)], [["1"]])
    t_uid = json.loads(b._members[f"data/sheets/{sid}/sheet.json"])["table"]["uid"]
    b.add_member(f"data/tables/{t_uid}/data.csv", b'1,"abc\n2,3\n')
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        assert read_table(pf, sid) is None
        assert any("Could not parse" in w for w in pf.warnings)


def test_malformed_metadata_never_raises(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("A", "y_replicates", 2), ("B", "y_sd", 2)], [list("1234")],
                          subcolumn_titles=[{"column": 0, "replicates": [{"replicate": 0, "name": "x"}]}])
    t = json.loads(b._members[f"data/sheets/{sid}/sheet.json"])["table"]
    sub = t["subcolumnTitlesDataSet"]
    b.add_member(f"data/sets/{sub}.json", json.dumps({"titles": [
        {"column": 0, "replicates": 5}, {"column": 1, "replicates": None},
        "junk", {"column": [0], "replicates": []},
        {"column": 0, "replicates": [{"replicate": 1, "name": ["l"]}, "x", {"replicate": {}, "name": "q"}]}]}).encode())
    a_uid = t["dataSets"][0]
    put_json(b, f"data/sets/{a_uid}.json", format=["list"])  # unhashable format
    b_uid = t["dataSets"][1]
    put_json(b, f"data/sets/{b_uid}.json", format={"a": 1}, replicates=7)
    put_json(b, f"data/sheets/{sid}/sheet.json", title=5)
    t = table_of(tmp_path, b, sid)
    assert t is not None and len(t.columns) == 4


def test_unhashable_x_format(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "xy", [("S", "y_single", 1)], [["1", "2"]], x_data_set=("T", "y_single", 1))
    xuid = json.loads(b._members[f"data/sheets/{sid}/sheet.json"])["table"]["xDataSet"]
    put_json(b, f"data/sets/{xuid}.json", format=["x"])
    put_json(b, f"data/sheets/{sid}/sheet.json", table={**json.loads(b._members[f"data/sheets/{sid}/sheet.json"])["table"], "format": ["y"], "dataFormat": {}})
    t = table_of(tmp_path, b, sid)
    assert t.columns == ["T", "S"] and t.table_format is None and t.data_format is None


def test_integral_float_subcolumn_indices(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("WT", "y_replicates", 2)], [["1", "2"]],
                          subcolumn_titles=[{"column": 0.0, "replicates": [{"replicate": 1.0, "name": "b"}]}])
    assert table_of(tmp_path, b, sid).columns == ["WT 1", "WT b"]


def test_replicate_ranges_width(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("A", "y_replicates", 1), ("B", "y_single", 1)],
                          [list("1234")])
    a_uid = b.data_sets(sid)[0]
    obj = json.loads(b._members[f"data/sets/{a_uid}.json"])
    del obj["replicates"]
    obj["replicate ranges"] = [{"range": "0", "replicate": {}}, {"range": "1~2", "replicate": {}}]
    b.add_member(f"data/sets/{a_uid}.json", json.dumps(obj).encode())
    assert table_of(tmp_path, b, sid).columns == ["A 1", "A 2", "A 3", "B"]


def test_structured_data_set_title(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("A", "y_single", 1), ("B", "y_single", 1)], [["1", "2"]])
    uid = b.data_sets(sid)[0]
    put_json(b, f"data/sets/{uid}.json", title={"string": "Fancy\rTitle", "version": 1})
    assert table_of(tmp_path, b, sid).columns == ["Fancy\rTitle", "B"]


def test_row_titles_and_x_order(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "xy", [("S", "y_single", 1)], [list("rxy")], row_titles=True,
                          x_data_set=("Time", "y_single", 1))
    assert table_of(tmp_path, b, sid).columns == ["Row title", "Time", "S"]


def test_subcolumn_titles_on_second_data_set(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("A", "y_replicates", 2), ("B", "y_replicates", 2)], [list("1234")],
                          subcolumn_titles=[{"column": 1, "replicates": [{"replicate": 1, "name": "z"}]}])
    assert table_of(tmp_path, b, sid).columns == ["A 1", "A 2", "B 1", "B z"]


def test_width_mismatch_short_first_row(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("A", "y_single", 1), ("B", "y_single", 1)], [["1"], list("1234")])
    t = table_of(tmp_path, b, sid)
    assert t.columns == ["A", "B", "Column 3", "Column 4"]
    assert t.rows == [["1"], list("1234")]  # rows are not padded


@pytest.mark.parametrize("fmt", ["column", "xy"])
def test_result_view_with_data_format_tables(tmp_path, fmt):
    b = PrismBuilder()
    aid = b.add_analysis("An", "ONE_WAY_ANOVA", {}, None, views=[("V", [["1", "2"]], "y_replicates")])
    sheet = json.loads(b._members[f"analyses/{aid}/sheet.json"])
    view = json.loads(b._members[f"analyses/{aid}/result_sheets/{sheet['resultSheets'][0]['uid']}.json"])
    rname = f"data/sheets/{view['dataSheet']}/sheet.json"
    r = json.loads(b._members[rname])
    r["table"]["format"] = fmt
    b.add_member(rname, json.dumps(r).encode())
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        t = pf.result_table(view["dataSheet"])
        assert t is not None and t.table_format == fmt and t.rows == [["1", "2"]]
        assert pf.data_tables() == []


def test_result_table_only_for_view_sheets(tmp_path):
    b = PrismBuilder()
    raw = b.add_raw_table("R", "column", [("A", "y_single", 1)], [["1"]])
    b.add_analysis("An", "ONE_WAY_ANOVA", {}, None, views=[("V", [["x"]])])
    b.add_raw_table("Orphan", "column", [("A", "y_single", 1)], [["1"]])
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        assert pf.result_table(raw) is None
        ds = pf.analyses()[0].views[0][1]
        assert pf.result_table(ds).rows == [["x"]]


def test_raw_tables_listed_order(tmp_path):
    b = PrismBuilder()
    ids = [b.add_raw_table(t, "column", [("A", "y_single", 1)], [["1"]]) for t in ("Mid", "Zed", "Abe")]
    p = b.save(tmp_path / "t.prism")
    title_order = [ids[2], ids[0], ids[1]]  # Abe, Mid, Zed
    pick = next(o for o in itertools.permutations(ids)
                if list(o) not in (ids, sorted(ids), title_order))
    rewrite_document(p, lambda d: d["sheets"].__setitem__("data", list(pick)))
    with prsmfile.open(p) as pf:
        assert pf.data_tables() == list(pick)


@pytest.mark.parametrize("bad", [[], ["a", "b"], [5], 5, {"x": 1}, "a/b", "", None, " ", "invalid-ref"])
def test_invalid_x_reference_reserves_no_column(tmp_path, bad):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "xy", [("S", "y_single", 1)], [["2"]], x_data_set=("T", "y_single", 1))
    table = json.loads(b._members[f"data/sheets/{sid}/sheet.json"])["table"]
    table["xDataSet"] = bad
    put_json(b, f"data/sheets/{sid}/sheet.json", table=table)
    assert table_of(tmp_path, b, sid).columns == ["S"]


def test_result_table_does_not_load_analysis_content(tmp_path):
    b = PrismBuilder()
    b.add_analysis("An", "ONE_WAY_ANOVA", {}, {"status": {"error": "VALID"}}, views=[("V", [["x"]])])
    p = b.save(tmp_path / "t.prism")
    with prsmfile.open(p) as pf:
        ds = next(n for n in pf._names if n.startswith("data/sheets/")).split("/")[2]
        reads = []
        orig = pf.read_json
        pf.read_json = lambda name: (reads.append(name), orig(name))[1]
        assert pf.result_table(ds).rows == [["x"]]
        assert pf.result_table(ds) is not None
        assert not any(n.endswith(("parameters.json", "results.json")) for n in reads)
        assert pf._analyses is None
        n_first = len(reads)
        pf.result_table(ds)
        assert not any("analyses/" in n for n in reads[n_first:])


def test_result_table_independent_of_mutable_views(tmp_path):
    b = PrismBuilder()
    raw = b.add_raw_table("R", "column", [("A", "y_single", 1)], [["1"]])
    b.add_analysis("An", "ONE_WAY_ANOVA", {}, None, views=[("V", [["x"]])])
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        a = pf.analyses()[0]
        real = a.views[0][1]
        a.views.append(("evil", raw))
        a.views.clear()
        assert pf.result_table(raw) is None
        assert pf.result_table(real).rows == [["x"]]
        assert pf.analyses()[0].views[0][1] == real
        pf.analyses()[0].views.clear()
        assert pf.analyses()[0].views[0][1] == real


def test_result_table_unhashable_id(tmp_path):
    b = PrismBuilder()
    b.add_raw_table("R", "column", [("A", "y_single", 1)], [["1"]])
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        assert pf.result_table(["x"]) is None
        assert pf.result_table({}) is None
        assert pf.result_table(None) is None


def test_result_table_orphan_sheet_is_none(tmp_path):
    b = PrismBuilder()
    orphan = b.add_raw_table("Orphan", "column", [("A", "y_single", 1)], [["1"]])
    b.add_analysis("An", "ONE_WAY_ANOVA", {}, None, views=[("V", [["x"]])])
    p = b.save(tmp_path / "t.prism")
    rewrite_document(p, lambda d: d["sheets"].__setitem__("data", []))
    with prsmfile.open(p) as pf:
        assert pf.data_tables() == []
        assert read_table(pf, orphan) is not None  # the member exists
        assert pf.result_table(orphan) is None


def test_view_sort_adjacent_huge_ints_reverse_stored(tmp_path):
    b = PrismBuilder()
    b.add_analysis("An", "ONE_WAY_ANOVA", {}, None, views=[("First", [["1"]]), ("Second", [["2"]])])
    for name in [n for n in b._members if "/result_sheets/" in n]:
        obj = json.loads(b._members[name])
        big = {"First": 9007199254740992, "Second": 9007199254740993}[obj["name"]]
        # stored in reverse of the sort order
        b.add_member(name, json.dumps({**obj, "viewIdx": big}).encode())
    sheet = next(n for n in b._members if n.endswith("/sheet.json") and n.startswith("analyses/"))
    obj = json.loads(b._members[sheet])
    obj["resultSheets"].reverse()
    b.add_member(sheet, json.dumps(obj).encode())
    with prsmfile.open(b.save(tmp_path / "t.prism")) as pf:
        assert [v[0] for v in pf.analyses()[0].views] == ["First", "Second"]
