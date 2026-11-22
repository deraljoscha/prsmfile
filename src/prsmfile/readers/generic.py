"""Generic reader: every stored value as a (path, value) row."""
from __future__ import annotations

from ..report import Cell, Section
from ..values import PValue, entries, is_uid, label, num


_P_KEYS = ("value", "level", "isSignificant", "state")


def _is_p(node) -> bool:
    return isinstance(node, dict) and "value" in node and "state" in node


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


def flatten(node, prefix: str = "") -> list[list[Cell]]:
    """Rows [path, value] in document order (iterative: no recursion limit)."""
    rows: list[list[Cell]] = []
    stack = [(prefix, node)]
    while stack:
        path, cur = stack.pop()
        if _is_p(cur):
            rows.append([path, PValue.from_obj(cur)])
            extras = [
                (f"{path}.{k}" if path else str(k), v)
                for k, v in cur.items()
                if k not in _P_KEYS
            ]
            stack.extend(reversed(extras))
        elif _is_collection(cur):
            children = []
            for id_, value in entries(cur):
                seg = label(id_)
                children.append((f"{path}[{seg}]" if seg else path, value))
            stack.extend(reversed(children))
        elif isinstance(cur, dict):
            stack.extend(
                reversed([(f"{path}.{k}" if path else str(k), v) for k, v in cur.items()])
            )
        elif isinstance(cur, list):
            stack.extend(reversed([(f"{path}[{i}]", v) for i, v in enumerate(cur)]))
        else:
            rows.append([path, _leaf(cur)])
    return rows


def generic_sections(pf, a) -> list[Section]:
    body = {k: v for k, v in (a.results or {}).items() if k != "status"}
    return [Section("Values", ["Path", "Value"], flatten(body))]
