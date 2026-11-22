"""Synthetic .prism builder matching docs/format.md sections 1.2 to 1.4."""
from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile
from pathlib import Path


class PrismBuilder:
    def __init__(self):
        self._members: dict[str, bytes] = {}
        self._data_ids: list[str] = []
        self._analysis_ids: list[str] = []
        self._titles: dict[str, str] = {}
        self._n = 0

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

    def _csv(self, rows: list[list[str]]) -> bytes:
        if not rows:
            return b""
        buf = io.StringIO(newline="")
        csv.writer(buf, lineterminator="\n").writerows(rows)
        return buf.getvalue().encode("utf-8")

    def _write_table(self, rows: list[list[str]]) -> str:
        t = self._uid()
        width = max((len(r) for r in rows), default=0)
        self._members[f"data/tables/{t}/data.csv"] = self._csv(rows)
        self._members[f"data/tables/{t}/content.json"] = self._dump(
            {"numberOfColumns": width, "numberOfRows": len(rows), "version": 1}
        )
        self._members[f"data/tables/{t}/data.dt"] = uuid.uuid4().hex.encode()
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
        table = {
            "@class": "DataTable",
            "uid": t,
            "format": table_format,
            "dataFormat": "y_replicates",
            "dataSets": [self._write_set(*ds) for ds in data_sets],
        }
        if row_titles:
            table["rowTitlesDataSet"] = self._write_set(None, "text", 1)
        if x_data_set is not None:
            table["xDataSet"] = self._write_set(*x_data_set)
            table["xDataSetFormat"] = x_data_set[1]
        if subcolumn_titles is not None:
            ncols = max((len(c.get("replicates", [])) for c in subcolumn_titles), default=0)
            table["subcolumnTitlesDataSet"] = self._write_set(
                None, "text_replicates", 0, {"replicate count": ncols, "titles": subcolumn_titles}
            )
        self._members[f"data/sheets/{sid}/sheet.json"] = self._dump(
            {"@class": "DataSheet", "uid": sid, "title": title, "table": table}
        )
        self._data_ids.append(sid)
        self._titles[sid] = title
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
        for item in inputs:
            if item is None:
                sheet["inputDataSets"].append(None)
                continue
            ltr, ititle = item
            entry = {"uid": self._uid(), "idx": ltr}
            if ititle is not None:
                entry["title"] = ititle
            sheet["inputDataSets"].append(entry)
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
            v, r = self._uid(), self._uid()
            tuid = self._uid() if vrows is None else self._write_table(vrows)
            sheet["resultSheets"].append({"uid": v, "title": name})
            self._members[base + f"result_sheets/{v}.json"] = self._dump(
                {"@class": "AnalysisView", "uid": v, "name": name, "viewIdx": idx, "dataSheet": r}
            )
            self._members[f"data/sheets/{r}/sheet.json"] = self._dump(
                {"@class": "DataSheet", "uid": r, "title": f"{title}:{name}",
                 "table": {"@class": "DataTable", "uid": tuid, "format": "view",
                           "dataFormat": fmt, "dataSets": []}}
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

    def save(self, path, format_version="1-6-1", prism_version="11.1.0.224") -> Path:
        path = Path(path)
        who = {"name": "Prism", "user": "tester", "version": prism_version, "platform": "Win"}
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
            z.writestr("document.json", self._dump(doc))
            for name, data in self._members.items():
                z.writestr(name, data)
        return path
