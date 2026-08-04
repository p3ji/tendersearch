"""Verdicts -- stage-2 judgment output, read by /apply.

/rank (an LLM step, not code) writes matches/<date>/verdicts.json in the
shape documented in .claude/skills/tender-matcher/SKILL.md. This module only
reads that output; it never judges anything itself.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib


class VerdictError(Exception):
    pass


@dataclasses.dataclass
class Requirement:
    text: str
    kind: str
    status: str
    covered_by: str | None
    note: str = ""


@dataclasses.dataclass
class LowBarrier:
    is_low_barrier: bool
    kind: str


@dataclasses.dataclass
class Verdict:
    reference: str
    subject: str
    subject_kind: str
    score: int
    recommendation: str
    low_barrier: LowBarrier
    requirements: list[Requirement]
    reasoning: str
    deal_breakers: list[str]
    matches_date: str


def _parse_verdict(record: dict, matches_date: str, verdicts_path: pathlib.Path) -> Verdict:
    lb = record.get("low_barrier") or {}
    try:
        return Verdict(
            reference=record["reference"],
            subject=record["subject"],
            subject_kind=record.get("subject_kind", "profile"),
            score=record.get("score", 0),
            recommendation=record.get("recommendation", ""),
            low_barrier=LowBarrier(
                is_low_barrier=bool(lb.get("is_low_barrier", False)),
                kind=lb.get("kind", "none"),
            ),
            requirements=[
                Requirement(
                    text=r["text"],
                    kind=r.get("kind", "mandatory"),
                    status=r.get("status", "unclear"),
                    covered_by=r.get("covered_by"),
                    note=r.get("note", ""),
                )
                for r in record.get("requirements") or []
            ],
            reasoning=record.get("reasoning", ""),
            deal_breakers=list(record.get("deal_breakers") or []),
            matches_date=matches_date,
        )
    except KeyError as exc:
        raise VerdictError(
            f"{verdicts_path}: verdict record missing required field {exc}"
        ) from exc


def load_verdicts(matches_root: pathlib.Path, reference: str) -> list[Verdict]:
    """Every verdict written for this notice, newest matches/<date>/ first."""
    matches_root = pathlib.Path(matches_root)
    found: list[Verdict] = []
    for verdicts_path in sorted(matches_root.glob("*/verdicts.json"), reverse=True):
        date = verdicts_path.parent.name
        try:
            records = json.loads(verdicts_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise VerdictError(f"{verdicts_path}: could not read verdicts: {exc}") from exc
        for record in records:
            if record.get("reference") == reference:
                found.append(_parse_verdict(record, date, verdicts_path))
    return found


def load_verdict(
    matches_root: pathlib.Path, reference: str, subject: str | None = None
) -> Verdict:
    """The verdict /apply should use, optionally disambiguated by subject.

    Raises VerdictError if no verdict exists (/apply requires one), or if
    `subject` is omitted while more than one subject has judged this notice.
    Ties across matches/<date>/ dirs for the same subject resolve to the
    newest date.
    """
    candidates = load_verdicts(matches_root, reference)
    if subject is not None:
        candidates = [v for v in candidates if v.subject == subject]
    if not candidates:
        target = f"reference {reference!r}" + (f", subject {subject!r}" if subject else "")
        raise VerdictError(f"no verdict found for {target} -- run /rank first")

    subjects = sorted({v.subject for v in candidates})
    if subject is None and len(subjects) > 1:
        raise VerdictError(
            f"notice {reference!r} has verdicts for multiple subjects "
            f"({', '.join(subjects)}) -- pass --profile or --team to disambiguate"
        )
    chosen = subject or subjects[0]
    for v in candidates:
        if v.subject == chosen:
            return v
    raise VerdictError(f"no verdict found for reference {reference!r}, subject {chosen!r}")
