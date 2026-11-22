from pathlib import Path

import pytest

import prsmfile
from prsmfile import read_analysis

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "cc0-figure4.prism"

pytestmark = pytest.mark.skipif(not EXAMPLE.is_file(), reason="examples/cc0-figure4.prism not present")


def test_example_opens_with_structured_t_test():
    with prsmfile.open(EXAMPLE) as pf:
        reports = [read_analysis(pf, a) for a in pf.analyses()]
    structured = [r for r in reports
                  if r.kind == "structured" and r.analysis.analysis_class == "T_TESTS_AND_NONPARAMETRIC"]
    assert structured
