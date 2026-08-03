"""Low-barrier track classification.

For a group with thin past performance, the realistic entry path is vehicles
rather than large open competitions. Measured on the live feed (2026-08-03),
~28% of open notices qualify.

Keyed off noticeType and procurementMethod, NOT contract value -- the feed has
no value column.

CONFIDENCE LEVELS:
The confidence field distinguishes structured signals from heuristics.
- "high": noticeType or procurementMethod signals (supply-arrangement, standing-offer, acan).
  These are reliable procurement-method classifications.
- "low": description-keyword heuristic (subcontract). Measured against real feed data (Aug 2026),
  this rule produced 30 description matches: 26 were the identical Indigenous Business Directory
  boilerplate clause (an obligation on the prime, not an offer to subcontractors), and the rest
  were standard security-clause or Indigenous Benefits Plan language. No genuine opportunities.
  Retained deliberately for visibility; consumers must treat confidence=="low" as unverified.
"""
from __future__ import annotations

import dataclasses

from canadabuys.notice import Notice

KIND_NONE = "none"
KIND_SUPPLY_ARRANGEMENT = "supply-arrangement"
KIND_STANDING_OFFER = "standing-offer"
KIND_ACAN = "acan"
KIND_SUBCONTRACT = "subcontract"

CONFIDENCE_HIGH = "high"
CONFIDENCE_LOW = "low"

# Checked in order; the first match wins. Explicit notice types beat heuristics.
_TYPE_RULES = (
    ("supply arrangement", KIND_SUPPLY_ARRANGEMENT),
    ("standing offer", KIND_STANDING_OFFER),
    ("advance contract award", KIND_ACAN),
)

_DESCRIPTION_HINTS = ("subcontract", "sub-contract", "subcontracting")


@dataclasses.dataclass
class LowBarrierResult:
    is_low_barrier: bool
    kind: str
    evidence: str = ""
    confidence: str = CONFIDENCE_HIGH


def classify(notice: Notice) -> LowBarrierResult:
    notice_type = notice.notice_type.strip().lower()
    method = notice.procurement_method.strip().lower()

    for needle, kind in _TYPE_RULES:
        if needle in notice_type:
            return LowBarrierResult(True, kind, f"noticeType: {notice.notice_type}", CONFIDENCE_HIGH)

    # noticeType is blank on ~13% of notices; fall back to the method field.
    for needle, kind in _TYPE_RULES:
        if needle in method:
            return LowBarrierResult(
                True, kind, f"procurementMethod: {notice.procurement_method}", CONFIDENCE_HIGH
            )

    description = notice.description.lower()
    for hint in _DESCRIPTION_HINTS:
        if hint in description:
            return LowBarrierResult(True, KIND_SUBCONTRACT, f"description mentions {hint!r}", CONFIDENCE_LOW)

    return LowBarrierResult(False, KIND_NONE, "", CONFIDENCE_HIGH)
