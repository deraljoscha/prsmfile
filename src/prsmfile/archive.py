from __future__ import annotations

import copy
import io
import json
import math
import os
import re
import struct
import threading
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

# Limits against zip bombs and oversized members. Real Prism files store members
# (compression ratio 1) and stay far below these values.
MAX_MEMBERS = 100_000  # number of entries in the archive
MAX_DIRECTORY_SIZE = 64 * 1024 * 1024  # bytes of the central directory (the member list)
MAX_MEMBER_SIZE = 512 * 1024 * 1024  # bytes of one member read into memory
MAX_TOTAL_SIZE = 4 * 1024 * 1024 * 1024  # bytes across all members read from one file
MAX_RATIO = 200  # uncompressed / compressed size of one member ...
RATIO_MIN_SIZE = 10 * 1024 * 1024  # ... only checked for members larger than this
_CHUNK = 1024 * 1024
# Only these are read: the decompression of other methods (bzip2, lzma) is not
# bounded by the chunked reads, and Prism does not write them.
_METHODS = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)


class _BudgetError(PrismFormatError):
    """MAX_TOTAL_SIZE used up."""


def _read_bounded(fp, name: str, limit: int, what: str = "MAX_MEMBER_SIZE", on_chunk=None) -> bytes:
    """Read a stream to the end, raising PrismFormatError once it exceeds limit
    bytes. Never trusts a size from the archive header. on_chunk(n) is called with
    the size of every chunk as soon as it has been read."""
    parts: list[bytes] = []
    got = 0
    while True:
        chunk = fp.read(min(_CHUNK, limit + 1 - got))
        if not chunk:
            return b"".join(parts)
        got += len(chunk)
        if on_chunk is not None:
            on_chunk(len(chunk))
        if got > limit:
            raise PrismFormatError(f"{name}: member larger than the limit of {limit} bytes ({what})")
        parts.append(chunk)


def _check_directory(path) -> None:
    """Reject archives with too many members or a too large member list before
    zipfile parses the central directory (its cost grows with both). Reads only the
    end-of-central-directory records (and the zip64 one); the member count is
    checked again after parsing. Anything unreadable is left to zipfile."""
    try:
        with io.open(os.fspath(path), "rb") as fp:
            fp.seek(0, 2)
            size = fp.tell()
            tail_len = min(size, 22 + 0xFFFF + 20)  # record, longest comment, zip64 locator
            fp.seek(size - tail_len)
            tail = fp.read(tail_len)
            i = tail.rfind(b"PK\x05\x06")
            if i < 0 or len(tail) - i < 22:
                return
            _s, _d, _cd, _n, count, cd_size, _off, _c = struct.unpack("<4s4H2LH", tail[i:i + 22])
            if i >= 20 and tail[i - 20:i - 16] == b"PK\x06\x07":
                _s, _disk, off64, _disks = struct.unpack("<4sLQL", tail[i - 20:i])
                fp.seek(off64)
                rec = fp.read(56)
                if len(rec) == 56 and rec[:4] == b"PK\x06\x06":
                    fields = struct.unpack("<4sQHHLLQQQQ", rec)
                    count, cd_size = max(count, fields[7]), max(cd_size, fields[8])
    except (OSError, TypeError, ValueError, OverflowError, struct.error):
        return
    if count > MAX_MEMBERS:
        raise PrismFormatError(
            f"{path}: {count} members exceed the limit of {MAX_MEMBERS} (MAX_MEMBERS)"
        )
    if cd_size > MAX_DIRECTORY_SIZE:
        raise PrismFormatError(
            f"{path}: member list of {cd_size} bytes exceeds the limit of "
            f"{MAX_DIRECTORY_SIZE} bytes (MAX_DIRECTORY_SIZE)"
        )


def _is_opaque(name: str) -> bool:
    """Members that are never read: media, binary graph and layout data."""
    return name.startswith("media/") or name.endswith(".bin")


def _text(x) -> str | None:
    if isinstance(x, str) and x.strip():
        return x
    return None


def _norm(s: str) -> str:
    return " ".join(s.split())


def _squash(s: str) -> str:
    """All whitespace removed: Prism stores alertText without the separators of the note."""
    return "".join(s.split())


_LINE_SEP = re.compile(r"(\r\n|\r|\n)")


def _drop_link_text(s: str) -> str:
    """Remove the UI link text "Learn more" that Prism appends to a note paragraph."""
    parts = _LINE_SEP.split(s)  # text, sep, text, sep, ...
    out: list[str] = []
    i = 0
    while i < len(parts):
        if i % 2 == 0 and parts[i].strip() == "Learn more":
            i += 2  # the text and the separator after it
            continue
        out.append(parts[i])
        i += 1
    return "".join(out).strip()


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
    views: list[tuple[str, str | None]] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    input_titles: list[str | None] = field(default_factory=list)  # title as stored, None if blank; parallel to inputs

    @property
    def has_results(self) -> bool:
        return self.results is not None


