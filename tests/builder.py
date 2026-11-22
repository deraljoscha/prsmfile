"""Synthetic .prism builder matching docs/format.md sections 1.2 to 1.4."""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

# subcolumns per data-set format (docs/format.md 1.7); all others are 1
_WIDTH = {"y_sd_n": 3, "y_sd": 2, "y_se": 2, "y_plus_minus": 3, "date_se": 2, "y_errorBar": 2}


def _letter_index(ltr) -> int:
    """Spreadsheet letters to a 0-based index (A 0, Z 25, AA 26); -1 if not letters."""
    if not isinstance(ltr, str) or not ltr.isalpha() or not ltr.isascii():
        return -1
    n = 0
    for ch in ltr.upper():
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


class PrismBuilder:
    def __init__(self):
        self._members: dict[str, bytes] = {}
        self._data_ids: list[str] = []
        self._analysis_ids: list[str] = []
        self._titles: dict[str, str] = {}
        self._n = 0
        self._sets: dict[str, list[str]] = {}
        self._last_raw: str | None = None
        self._view_titles: dict[str, str] = {}

    def _uid(self) -> str:
        self._n += 1
        return str(uuid.uuid5(uuid.NAMESPACE_OID, f"prsmfile-test-{self._n}")).upper()

    @staticmethod
    def _dump(obj) -> bytes:
        return json.dumps(obj, indent="\t", ensure_ascii=False).encode("utf-8")

    def add_member(self, name: str, data: bytes) -> None:
        self._members[name] = data

    @staticmethod
    def keyed(items) -> dict:
        out = {}
        for id_, value in items:
            key = str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(id_, sort_keys=True)))
            out[key] = {"id": id_, "value": value}
        return out

    @staticmethod
    def _csv(rows: list[list[str]]) -> bytes:
        """RFC 4180 with LF row ends; cells with comma, quote, CR or LF are quoted
        (the csv module does not quote a bare CR on Python 3.10)."""
        def cell(c: str) -> str:
            if any(ch in c for ch in ',"\r\n'):
                return '"' + c.replace('"', '""') + '"'
            return c

        def line(r: list[str]) -> str:
            if r == [""]:  # a bare empty line would read back as no row
                return '""\n'
            return ",".join(cell(c) for c in r) + "\n"

        return "".join(line(r) for r in rows).encode("utf-8")

    def _write_table(self, rows: list[list[str]]) -> str:
        t = self._uid()
        width = max((len(r) for r in rows), default=0)
        self._members[f"data/tables/{t}/data.csv"] = self._csv(rows)
        self._members[f"data/tables/{t}/content.json"] = self._dump(
            {"numberOfColumns": width, "numberOfRows": len(rows), "version": 1}
        )
        self._members[f"data/tables/{t}/data.dt"] = uuid.uuid5(uuid.NAMESPACE_OID, f"dt-{t}").hex.encode()
        return t

    def _write_set(self, title, fmt: str, width: int, extra: dict | None = None) -> str:
        d = self._uid()
        obj = {
            "@class": "DataSet",
            "uid": d,
            "format": fmt,
            "replicates": [
                {"@class": "DriverReplicate", "valueType": "string" if fmt == "text" else "real"}
                for _ in range(width)
            ],
        }
        if title is not None:
            obj["title"] = title
        if extra:
            obj.update(extra)
        self._members[f"data/sets/{d}.json"] = self._dump(obj)
        return d

    def data_sets(self, sheet_id: str) -> list[str]:
        """Data set uids of a raw table, in column order."""
        return list(self._sets[sheet_id])

    def add_raw_table(
        self,
        title,
        table_format,
        data_sets,
        rows,
        row_titles=False,
        x_data_set=None,
        subcolumn_titles=None,
    ) -> str:
        sid = self._uid()
        t = self._write_table(rows)
        set_ids = [self._write_set(*ds) for ds in data_sets]
        table = {
            "@class": "XYDataTable" if (x_data_set is not None or table_format in ("xy", "survival")) else "DataTable",
            "uid": t,
            "format": table_format,
            "dataFormat": data_sets[0][1] if data_sets else "y_replicates",
            "dataSets": set_ids,
        }
        if row_titles:
            table["rowTitlesDataSet"] = self._write_set(None, "text", 1)
        if x_data_set is not None:
            table["xDataSet"] = self._write_set(*x_data_set)
            table["xDataSetFormat"] = x_data_set[1]
        if subcolumn_titles is not None:
            ncols = max(
                [ds[2] for ds in data_sets]
                or [len(c.get("replicates", [])) for c in subcolumn_titles]
                or [0]
            )
            table["replicatesCount"] = ncols
            table["subcolumnTitlesDataSet"] = self._write_set(
                None, "text_replicates", 0, {"replicate count": ncols, "titles": subcolumn_titles}
            )
        self._members[f"data/sheets/{sid}/sheet.json"] = self._dump(
            {"@class": "DataSheet", "uid": sid, "title": title, "table": table}
        )
        self._data_ids.append(sid)
        self._titles[sid] = title
        self._sets[sid] = set_ids
        self._last_raw = sid
        return sid

    def add_analysis(
        self,
        title,
        analysis_class,
        parameters,
        results,
        is_calculated=True,
        inputs=(),
        views=(),
        listed=True,
        alert=None,
        auto_note=None,
    ) -> str:
        aid = self._uid()
        base = f"analyses/{aid}/"
        sheet = {
            "@class": "AnalysisSheet",
            "uid": aid,
            "analysisClass": analysis_class,
            "resultSheets": [],
            "inputDataSets": [],
        }
        if title is not None:
            sheet["title"] = title
        if is_calculated is not None:
            sheet["isCalculated"] = is_calculated
        if alert is not None:
            sheet["alertText"] = alert
        input_sheets: list[str] = []
        for item in inputs:
            if item is None:
                sheet["inputDataSets"].append(None)
                continue
            ltr, ititle = item[0], item[1]
            ref = item[2] if len(item) > 2 else None
            if ref is None and self._last_raw is not None:
                ref = (self._last_raw, _letter_index(ltr))
            uid = self._uid()  # dangling unless a real data set is referenced
            if isinstance(ref, str):
                uid = ref
                for sid, ids in self._sets.items():  # owning sheet, if any
                    if ref in ids and sid not in input_sheets:
                        input_sheets.append(sid)
            elif isinstance(ref, tuple) and 0 <= ref[1] < len(self._sets.get(ref[0], [])):
                uid = self._sets[ref[0]][ref[1]]
                if ref[0] not in input_sheets:
                    input_sheets.append(ref[0])
            entry = {"uid": uid}
            if ltr is not None:
                entry["idx"] = ltr
            if ititle is not None:
                entry["title"] = ititle
            sheet["inputDataSets"].append(entry)
        sheet["inputSheets"] = [
            {"uid": u, "title": self._titles[u] if u in self._titles else self._view_titles[u]} for u in input_sheets
        ]
        self._members[base + "parameters.json"] = self._dump(
            {"@class": "AnalysisParameters", "version": "0.0.0", "content": parameters}
        )
        if results is None:
            self._members[base + "results.json"] = self._dump({"@class": "AnalysisResults"})
        else:
            self._members[base + "results.json"] = self._dump(
                {"@class": "AnalysisResults", "$id": "analyses/x/results.schema.json",
                 "version": "0.0.0", "content": results}
            )
        for idx, view in enumerate(views):
            name, vrows = view[0], view[1]
            fmt = view[2] if len(view) > 2 else "text"
            ncols = view[3] if len(view) > 3 else None  # csv column count
            width = view[4] if len(view) > 4 else None  # subcolumns per data set
            v, r = self._uid(), self._uid()
            tuid = self._uid() if vrows is None else self._write_table(vrows)
            if ncols is None:
                ncols = 1 if vrows is None else max((len(x) for x in vrows), default=0)
            w = width or _WIDTH.get(fmt, 1)
            vsets = [self._write_set(None, fmt, w) for _ in range(-(-ncols // w))]
            self._sets[r] = vsets
            self._view_titles[r] = f"{title}:{name}"
            sheet["resultSheets"].append({"uid": v, "title": name})
            self._members[base + f"result_sheets/{v}.json"] = self._dump(
                {"@class": "AnalysisView", "uid": v, "name": name, "viewIdx": idx, "dataSheet": r}
            )
            self._members[f"data/sheets/{r}/sheet.json"] = self._dump(
                {"@class": "DataSheet", "uid": r, "title": f"{title}:{name}",
                 "table": {"@class": "DataTable", "uid": tuid, "format": "view",
                           "dataFormat": fmt, "dataSets": vsets}}
            )
        if auto_note is not None:
            n = self._uid()
            self._members[base + f"floating_notes/{n}.json"] = self._dump(
                {"@class": "FloatingNote", "uid": n, "isAuto": True, "text": {"string": auto_note, "version": 1}}
            )
        self._members[base + "sheet.json"] = self._dump(sheet)
        if listed:
            self._analysis_ids.append(aid)
        if title is not None:
            self._titles[aid] = title
        return aid

    def save(self, path, format_version="1-6-1", prism_version="11.1.0.224", user="tester") -> Path:
        path = Path(path)
        who = {"name": "Prism", "user": user, "version": prism_version, "platform": "Win"}
        doc = {
            "@class": "Document",
            "formatVersion": format_version,
            "createdBy": who,
            "modifiedBy": who,
            "sheets": {"graphs": [], "analyses": self._analysis_ids, "info": [],
                       "data": self._data_ids, "layouts": []},
            "sheetAttributesMap": {k: {"title": v} for k, v in self._titles.items()},
        }
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in [("document.json", self._dump(doc)), *self._members.items()]:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))  # fixed: same bytes every run
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3  # fixed (Unix): the field otherwise follows the platform
                info.external_attr = 0o644 << 16
                z.writestr(info, data)
        return path
