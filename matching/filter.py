"""Stage-1 deterministic filter.

THIS IS A RECALL GATE. A notice dropped here is never judged, never appears in
a digest, and is invisible forever. Precision failures self-correct at stage 2;
recall failures are permanent and silent.

Consequence for every rule below: when data is absent or ambiguous, PASS the
notice. Absent data must never read as disqualifying.
"""
from __future__ import annotations

import dataclasses
import datetime

from canadabuys.notice import Notice
from matching.profile import ServiceLine

REASON_PASS = "pass"
REASON_CLOSED = "not-open"
REASON_TOO_SOON = "closing-too-soon"
REASON_REGION = "region-not-served"
REASON_NO_SIGNAL = "no-code-or-keyword-match"

# A notice deliverable anywhere in Canada is deliverable from any province.
NATIONAL_REGIONS = {"canada", "national capital region"}


@dataclasses.dataclass
class FilterConfig:
    min_turnaround_days: int = 5
    now: datetime.datetime = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    ignore_status: bool = False


@dataclasses.dataclass
class FilterResult:
    passed: bool
    reason: str
    matched_codes: list[str] = dataclasses.field(default_factory=list)
    matched_keywords: list[str] = dataclasses.field(default_factory=list)
    matched_service_lines: list[str] = dataclasses.field(default_factory=list)


def _region_ok(notice: Notice, regions: list[str]) -> bool:
    if not notice.regions_delivery:
        return True  # not stated -> do not hide it
    if not regions:
        return True  # profile-side regions unspecified -> do not hide it
    served = {r.strip().lower() for r in regions}
    if served & NATIONAL_REGIONS:
        return True
    for region in notice.regions_delivery:
        r = region.strip().lower()
        if r in NATIONAL_REGIONS or r in served:
            return True
    return False


def filter_notice(
    notice: Notice,
    service_lines: list[ServiceLine],
    regions: list[str],
    config: FilterConfig,
) -> FilterResult:
    if not config.ignore_status and notice.status and not notice.is_open():
        return FilterResult(False, REASON_CLOSED)

    if notice.closing is not None:
        deadline = config.now + datetime.timedelta(days=config.min_turnaround_days)
        if notice.closing < deadline:
            return FilterResult(False, REASON_TOO_SOON)

    if not _region_ok(notice, regions):
        return FilterResult(False, REASON_REGION)

    notice_codes = {c.strip().upper() for c in (notice.unspsc + notice.gsin) if c.strip()}
    text = notice.searchable_text()

    codes, keywords, lines = [], [], []
    for line in service_lines:
        line_codes = {c.strip().upper() for c in (line.unspsc + line.gsin) if c.strip()}
        hit_codes = sorted(notice_codes & line_codes)
        hit_keywords = sorted({k for k in line.keywords if k and k in text})
        if hit_codes or hit_keywords:
            codes.extend(hit_codes)
            keywords.extend(hit_keywords)
            lines.append(line.label)

    if not codes and not keywords:
        return FilterResult(False, REASON_NO_SIGNAL)

    return FilterResult(
        True, REASON_PASS,
        matched_codes=sorted(set(codes)),
        matched_keywords=sorted(set(keywords)),
        matched_service_lines=lines,
    )


def filter_all(notices, profiles, config: FilterConfig) -> dict[str, FilterResult]:
    """Filter each notice against the union of all active profiles.

    A notice passes if ANY profile could want it; per-subject scoring is
    stage 2's job, not stage 1's.

    Teams are deliberately NOT a parameter here: teams are a stage-2 concept
    (the rubric judges against profiles AND teams). Stage 1 already unions
    across all profiles, so a team -- itself just a union of member profiles
    -- adds nothing to this gate.
    """
    all_lines = [sl for p in profiles for sl in p.service_lines]
    all_regions = sorted({r for p in profiles for r in p.regions})
    return {
        n.reference: filter_notice(n, all_lines, all_regions, config) for n in notices
    }
