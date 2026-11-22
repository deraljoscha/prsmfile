"""AREA_UNDER_CURVE (docs/format.md 2.6)."""
from __future__ import annotations

import re

from ..report import Section
from ..values import entries, num
from . import register
from .nonlinear import dataset_label

_SUMMARY_COLUMNS = ["Data set", "Baseline", "Total area", "Total peak area", "Peaks"]
_PEAK_COLUMNS = ["Data set", "Peak", "First X", "Last X", "Peak X", "Peak Y", "Area", "Area %"]
_PEAK_RE = re.compile(r"(\d+)")


def _dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def _peak_order(name) -> tuple:
    m = _PEAK_RE.search(name) if isinstance(name, str) else None
    return (0, int(m.group(1)), "") if m else (1, 0, str(name))


@register("AREA_UNDER_CURVE")
def read_auc(pf, a, warn):
    samples = a.results.get("samples")
    if not isinstance(samples, dict):
        raise KeyError("samples")
    summary_rows, peak_rows = [], []
    for id_, value in entries(samples):
        v = _dict(value)
        ds = dataset_label(id_)
        s = _dict(v.get("summary"))
        summary_rows.append([ds, num(s.get("baseline")), num(s.get("totalArea")),
                             num(s.get("totalPeakArea")), num(s.get("peakCount"))])
        peaks = _dict(v.get("peaks"))
        for name in sorted(peaks, key=_peak_order):
            p = _dict(peaks[name])
            peak_rows.append([ds, str(name), num(p.get("firstX")), num(p.get("lastX")),
                              num(p.get("peakX")), num(p.get("peakY")), num(p.get("area")),
                              num(p.get("areaPercentage"))])
    sections = []
    if summary_rows:
        sections.append(Section("Area under curve", list(_SUMMARY_COLUMNS), summary_rows))
    if peak_rows:
        sections.append(Section("Peaks", list(_PEAK_COLUMNS), peak_rows))
    return sections
