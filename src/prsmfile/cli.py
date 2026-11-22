"""Command line interface."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from . import open as open_prism
from .errors import PrismFormatError
from .readers import read_analysis
from .render import flat, to_json_obj, to_text, write_csv
from .tables import read_table


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="prsmfile",
        description="Read analysis results and data tables from GraphPad Prism .prism files.",
    )
    p.add_argument("file", metavar="FILE", help="a .prism file")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="list the analyses and their state")
    mode.add_argument("--json", action="store_true", help="print JSON instead of text tables")
    mode.add_argument("--csv", metavar="DIR", help="write CSV files into a new or empty directory")
    p.add_argument("--data", action="store_true", help="include the raw data tables")
    p.add_argument("--analysis", metavar="TEXT",
                   help="only analyses whose title contains TEXT (case-insensitive)")
    p.add_argument("--version", action="version", version=f"prsmfile {__version__}")
    return p


def _state(a) -> str:
    if a.has_results:
        return "calculated"
    if a.is_calculated is False:
        return "not calculated"
    return "no stored results"


def _warn_file(pf) -> None:
    for w in pf.warnings:
        print(f"Warning: {flat(w)}", file=sys.stderr)


def _run(args) -> int:
    with open_prism(args.file) as pf:
        numbered = list(enumerate(pf.analyses(), 1))
        if args.analysis is not None:
            needle = args.analysis.casefold()
            numbered = [(n, a) for n, a in numbered if needle in flat(a.title).casefold()]
            if not numbered:
                print(f'no analysis matches "{args.analysis}"', file=sys.stderr)
                return 1
        if args.list:
            for n, a in numbered:
                print(f"{n:02d}  {a.analysis_class}  {_state(a)}  {flat(a.title)}")
            _warn_file(pf)
            return 0
        analyses = [a for _, a in numbered]
        reports = [read_analysis(pf, a) for a in analyses]
        tables = []
        if args.data:
            tables = [t for t in (read_table(pf, sid) for sid in pf.data_tables()) if t is not None]
        if args.csv is not None:
            print(len(write_csv(Path(args.csv), reports, tables)))
            _warn_file(pf)
        elif args.json:
            import json

            print(json.dumps(to_json_obj(pf, reports, tables), ensure_ascii=False, indent=2,
                             allow_nan=False))
        else:
            sys.stdout.write(to_text(pf, reports, tables))
    return 0


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is not None:
            reconf(encoding="utf-8", errors="replace")
    try:
        code = _run(args)
        sys.stdout.flush()
        return code
    except BrokenPipeError:
        # the reader went away (e.g. `| head`): silence the flush at exit
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except (OSError, ValueError, AttributeError):
            pass
        return 1
    except PrismFormatError as e:
        msg = str(e)
        if args.file.lower().endswith(".pzf"):
            msg += " (.pzf files are not supported, save the project as .prism)"
        print(f"prsmfile: {msg}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"prsmfile: {e.filename or args.csv or args.file}: {e.strerror or e}", file=sys.stderr)
        return 1
