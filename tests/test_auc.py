import prsmfile
from prsmfile import read_analysis
from tests.builder import PrismBuilder
from tests.helpers import assert_sections_well_formed

OK = {"error": "VALID", "warning": []}


def peak(first, last, px, py, area, pct):
    return {"firstX": first, "lastX": last, "peakX": px, "peakY": py, "area": area, "areaPercentage": pct}


def sample(idx, title, peaks, base=0.0):
    c = {"uid": f"U{idx}", "idx": idx}
    if title is not None:
        c["title"] = title
    return {"id": {"col": c},
            "value": {"status": "VALID",
                      "summary": {"baseline": base, "peakCount": len(peaks), "totalArea": 1.5,
                                  "totalPeakArea": 1.25},
                      "peaks": peaks}}


def run(tmp_path, results):
    b = PrismBuilder()
    b.add_analysis("U", "AREA_UNDER_CURVE", {"calc": {}}, results, inputs=(("A", "DD"), ("B", "EE")))
    with prsmfile.open(b.save(tmp_path / "u.prism")) as pf:
        r = read_analysis(pf, pf.analyses()[0])
    assert_sections_well_formed(r)
    return r


def sec(r, title):
    (s,) = [s for s in r.sections if s.title == title]
    return s


def test_auc_summary_and_peaks(tmp_path):
    r = run(tmp_path, {"status": OK, "samples": {
        "b": sample(1, "EE", {"Peak 1": peak(0, 1, 0.5, 2.0, 0.5, 100.0)}),
        "a": sample(0, "DD", {"Peak 1": peak(0.0, 0.5, 0.25, 0.54, 0.1355, 100.0)}, base=0.1)}})
    assert r.kind == "structured" and r.warnings == []
    assert [s.title for s in r.sections] == ["Area under curve", "Peaks"]
    t = sec(r, "Area under curve")
    assert t.columns == ["Data set", "Baseline", "Total area", "Total peak area", "Peaks"]
    assert t.rows == [["A:DD", 0.1, 1.5, 1.25, 1.0], ["B:EE", 0.0, 1.5, 1.25, 1.0]]
    assert sec(r, "Peaks").rows[0] == ["A:DD", "Peak 1", 0.0, 0.5, 0.25, 0.54, 0.1355, 100.0]


def test_auc_peaks_order(tmp_path):
    peaks = {"Peak 10": peak(9, 10, 9.5, 1, 0.0, "undefined"), "Peak 2": peak(1, 2, 1.5, 1, 0.3, 30.0),
             "Peak 1": peak(0, 1, 0.5, 1, 0.7, 70.0)}
    r = run(tmp_path, {"status": OK, "samples": {"a": sample(0, "DD", peaks)}})
    rows = sec(r, "Peaks").columns, sec(r, "Peaks").rows
    assert rows[0] == ["Data set", "Peak", "First X", "Last X", "Peak X", "Peak Y", "Area", "Area %"]
    assert [x[1] for x in rows[1]] == ["Peak 1", "Peak 2", "Peak 10"]
    assert rows[1][2][7] is None and rows[1][2][6] == 0.0


def test_auc_garbage_does_not_raise(tmp_path):
    r = run(tmp_path, {"status": OK, "samples": {"k": {"id": {}, "value": {"summary": 3, "peaks": [1]}}}})
    assert r.kind == "structured"
