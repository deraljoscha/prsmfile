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
    assert a.input_titles == ["WT", None, None]
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
    assert a.alerts == ["Warning: data\nnot normal"]


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


# ---- review fix round ----

def _patch_member_bytes(path, member, fn):
    import struct
    raw = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as z:
        info = z.getinfo(member)
    off = info.header_offset
    nlen, elen = struct.unpack("<HH", raw[off + 26:off + 30])
    start = off + 30 + nlen + elen
    raw[start:start + info.compress_size] = fn(bytes(raw[start:start + info.compress_size]))
    path.write_bytes(bytes(raw))


def test_invalid_utf8_member_name(tmp_path):
    p = PrismBuilder().save(tmp_path / "a.prism")
    with zipfile.ZipFile(p, "a") as z:
        zi = zipfile.ZipInfo("aaaa")
        zi.flag_bits |= 0x800
        z.writestr(zi, b"x")
    raw = p.read_bytes()
    assert raw.count(b"aaaa") == 2
    raw = bytearray(raw.replace(b"aaaa", b"\xff\xfeaa"))
    for sig, flag_off, name_off in ((b"PK\x03\x04", 6, 30), (b"PK\x01\x02", 8, 46)):
        i = raw.rfind(sig, 0, raw.rfind(b"\xff\xfeaa") if sig == b"PK\x03\x04" else len(raw))
        while bytes(raw[i + name_off:i + name_off + 4]) != b"\xff\xfeaa":
            i = raw.find(sig, i + 1)
        raw[i + flag_off + 1] |= 0x08  # 0x800 utf-8 flag
    p.write_bytes(bytes(raw))
    with pytest.raises(PrismFormatError) as e:
        prsmfile.open(p)
    assert str(p) in str(e.value)


def test_unsupported_zip_feature(tmp_path, monkeypatch):
    p = PrismBuilder().save(tmp_path / "a.prism")

    def boom(self, *a, **k):
        raise NotImplementedError("compression type 99")

    monkeypatch.setattr(zipfile.ZipFile, "__init__", boom)
    with pytest.raises(PrismFormatError) as e:
        prsmfile.open(p)
    assert str(p) in str(e.value)


def test_permission_denied(tmp_path):
    import os
    if not hasattr(os, "geteuid") or os.geteuid() == 0:
        pytest.skip("file modes not enforced (Windows or root)")
    p = PrismBuilder().save(tmp_path / "a.prism")
    p.chmod(0)
    try:
        with pytest.raises(PrismFormatError) as e:
            prsmfile.open(p)
        assert str(p) in str(e.value)
    finally:
        p.chmod(0o600)


def test_recursion_error_member(tmp_path):
    b = PrismBuilder()
    bad = b.add_analysis("Bad", "ONE_WAY_ANOVA", {}, {"status": {}})
    b.add_analysis("Good", "ONE_WAY_ANOVA", {}, {"status": {}})
    b.add_member(f"analyses/{bad}/sheet.json", b'{"a":' * 200000)
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        assert [x.title for x in pf.analyses()] == ["Good"]
        assert any(f"analyses/{bad}/sheet.json" in w for w in pf.warnings)
        assert f"Skipped analysis {bad}: unreadable sheet.json" in pf.warnings


def test_recursion_error_document(tmp_path):
    t = tmp_path / "z.prism"
    with zipfile.ZipFile(t, "w") as z:
        z.writestr("document.json", '{"a":' * 200000)
    with pytest.raises(PrismFormatError):
        prsmfile.open(t)


def test_zip_read_error_in_analysis_skipped(tmp_path):
    b = PrismBuilder()
    bad = b.add_analysis("Bad", "ONE_WAY_ANOVA", {}, {"status": {}})
    b.add_analysis("Good", "ONE_WAY_ANOVA", {}, {"status": {}})
    p = b.save(tmp_path / "a.prism")
    _patch_member_bytes(p, f"analyses/{bad}/sheet.json", lambda d: bytes(x ^ 0xFF for x in d))
    with prsmfile.open(p) as pf:
        assert [x.title for x in pf.analyses()] == ["Good"]
        assert f"Skipped analysis {bad}: unreadable sheet.json" in pf.warnings


def test_read_text_zlib_error_warns(tmp_path):
    b = PrismBuilder()
    b.add_member("extra.json", b'{"k": "' + b"v" * 200 + b'"}')
    p = b.save(tmp_path / "a.prism")
    _patch_member_bytes(p, "extra.json", lambda d: bytes(x ^ 0xFF for x in d))
    with prsmfile.open(p) as pf:
        assert pf.read_json("extra.json") is None
        assert any("extra.json" in w for w in pf.warnings)


def test_views_only_referenced(tmp_path):
    b = PrismBuilder()
    aid = b.add_analysis("A1", "ONE_WAY_ANOVA", {}, {"status": {}}, views=[("Real", [["x"]])])
    b.add_member(
        f"analyses/{aid}/result_sheets/STRAY.json",
        json.dumps({"@class": "AnalysisView", "uid": "STRAY", "name": "Stray", "viewIdx": 0,
                    "dataSheet": "S"}).encode(),
    )
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        assert [v[0] for v in pf.analyses()[0].views] == ["Real"]


