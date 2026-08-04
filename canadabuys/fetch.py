"""Feed retrieval and ingestion. The only module that touches the network."""
from __future__ import annotations

import csv
import dataclasses
import io
import pathlib

import requests

from canadabuys import fields as F
from canadabuys.notice import Notice
from canadabuys.store import NoticeStore

FEEDS = {
    "open": "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv",
    "new": "https://canadabuys.canada.ca/opendata/pub/newTenderNotice-nouvelAvisAppelOffres.csv",
}

# If these are absent the file is not a tender feed. Fail loudly rather than
# writing an empty digest that reads as "nothing today".
#
# The matching-critical columns are included deliberately: if any of these
# get silently renamed upstream, row.get() returns None, stage 1 loses its
# codes/text and rejects every notice as "no-code-or-keyword-match", and
# `canadabuys filter` prints "passed: 0" and exits 0 -- a silent, successful
# recall failure. Guarding them here turns that into a loud ingest failure.
REQUIRED_COLUMNS = (
    F.COL_REF,
    F.COL_TITLE,
    F.COL_CLOSING,
    F.COL_STATUS,
    F.COL_UNSPSC,
    F.COL_GSIN,
    F.COL_UNSPSC_DESC,
    F.COL_GSIN_DESC,
    F.COL_REGIONS_DELIVERY,
    F.COL_DESCRIPTION,
    F.COL_SELECTION,
    F.COL_NOTICE_TYPE,
    F.COL_PROC_METHOD,
)

# The feed rejects non-browser User-Agents with a bare 403. A descriptive
# UA (e.g. "tendersearch/1.0 ...") is also rejected; only a browser-shaped
# UA string gets through.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


@dataclasses.dataclass
class IngestSummary:
    created: int = 0
    amended: int = 0
    unchanged: int = 0
    rematch_needed: list[str] = dataclasses.field(default_factory=list)


def fetch_feed(name: str, timeout: int = 180) -> bytes:
    response = requests.get(
        FEEDS[name], timeout=timeout, headers={"User-Agent": _USER_AGENT}
    )
    response.raise_for_status()
    return response.content


def parse_csv_bytes(raw: bytes, source_feed: str, now_iso: str) -> list[Notice]:
    text = raw.decode("utf-8-sig")  # the feed carries a BOM
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("feed is empty: no CSV header found")
    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise ValueError(
            f"feed schema changed: expected column(s) {missing} not found. "
            f"Refusing to ingest. See .agents/skills/canadabuys-search/url-reference.md"
        )
    return [Notice.from_csv_row(row, source_feed, now_iso) for row in reader]


def ingest(raw: bytes, store: NoticeStore, source_feed: str, now_iso: str) -> IngestSummary:
    summary = IngestSummary()
    for notice in parse_csv_bytes(raw, source_feed, now_iso):
        result = store.upsert(notice, now_iso)
        if result.action == "created":
            summary.created += 1
        elif result.action == "unchanged":
            summary.unchanged += 1
        else:
            summary.amended += 1
        if result.needs_rematch:
            summary.rematch_needed.append(result.reference)
    return summary
