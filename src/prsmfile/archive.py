from __future__ import annotations

import json
import math
import re
import zipfile
import zlib
from dataclasses import dataclass, field, replace

from .errors import PrismFormatError
from .values import letter

_SHEET_RE = re.compile(r"analyses/([^/]+)/sheet\.json")
_READ_ERRORS = (
    zipfile.BadZipFile,
    zlib.error,
    OSError,
    EOFError,
    NotImplementedError,
    RuntimeError,
    UnicodeDecodeError,
)
_JSON_ERRORS = (ValueError, RecursionError)


def _is_opaque(name: str) -> bool:
    """Members that are never read: media, binary graph and layout data."""
    return name.startswith("media/") or name.endswith(".bin")


def _text(x) -> str | None:
    if isinstance(x, str) and x.strip():
        return x
    return None


def _norm(s: str) -> str:
    return " ".join(s.split())


def _parse_version(raw) -> tuple[int, ...]:
    if not isinstance(raw, str):
        return ()
    try:
        return tuple(int(p) for p in raw.split("-"))
    except ValueError:
        return ()


@dataclass
class Analysis:
    id: str
    title: str
    analysis_class: str
    is_calculated: bool | None
    parameters: dict = field(default_factory=dict)
    results: dict | None = None
    inputs: list[tuple[str, str]] = field(default_factory=list)  # (letter, title or letter)
    input_titles: list[str | None] = field(default_factory=list)  # title as stored, None if blank; parallel to inputs
    views: list[tuple[str, str | None]] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)

    # parameters and results are shared with the cache: treat them as read-only

    @property
    def has_results(self) -> bool:
        return self.results is not None


