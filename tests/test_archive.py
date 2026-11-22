import json
import zipfile

import pytest

import prsmfile
from prsmfile import PrismFormatError
from prsmfile.archive import Analysis, PrismFile
from tests.builder import PrismBuilder


def build(tmp_path, **kw):
    b = PrismBuilder()
    return b, lambda: b.save(tmp_path / "t.prism", **kw)


def test_open_reads_versions(tmp_path):
    b = PrismBuilder()
    p = b.save(tmp_path / "a.prism", format_version="1-6-1", prism_version="11.1.0.224")
    with prsmfile.open(p) as pf:
        assert isinstance(pf, PrismFile)
        assert pf.format_version == (1, 6, 1)
        assert pf.format_version_raw == "1-6-1"
        assert pf.prism_version == "11.1.0.224"
        assert pf.saved_with == "11.1.0.224"
        assert pf.warnings == []
        assert pf.analyses() == []


def test_major_version_warns(tmp_path):
    p = PrismBuilder().save(tmp_path / "a.prism", format_version="2-0-0")
    with prsmfile.open(p) as pf:
        assert pf.format_version == (2, 0, 0)
        assert len(pf.warnings) == 1
        assert "2-0-0" in pf.warnings[0]


def test_not_a_zip(tmp_path):
    t = tmp_path / "x.prism"
    t.write_text("hello")
    with pytest.raises(PrismFormatError) as e:
        prsmfile.open(t)
    assert str(t) in str(e.value)
    t.write_bytes(b"\x00\x01")
    with pytest.raises(PrismFormatError) as e:
        prsmfile.open(t)
    assert str(t) in str(e.value)


def test_missing_file(tmp_path):
    t = tmp_path / "nope.prism"
    with pytest.raises(PrismFormatError) as e:
        prsmfile.open(t)
    assert str(t) in str(e.value)
    with pytest.raises(PrismFormatError):
        prsmfile.open(tmp_path)  # a directory


def test_zip_without_document(tmp_path):
    t = tmp_path / "z.prism"
    with zipfile.ZipFile(t, "w") as z:
        z.writestr("other.json", "{}")
    with pytest.raises(PrismFormatError) as e:
        prsmfile.open(t)
    assert "document.json" in str(e.value)


def test_document_root_not_dict(tmp_path):
    t = tmp_path / "z.prism"
    with zipfile.ZipFile(t, "w") as z:
        z.writestr("document.json", "[1, 2]")
    with pytest.raises(PrismFormatError):
        prsmfile.open(t)
    with zipfile.ZipFile(t, "w") as z:
        z.writestr("document.json", "{not json")
    with pytest.raises(PrismFormatError):
        prsmfile.open(t)


def test_analyses_found_without_listing(tmp_path):
    b = PrismBuilder()
    b.add_analysis("Zeta", "ONE_WAY_ANOVA", {}, {"status": {}}, listed=False)
    b.add_analysis("Alpha", "ONE_WAY_ANOVA", {}, {"status": {}}, listed=False)
    listed = b.add_analysis("Listed", "T_TESTS_AND_NONPARAMETRIC", {}, {"status": {}})
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        a = pf.analyses()
        assert [x.title for x in a] == ["Listed", "Alpha", "Zeta"]
        assert a[0].id == listed
        assert a[0].analysis_class == "T_TESTS_AND_NONPARAMETRIC"


def test_corrupt_analysis_sheet_skipped(tmp_path):
    b = PrismBuilder()
    bad = b.add_analysis("Bad", "ONE_WAY_ANOVA", {}, {"status": {}})
    b.add_analysis("Good", "ONE_WAY_ANOVA", {}, {"status": {}})
    b.add_member(f"analyses/{bad}/sheet.json", b"{not json")
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        assert [x.title for x in pf.analyses()] == ["Good"]
        assert f"Skipped analysis {bad}: unreadable sheet.json" in pf.warnings
    b.add_member(f"analyses/{bad}/sheet.json", b"[1]")
    with prsmfile.open(b.save(tmp_path / "b.prism")) as pf:
        assert [x.title for x in pf.analyses()] == ["Good"]
        assert f"Skipped analysis {bad}: unreadable sheet.json" in pf.warnings


def test_stub_results(tmp_path):
    b = PrismBuilder()
    b.add_analysis("calc", "ONE_WAY_ANOVA", {"x": 1}, {"status": {"error": "VALID"}}, is_calculated=True)
    b.add_analysis("not", "ONE_WAY_ANOVA", {}, None, is_calculated=False)
    b.add_analysis("unk", "ONE_WAY_ANOVA", {}, None, is_calculated=None)
    b.add_analysis(None, "ONE_WAY_ANOVA", {}, None, is_calculated=None)
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        by = {a.title: a for a in pf.analyses()}
    assert by["calc"].is_calculated is True and by["calc"].has_results
    assert by["calc"].results == {"status": {"error": "VALID"}}
    assert by["calc"].parameters == {"x": 1}
    assert by["not"].is_calculated is False and not by["not"].has_results
    assert by["not"].results is None
    assert by["unk"].is_calculated is None and by["unk"].results is None
    assert "(untitled)" in by


def test_inputs_and_views(tmp_path):
    b = PrismBuilder()
    b.add_analysis(
        "A1", "ONE_WAY_ANOVA", {}, {"status": {}},
        inputs=[("A", "WT"), None, ("B", "  "), ("C", None)],
        views=[("ANOVA results", [["x", "1"]]), ("Multiple comparisons", None)],
    )
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        a = pf.analyses()[0]
    assert a.inputs == [("A", "WT"), ("B", "B"), ("C", "C")]
    assert [v[0] for v in a.views] == ["ANOVA results", "Multiple comparisons"]
    assert all(isinstance(v[1], str) for v in a.views)


def test_alerts_collected_and_deduped(tmp_path):
    b = PrismBuilder()
    aid = b.add_analysis(
        "A1", "ONE_WAY_ANOVA", {}, {"status": {}},
        alert="Warning: data\nnot normal", auto_note="Warning: data\rnot  normal\r\r",
    )
    b.add_member(
        "graphs/G1/floating_notes/n.json",
        json.dumps({"isAuto": True, "text": {"string": "graph note"}}).encode(),
    )
    b.add_member(
        f"analyses/{aid}/floating_notes/manual.json",
        json.dumps({"isAuto": False, "text": {"string": "user note"}}).encode(),
    )
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        a = pf.analyses()[0]
    assert a.alerts == ["Warning: data not normal"]


def test_media_never_read(tmp_path, monkeypatch):
    b = PrismBuilder()
    b.add_analysis("A1", "ONE_WAY_ANOVA", {}, {"status": {}})
    b.add_member("media/pic.svg", b"<svg/>")
    b.add_member("misc/x.bin", b"\x00")
    p = b.save(tmp_path / "a.prism")
    opened = []
    orig_open, orig_read = zipfile.ZipFile.open, zipfile.ZipFile.read

    def spy_open(self, name, *a, **k):
        opened.append(getattr(name, "filename", name))
        return orig_open(self, name, *a, **k)

    def spy_read(self, name, *a, **k):
        opened.append(getattr(name, "filename", name))
        return orig_read(self, name, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "open", spy_open)
    monkeypatch.setattr(zipfile.ZipFile, "read", spy_read)
    with prsmfile.open(p) as pf:
        pf.analyses()
        assert pf.read_text("media/pic.svg") is None
        assert pf.read_json("misc/x.bin") is None
    assert opened and not any(n.startswith(("media/", "misc/")) for n in opened)
