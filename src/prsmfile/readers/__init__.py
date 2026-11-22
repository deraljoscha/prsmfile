"""Reader registry: analysisClass to a typed reader, with a generic fallback."""
from __future__ import annotations

from typing import Callable

from ..report import Report, Section, is_empty_rows
from .generic import flatten, generic_sections

Reader = Callable[..., "list[Section]"]
REGISTRY: dict[str, Reader] = {}
_NOTE = "Rounded values from Prism's rendered table."
_READER_ERRORS = (KeyError, TypeError, ValueError, IndexError, AttributeError)


def register(analysis_class: str):
    def deco(fn: Reader) -> Reader:
        REGISTRY[analysis_class] = fn
        return fn

    return deco


def _status(a) -> tuple[str | None, list[str]]:
    status = a.results.get("status") if isinstance(a.results, dict) else None
    if not isinstance(status, dict):
        return None, []
    err = status.get("error")
    warns = status.get("warning")
    return (
        err if isinstance(err, str) else None,
        [w for w in warns if isinstance(w, str)] if isinstance(warns, list) else [],
    )


def _rendered_sections(pf, a) -> list[Section]:
    out = []
    for name, ds in a.views:
        if ds is None:
            continue
        t = pf.result_table(ds)
        if t is None or is_empty_rows(t.rows):
            continue
        n = len(t.columns)
        rows = [list(r) + [""] * (n - len(r)) for r in t.rows]
        out.append(Section(
            title=name if name.strip() else t.title,
            columns=list(t.columns),
            rows=rows,
            note=_NOTE if t.data_format == "text" else None,
        ))
    return out


def _major_unknown(pf) -> bool:
    raw = pf.format_version_raw
    return raw is not None and (not pf.format_version or pf.format_version[0] != 1)


def read_analysis(pf, a) -> Report:
    warnings: list[str] = list(a.alerts)
    warn = warnings.append
    if a.is_calculated is False and not a.has_results:
        warn(
            "Not calculated when saved: open the file in Prism, "
            "view this analysis's results and save again."
        )
        return Report(a, "not_calculated", [], warnings)
    err, codes = _status(a)
    if a.results is None or all(k == "status" for k in a.results):
        if a.results is None:
            warn(f"No stored results (file saved by Prism {pf.saved_with or 'unknown'}).")
        if err is not None and err != "VALID":
            warn(f"Prism reported {err}")
        return Report(a, "generic", _rendered_sections(pf, a), warnings)
    kind, sections = "generic", None
    if _major_unknown(pf):
        sections = generic_sections(pf, a)
    else:
        reader = REGISTRY.get(a.analysis_class)
        if reader is not None:
            try:
                sections = reader(pf, a, warn)
                kind = "structured"
            except _READER_ERRORS as e:
                warn(f"Structured reader failed ({type(e).__name__}), showing generic values.")
        if sections is None:
            sections = generic_sections(pf, a)
    warnings.extend(codes)
    if err is not None and err != "VALID":
        warn(f"Prism reported {err}")
    return Report(a, kind, sections, warnings)


__all__ = ["REGISTRY", "register", "read_analysis", "flatten", "generic_sections"]
