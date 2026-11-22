import json
import zipfile

from tests.builder import PrismBuilder


def members(p):
    with zipfile.ZipFile(p) as z:
        return {n: z.read(n) for n in z.namelist()}


def js(m, name):
    return json.loads(m[name].decode("utf-8"))


def test_inputs_reference_real_data_sets(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("Raw", "column", [("WT", "y_replicates", 2), ("KO", "y_replicates", 2)],
                          [["1", "2", "3", "4"]])
    aid = b.add_analysis("An", "ONE_WAY_ANOVA", {}, None,
                         inputs=[("A", "WT", (sid, 0)), ("B", "KO"), ("C", "gone")])
    m = members(b.save(tmp_path / "a.prism"))
    sheet = js(m, f"analyses/{aid}/sheet.json")
    raw = js(m, f"data/sheets/{sid}/sheet.json")
    sets = raw["table"]["dataSets"]
    assert [i["uid"] for i in sheet["inputDataSets"][:2]] == sets
    assert all(f"data/sets/{u}.json" in m for u in sets)
    assert sheet["inputDataSets"][2]["uid"] not in sets  # out of range: dangling, like the corpus
    assert sheet["inputSheets"] == [{"uid": sid, "title": "Raw"}]
    assert b.data_sets(sid) == sets


def test_view_tables_declare_data_sets(tmp_path):
    b = PrismBuilder()
    aid = b.add_analysis("An", "ONE_WAY_ANOVA", {}, None, views=[("V", [["a", "b", "c"], ["d"]])])
    m = members(b.save(tmp_path / "a.prism"))
    view = js(m, [n for n in m if "/result_sheets/" in n][0])
    table = js(m, f"data/sheets/{view['dataSheet']}/sheet.json")["table"]
    assert table["format"] == "view" and len(table["dataSets"]) == 3
    assert view["dataSheet"] not in b._data_ids


def test_raw_table_shape(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("XY", "xy", [("S1", "y_sd", 2)], [["1", "2", "3"]],
                          x_data_set=("X", "y_single", 1),
                          subcolumn_titles=[{"column": 0, "replicates": [{"replicate": 0, "name": "a"}]}])
    sid2 = b.add_raw_table("Txt", "column", [("T", "text", 1)], [["a"]])
    sid3 = b.add_raw_table("None", "column", [], [])
    m = members(b.save(tmp_path / "a.prism"))
    t = js(m, f"data/sheets/{sid}/sheet.json")["table"]
    assert t["@class"] == "XYDataTable" and t["dataFormat"] == "y_sd"
    sub = js(m, f"data/sets/{t['subcolumnTitlesDataSet']}.json")
    assert sub["replicate count"] == 2  # declared width, not number of titles
    t2 = js(m, f"data/sheets/{sid2}/sheet.json")["table"]
    assert t2["@class"] == "DataTable" and t2["dataFormat"] == "text"
    assert js(m, f"data/sheets/{sid3}/sheet.json")["table"]["dataSets"] == []


def test_numeric_view_data_set_widths(tmp_path):
    b = PrismBuilder()
    cases = [("y_sd_n", 6, [("y_sd_n", 3)] * 2), ("y_sd", 4, [("y_sd", 2)] * 2),
             ("y_se", 2, [("y_se", 2)]), ("y_plus_minus", 3, [("y_plus_minus", 3)]),
             ("date_se", 4, [("date_se", 2)] * 2), ("y_errorBar", 2, [("y_errorBar", 2)]),
             ("y_single", 2, [("y_single", 1)] * 2), ("text", 2, [("text", 1)] * 2)]
    for i, (fmt, n, _) in enumerate(cases):
        b.add_analysis(f"A{i}", "ONE_WAY_ANOVA", {}, None, views=[("V", [list("abcdef"[:n])], fmt)])
    m = members(b.save(tmp_path / "a.prism"))
    got = {}
    for name in sorted(n for n in m if "/result_sheets/" in n):
        view = js(m, name)
        table = js(m, f"data/sheets/{view['dataSheet']}/sheet.json")["table"]
        sets = [js(m, f"data/sets/{u}.json") for u in table["dataSets"]]
        got[table["dataFormat"]] = [(d["format"], len(d["replicates"])) for d in sets]
    assert got == {fmt: exp for fmt, _, exp in cases}


def test_empty_view_declares_data_sets(tmp_path):
    b = PrismBuilder()
    b.add_analysis("A", "ONE_WAY_ANOVA", {}, None, views=[("V", [], "y_sd_n", 6)])
    b.add_analysis("B", "ONE_WAY_ANOVA", {}, None, views=[("V", [], "text", 2)])
    m = members(b.save(tmp_path / "a.prism"))
    got = []
    for name in sorted(n for n in m if "/result_sheets/" in n):
        view = js(m, name)
        t = js(m, f"data/sheets/{view['dataSheet']}/sheet.json")["table"]
        got.append((t["dataFormat"], len(t["dataSets"])))
    assert sorted(got) == [("text", 2), ("y_sd_n", 2)]


def test_input_autolink_multi_letter_and_none(tmp_path):
    b = PrismBuilder()
    sets = [(f"c{i}", "y_single", 1) for i in range(28)]
    sid = b.add_raw_table("Wide", "column", sets, [["1"] * 28])
    aid = b.add_analysis("An", "ONE_WAY_ANOVA", {}, None,
                         inputs=[("AA", "c26"), (None, "nolabel"), ("B", None)])
    m = members(b.save(tmp_path / "a.prism"))
    sheet = js(m, f"analyses/{aid}/sheet.json")
    ids = b.data_sets(sid)
    assert sheet["inputDataSets"][0]["uid"] == ids[26]
    assert "idx" not in sheet["inputDataSets"][1]
    assert sheet["inputDataSets"][2]["uid"] == ids[1]


def test_explicit_uid_ref_adds_owning_sheet(tmp_path):
    b = PrismBuilder()
    s1 = b.add_raw_table("One", "column", [("a", "y_single", 1)], [["1"]])
    s2 = b.add_raw_table("Two", "column", [("b", "y_single", 1)], [["2"]])
    uid = b.data_sets(s1)[0]
    aid = b.add_analysis("An", "ONE_WAY_ANOVA", {}, None, inputs=[("A", "a", uid)])
    m = members(b.save(tmp_path / "a.prism"))
    assert js(m, f"analyses/{aid}/sheet.json")["inputSheets"] == [{"uid": s1, "title": "One"}]


def test_saved_zip_structure(tmp_path):
    b = PrismBuilder()
    s1 = b.add_raw_table("Raw", "column", [("a", "y_single", 1)], [["1"]])
    aid = b.add_analysis("An", "ONE_WAY_ANOVA", {}, None, views=[("V", [["x"]])])
    p = b.save(tmp_path / "a.prism")
    with zipfile.ZipFile(p) as z:
        assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in z.infolist())
    m = members(p)
    doc = js(m, "document.json")
    assert doc["sheets"]["data"] == [s1]  # raw tables only, no result sheets
    assert doc["sheets"]["analyses"] == [aid]
    table_uid = js(m, f"data/sheets/{s1}/sheet.json")["table"]["uid"]
    assert table_uid != s1
    assert f"data/tables/{table_uid}/data.csv" in m
    view = js(m, [n for n in m if "/result_sheets/" in n][0])
    rt = js(m, f"data/sheets/{view['dataSheet']}/sheet.json")["table"]["uid"]
    assert rt != view["dataSheet"]


def test_csv_quotes_cr_and_lf(tmp_path):
    b = PrismBuilder()
    sid = b.add_raw_table("T", "column", [("a", "text", 1)], [["x\ry"], ["p\nq"], ["a,b"], ['q"q'], ["plain"]])
    m = members(b.save(tmp_path / "a.prism"))
    t = js(m, f"data/sheets/{sid}/sheet.json")["table"]["uid"]
    assert m[f"data/tables/{t}/data.csv"] == '"x\ry"\n"p\nq"\n"a,b"\n"q""q"\nplain\n'.encode()


def test_view_per_data_set_width_override(tmp_path):
    b = PrismBuilder()
    b.add_analysis("A", "ONE_WAY_ANOVA", {}, None, views=[("V", [list("abcdef")], "y_replicates", 6, 3)])
    m = members(b.save(tmp_path / "a.prism"))
    view = js(m, [n for n in m if "/result_sheets/" in n][0])
    t = js(m, f"data/sheets/{view['dataSheet']}/sheet.json")["table"]
    assert [len(js(m, f"data/sets/{u}.json")["replicates"]) for u in t["dataSets"]] == [3, 3]


def test_explicit_uid_from_result_view_adds_its_sheet(tmp_path):
    b = PrismBuilder()
    b.add_analysis("First", "ONE_WAY_ANOVA", {}, None, views=[("V", [["1", "2"]])])
    result_sheet = list(b._sets)[0]
    a2 = b.add_analysis("Chained", "ONE_WAY_ANOVA", {}, None,
                        inputs=[("A", "c", b.data_sets(result_sheet)[0])])
    m = members(b.save(tmp_path / "y.prism"))
    assert js(m, f"analyses/{a2}/sheet.json")["inputSheets"] == [{"uid": result_sheet, "title": "First:V"}]
