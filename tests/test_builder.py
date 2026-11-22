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
