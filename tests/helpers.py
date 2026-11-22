from __future__ import annotations


def assert_sections_well_formed(report) -> None:
    for section in report.sections:
        n = len(section.columns)
        for i, row in enumerate(section.rows):
            assert len(row) == n, (
                f"section {section.title!r} row {i} has {len(row)} cells, expected {n}"
            )
