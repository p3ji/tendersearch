"""Offline archive analysis for Annex B passes 2 and 5.

Pass 2 (filter tuning): survivor volume per week.
Pass 5 (market map): which organizations buy your service lines, via which methods.

Usage:
    python tools/archive_report.py archives/2024-2025-TenderNotice-AvisAppelOffres.csv
"""
from __future__ import annotations

import collections
import datetime
import pathlib
import sys

import yaml

from canadabuys.fetch import parse_csv_bytes
from matching.filter import FilterConfig, filter_all
from matching.lowbarrier import classify
from matching.profile import load_profiles

NOW_ISO = "2000-01-01T00:00:00+00:00"  # archives are historical; ingest time is irrelevant


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    archive = pathlib.Path(argv[1])
    profiles = load_profiles(pathlib.Path("profiles"))
    cfg = yaml.safe_load(pathlib.Path("config.yml").read_text(encoding="utf-8")) or {}

    notices = parse_csv_bytes(archive.read_bytes(), "archive", NOW_ISO)
    print(f"archive: {archive.name}  notices: {len(notices)}")

    # Pass 2 — volume. Date and status rules are meaningless on historical data,
    # so use a far-past `now` to neutralize them and isolate code/keyword reach.
    config = FilterConfig(
        min_turnaround_days=cfg.get("min_turnaround_days", 5),
        now=datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc),
    )
    results = filter_all(notices, profiles, [], config)
    survivors = [n for n in notices if results[n.reference].passed]
    print(f"\n--- Pass 2: filter reach ---")
    print(f"survivors: {len(survivors)} ({len(survivors)/max(len(notices),1):.1%})")
    print(f"per week:  {len(survivors)/52:.1f}")
    reasons = collections.Counter(r.reason for r in results.values())
    for reason, count in reasons.most_common():
        print(f"  {reason}: {count}")

    matched_by_line = collections.Counter(
        label for r in results.values() for label in r.matched_service_lines
    )
    print("\nsurvivors by service line:")
    for label, count in matched_by_line.most_common():
        print(f"  {label}: {count}")

    # Pass 5 — market map.
    print(f"\n--- Pass 5: market map (survivors only) ---")
    print("top buying organizations:")
    for entity, count in collections.Counter(n.entity for n in survivors).most_common(15):
        print(f"  {count:4d}  {entity}")
    print("\nby procurement method:")
    for method, count in collections.Counter(
        n.procurement_method or "(blank)" for n in survivors
    ).most_common():
        print(f"  {count:4d}  {method}")
    print("\nlow-barrier share (by kind, confidence):")
    print("  note: confidence=low results are unverified description-keyword matches")
    lowbarrier_counts = collections.Counter(
        (lambda r: (r.kind, r.confidence))(classify(n)) for n in survivors
    )
    for (kind, confidence), count in lowbarrier_counts.most_common():
        print(f"  {count:4d}  {kind} (confidence={confidence})")
    print("\nby month published:")
    for month, count in sorted(collections.Counter(
        n.published.strftime("%Y-%m") for n in survivors if n.published
    ).items()):
        print(f"  {month}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
