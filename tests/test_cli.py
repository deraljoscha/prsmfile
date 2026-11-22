import csv
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import prsmfile
from prsmfile import PValue, Report, Section, read_analysis
from prsmfile.cli import main
from prsmfile.errors import PrismFormatError
from prsmfile.render import to_json_obj, to_text, write_csv
from tests.builder import PrismBuilder

OK = {"status": {"error": "VALID", "warning": []}}


def build_three(tmp_path, title="Plain"):
    b = PrismBuilder()
    b.add_analysis(title, "ONE_WAY_ANOVA", {}, {"x": 1, **OK})
    b.add_analysis("Never", "ONE_WAY_ANOVA", {}, None, is_calculated=False)
    b.add_analysis("Stub", "ONE_WAY_ANOVA", {}, None, is_calculated=None)
    return b.save(tmp_path / "t.prism")


def run_cli(argv, capsys):
    code = main([str(a) for a in argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def reports_of(path, mutate=None):
    pf = prsmfile.open(path)
    reps = [read_analysis(pf, a) for a in pf.analyses()]
    if mutate:
        mutate(reps)
    return pf, reps


def test_list_states(tmp_path, capsys):
    p = build_three(tmp_path)
    code, out, _ = run_cli([p, "--list"], capsys)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "01  ONE_WAY_ANOVA  calculated  Plain"
    assert lines[1] == "02  ONE_WAY_ANOVA  not calculated  Never"
    assert lines[2] == "03  ONE_WAY_ANOVA  no stored results  Stub"


def test_json_roundtrip(tmp_path, capsys):
    b = PrismBuilder()
    b.add_analysis("Δtemp\r(a)", "ONE_WAY_ANOVA", {}, {"x": 1, **OK})
    p = b.save(tmp_path / "t.prism")
    code, out, _ = run_cli([p, "--json"], capsys)
    assert code == 0
    assert "Δtemp" in out  # not escaped
    obj = json.loads(out)
    assert obj["analyses"][0]["title"] == "Δtemp\r(a)"
    assert obj["analyses"][0]["id"]
    assert obj["format_version"] == "1-6-1"
    assert obj["data_tables"] == []
    assert set(obj) >= {"file", "prism_version", "saved_with", "warnings"}


def test_json_cp1252_stdout(tmp_path, monkeypatch):
    b = PrismBuilder()
    b.add_analysis("Δtemp.", "ONE_WAY_ANOVA", {}, {"x": 1, **OK})
    p = b.save(tmp_path / "t.prism")
    raw = io.BytesIO()
    wrapper = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr("sys.stdout", wrapper)
    assert main([str(p), "--json"]) == 0
    wrapper.flush()
    assert "Δtemp.".encode("utf-8") in raw.getvalue()


def test_json_data_tables_only_with_flag(tmp_path, capsys):
    b = PrismBuilder()
    b.add_raw_table("Raw", "column", [("A", "y_replicates", 2)], [["1", "2"], ["3", "4"]])
    p = b.save(tmp_path / "t.prism")
    assert json.loads(run_cli([p, "--json"], capsys)[1])["data_tables"] == []
    obj = json.loads(run_cli([p, "--json", "--data"], capsys)[1])
    t = obj["data_tables"][0]
    assert t["title"] == "Raw" and t["rows"] == [["1", "2"], ["3", "4"]]
    assert t["columns"] == ["A 1", "A 2"] and t["format"] == "column"


def test_csv_files(tmp_path, capsys):
    b = PrismBuilder()
    b.add_raw_table("Raw, data", "column", [("A", "y_replicates", 1)], [["WT\r(3 weeks)"], ["a,b"]])
    b.add_analysis("Plain", "ONE_WAY_ANOVA", {}, {"x": 1, **OK})
    b.add_analysis("Never", "ONE_WAY_ANOVA", {}, None, is_calculated=False)
    p = b.save(tmp_path / "t.prism")
    out_dir = tmp_path / "out"
    code, out, _ = run_cli([p, "--csv", out_dir, "--data"], capsys)
    assert code == 0
    files = sorted(f for f in out_dir.rglob("*.csv"))
    assert out.strip() == str(len(files))
    with open(out_dir / "index.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Number", "Id", "Title", "Class", "Kind", "Folder", "Warnings"]
    assert [r[2] for r in rows[1:]] == ["Plain", "Never"]
    assert rows[1][4] == "generic" and rows[2][4] == "not_calculated"
    assert rows[2][5] == "" and "Not calculated" in rows[2][6]
    assert rows[1][5] == "analyses/01_plain"
    data = (out_dir / "data").glob("*.csv")
    (dfile,) = list(data)
    assert dfile.name == "01_raw-data.csv"
    with open(dfile, newline="", encoding="utf-8") as f:
        drows = list(csv.reader(f))
    assert drows == [["A"], ["WT\r(3 weeks)"], ["a,b"]] or drows[1:] == [["WT\r(3 weeks)"], ["a,b"]]
    sec = sorted((out_dir / "analyses" / "01_plain").glob("*.csv"))
    assert sec and sec[0].name.startswith("01_")


def test_write_csv_cells_and_returns_index(tmp_path):
    p = build_three(tmp_path)
    pf, reps = reports_of(p)
    reps[0].sections = [Section("S, one", ["a", "b", "c", "d", "e"], [
        [0.1, PValue(0.05, 0.05, True, False), PValue(0.1, 0.05, False, True), None, True]])]
    reps[0].sections[0].note = "n"
    reps[0].warnings = []
    out = tmp_path / "o"
    files = write_csv(out, reps, [])
    assert out / "index.csv" in files
    with open(out / "analyses" / "01_plain" / "01_s-one.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows == [["a", "b", "c", "d", "e"], ["0.1", "0.05", ">0.1", "", "yes"]]
    with open(out / "index.csv", newline="", encoding="utf-8") as f:
        idx = list(csv.reader(f))
    assert idx[1][6] == "S, one: n"


def test_csv_refuses_non_empty_dir(tmp_path, capsys):
    p = build_three(tmp_path)
    d = tmp_path / "out"
    d.mkdir()
    (d / "x.txt").write_text("hi")
    code, out, err = run_cli([p, "--csv", d], capsys)
    assert code == 1 and "Traceback" not in err and err.strip()
    assert [f.name for f in d.iterdir()] == ["x.txt"]
    with pytest.raises(PrismFormatError):
        write_csv(d, [], [])


def test_csv_empty_existing_dir_ok(tmp_path, capsys):
    p = build_three(tmp_path)
    d = tmp_path / "out"
    d.mkdir()
    assert run_cli([p, "--csv", d], capsys)[0] == 0
    assert (d / "index.csv").exists()


def test_text_newlines_flattened(tmp_path):
    p = build_three(tmp_path, title="WT\r\n(3\nweeks)")
    pf, reps = reports_of(p)
    reps[0].warnings.append("w\rx")
    reps[0].sections = [Section("T\r1", ["c\n1"], [["a\rb"]], note="no\nte")]
    text = to_text(pf, reps, [])
    assert "\r" not in text and "\n\n\n" not in text
    assert "WT (3 weeks)" in text and "w x" in text and "T 1" in text and "(no te)" in text
    assert "a b" in text and "c 1" in text


def test_filter_matches_flattened_title(tmp_path, capsys):
    p = build_three(tmp_path, title="WT\r(3 weeks)")
    code, out, _ = run_cli([p, "--list", "--analysis", "wt (3"], capsys)
    assert code == 0 and "WT" in out and "Never" not in out


def test_bad_file_exit_1(tmp_path, capsys):
    bad = tmp_path / "x.prism"
    bad.write_text("not a zip")
    code, out, err = run_cli([bad], capsys)
    assert code == 1 and out == "" and "not a zip" in err and "Traceback" not in err
    code, out, err = run_cli([tmp_path / "missing.prism"], capsys)
    assert code == 1 and err.strip() and "Traceback" not in err
    pzf = tmp_path / "x.pzf"
    with zipfile.ZipFile(pzf, "w") as z:
        z.writestr("a.txt", "x")
    code, out, err = run_cli([pzf], capsys)
    assert code == 1 and ".pzf" in err and "Traceback" not in err
    code, out, err = run_cli([tmp_path], capsys)  # a directory
    assert code == 1 and "Traceback" not in err


def test_filter_no_match(tmp_path, capsys):
    p = build_three(tmp_path)
    code, out, err = run_cli([p, "--analysis", "zzz"], capsys)
    assert code == 1 and out == "" and err.strip() == 'no analysis matches "zzz"'


def test_text_pvalue_bound(tmp_path):
    p = build_three(tmp_path)
    pf, reps = reports_of(p)
    reps[0].sections = [Section("P", ["p", "q", "r", "f", "s", "t", "u"], [
        [PValue(0.1, 0.05, False, True), PValue(0.01234567, 0.05, True, False),
         PValue(None, None, None, False), 1.23456789, True, False, None]])]
    text = to_text(pf, reps, [])
    assert ">0.1" in text and "0.01235" in text and "n/a" in text
    assert "1.23457" in text and "yes" in text and "no" in text


def test_text_note_shown(tmp_path):
    p = build_three(tmp_path)
    pf, reps = reports_of(p)
    reps[0].sections = [Section("Tbl", ["a", "bb"], [["x", "y"]], note="Rounded values")]
    lines = to_text(pf, reps, []).splitlines()
    i = lines.index("Tbl")
    assert lines[i + 1] == "(Rounded values)"
    assert lines[i + 2] == "a  bb"
    assert lines[i + 3] == "-  --"
    assert lines[i + 4] == "x  y"


def test_text_not_calculated_message(tmp_path, capsys):
    p = build_three(tmp_path)
    code, out, _ = run_cli([p], capsys)
    assert code == 0 and "Not calculated when saved" in out


def test_json_obj_nan_free(tmp_path):
    p = build_three(tmp_path)
    pf, reps = reports_of(p)
    reps[0].sections = [Section("S", ["a"], [[float("nan")], [float("inf")]])]
    s = json.dumps(to_json_obj(pf, reps, []), allow_nan=False)
    assert "NaN" not in s


def test_json_and_csv_exclusive(tmp_path, capsys):
    p = build_three(tmp_path)
    with pytest.raises(SystemExit) as e:
        main([str(p), "--json", "--csv", str(tmp_path / "o")])
    assert e.value.code == 2
    capsys.readouterr()


def test_help_lists_options(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for opt in ("--list", "--json", "--csv", "--data", "--analysis"):
        assert opt in out


def test_csv_dotdot_into_populated_dir(tmp_path, capsys):
    p = build_three(tmp_path)
    old = tmp_path / "old"
    old.mkdir()
    (old / "keep.txt").write_text("k")
    code, out, err = run_cli([p, "--csv", tmp_path / "missing" / ".." / "old"], capsys)
    assert code == 1 and "Traceback" not in err and err.strip()
    assert [f.name for f in old.iterdir()] == ["keep.txt"]


def test_csv_symlink_index_not_followed(tmp_path, capsys):
    p = build_three(tmp_path)
    d = tmp_path / "out"
    d.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("precious")
    _symlink(d / "index.csv", victim)
    code, out, err = run_cli([p, "--csv", d], capsys)
    assert code == 1 and err.strip()
    assert victim.read_text() == "precious"


def test_csv_files_opened_exclusively(tmp_path, monkeypatch):
    p = build_three(tmp_path)
    pf, reps = reports_of(p)
    modes = []
    real = open

    def spy(file, mode="r", *a, **k):
        modes.append(mode)
        return real(file, mode, *a, **k)

    monkeypatch.setattr("prsmfile.render.open", spy, raising=False)
    write_csv(tmp_path / "o", reps, [])
    assert modes and set(modes) == {"x"}


def test_csv_oserror_message(tmp_path, capsys):
    p = build_three(tmp_path)
    f = tmp_path / "afile"
    f.write_text("x")
    code, out, err = run_cli([p, "--csv", f / "sub"], capsys)
    assert code == 1 and "Traceback" not in err
    assert err.startswith("prsmfile: ") and "Not a directory" in err


ROOT = Path(__file__).resolve().parents[1]


def _spawn(args):
    """Start the CLI as a child process with a stdout pipe we control."""
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.Popen([sys.executable, "-m", "prsmfile", *map(str, args)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                            cwd=str(ROOT))


@pytest.mark.parametrize("keep", [0, 1])
@pytest.mark.parametrize("flag", ["--list", "--json", ""])
def test_broken_pipe(tmp_path, flag, keep):
    b = PrismBuilder()
    for i in range(3000):  # output well above the pipe buffer
        b.add_analysis(f"Analysis {i}", "ONE_WAY_ANOVA", {}, {"x": 1, **OK})
    p = b.save(tmp_path / "t.prism")
    proc = _spawn([p, *([flag] if flag else [])])
    first = proc.stdout.readline() if keep else b""
    proc.stdout.close()  # the reader goes away
    err = proc.stderr.read().decode()
    proc.stderr.close()
    code = proc.wait()
    assert err == "", err
    if keep:
        assert first.strip(), "the CLI produced no output before the pipe closed"
    # exit status of prsmfile itself: 1 on a closed pipe, never a crash status
    assert code == 1


@pytest.mark.parametrize("flag", ["--help", "--version"])
def test_help_version_closed_pipe(flag):
    proc = _spawn([flag])
    proc.stdout.close()
    err = proc.stderr.read().decode()
    proc.stderr.close()
    code = proc.wait()
    assert "Traceback" not in err and "Exception ignored" not in err and "BrokenPipe" not in err, err
    assert code in (0, 1)


@pytest.mark.parametrize("flag", ["--help", "--version"])
def test_help_version_output(flag):
    proc = _spawn([flag])
    out, err = proc.communicate()
    assert proc.returncode == 0 and err == b""
    assert (b"--list" if flag == "--help" else b"prsmfile ") in out


def _symlink(link, target):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not permitted here")


def test_csv_dangling_symlink_target_refused(tmp_path, capsys):
    p = build_three(tmp_path)
    link = tmp_path / "out"
    _symlink(link, tmp_path / "nowhere")
    code, out, err = run_cli([p, "--csv", link], capsys)
    assert code == 1 and err.startswith("prsmfile: ") and "Traceback" not in err
    assert not (tmp_path / "nowhere").exists()


def test_csv_symlink_loop_exit_1(tmp_path, capsys):
    p = build_three(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    _symlink(a, b)
    _symlink(b, a)
    code, out, err = run_cli([p, "--csv", a / "sub"], capsys)
    assert code == 1 and err.startswith("prsmfile: ") and "Traceback" not in err


def test_csv_is_atomic_failure_leaves_nothing(tmp_path, monkeypatch, capsys):
    p = build_three(tmp_path)
    import prsmfile.render as render
    real = render._write
    calls = []

    def failing(path, header, rows):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("disk full")
        return real(path, header, rows)

    monkeypatch.setattr(render, "_write", failing)
    target = tmp_path / "out"
    code, out, err = run_cli([p, "--csv", target], capsys)
    assert code == 1 and "disk full" in err
    assert not target.exists()
    assert sorted(f.name for f in tmp_path.iterdir()) == ["t.prism"]  # no staging dir left


def test_csv_stages_then_renames(tmp_path, monkeypatch):
    p = build_three(tmp_path)
    pf, reps = reports_of(p)
    seen = []
    real = os.rename

    def spy(src, dst):
        seen.append((Path(src), Path(dst), (Path(src) / "index.csv").exists()))
        return real(src, dst)

    monkeypatch.setattr(os, "rename", spy)
    target = tmp_path / "out"
    files = write_csv(target, reps, [])
    assert len(seen) == 1
    src, dst, complete = seen[0]
    assert dst == target.resolve() and src.parent == tmp_path.resolve() and src != dst
    assert complete  # everything was written before the rename
    assert all(f.is_file() and target.resolve() in f.parents for f in files)


def test_csv_parallel_exports_one_wins(tmp_path):
    p = build_three(tmp_path)
    pf, reps = reports_of(p)
    target = tmp_path / "out"
    write_csv(target, reps, [])
    with pytest.raises(PrismFormatError):
        write_csv(target, reps, [])
    assert sorted(f.name for f in tmp_path.iterdir()) == ["out", "t.prism"]


def test_no_absolute_developer_paths():
    needle = "/" + "home" + "/"
    for f in [*ROOT.glob("tests/*.py"), *ROOT.glob("src/prsmfile/**/*.py")]:
        assert needle not in f.read_text(encoding="utf-8"), f


def test_file_warnings_on_stderr_csv_and_list(tmp_path, capsys):
    b = PrismBuilder()
    b.add_analysis("A", "ONE_WAY_ANOVA", {}, {"x": 1, **OK})
    p = b.save(tmp_path / "t.prism", format_version="2-0-0")
    code, out, err = run_cli([p, "--list"], capsys)
    assert code == 0 and "Warning: Unknown format version 2-0-0" in err
    code, out, err = run_cli([p, "--csv", tmp_path / "o"], capsys)
    assert code == 0 and "Warning: Unknown format version 2-0-0" in err
    code, out, err = run_cli([p, "--json"], capsys)
    assert "Unknown format version" in json.loads(out)["warnings"][0]
    assert "Warning:" not in err


def test_filter_casefold(tmp_path, capsys):
    b = PrismBuilder()
    b.add_analysis("Straße test", "ONE_WAY_ANOVA", {}, {"x": 1, **OK})
    p = b.save(tmp_path / "t.prism")
    code, out, _ = run_cli([p, "--list", "--analysis", "STRASSE"], capsys)
    assert code == 0 and "Straße" in out


def test_slug_unicode_separators():
    from prsmfile.render import slug
    assert slug("a\u2013b\u00a0c\u2014d") == "a-b-c-d"
    assert slug("\u2013") == "untitled"
    assert slug("Δ") == "untitled"


def build_named(tmp_path):
    b = PrismBuilder()
    ids = [b.add_analysis(t, "ONE_WAY_ANOVA", {}, {"x": 1, **OK}) for t in ("Alpha", "Beta", "Gamma")]
    return b.save(tmp_path / "n.prism"), ids


def test_filtered_analysis_keeps_its_list_number_everywhere(tmp_path, capsys):
    p, _ = build_named(tmp_path)
    _, lst, _ = run_cli([p, "--list", "--analysis", "gamma"], capsys)
    assert lst.splitlines() == ["03  ONE_WAY_ANOVA  calculated  Gamma"]
    _, text, _ = run_cli([p, "--analysis", "gamma"], capsys)
    assert "== 03 Gamma [ONE_WAY_ANOVA] ==" in text and "== 01" not in text
    out = tmp_path / "out"
    run_cli([p, "--analysis", "gamma", "--csv", out], capsys)
    with open(out / "index.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[1][0] == "3" and rows[1][5] == "analyses/03_gamma"
    assert (out / "analyses" / "03_gamma").is_dir()


def test_analysis_matches_exact_number_or_id(tmp_path, capsys):
    p, ids = build_named(tmp_path)
    _, lst, _ = run_cli([p, "--list", "--analysis", "02"], capsys)
    assert lst.splitlines() == ["02  ONE_WAY_ANOVA  calculated  Beta"]
    _, lst, _ = run_cli([p, "--list", "--analysis", ids[0].lower()], capsys)
    assert lst.splitlines() == ["01  ONE_WAY_ANOVA  calculated  Alpha"]


def test_list_with_data_is_a_usage_error(tmp_path, capsys):
    p, _ = build_named(tmp_path)
    with pytest.raises(SystemExit) as e:
        main([str(p), "--list", "--data"])
    assert e.value.code == 2
    assert "--data" in capsys.readouterr().err


def test_list_does_not_call_error_status_calculated(tmp_path, capsys):
    b = PrismBuilder()
    b.add_analysis("Bad", "ONE_WAY_ANOVA", {}, {"status": {"error": "INVALID_DATA_TOO_FEW_COLUMNS", "warning": []}})
    code, out, _ = run_cli([b.save(tmp_path / "e.prism"), "--list"], capsys)
    assert "calculated  Bad" not in out.replace("not calculated", "") and "INVALID_DATA_TOO_FEW_COLUMNS" in out


def test_failed_export_removes_parents_it_created(tmp_path, monkeypatch, capsys):
    p = build_three(tmp_path)
    import prsmfile.render as render

    def failing(path, header, rows):
        raise OSError("disk full")

    monkeypatch.setattr(render, "_write", failing)
    code, _, err = run_cli([p, "--csv", tmp_path / "a" / "b" / "out"], capsys)
    assert code == 1 and "disk full" in err
    assert not (tmp_path / "a").exists()


def test_failed_rename_restores_empty_target(tmp_path, monkeypatch, capsys):
    p = build_three(tmp_path)
    target = tmp_path / "out"
    target.mkdir()

    def no_rename(src, dst):
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(os, "rename", no_rename)
    code, _, _ = run_cli([p, "--csv", target], capsys)
    assert code == 1 and target.is_dir() and not any(target.iterdir())
    assert sorted(f.name for f in tmp_path.iterdir()) == ["out", "t.prism"]


def test_package_exports_table_reader():
    assert prsmfile.read_table is not None and prsmfile.Table is not None
    assert {"read_table", "Table"} <= set(prsmfile.__all__)


def test_unmatched_number_does_not_fall_back_to_title(tmp_path, capsys):
    b = PrismBuilder()
    b.add_analysis("Run 7 of the series", "ONE_WAY_ANOVA", {}, {"x": 1, **OK})
    p = b.save(tmp_path / "n.prism")
    code, out, err = run_cli([p, "--list", "--analysis", "7"], capsys)
    assert code == 1 and out == "" and err.strip() == "no analysis numbered 7"
