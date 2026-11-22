import json
import zipfile

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