def test_views_order_float_idx_missing_datasheet_blank_name(tmp_path):
    b = PrismBuilder()
    aid = b.add_analysis("A1", "ONE_WAY_ANOVA", {}, {"status": {}},
                         views=[("first", [["x"]]), ("second", [["y"]]), ("third", [["z"]])])
    base = f"analyses/{aid}/result_sheets/"
    sheet = json.loads(b._members[f"analyses/{aid}/sheet.json"])
    uids = [r["uid"] for r in sheet["resultSheets"]]

    def put(uid, **kw):
        obj = {"@class": "AnalysisView", "uid": uid}
        obj.update(kw)
        b.add_member(base + f"{uid}.json", json.dumps(obj).encode())

    put(uids[0], name="first", viewIdx=2.0, dataSheet="S0")  # float, last
    put(uids[1], name="  ", viewIdx=0)                       # blank name, no dataSheet
    put(uids[2], name="third", viewIdx=1.0, dataSheet="S2")
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        v = pf.analyses()[0].views
    assert v == [("", None), ("third", "S2"), ("first", "S0")]


def test_two_listed_analyses_keep_listed_order(tmp_path):
    b = PrismBuilder()
    z = b.add_analysis("Zeta", "ONE_WAY_ANOVA", {}, {"status": {}})
    a = b.add_analysis("Alpha", "ONE_WAY_ANOVA", {}, {"status": {}})
    p = b.save(tmp_path / "a.prism")
    # rewrite the zip with the analysis members in reverse order
    with zipfile.ZipFile(p) as zf:
        items = [(n, zf.read(n)) for n in zf.namelist()]
    assert [x for x in (z, a)] == json.loads(dict(items)["document.json"])["sheets"]["analyses"]
    items.sort(key=lambda it: (it[0] != "document.json", a not in it[0], it[0]))
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, d in items:
            zf.writestr(n, d)
    with zipfile.ZipFile(p) as zf:
        names = [n for n in zf.namelist() if n.endswith("/sheet.json") and n.startswith("analyses/")]
    assert names.index(f"analyses/{a}/sheet.json") < names.index(f"analyses/{z}/sheet.json")
    with prsmfile.open(p) as pf:
        assert [x.title for x in pf.analyses()] == ["Zeta", "Alpha"]


def test_view_idx_sorts_by_any_number(tmp_path):
    b = PrismBuilder()
    aid = b.add_analysis("A1", "ONE_WAY_ANOVA", {}, {"status": {}},
                         views=[("a", [["x"]]), ("b", [["y"]]), ("c", [["z"]])])
    base = f"analyses/{aid}/result_sheets/"
    sheet = json.loads(b._members[f"analyses/{aid}/sheet.json"])
    uids = [r["uid"] for r in sheet["resultSheets"]]
    for uid, name, idx in zip(uids, "abc", (2, 0.5, 1)):
        b.add_member(base + f"{uid}.json", json.dumps(
            {"@class": "AnalysisView", "uid": uid, "name": name, "viewIdx": idx, "dataSheet": "S"}).encode())
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        assert [v[0] for v in pf.analyses()[0].views] == ["b", "c", "a"]


def test_result_sheet_uid_with_slash_ignored(tmp_path):
    b = PrismBuilder()
    aid = b.add_analysis("A1", "ONE_WAY_ANOVA", {}, {"status": {}}, views=[("Real", [["x"]])])
    sheet = json.loads(b._members[f"analyses/{aid}/sheet.json"])
    sheet["resultSheets"].append({"uid": "sub/evil", "title": "bad"})
    b.add_member(f"analyses/{aid}/sheet.json", json.dumps(sheet).encode())
    b.add_member(f"analyses/{aid}/result_sheets/sub/evil.json", json.dumps(
        {"@class": "AnalysisView", "name": "Evil", "viewIdx": 0, "dataSheet": "S"}).encode())
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        assert [v[0] for v in pf.analyses()[0].views] == ["Real"]


def test_results_kept_when_is_calculated_missing(tmp_path):
    b = PrismBuilder()
    b.add_analysis("old", "T_TESTS_AND_NONPARAMETRIC", {}, {"status": {"error": "VALID"}}, is_calculated=None)
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        a = pf.analyses()[0]
    assert a.is_calculated is None and a.has_results and a.results == {"status": {"error": "VALID"}}


