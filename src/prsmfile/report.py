from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Union

from .values import PValue

if TYPE_CHECKING:
    from .archive import Analysis

Cell = Union[str, int, float, bool, None, PValue]


def is_empty_rows(rows) -> bool:
    """True when every cell of every row is blank (None, or whitespace-only text)."""
    for row in rows:
        for cell in row:
            if cell is None:
                continue
            if isinstance(cell, str) and not cell.strip():
                continue
            return False
    return True


@dataclass
class Section:
    title: str
    columns: list[str]
    rows: list[list[Cell]]
    note: str | None = None


def _cell(c: Cell):
    if isinstance(c, PValue):
        return {"p": c.value, "bound": c.bound, "significant": c.significant, "alpha": c.alpha}
    return c


@dataclass
class Report:
    analysis: "Analysis"
    kind: str  # "structured" | "generic" | "not_calculated"
    sections: list[Section] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        a = self.analysis
        return {
            "id": a.id,
            "title": a.title,
            "class": a.analysis_class,
            "kind": self.kind,
            "calculated": a.is_calculated,
            "warnings": list(self.warnings),
            "sections": [
                {
                    "title": s.title,
                    "columns": list(s.columns),
                    "rows": [[_cell(c) for c in row] for row in s.rows],
                    "note": s.note,
                }
                for s in self.sections
            ],
        }
