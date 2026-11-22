from __future__ import annotations


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
