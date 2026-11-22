"""Generic reader: every stored value as a (path, value) row."""
from __future__ import annotations

from ..report import Cell, Section
from ..values import PValue, entries, is_uid, label, num


_P_KEYS = ("value", "level", "isSignificant", "state")


def _is_p(node) -> bool:
    """A stored p-value: `value` next to `state` or `isSignificant` (the latter alone also occurs)."""
    return isinstance(node, dict) and "value" in node and ("state" in node or "isSignificant" in node)


def _is_collection(node) -> bool:
    return (
        isinstance(node, dict)
        and bool(node)
        and all(
            is_uid(k) and isinstance(v, dict) and "id" in v and "value" in v
            for k, v in node.items()
        )
    )


def _leaf(x) -> Cell:
    if isinstance(x, bool) or x is None:
        return x
    if isinstance(x, (int, float)):
        return num(x)  # inf, nan and ints beyond float range become None
    if x == "undefined":
        return None
    return x if isinstance(x, str) else str(x)


def flatten(node, prefix: str = "", skip=None, shape: tuple = ()) -> list[list[Cell]]:
    """Rows [path, value] in document order (iterative: no recursion limit).

    `skip` is an optional set of key tuples ("shapes": the dict keys from the root down, collection
    ids and list indexes left out). A node whose shape, or the shape of any ancestor, is in `skip`
    is not listed, except the extra keys of a p-value object (only its value row is skipped)."""
    rows: list[list[Cell]] = []
    skip = skip or ()
    stack = [(prefix, node, shape, shape in skip if shape else False)]
    while stack:
        path, cur, shp, gone = stack.pop()
        if _is_p(cur):
            if not gone:
                rows.append([path, PValue.from_obj(cur)])
            extras = [
                (f"{path}.{k}" if path else str(k), v, shp + (k,), (shp + (k,)) in skip)
                for k, v in cur.items()
                if k not in _P_KEYS
            ]
            stack.extend(reversed(extras))
        elif _is_collection(cur):
            children = []
            for id_, value in entries(cur):
                seg = label(id_)
                children.append((f"{path}[{seg}]" if seg else path, value, shp, gone))
            stack.extend(reversed(children))
        elif isinstance(cur, dict):
            kids = []
            for k, v in cur.items():
                ks = shp + (k,)
                kids.append((f"{path}.{k}" if path else str(k), v, ks, gone or ks in skip))
            stack.extend(reversed(kids))
        elif isinstance(cur, list):
            stack.extend(reversed([(f"{path}[{i}]", v, shp, gone) for i, v in enumerate(cur)]))
        elif not gone:
            rows.append([path, _leaf(cur)])
    return rows


def generic_sections(pf, a) -> list[Section]:
    body = {k: v for k, v in (a.results or {}).items() if k != "status"}
    return [Section("Values", ["Path", "Value"], flatten(body))]
