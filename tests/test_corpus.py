"""Checks against the public corpus (corpus/, never committed).

Fetch it with `python scripts/fetch_corpus.py`. Without any .prism file in the corpus
directory every test in this module is skipped. Set PRSMFILE_CORPUS_DIR to use another
directory. Run with `-s` to see the printed counts.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

import prsmfile
from prsmfile.readers import read_analysis
from prsmfile.render import write_csv
from prsmfile.report import is_empty_rows
from prsmfile.tables import read_table
from tests.helpers import assert_sections_well_formed

ROOT = Path(__file__).resolve().parents[1]
CORPUS = Path(os.environ.get("PRSMFILE_CORPUS_DIR") or ROOT / "corpus")
FILES = sorted(CORPUS.glob("*.prism")) if CORPUS.is_dir() else []

pytestmark = pytest.mark.skipif(not FILES, reason=f"no .prism files in {CORPUS.name}/ (see scripts/fetch_corpus.py)")

KNOWN_MODEL_KEYS = (
    "welchTTestModel", "unpairedTTestModel", "pairedTTestModel", "mannWhitneyTestModel",
    "wilcoxonTestModel", "ordinaryAnovaModel", "repeatedMeasuresGlmAnovaModel",
    "repeatedMeasuresRemlAnovaModel", "models", "samples",
)
FIVE = ("T_TESTS_AND_NONPARAMETRIC", "ONE_WAY_ANOVA", "TWO_WAY_ANOVA",
        "NONLINEAR_REGRESSION", "AREA_UNDER_CURVE")


def _analyses():
    for path in FILES:
        with prsmfile.open(path) as pf:
            for a in pf.analyses():
                yield path, pf, a


def test_manifest_hashes():
    manifest = json.loads((ROOT / "tests" / "corpus_manifest.json").read_text(encoding="utf-8"))
    present = [m for m in manifest if (CORPUS / m["file"]).is_file()]
    assert present, "no manifest file found in the corpus directory"
    bad = [m["file"] for m in present
           if hashlib.sha256((CORPUS / m["file"]).read_bytes()).hexdigest() != m["sha256"]]
    assert not bad, f"hash mismatch: {bad}"


def test_every_file_opens_and_reports(tmp_path, capsys):
    counts = collections.Counter()
    for i, path in enumerate(FILES):
        with prsmfile.open(path) as pf:
            reports = []
            for a in pf.analyses():
                r = read_analysis(pf, a)
                assert_sections_well_formed(r)
                json.dumps(r.to_dict(), allow_nan=False)
                counts[(a.analysis_class, r.kind)] += 1
                reports.append(r)
            tables = [t for t in (read_table(pf, sid) for sid in pf.data_tables()) if t is not None]
            write_csv(tmp_path / f"f{i:03d}", reports, tables)
    with capsys.disabled():
        print("\nanalyses per (class, kind):")
        for (cls, kind), n in sorted(counts.items()):
            print(f"  {cls:28s} {kind:15s} {n}")
        print(f"  files {len(FILES)}, analyses {sum(counts.values())}")


def test_structured_coverage():
    bad = []
    for path, pf, a in _analyses():
        if a.analysis_class not in FIVE or not isinstance(a.results, dict):
            continue
        if not any(k in a.results for k in KNOWN_MODEL_KEYS):
            continue
        r = read_analysis(pf, a)
        if r.kind != "structured":
            bad.append((path.name, a.title, a.analysis_class, r.kind, r.warnings))
    assert not bad, bad


# ---- stored values against Prism's rendered tables -------------------------------------

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _numbers(text: str) -> list[float]:
    return [float(m) for m in _NUM.findall(text)]


def _stat_ok(x, text: str) -> bool:
    """x as f"{x:.4g}" appears in the cell (after `=` when there is one)."""
    want = float(f"{x:.4g}")
    part = text.split("=", 1)[1] if "=" in text else text
    return any(n == want for n in _numbers(part))


def _p_ok(p, text: str) -> bool:
    if p < 0.0001 and "<0.0001" in text.replace(" ", ""):
        return True
    if p > 0.9999 and ">0.9999" in text.replace(" ", ""):
        return True
    wants = {float(f"{p:.4f}"), float(f"{p:.4g}")}
    part = text.split("=", 1)[1] if "=" in text else text.lstrip("P ")
    return any(n in wants for n in _numbers(part))


def _view(a, name):
    for n, ds in a.views:
        if n == name and ds:
            return n, ds
    return None


def _rendered_rows(pf, a, name):
    v = _view(a, name)
    if v is None:
        return None
    t = pf.result_table(v[1])
    if t is None or is_empty_rows(t.rows):
        return None
    return [[str(c).strip() for c in row] for row in t.rows]


def _row_with(rows, test):
    for row in rows:
        if row and test(row[0]):
            return row
    return None


def _section(report, title):
    return next((s for s in report.sections if s.title == title), None)


def _pvalue(cell):
    return cell.value if cell is not None and hasattr(cell, "value") else None


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _check_ttest(pf, a, report):
    """None = skipped, else a list of mismatch strings (empty = matched)."""
    rows = _rendered_rows(pf, a, "Tabular results")
    sec = _section(report, "Test")
    if rows is None or sec is None or not sec.rows:
        return None
    stat_name, value, _df, pcell = sec.rows[0][1:5]
    p, value = _pvalue(pcell), _num(value)
    if value is None and p is None:
        return None
    out = []
    if value is not None:
        if stat_name == "t":
            cells = [c for row in rows for c in row if re.search(r"\bt=", c)]
            ok = bool(cells) and _stat_ok(value, cells[0])
        else:
            key = "Mann-Whitney U" if stat_name == "U" else "Sum of signed ranks"
            row = _row_with(rows, lambda s: key in s)
            ok = row is not None and len(row) > 1 and _stat_ok(value, row[1])
        if not ok:
            out.append(f"{stat_name}={value:.4g} not in rendered table")
    if p is not None:
        row = _row_with(rows, lambda s: s == "P value")
        if row is None or len(row) < 2 or not _p_ok(p, row[1]):
            out.append(f"p={p:.4g} not in rendered table")
    return out


def _find_effect(rows, label, f, p):
    """True if some rendered row labelled `label` carries both F and p."""
    for row in rows:
        if not row or row[0] != label:
            continue
        cells = row[1:]
        if (f is None or any(_stat_ok(f, c) for c in cells if "=" in c)) and \
           (p is None or any(_p_ok(p, c) for c in cells)):
            return True
    return False


def _check_oneway(pf, a, report):
    rows = _rendered_rows(pf, a, "ANOVA results")
    sec = _section(report, "ANOVA")
    if rows is None or sec is None:
        return None
    row = next((r for r in sec.rows if r[0] == "Treatment"), None)
    if row is None:
        return None
    f, p = _num(row[sec.columns.index("F")]), _pvalue(row[sec.columns.index("P")])
    if f is None and p is None:
        return None
    ok = False
    for r in rows:
        if r and r[0].startswith("Treatment"):
            cells = r[1:]
            if (f is None or any(_stat_ok(f, c) for c in cells if "=" in c)) and \
               (p is None or any(_p_ok(p, c) for c in cells)):
                ok = True
    return [] if ok else [f"Treatment F={f} p={p} not in rendered table"]


def _check_twoway(pf, a, report, reml):
    rows = _rendered_rows(pf, a, "Tabular results" if reml else "ANOVA results")
    sec = _section(report, "Fixed effects" if reml else "ANOVA")
    if rows is None or sec is None or not isinstance(a.results, dict):
        return None
    model = next((v for k, v in a.results.items() if k.endswith("AnovaModel") and isinstance(v, dict)), {})
    names = model.get("factorNames") if isinstance(model.get("factorNames"), dict) else {}
    row_name, col_name = names.get("rowFactor"), names.get("colFactor")
    labels = {"Row factor": row_name, "Column factor": col_name}
    out, compared = [], 0
    for r in sec.rows:
        src = r[0]
        if src not in ("Row factor", "Column factor", "Interaction"):
            continue
        f, p = _num(r[sec.columns.index("F")]), _pvalue(r[sec.columns.index("P")])
        if f is None and p is None:
            continue
        if src == "Interaction":
            if not (row_name and col_name):
                continue
            cands = ["Interaction", f"{row_name} x {col_name}"]
        else:
            if not labels[src]:
                continue
            cands = [labels[src]]
        compared += 1
        if not any(_find_effect(rows, c, f, p) for c in cands):
            out.append(f"{src} F={f} p={p} not in rendered table")
    return out if compared else None


def test_matches_rendered_tables(capsys):
    stats = collections.defaultdict(lambda: collections.Counter())
    mismatches = collections.defaultdict(list)
    for path, pf, a in _analyses():
        if a.analysis_class not in ("T_TESTS_AND_NONPARAMETRIC", "ONE_WAY_ANOVA", "TWO_WAY_ANOVA"):
            continue
        report = read_analysis(pf, a)
        if report.kind != "structured":
            continue
        if a.analysis_class == "T_TESTS_AND_NONPARAMETRIC":
            cls, res = "t tests", _check_ttest(pf, a, report)
        elif a.analysis_class == "ONE_WAY_ANOVA":
            cls, res = "one-way ANOVA", _check_oneway(pf, a, report)
        else:
            reml = isinstance(a.results, dict) and "repeatedMeasuresRemlAnovaModel" in a.results
            cls = "two-way REML" if reml else "two-way ordinary/GLM"
            res = _check_twoway(pf, a, report, reml)
        if res is None:
            stats[cls]["skipped"] += 1
        elif res:
            stats[cls]["compared"] += 1
            mismatches[cls].append((path.name, a.title, res))
        else:
            stats[cls]["compared"] += 1
            stats[cls]["matched"] += 1
    with capsys.disabled():
        print("\nrendered-table comparison:")
        for cls, c in sorted(stats.items()):
            print(f"  {cls:22s} compared {c['compared']:3d}  matched {c['matched']:3d}  skipped {c['skipped']:3d}")
        for cls, lst in sorted(mismatches.items()):
            for m in lst:
                print(f"  MISMATCH {cls}: {m}")
    for cls, c in stats.items():
        if c["compared"]:
            assert c["matched"] / c["compared"] >= 0.95, (cls, dict(c), mismatches[cls])
    reml = stats["two-way REML"]
    assert reml["compared"] >= 1 and reml["matched"] == reml["compared"], (dict(reml), mismatches["two-way REML"])
