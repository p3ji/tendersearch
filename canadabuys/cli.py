"""Command-line entry point."""
from __future__ import annotations

import argparse
import collections
import datetime
import pathlib
import sys

import yaml

from canadabuys.fetch import FEEDS, fetch_feed, ingest
from canadabuys.store import NoticeStore
from matching.filter import FilterConfig, filter_all
from matching.profile import load_profiles


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


def cmd_filter(args) -> int:
    """Run stage 1 and report what survived and what was dropped, by reason.

    This is Annex B Pass 2 (filter tuning): the reject histogram is how you
    tell an over-broad keyword list from an over-narrow one.
    """
    profiles, errors = load_profiles(pathlib.Path(args.profiles), collect_errors=True)
    for err in errors:
        print(f"WARNING: skipping unreadable profile: {err}", file=sys.stderr)
    if not profiles:
        print("ERROR: no usable profiles found", file=sys.stderr)
        return 1

    cfg_data = {}
    if pathlib.Path(args.config).exists():
        try:
            cfg_data = yaml.safe_load(pathlib.Path(args.config).read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            print(f"ERROR: could not parse config file {args.config}: {exc}", file=sys.stderr)
            return 1
    config = FilterConfig(
        min_turnaround_days=cfg_data.get("min_turnaround_days", 5),
        now=datetime.datetime.now(datetime.timezone.utc),
    )

    notices = list(NoticeStore(pathlib.Path(args.notices)).all())
    results = filter_all(notices, profiles, [], config)
    counts = collections.Counter(r.reason for r in results.values())
    passed = counts.get("pass", 0)

    print(f"notices: {len(notices)}")
    print(f"passed:  {passed}")
    for reason, count in counts.most_common():
        if reason != "pass":
            print(f"  dropped [{reason}]: {count}")
    if len(notices):
        print(f"pass rate: {passed / len(notices):.1%}")
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

    p_filter = sub.add_parser("filter", help="run stage 1 and report the outcome")
    p_filter.add_argument("--profiles", default="profiles")
    p_filter.add_argument("--config", default="config.yml")
    p_filter.set_defaults(func=cmd_filter)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