class PrismFile:
    def __init__(self, path):
        self.path = path
        self.warnings: list[str] = []
        self._analyses: list[Analysis] | None = None
        self._view_ids: frozenset[str] | None = None
        self._total_read = 0  # bytes of all reads, each member counted once (see _charge)
        self._charged: dict[str, int] = {}
        self._budget_lock = threading.Lock()  # PrismFile is otherwise single-threaded
        _check_directory(path)
        try:
            self._zip = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            raise PrismFormatError(f"{path}: not a zip archive (not a .prism file)") from None
        except OSError as e:
            raise PrismFormatError(f"{path}: {e.strerror or e}") from None
        except (UnicodeDecodeError, NotImplementedError, EOFError, zlib.error, RuntimeError) as e:
            raise PrismFormatError(f"{path}: unsupported or damaged zip archive ({e})") from None
        try:
            n_members = len(self._zip.infolist())
            if n_members > MAX_MEMBERS:
                raise PrismFormatError(
                    f"{path}: {n_members} members exceed the limit of {MAX_MEMBERS} (MAX_MEMBERS)"
                )
            self._names = set(self._zip.namelist())
            if "document.json" not in self._names:
                raise PrismFormatError(f"{path}: document.json missing (not a .prism file)")
            try:
                raw = self._read_member("document.json")
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

    def _charge(self, name: str, got: int) -> None:
        """Account for got bytes read from name in the current read. A member counts
        with the most bytes any read of it has used, so repeated access is free."""
        with self._budget_lock:
            more = got - self._charged.get(name, 0)
            if more > 0:
                self._charged[name] = got
                self._total_read += more
            if self._total_read > MAX_TOTAL_SIZE:
                raise _BudgetError(
                    f"{name}: total size read exceeds the limit of "
                    f"{MAX_TOTAL_SIZE} bytes (MAX_TOTAL_SIZE)"
                )

    def _read_member(self, name: str) -> bytes:
        """Bytes of a member, within MAX_MEMBER_SIZE, MAX_RATIO and MAX_TOTAL_SIZE.
        The data must be exactly as long as the header says."""
        info = self._zip.getinfo(name)
        if info.compress_type not in _METHODS:
            raise PrismFormatError(
                f"{name}: unsupported compression method {info.compress_type} (only stored and deflate)"
            )
        declared = info.file_size
        if declared > MAX_MEMBER_SIZE:
            raise PrismFormatError(
                f"{name}: member size {declared} exceeds the limit of "
                f"{MAX_MEMBER_SIZE} bytes (MAX_MEMBER_SIZE)"
            )
        if declared > RATIO_MIN_SIZE and declared > MAX_RATIO * info.compress_size:
            raise PrismFormatError(
                f"{name}: compression ratio exceeds the limit of {MAX_RATIO} (MAX_RATIO)"
            )
        mismatch = PrismFormatError(f"{name}: data size differs from the size {declared} in the archive header")
        # zipfile stops reading at file_size: one byte more lets the reader show data
        # that is longer than the header says instead of silently truncating it
        probe = copy.copy(info)
        probe.file_size = declared + 1
        seen = 0

        def count(n: int) -> None:
            nonlocal seen
            seen += n
            self._charge(name, seen)

        with self._zip.open(probe) as fp:
            try:
                data = _read_bounded(fp, name, declared, "size in the archive header", count)
            except _BudgetError:
                raise
            except PrismFormatError:
                raise mismatch from None
            except zipfile.BadZipFile:
                if seen != declared:  # the CRC fails because the length is wrong
                    raise mismatch from None
                raise
        if len(data) != declared:
            raise mismatch
        return data

    def read_text(self, name: str) -> str | None:
        if _is_opaque(name) or name not in self._names:
            return None
        try:
            return self._read_member(name).decode("utf-8")
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
        # copies: callers cannot change the cached state
        return [
            replace(
                a,
                parameters=copy.deepcopy(a.parameters),
                results=copy.deepcopy(a.results),
                inputs=list(a.inputs),
                input_titles=list(a.input_titles),
                views=list(a.views),
                alerts=list(a.alerts),
            )
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
        head = _text(sheet.get("alertText"))
        notes = []
        pattern = re.compile(re.escape(base) + r"floating_notes/[^/]+\.json")
        for n in self._zip.namelist():  # archive member order
            if not pattern.fullmatch(n):
                continue
            note = self.read_json(n)
            if not note or note.get("isAuto") is not True:
                continue
            s = note.get("text")
            s = s.get("string") if isinstance(s, dict) else None
            s = _drop_link_text(s) if _text(s) else None
            if s:
                notes.append(s)
        texts = []
        if head:
            head = _drop_link_text(head)
            # alertText is often the first characters of a note without its separators
            sq = _squash(head)
            if head and not any(_squash(s).startswith(sq) and _squash(s) != sq for s in notes):
                texts.append(head)
        texts.extend(notes)
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
