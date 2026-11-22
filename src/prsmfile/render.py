"""Renderers: text tables, JSON object and CSV files."""
from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

from .errors import PrismFormatError
from .values import PValue

_NEWLINES = re.compile(r"\r\n|\r|\n")


def flat(s) -> str:
    """Text for one-line output: CR and LF become a space."""
    return _NEWLINES.sub(" ", s)


def _text_cell(c) -> str:
    if c is None:
        return ""
    if isinstance(c, PValue):
        if c.value is None:
            return "n/a"
        return (">" if c.bound else "") + format(c.value, ".4g")
    if isinstance(c, bool):
        return "yes" if c else "no"
    if isinstance(c, float):
        return format(c, ".6g")
    return flat(str(c))


def _csv_cell(c) -> str:
    if c is None:
        return ""
    if isinstance(c, PValue):
        if c.value is None:
            return ""
        return (">" if c.bound else "") + repr(c.value)
    if isinstance(c, float):
        return repr(c)
    return str(c)


def _grid(columns, rows) -> list[str]:
    n = len(columns)
    head = [flat(c) for c in columns]
    body = [[_text_cell(c) for c in (list(r) + [""] * n)[:n]] for r in rows]
    widths = [max([len(head[i])] + [len(r[i]) for r in body]) for i in range(n)]

    def line(cells):
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()

    return [line(head), line(["-" * w for w in widths])] + [line(r) for r in body]


def to_text(pf, reports, tables) -> str:
    out: list[str] = [f"File: {flat(str(pf.path))}"]
    bits = []
    if pf.prism_version:
        bits.append(f"created with Prism {pf.prism_version}")
    if pf.saved_with:
        bits.append(f"saved with Prism {pf.saved_with}")
    if pf.format_version_raw:
        bits.append(f"format {pf.format_version_raw}")
    if bits:
        out.append(", ".join(bits))
    for w in pf.warnings:
        out.append(f"Warning: {flat(w)}")
    for n, r in enumerate(reports, 1):
        a = r.analysis
        out += ["", f"== {n:02d} {flat(a.title)} [{a.analysis_class}] =="]
        for w in r.warnings:
            out.append(f"Warning: {flat(w)}")
        for s in r.sections:
            out += ["", flat(s.title)]
            if s.note:
                out.append(f"({flat(s.note)})")
            if s.columns:
                out += _grid(s.columns, s.rows)
    for t in tables:
        out += ["", f"== Data table: {flat(t.title)} =="]
        if t.columns:
            out += _grid(t.columns, t.rows)
    return "\n".join(out) + "\n"


def to_json_obj(pf, reports, tables) -> dict:
    return {
        "file": str(pf.path),
        "prism_version": pf.prism_version,
        "saved_with": pf.saved_with,
        "format_version": pf.format_version_raw,
        "warnings": list(pf.warnings),
        "analyses": [r.to_dict() for r in reports],
        "data_tables": [
            {"title": t.title, "format": t.table_format, "columns": list(t.columns),
             "rows": [list(r) for r in t.rows]}
            for t in tables
        ],
    }


def slug(s: str) -> str:
    s = "".join("-" if unicodedata.category(ch) in ("Pd", "Zs") else ch for ch in s)
    s = re.sub(r"[^a-z0-9]+", "-", s.lower().encode("ascii", "ignore").decode()).strip("-")
    return s[:60].strip("-") or "untitled"


def _write(path: Path, header, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", newline="", encoding="utf-8", errors="replace") as f:
        w = csv.writer(f)
        if header:
            w.writerow(header)
        w.writerows(rows)


def write_csv(out_dir: Path, reports, tables) -> list[Path]:
    out_dir = Path(out_dir).resolve()
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        raise PrismFormatError(f"{out_dir}: output directory exists and is not empty")
    written: list[Path] = []
    for n, t in enumerate(tables, 1):
        p = out_dir / "data" / f"{n:02d}_{slug(t.title)}.csv"
        width = len(t.columns)
        _write(p, t.columns, [(list(r) + [""] * width)[: max(width, len(r))] for r in t.rows])
        written.append(p)
    index = []
    for n, r in enumerate(reports, 1):
        a = r.analysis
        folder = f"analyses/{n:02d}_{slug(a.title)}" if r.sections else ""
        notes = list(r.warnings) + [f"{s.title}: {s.note}" for s in r.sections if s.note]
        for m, s in enumerate(r.sections, 1):
            p = out_dir / folder / f"{m:02d}_{slug(s.title)}.csv"
            _write(p, s.columns, [[_csv_cell(c) for c in row] for row in s.rows])
            written.append(p)
        index.append([n, a.id, a.title, a.analysis_class, r.kind, folder, " | ".join(notes)])
    p = out_dir / "index.csv"
    _write(p, ["Number", "Id", "Title", "Class", "Kind", "Folder", "Warnings"], index)
    written.append(p)
    return written
