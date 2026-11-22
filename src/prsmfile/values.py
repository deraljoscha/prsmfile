from __future__ import annotations

from dataclasses import dataclass


def num(x) -> float | None:
    """Return x as float; bool, strings (e.g. "undefined") and None give None."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


@dataclass(frozen=True)
class PValue:
    value: float | None
    alpha: float | None
    significant: bool | None
    bound: bool  # state == "P_VALUE_GREATER": true p > value

    @classmethod
    def from_obj(cls, obj) -> PValue | None:
        if not isinstance(obj, dict):
            return None
        sig = obj.get("isSignificant")
        return cls(
            value=num(obj.get("value")),
            alpha=num(obj.get("level")),
            significant=sig if isinstance(sig, bool) else None,
            bound=obj.get("state") == "P_VALUE_GREATER",
        )


def ci(obj) -> tuple[float | None, float | None, float | None]:
    """Return (lower, upper, level) of a confidence interval object."""
    if not isinstance(obj, dict):
        return (None, None, None)
    return (num(obj.get("lower")), num(obj.get("upper")), num(obj.get("level")))


def letter(i: int) -> str:
    """Spreadsheet column letter: 0 -> A, 25 -> Z, 26 -> AA."""
    i += 1
    out = ""
    while i > 0:
        i, r = divmod(i - 1, 26)
        out = chr(ord("A") + r) + out
    return out


def _text(x) -> str | None:
    if isinstance(x, str) and x.strip():
        return x
    return None


def dataset_title(ds: dict) -> str | None:
    t = ds.get("title") if isinstance(ds, dict) else None
    if isinstance(t, dict):
        t = t.get("string")
    return _text(t)


def _int_idx(v) -> int | None:
    """int, or integral float (bool excluded); else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


int_idx = _int_idx  # public alias: int, or integral float (bool excluded)


def _idx(part) -> float:
    if isinstance(part, dict):
        v = _int_idx(part.get("idx"))
        if v is not None:
            return v
    return float("inf")


def _key_of(id_) -> tuple:
    if isinstance(id_, list):
        return _key_of(id_[0]) if id_ else (float("inf"), float("inf"), (1, ""))
    if not isinstance(id_, dict):
        return (float("inf"), float("inf"), (1, ""))
    model = id_.get("model")
    name = model.get("name") if isinstance(model, dict) else None
    return (
        _idx(id_.get("row")),
        _idx(id_.get("col")),
        (0, name) if isinstance(name, str) else (1, ""),
    )


def entries(coll: dict | None) -> list[tuple[dict | list, object]]:
    """Return (id, value) pairs of a keyed collection, sorted by position."""
    if not isinstance(coll, dict):
        return []
    pairs = [
        (item.get("id"), item.get("value"))
        for item in coll.values()
        if isinstance(item, dict)
    ]
    return sorted(pairs, key=lambda p: _key_of(p[0]))  # stable: ties keep order


def _col_part(col, with_letter: bool) -> str:
    col = col if isinstance(col, dict) else {}
    idx = _int_idx(col.get("idx"))
    letter_ = letter(idx) if idx is not None else ""
    title = _text(col.get("title"))
    if with_letter:
        if title is None:
            return letter_
        return f"{letter_}:{title}" if letter_ else title
    return title if title is not None else letter_


def _row_part(row) -> str:
    row = row if isinstance(row, dict) else {}
    idx = _int_idx(row.get("idx"))
    base = f"row {idx + 1}" if idx is not None else "row"
    title = _text(row.get("title"))
    return f"{base}:{title}" if title is not None else base


def label(id: dict | list, with_letter: bool = True) -> str:
    """The single way to name a column, row, cell, model or pair."""
    if isinstance(id, list):
        return " vs ".join(label(x, with_letter) for x in id)
    if not isinstance(id, dict):
        return ""
    parts: list[str] = []
    if "row" in id:
        parts.append(_row_part(id["row"]))
    if "col" in id:
        parts.append(_col_part(id["col"], with_letter))
    if "model" in id and "col" in id:
        m = id["model"] if isinstance(id["model"], dict) else {}
        name = _text(m.get("title")) or _text(m.get("name"))
        if name:
            return f"{parts[-1]}:{name}" if not parts[:-1] else " ".join(parts[:-1] + [f"{parts[-1]}:{name}"])
    return " ".join(p for p in parts if p)
