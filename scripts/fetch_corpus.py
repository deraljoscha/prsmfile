#!/usr/bin/env python3
"""Download the public test corpus listed in tests/corpus_manifest.json.

Usage: python scripts/fetch_corpus.py [--dest corpus] [--limit N]

Files that already exist with the right SHA256 are skipped. Exit status 1 if a
downloaded or existing file does not match its recorded hash. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "corpus_manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dest", default=str(ROOT / "corpus"), help="target directory (default: corpus)")
    ap.add_argument("--limit", type=int, default=None, help="only the first N manifest entries")
    args = ap.parse_args(argv)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.limit is not None:
        manifest = manifest[: args.limit]
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    failed = 0
    for entry in manifest:
        target = dest / entry["file"]
        if target.is_file() and sha256(target) == entry["sha256"]:
            print(f"ok       {entry['file']} (already present)")
            continue
        tmp = target.with_name(target.name + ".part")
        try:
            with urllib.request.urlopen(entry["download_url"], timeout=60) as resp, open(tmp, "wb") as out:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
        except (OSError, http.client.HTTPException) as e:  # IncompleteRead is an HTTPException
            print(f"FAILED   {entry['file']}: {e}", file=sys.stderr)
            tmp.unlink(missing_ok=True)
            failed += 1
            continue
        if sha256(tmp) != entry["sha256"]:
            print(f"MISMATCH {entry['file']}: SHA256 differs from the manifest", file=sys.stderr)
            tmp.unlink(missing_ok=True)
            failed += 1
            continue
        tmp.replace(target)
        print(f"ok       {entry['file']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
