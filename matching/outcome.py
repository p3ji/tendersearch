"""Outcome recording: the decision the group made on a notice, and what happened.

`/outcome` writes here (append-only, one record per line) and never adjusts
the rubric. A human reads accumulated outcomes, spots a pattern, and edits
`.claude/skills/tender-matcher/SKILL.md`. Automating that proposal step is
A5 in the design's deferred-functionality appendix, gated on enough records
to distinguish pattern from noise -- see spec, Annex/Appendix and the
Outcome schema.

Record no-bids as diligently as bids. They accumulate weekly, while bid
outcomes accumulate over a quarter and wins are rarer still -- see
REASON_CODES below and the design spec's outcome section for why a
no-bid's reason code is the highest-value signal this file holds.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib

# Controlled vocabulary so patterns are countable, not buried in prose. Two of
# these -- price-uncompetitive and incumbent-entrenched -- mark losses on
# well-fitted work that the rubric could not and should not have predicted;
# any future analysis over this file must exclude them from fit-related
# tuning, or it will teach the rubric to avoid work the group is good at.
REASON_CODES = (
    "capability-gap",
    "clearance",
    "past-performance",
    "capacity",
    "timeline",
    "poor-fit",
    "incumbent-entrenched",
    "price-uncompetitive",
    "scope-too-large",
    "not-actually-our-work",
)

DECISIONS = ("bid", "no-bid")
RESULTS = ("won", "lost", "no-award", "pending")

# Losses on work the rubric fit correctly -- competitive outcomes, not scoring
# errors. Excluded from any future rubric-tuning pass over this file. Kept
# here, next to REASON_CODES, so the two lists cannot drift apart.
EXCLUDED_FROM_FIT_TUNING = ("price-uncompetitive", "incumbent-entrenched")


class OutcomeError(Exception):
    pass


@dataclasses.dataclass
class WinDetails:
    """Captured only when result == "won". Becomes past-performance evidence --
    the thin-past-performance problem this whole design is built around."""
    value: float | None = None
    start: str | None = None
    end: str | None = None
    client: str | None = None
    reference_name: str | None = None
    reference_email: str | None = None


@dataclasses.dataclass
class Outcome:
    reference: str
    subject: str
    subject_kind: str          # "profile" | "team"
    date: str                  # ISO date the decision was recorded
    score_at_decision: int     # snapshot -- see module docstring
    recommendation_at_decision: str
    decision: str              # "bid" | "no-bid"
    reason_code: str
    notes: str = ""
    result: str | None = None  # "won" | "lost" | "no-award" | "pending" | None
    result_reason: str = ""
    debrief_notes: str = ""
    win_details: WinDetails | None = None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        if self.win_details is None:
            d["win_details"] = None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Outcome":
        d = dict(d)
        wd = d.pop("win_details", None)
        return cls(**d, win_details=WinDetails(**wd) if wd else None)


def validate(o: Outcome) -> None:
    """Raise OutcomeError on anything that would corrupt analysis later.

    Loud validation here matters more than usual: outcomes.jsonl is the only
    path to ever calibrating the rubric against reality, and a malformed or
    silently-accepted record poisons that analysis invisibly.
    """
    if not o.reference.strip():
        raise OutcomeError("reference must not be empty")
    if o.subject_kind not in ("profile", "team"):
        raise OutcomeError(f"subject_kind must be 'profile' or 'team', got {o.subject_kind!r}")
    if o.decision not in DECISIONS:
        raise OutcomeError(f"decision must be one of {DECISIONS}, got {o.decision!r}")
    if o.reason_code not in REASON_CODES:
        raise OutcomeError(
            f"reason_code {o.reason_code!r} is not in the controlled vocabulary "
            f"{REASON_CODES} -- add it there deliberately if a real category is missing, "
            f"rather than writing free text that can never be counted"
        )
    if o.result is not None and o.result not in RESULTS:
        raise OutcomeError(f"result must be one of {RESULTS} or None, got {o.result!r}")
    if o.result == "won" and o.win_details is None:
        raise OutcomeError(
            "result is 'won' but win_details is missing -- capture client, value, dates, "
            "and a reference contact now, while they are known; this is the group's only "
            "path to real past-performance evidence"
        )


def append(path: pathlib.Path, outcome: Outcome) -> None:
    """Validate, then append one JSON line. Never truncates or rewrites."""
    validate(outcome)
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(outcome.to_dict(), ensure_ascii=False) + "\n")


def load_all(path: pathlib.Path) -> list[Outcome]:
    """Every recorded outcome, in file order. Empty list if the file is absent."""
    path = pathlib.Path(path)
    if not path.exists():
        return []
    records = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(Outcome.from_dict(json.loads(line)))
        except (json.JSONDecodeError, TypeError) as exc:
            raise OutcomeError(f"{path}:{lineno}: malformed outcome record: {exc}") from exc
    return records
