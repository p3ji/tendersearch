"""Command-line entry point."""
from __future__ import annotations

import argparse
import datetime
import pathlib
import sys

from canadabuys.fetch import FEEDS, fetch_feed, ingest
from canadabuys.store import NoticeStore


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def cmd_fetch(args) -> int:
    store = NoticeStore(pathlib.Path(args.notices))
    if args.file:
        raw = pathlib.Path(args.file).read_bytes()
    else:
        raw = fetch_feed(args.feed)
    try:
        summary = ingest(raw, store, args.feed, _now_iso())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"created={summary.created} amended={summary.amended} "
        f"unchanged={summary.unchanged} needs_rematch={len(summary.rematch_needed)}"
    )
    return 0


def cmd_stats(args) -> int:
    notices = list(NoticeStore(pathlib.Path(args.notices)).all())
    print(f"stored: {len(notices)}")
    print(f"open: {sum(1 for n in notices if n.is_open())}")
    print(f"needing rematch: {sum(1 for n in notices if n.needs_rematch)}")
    print(f"with no procurement code: {sum(1 for n in notices if not n.unspsc and not n.gsin)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="canadabuys")
    parser.add_argument("--notices", default="notices", help="notice store root")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="pull a feed into the notice store")
    p_fetch.add_argument("--feed", choices=sorted(FEEDS), default="open")
    p_fetch.add_argument("--file", help="ingest a local CSV instead of fetching")
    p_fetch.set_defaults(func=cmd_fetch)

    p_stats = sub.add_parser("stats", help="summarize the notice store")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
