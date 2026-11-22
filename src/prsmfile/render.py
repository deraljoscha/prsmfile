"""Renderers: text tables, JSON object and CSV files."""
from __future__ import annotations

import csv
import errno
import os
import re
import shutil
import tempfile
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
    if isinstance(c, bool):
        return "yes" if c else "no"
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


def _numbers(reports, numbers) -> list[int]:
    """The analysis numbers of --list; 1, 2, ... when not given."""
    return list(numbers) if numbers is not None else list(range(1, len(reports) + 1))


def to_text(pf, reports, tables, numbers=None) -> str:
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
    for n, r in zip(_numbers(reports, numbers), reports):
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


def _resolve_target(out_dir) -> Path:
    raw = Path(out_dir)
    if os.path.islink(raw) and not raw.exists():
        raise PrismFormatError(f"{raw}: output path is a dangling symlink")
    try:
        return raw.resolve()
    except RuntimeError as e:  # symlink loop on Python 3.10
        raise OSError(errno.ELOOP, os.strerror(errno.ELOOP), str(raw)) from e


def _not_empty(target: Path) -> PrismFormatError:
    return PrismFormatError(f"{target}: output directory exists and is not empty")


def _make_parents(parent: Path) -> list[Path]:
    """Create the missing ancestors of the export target; return those created, deepest first."""
    missing = []
    for anc in (parent, *parent.parents):
        if anc.exists():
            if not anc.is_dir():
                raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), str(anc))
            break
        missing.append(anc)
    created: list[Path] = []
    try:
        for anc in reversed(missing):
            anc.mkdir()
            created.insert(0, anc)
    except BaseException:
        _remove_dirs(created)
        raise
    return created


def _remove_dirs(dirs: list[Path]) -> None:
    for d in dirs:
        try:
            d.rmdir()
        except OSError:
            pass


def _stage_and_publish(target: Path, build) -> None:
    """Run build(staging_dir), then rename the staging dir to target.

    The staging dir is a fresh mkdtemp in the parent of target, so a failed or
    parallel export never leaves a partial or mixed target. Parent directories
    created for the export are removed again when it fails."""
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise _not_empty(target)
    created = _make_parents(target.parent)
    try:
        staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent))
    except BaseException:
        _remove_dirs(created)
        raise
    try:
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(staging, 0o777 & ~umask)  # mkdtemp creates 0700
        build(staging)
        try:
            os.rename(staging, target)  # POSIX replaces an empty target directory atomically
        except OSError:
            if not target.is_dir():
                raise
            try:
                target.rmdir()  # elsewhere (e.g. Windows) the empty target is removed first
            except OSError:
                raise _not_empty(target) from None
            try:
                os.rename(staging, target)
            except OSError:
                if not target.exists():
                    target.mkdir()  # put the empty directory back
                raise
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        _remove_dirs(created)
        raise


def write_csv(out_dir: Path, reports, tables, numbers=None) -> list[Path]:
    target = _resolve_target(out_dir)
    written: list[Path] = []

    def build(staging: Path) -> None:
        for p in _write_all(staging, reports, tables, numbers):
            written.append(target / p.relative_to(staging))

    _stage_and_publish(target, build)
    return written


def _write_all(out_dir: Path, reports, tables, numbers=None) -> list[Path]:
    written: list[Path] = []
    for n, t in enumerate(tables, 1):
        p = out_dir / "data" / f"{n:02d}_{slug(t.title)}.csv"
        width = len(t.columns)
        _write(p, t.columns, [(list(r) + [""] * width)[: max(width, len(r))] for r in t.rows])
        written.append(p)
    index = []
    for n, r in zip(_numbers(reports, numbers), reports):
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