class PrismFile:
    def __init__(self, path):
        self.path = path
        self.warnings: list[str] = []
        self._analyses: list[Analysis] | None = None
        self._view_ids: frozenset[str] | None = None
        try:
            self._zip = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            raise PrismFormatError(f"{path}: not a zip archive (not a .prism file)") from None
        except OSError as e:
            raise PrismFormatError(f"{path}: {e.strerror or e}") from None
        except (UnicodeDecodeError, NotImplementedError, EOFError, zlib.error, RuntimeError) as e:
            raise PrismFormatError(f"{path}: unsupported or damaged zip archive ({e})") from None
        try:
            self._names = set(self._zip.namelist())
            if "document.json" not in self._names:
                raise PrismFormatError(f"{path}: document.json missing (not a .prism file)")
            try:
                raw = self._zip.read("document.json")
                doc = json.loads(raw.decode("utf-8"))
            except _READ_ERRORS + _JSON_ERRORS as e:
                raise PrismFormatError(f"{path}: document.json unreadable ({e})") from None
            if not isinstance(doc, dict):
                raise PrismFormatError(f"{path}: document.json root is not an object")
        except BaseException:
            self._zip.close()
            raise
        self._doc = doc
        raw_v = doc.get("formatVersion")
        self.format_version_raw: str | None = raw_v if isinstance(raw_v, str) else None
        self.format_version: tuple[int, ...] = _parse_version(raw_v)
        if not self.format_version or self.format_version[0] != 1:
            raw = self.format_version_raw if self.format_version_raw is not None else "missing"
            self.warnings.append(f"Unknown format version {raw}; structured readers skipped.")
        self.prism_version = self._version_of("createdBy")
        self.saved_with = self._version_of("modifiedBy")

    def _version_of(self, key: str) -> str | None:
        v = self._doc.get(key)
        v = v.get("version") if isinstance(v, dict) else None
        return v if isinstance(v, str) else None

    def __enter__(self) -> "PrismFile":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._zip.close()

    def _warn(self, msg: str) -> None:
        if msg not in self.warnings:  # members may be read by several indexes
            self.warnings.append(msg)

    def read_text(self, name: str) -> str | None:
        if _is_opaque(name) or name not in self._names:
            return None
        try:
            return self._zip.read(name).decode("utf-8")
        except UnicodeDecodeError:
            self._warn(f"Could not decode {name}")
        except _READ_ERRORS:
            self._warn(f"Could not read {name}")
        return None

    def read_json(self, name: str) -> dict | None:
        text = self.read_text(name)
        if text is None:
            return None
        try:
            obj = json.loads(text)
        except _JSON_ERRORS:
            self._warn(f"Could not parse {name}")
            return None
        if not isinstance(obj, dict):
            self._warn(f"{name} is not a JSON object")
            return None
        return obj

    def data_tables(self) -> list[str]:
        """Sheet ids of the raw data tables, in the listed order."""
        sheets = self._doc.get("sheets")
        lst = sheets.get("data") if isinstance(sheets, dict) else None
        out: list[str] = []
        for sid in lst if isinstance(lst, list) else []:
            if isinstance(sid, str) and sid not in out:
                out.append(sid)
        return out

    def result_table(self, sheet_id: str):
        """The data table behind a view's result sheet id, or None."""
        from .tables import read_table

        if not isinstance(sheet_id, str) or sheet_id not in self._view_sheet_ids():
            return None
        return read_table(self, sheet_id)

    def _view_sheet_ids(self) -> frozenset[str]:
        """Data-sheet ids of all result views, indexed once from sheet.json
        resultSheets and the result_sheets members (no parameters or results)."""
        if self._view_ids is None:
            ids: set[str] = set()
            for n in sorted(self._names):
                m = _SHEET_RE.fullmatch(n)
                if not m:
                    continue
                sheet = self.read_json(n)
                refs = sheet.get("resultSheets") if sheet else None
                for r in refs if isinstance(refs, list) else []:
                    uid = r.get("uid") if isinstance(r, dict) else None
                    if not isinstance(uid, str) or "/" in uid:
                        continue
                    v = self.read_json(f"analyses/{m.group(1)}/result_sheets/{uid}.json")
                    ds = v.get("dataSheet") if v else None
                    if isinstance(ds, str):
                        ids.add(ds)
            self._view_ids = frozenset(ids)
        return self._view_ids

    def analyses(self) -> list[Analysis]:
        if self._analyses is None:
            self._analyses = self._discover()
        # copies of the mutable lists: callers cannot change the cached state
        return [
            replace(a, inputs=list(a.inputs), input_titles=list(a.input_titles), views=list(a.views), alerts=list(a.alerts))
            for a in self._analyses
        ]

    def _discover(self) -> list[Analysis]:
        ids = []
        for n in self._zip.namelist():
            m = _SHEET_RE.fullmatch(n)
            if m:
                ids.append(m.group(1))
        found: dict[str, Analysis] = {}
        for aid in ids:
            a = self._load(aid)
            if a is not None:
                found[aid] = a
        listed = []
        sheets = self._doc.get("sheets")
        lst = sheets.get("analyses") if isinstance(sheets, dict) else None
        if isinstance(lst, list):
            for aid in lst:
                if isinstance(aid, str) and aid in found and aid not in listed:
                    listed.append(aid)
        rest = sorted((a for k, a in found.items() if k not in listed), key=lambda a: a.title)
        return [found[k] for k in listed] + rest

    def _load(self, aid: str) -> Analysis | None:
        base = f"analyses/{aid}/"
        sheet = self.read_json(base + "sheet.json")
        if sheet is None:
            self.warnings.append(f"Skipped analysis {aid}: unreadable sheet.json")
            return None
        calc = sheet.get("isCalculated")
        a = Analysis(
            id=aid,
            title=_text(sheet.get("title")) or "(untitled)",
            analysis_class=_text(sheet.get("analysisClass")) or "UNKNOWN",
            is_calculated=calc if isinstance(calc, bool) else None,
        )
        params = self.read_json(base + "parameters.json")
        content = params.get("content") if params else None
        a.parameters = content if isinstance(content, dict) else {}
        res = self.read_json(base + "results.json")
        content = res.get("content") if res else None
        a.results = content if isinstance(content, dict) else None
        items = sheet.get("inputDataSets")
        for i, item in enumerate(items if isinstance(items, list) else []):
            if not isinstance(item, dict):
                continue
            idx = item.get("idx")
            ltr = idx if isinstance(idx, str) and idx.strip() else letter(i)
            title = _text(item.get("title"))
            a.inputs.append((ltr, title or ltr))
            a.input_titles.append(title)
        a.views = self._views(base, sheet)
        a.alerts = self._alerts(base, sheet)
        return a

    def _views(self, base: str, sheet: dict) -> list[tuple[str, str | None]]:
        refs = sheet.get("resultSheets")
        uids: list[str] = []
        for r in refs if isinstance(refs, list) else []:
            uid = r.get("uid") if isinstance(r, dict) else None
            if isinstance(uid, str) and "/" not in uid and uid not in uids:
                uids.append(uid)
        out = []
        for uid in uids:
            v = self.read_json(f"{base}result_sheets/{uid}.json")
            if v is None:
                continue
            key = v.get("viewIdx")
            ok = (isinstance(key, int) and not isinstance(key, bool)) or (
                isinstance(key, float) and math.isfinite(key)
            )
            name = v.get("name")
            ds = v.get("dataSheet")
            out.append((
                (0, key) if ok else (1, 0),  # ints stay exact; missing last
                (name if _text(name) else "", ds if isinstance(ds, str) else None),
            ))
        out.sort(key=lambda p: p[0])  # stable
        return [p[1] for p in out]

    def _alerts(self, base: str, sheet: dict) -> list[str]:
        texts = []
        t = _text(sheet.get("alertText"))
        if t:
            texts.append(t.strip())
        pattern = re.compile(re.escape(base) + r"floating_notes/[^/]+\.json")
        for n in self._zip.namelist():  # archive member order
            if not pattern.fullmatch(n):
                continue
            note = self.read_json(n)
            if not note or note.get("isAuto") is not True:
                continue
            s = note.get("text")
            s = s.get("string") if isinstance(s, dict) else None
            if _text(s):
                texts.append(s.strip())
        seen: set[str] = set()
        out = []
        for s in texts:
            k = _norm(s)
            if k not in seen:
                seen.add(k)
                out.append(s)
        return out


def open(path) -> PrismFile:  # noqa: A001
    return PrismFile(path)
