"""Raw data tables and result data sheets (docs/format.md 1.4 to 1.7)."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from .values import dataset_title, letter

_SUBCOLUMNS = {
    "y_sd_n": ("Mean", "SD", "N"),
    "y_sd": ("Mean", "SD"),
    "y_se": ("Mean", "SEM"),
    "y_plus_minus": ("Mean", "Plus", "Minus"),
}
_PAIR_FORMATS = ("date_se", "y_errorBar")


@dataclass
class Table:
    sheet_id: str
    title: str
    table_format: str | None
    data_format: str | None
    columns: list[str]
    rows: list[list[str]] = field(default_factory=list)


def _str(x) -> str | None:
    return x if isinstance(x, str) and x.strip() else None


def _width(ds: dict) -> int:
    reps = ds.get("replicates")
    if isinstance(reps, list) and reps:
        return len(reps)
    ranges = ds.get("replicate ranges")
    if isinstance(ranges, list):
        top = -1
        for item in ranges:
            r = item.get("range") if isinstance(item, dict) else None
            if isinstance(r, (str, int)) and not isinstance(r, bool):
                try:
                    top = max(top, int(str(r).split("~")[-1]))
                except ValueError:
                    pass
        if top >= 0:
            return top + 1
    return 1


def _name_text(n) -> str | None:
    if isinstance(n, dict):
        n = n.get("string")
    if isinstance(n, (int, float)) and not isinstance(n, bool):
        n = str(n)
    return _str(n)


def _sub_titles(pf, table: dict) -> dict[tuple[int, int], str]:
    uid = table.get("subcolumnTitlesDataSet")
    ds = pf.read_json(f"data/sets/{uid}.json") if isinstance(uid, str) and "/" not in uid else None
    out: dict[tuple[int, int], str] = {}
    titles = ds.get("titles") if ds else None
    for col in titles if isinstance(titles, list) else []:
        if not isinstance(col, dict) or isinstance(col.get("column"), bool) \
                or not isinstance(col.get("column"), int):
            continue
        for rep in col.get("replicates") or []:
            if not isinstance(rep, dict) or isinstance(rep.get("replicate"), bool) \
                    or not isinstance(rep.get("replicate"), int):
                continue
            name = _name_text(rep.get("name"))
            if name:
                out[(col["column"], rep["replicate"])] = name
    return out


def _headers(base: str, fmt, width: int, col: int, subs) -> list[str]:
    if width == 1:
        return [base]
    names = _SUBCOLUMNS.get(fmt)
    if names is not None and len(names) == width:
        return [f"{base} {n}" for n in names]
    out = []
    for i in range(width):
        if fmt in _PAIR_FORMATS:
            out.append(f"{base} {i + 1}")
        else:
            out.append(f"{base} {subs.get((col, i), i + 1)}")
    return out


def _read_set(pf, uid) -> dict | None:
    if not isinstance(uid, str) or "/" in uid:
        return None
    return pf.read_json(f"data/sets/{uid}.json")


def _declared_headers(pf, table: dict) -> list[str]:
    cols: list[str] = []
    if table.get("rowTitlesDataSet"):
        cols.append("Row title")
    x = _read_set(pf, table.get("xDataSet"))
    if x is not None and x.get("format") != "series":
        base = dataset_title(x) or "X"
        w = 2 if x.get("format") in _PAIR_FORMATS else 1
        cols.extend([base] if w == 1 else [f"{base} {i + 1}" for i in range(w)])
    subs = _sub_titles(pf, table)
    sets = table.get("dataSets")
    for i, uid in enumerate(sets if isinstance(sets, list) else []):
        ds = _read_set(pf, uid)
        if ds is None:
            cols.append(letter(i))
            continue
        base = dataset_title(ds) or letter(i)
        cols.extend(_headers(base, ds.get("format"), _width(ds), i, subs))
    return cols


def read_table(pf, sheet_id: str) -> Table | None:
    if not isinstance(sheet_id, str) or "/" in sheet_id:
        return None
    sheet = pf.read_json(f"data/sheets/{sheet_id}/sheet.json")
    table = sheet.get("table") if sheet else None
    if not isinstance(table, dict):
        return None
    uid = table.get("uid")
    if not isinstance(uid, str) or "/" in uid:
        return None
    prefix = f"data/tables/{uid}/"
    if not any(n.startswith(prefix) for n in pf._names):
        return None
    text = pf.read_text(prefix + "data.csv") or ""
    try:
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as e:
        pf.warnings.append(f"Could not parse {prefix}data.csv ({e})")
        return None
    columns = _declared_headers(pf, table)
    if rows:
        widest = max(len(r) for r in rows)
        columns = columns[:widest]
        columns += [f"Column {n}" for n in range(len(columns) + 1, widest + 1)]
    fmt, dfmt = table.get("format"), table.get("dataFormat")
    return Table(
        sheet_id=sheet_id,
        title=_str(sheet.get("title")) or "(untitled)",
        table_format=fmt if isinstance(fmt, str) else None,
        data_format=dfmt if isinstance(dfmt, str) else None,
        columns=columns,
        rows=rows,
    )
