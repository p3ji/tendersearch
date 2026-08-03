"""Low-barrier track classification.

For a group with thin past performance, the realistic entry path is vehicles
rather than large open competitions. Measured on the live feed (2026-08-03),
~28% of open notices qualify.

Keyed off noticeType and procurementMethod, NOT contract value -- the feed has
no value column.
"""
from __future__ import annotations

import dataclasses

from canadabuys.notice import Notice

KIND_NONE = "none"
KIND_SUPPLY_ARRANGEMENT = "supply-arrangement"
KIND_STANDING_OFFER = "standing-offer"
KIND_ACAN = "acan"
KIND_SUBCONTRACT = "subcontract"

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


def classify(notice: Notice) -> LowBarrierResult:
    notice_type = notice.notice_type.strip().lower()
    method = notice.procurement_method.strip().lower()

    for needle, kind in _TYPE_RULES:
        if needle in notice_type:
            return LowBarrierResult(True, kind, f"noticeType: {notice.notice_type}")

    # noticeType is blank on ~13% of notices; fall back to the method field.
    for needle, kind in _TYPE_RULES:
        if needle in method:
            return LowBarrierResult(
                True, kind, f"procurementMethod: {notice.procurement_method}"
            )

    description = notice.description.lower()
    for hint in _DESCRIPTION_HINTS:
        if hint in description:
            return LowBarrierResult(True, KIND_SUBCONTRACT, f"description mentions {hint!r}")

    return LowBarrierResult(False, KIND_NONE)