def test_alert_original_text_and_order(tmp_path):
    b = PrismBuilder()
    aid = b.add_analysis("A1", "ONE_WAY_ANOVA", {}, {"status": {}},
                         alert="  Alert one\r\nline two \n", auto_note="Note: A\r")
    base = f"analyses/{aid}/floating_notes/"
    # member order, not sorted file names: z-note is written before the a-note
    b.add_member(base + "zzz.json", json.dumps({"isAuto": True, "text": {"string": "Z note"}}).encode())
    b.add_member(base + "aaa.json", json.dumps({"isAuto": True, "text": {"string": "A note"}}).encode())
    b.add_member(base + "sub/deep.json", json.dumps({"isAuto": True, "text": {"string": "deep"}}).encode())
    b.add_member(base + "plain.json", json.dumps({"isAuto": True, "text": "plain str"}).encode())
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        a = pf.analyses()[0]
    assert a.alerts == ["Alert one\r\nline two", "Note: A", "Z note", "A note"]


def test_listed_order_neither_title_nor_uid_order(tmp_path):
    import itertools
    b = PrismBuilder()
    ids = {t: b.add_analysis(t, "ONE_WAY_ANOVA", {}, {"status": {}}) for t in ("Mid", "Zed", "Abe")}
    p = b.save(tmp_path / "a.prism")
    by_title = [ids[t] for t in sorted(ids)]
    by_uid = sorted(ids.values())
    creation = list(ids.values())
    pick = next(o for o in itertools.permutations(ids.values())
                if list(o) not in (by_title, by_uid, creation))
    with zipfile.ZipFile(p) as z:
        items = [(n, z.read(n)) for n in z.namelist()]
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in items:
            if n == "document.json":
                doc = json.loads(d)
                doc["sheets"]["analyses"] = list(pick)
                d = json.dumps(doc).encode()
            z.writestr(n, d)
    with prsmfile.open(p) as pf:
        assert [a.id for a in pf.analyses()] == list(pick)


def test_view_idx_huge_int_and_ints_stay_exact(tmp_path):
    b = PrismBuilder()
    aid = b.add_analysis("A1", "ONE_WAY_ANOVA", {}, {"status": {}},
                         views=[("big", [["x"]]), ("two", [["y"]]), ("none", [["z"]]), ("one", [["w"]])])
    base = f"analyses/{aid}/result_sheets/"
    sheet = json.loads(b._members[f"analyses/{aid}/sheet.json"])
    uids = [r["uid"] for r in sheet["resultSheets"]]
    raw = {"big": "1" + "0" * 400, "two": "2", "none": '"x"', "one": "1.5"}
    for uid, name in zip(uids, raw):
        b.add_member(base + f"{uid}.json", (
            '{"@class": "AnalysisView", "uid": "%s", "name": "%s", "viewIdx": %s, "dataSheet": "S"}'
            % (uid, name, raw[name])).encode())
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        assert [v[0] for v in pf.analyses()[0].views] == ["one", "two", "big", "none"]


def test_analysis_positional_field_order():
    a = Analysis("id", "t", "CLS", True, {"p": 1}, {"r": 2}, [("A", "x")], [("v", None)], ["al"])
    assert a.parameters == {"p": 1} and a.results == {"r": 2} and a.inputs == [("A", "x")]
    assert a.views == [("v", None)] and a.alerts == ["al"] and a.input_titles == []


def test_alert_text_truncated_without_separators_is_dropped(tmp_path):
    full = "Prism has identified an unstable parameter.\rThis suggests that your data are incomplete.\rLearn more"
    stored = "Prism has identified an unstable parameter.This suggests that your data are inco"
    b = PrismBuilder()
    b.add_analysis("A1", "NONLINEAR_REGRESSION", {}, {"status": {}}, alert=stored, auto_note=full)
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        a = pf.analyses()[0]
    assert a.alerts == ["Prism has identified an unstable parameter.\rThis suggests that your data are incomplete."]


def test_alert_text_that_is_not_a_prefix_is_kept(tmp_path):
    b = PrismBuilder()
    b.add_analysis("A1", "T", {}, {"status": {}}, alert="Orphaned analysis", auto_note="Something else entirely")
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        assert pf.analyses()[0].alerts == ["Orphaned analysis", "Something else entirely"]


def test_learn_more_link_text_is_removed(tmp_path):
    b = PrismBuilder()
    b.add_analysis("A1", "T", {}, {"status": {}},
                   auto_note="Best-fit value, no interval. \rLearn more \rSecond paragraph. \rLearn more")
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        (alert,) = pf.analyses()[0].alerts
    assert "Learn more" not in alert and alert.startswith("Best-fit value") and "Second paragraph." in alert


def test_mutating_returned_dicts_does_not_change_the_cache(tmp_path):
    b = PrismBuilder()
    b.add_analysis("A1", "T", {"x": {"y": 1}}, {"k": {"v": [1, 2]}})
    with prsmfile.open(b.save(tmp_path / "a.prism")) as pf:
        a = pf.analyses()[0]
        a.results["k"]["v"].append(3)
        a.results.clear()
        a.parameters["x"]["y"] = 99
        a.parameters.clear()
        again = pf.analyses()[0]
    assert again.results == {"k": {"v": [1, 2]}}
    assert again.parameters == {"x": {"y": 1}}
