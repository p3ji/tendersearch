# /apply command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/apply`, the ninth-of-nine-steps bid-draft assembly command: given a notice that already has a verdict, produce a requirements→response matrix, per-criterion evidence, draft prose, and an unchecked compliance checklist in `bids/<notice-id>/`.

**Architecture:** Same split as `/rank`/`filter`: a Python CLI subcommand (`canadabuys apply`) does the deterministic, testable half — find the verdict, find the notice, resolve each covering member's evidence file *paths* — and writes a structured `scaffold.json`. The `/apply` slash command (an LLM step, like `rank.md`) reads that scaffold plus the actual evidence files and a new `tender-assistant` skill (writing style + draft structure), and writes the real markdown deliverables. Judgment and prose live in the LLM step; file I/O and lookup live in code.

**Tech Stack:** Python 3 (dataclasses, argparse, pathlib, json, yaml), pytest, Claude Code slash commands (`.claude/commands/`) and skills (`.claude/skills/`).

## Global Constraints

- Never commit `profiles/`, `teams/`, or `outcomes.jsonl` — real resumes and client names. (`bids/` is also git-ignored; see `.gitignore`.)
- Tests never hit the network. This feature touches no network code, so this is satisfied by construction — just don't add any.
- Failures are loud: never write partial or silently-empty output as if it were a real result (design doc, "Error handling"). `canadabuys apply` must exit 1 and print `ERROR: ...` to stderr rather than writing a partial `scaffold.json`.
- `/apply` operates only on a notice that already has a verdict (design doc, Layer 3) — this is enforced by `canadabuys apply` failing when no verdict is found, not by the LLM step remembering to check.
- Follow existing CLI conventions exactly: global `--notices` flag lives on the top-level parser; subcommand-specific paths (`--profiles`, `--matches`, `--bids`) are subparser arguments with bare relative-path defaults; JSON output uses `json.dumps(..., indent=2, ensure_ascii=False)` via `path.write_text(..., encoding="utf-8")` after `path.parent.mkdir(parents=True, exist_ok=True)`.

---

## File structure

- `matching/verdict.py` — **new**. Reads `matches/<date>/verdicts.json`, the stage-2 judgment output. Dataclasses (`Verdict`, `Requirement`, `LowBarrier`) and `load_verdict()`/`load_verdicts()`. No LLM, no judgment — pure read/parse, same spirit as `matching/profile.py`.
- `canadabuys/store.py` — **modified**. Rename the private `_safe_filename` to public `safe_filename`; it's now used by two modules (`NoticeStore` and the new `apply` subcommand both need to turn a reference number into a filesystem-safe path component).
- `canadabuys/cli.py` — **modified**. New `cmd_apply()` function and `apply` subparser, following the exact pattern `cmd_filter()`/`p_filter` already establish.
- `.claude/skills/tender-assistant/SKILL.md` — **new**. Writing style and draft structure for bid prose. Referenced by the design doc (`docs/superpowers/specs/2026-08-03-tendersearch-design.md:193,212,237`) but never built until now.
- `.claude/commands/apply.md` — **new**. The `/apply` slash command itself: runs `canadabuys apply`, reads the scaffold + evidence + `tender-assistant` skill, writes the bid draft files.
- `tests/test_verdict.py` — **new**. Unit tests for `matching/verdict.py`.
- `tests/test_apply_cli.py` — **new**. CLI-level tests for `canadabuys apply`, following `tests/test_cli.py`'s existing pattern (in-process `main()` calls against `tmp_path`, no subprocess, no network).
- `README.md` — **modified**. Two spots currently say `/apply` isn't built (lines 24, 57); update once it is.

---

### Task 1: Verdict loader

**Files:**
- Create: `matching/verdict.py`
- Test: `tests/test_verdict.py`

**Interfaces:**
- Produces: `matching.verdict.VerdictError` (exception), `matching.verdict.Requirement` (dataclass: `text: str`, `kind: str`, `status: str`, `covered_by: str | None`, `note: str = ""`), `matching.verdict.LowBarrier` (dataclass: `is_low_barrier: bool`, `kind: str`), `matching.verdict.Verdict` (dataclass: `reference: str`, `subject: str`, `subject_kind: str`, `score: int`, `recommendation: str`, `low_barrier: LowBarrier`, `requirements: list[Requirement]`, `reasoning: str`, `deal_breakers: list[str]`, `matches_date: str`), `matching.verdict.load_verdicts(matches_root: pathlib.Path, reference: str) -> list[Verdict]`, `matching.verdict.load_verdict(matches_root: pathlib.Path, reference: str, subject: str | None = None) -> Verdict`.

The verdict JSON shape being parsed is the one `.claude/skills/tender-matcher/SKILL.md` already documents as what `/rank` writes to `matches/<date>/verdicts.json`:
```json
{
  "reference": "cb-450-77537023",
  "subject": "alex",
  "subject_kind": "profile",
  "score": 0,
  "recommendation": "bid | no-bid | investigate",
  "low_barrier": {"is_low_barrier": false, "kind": "none"},
  "requirements": [
    {"text": "...", "kind": "mandatory | rated",
     "status": "met | gap | unclear", "covered_by": "alex | null",
     "note": "..."}
  ],
  "reasoning": "2-4 sentences",
  "deal_breakers": ["..."]
}
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_verdict.py`:

```python
import json
import pathlib

import pytest

from matching.verdict import VerdictError, load_verdict, load_verdicts

REFERENCE = "cb-450-77537023"


def write_verdicts(root: pathlib.Path, date: str, records: list[dict]) -> None:
    d = root / date
    d.mkdir(parents=True, exist_ok=True)
    (d / "verdicts.json").write_text(json.dumps(records), encoding="utf-8")


def make_record(**overrides) -> dict:
    record = {
        "reference": REFERENCE,
        "subject": "alex",
        "subject_kind": "profile",
        "score": 82,
        "recommendation": "bid",
        "low_barrier": {"is_low_barrier": False, "kind": "none"},
        "requirements": [
            {"text": "3.1 valid security clearance", "kind": "mandatory",
             "status": "met", "covered_by": "alex", "note": "Reliability on file"},
        ],
        "reasoning": "Strong fit, all mandatories met.",
        "deal_breakers": [],
    }
    record.update(overrides)
    return record


def test_load_verdict_returns_the_only_candidate(tmp_path):
    write_verdicts(tmp_path, "2026-08-01", [make_record()])
    verdict = load_verdict(tmp_path, REFERENCE)
    assert verdict.subject == "alex"
    assert verdict.score == 82
    assert verdict.requirements[0].covered_by == "alex"
    assert verdict.matches_date == "2026-08-01"


def test_load_verdict_raises_when_none_exists(tmp_path):
    with pytest.raises(VerdictError, match="no verdict found"):
        load_verdict(tmp_path, REFERENCE)


def test_load_verdict_raises_when_matches_root_does_not_exist(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(VerdictError, match="no verdict found"):
        load_verdict(missing, REFERENCE)


def test_load_verdict_disambiguates_by_subject(tmp_path):
    write_verdicts(tmp_path, "2026-08-01", [
        make_record(subject="alex"),
        make_record(subject="priya", score=55),
    ])
    verdict = load_verdict(tmp_path, REFERENCE, subject="priya")
    assert verdict.subject == "priya"
    assert verdict.score == 55


def test_load_verdict_raises_when_ambiguous_without_subject(tmp_path):
    write_verdicts(tmp_path, "2026-08-01", [
        make_record(subject="alex"),
        make_record(subject="priya"),
    ])
    with pytest.raises(VerdictError, match="multiple subjects"):
        load_verdict(tmp_path, REFERENCE)


def test_load_verdict_raises_when_subject_not_found(tmp_path):
    write_verdicts(tmp_path, "2026-08-01", [make_record(subject="alex")])
    with pytest.raises(VerdictError, match="no verdict found"):
        load_verdict(tmp_path, REFERENCE, subject="priya")


def test_load_verdict_prefers_the_most_recent_date_for_the_same_subject(tmp_path):
    write_verdicts(tmp_path, "2026-07-01", [make_record(score=40)])
    write_verdicts(tmp_path, "2026-08-01", [make_record(score=90)])
    verdict = load_verdict(tmp_path, REFERENCE)
    assert verdict.score == 90
    assert verdict.matches_date == "2026-08-01"


def test_load_verdicts_returns_every_matching_record_across_dates(tmp_path):
    write_verdicts(tmp_path, "2026-07-01", [make_record(score=40)])
    write_verdicts(tmp_path, "2026-08-01", [make_record(score=90)])
    verdicts = load_verdicts(tmp_path, REFERENCE)
    assert [v.matches_date for v in verdicts] == ["2026-08-01", "2026-07-01"]


def test_load_verdict_raises_a_clear_error_on_malformed_json(tmp_path):
    d = tmp_path / "2026-08-01"
    d.mkdir(parents=True)
    (d / "verdicts.json").write_text("not json", encoding="utf-8")
    with pytest.raises(VerdictError, match="could not read verdicts"):
        load_verdict(tmp_path, REFERENCE)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_verdict.py -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'matching.verdict'`

- [ ] **Step 3: Write the implementation**

Create `matching/verdict.py`:

```python
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


def _parse_verdict(record: dict, matches_date: str) -> Verdict:
    lb = record.get("low_barrier") or {}
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
                found.append(_parse_verdict(record, date))
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_verdict.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add matching/verdict.py tests/test_verdict.py
git commit -m "feat: add verdict loader for /apply"
```

---

### Task 2: `canadabuys apply` CLI subcommand

**Files:**
- Modify: `canadabuys/store.py` (rename `_safe_filename` → `safe_filename`)
- Modify: `canadabuys/cli.py`
- Test: `tests/test_apply_cli.py`

**Interfaces:**
- Consumes: `matching.verdict.load_verdict`, `matching.verdict.VerdictError`, `matching.verdict.Verdict`/`Requirement` (Task 1); `matching.profile.load_profiles(root, collect_errors=True) -> (list[Profile], list[str])` and `Profile.evidence: dict` (existing, `matching/profile.py:39,49,128`); `canadabuys.store.NoticeStore.load(reference) -> Notice | None` (existing, `canadabuys/store.py:61`); `canadabuys.notice.Notice` fields `reference, title, entity, closing, description, selection_criteria, notice_url, attachments, needs_rematch` (existing, `canadabuys/notice.py:16-47`).
- Produces: `canadabuys.store.safe_filename(reference: str) -> str` (renamed, now public); `canadabuys.cli.cmd_apply(args) -> int`; a `bids/<notice-id>/scaffold.json` file with the shape asserted in the tests below — this is what `.claude/commands/apply.md` (Task 4) reads.

- [ ] **Step 1: Rename `_safe_filename` to `safe_filename`**

In `canadabuys/store.py`, rename the function and its two call sites:

```python
def safe_filename(reference: str) -> str:
```

(was `def _safe_filename(reference: str) -> str:`, line 28)

```python
    def path_for(self, reference: str, first_seen: str) -> pathlib.Path:
        month = first_seen[:7]  # "2026-08"
        return self.root / month / f"{safe_filename(reference)}.json"

    def _find(self, reference: str) -> pathlib.Path | None:
        matches = sorted(self.root.glob(f"*/{safe_filename(reference)}.json"))
        return matches[0] if matches else None
```

- [ ] **Step 2: Run the existing test suite to confirm the rename didn't break anything**

Run: `pytest -q`
Expected: 106 passed (unchanged — `_safe_filename` was never referenced by name outside `store.py`)

- [ ] **Step 3: Write the failing tests**

Create `tests/test_apply_cli.py`:

```python
import csv
import json
import pathlib

import pytest
import yaml

from canadabuys.cli import main
from canadabuys.notice import Notice
from canadabuys.store import NoticeStore, safe_filename

FIXTURE = pathlib.Path("tests/fixtures/open_sample.csv")
NOW = "2026-08-03T12:00:00+00:00"
REFERENCE = "cb-450-77537023"


def base_row():
    with open(FIXTURE, encoding="utf-8-sig", newline="") as f:
        return next(csv.DictReader(f))


def make_notice(**overrides) -> Notice:
    row = {
        **base_row(),
        "referenceNumber-numeroReference": REFERENCE,
        "tenderStatus-appelOffresStatut-eng": "Open",
        "tenderClosingDate-appelOffresDateCloture": "2026-09-30T14:00:00",
        "title-titre-eng": "Data pipeline modernization",
        "tenderDescription-descriptionAppelOffres-eng": "Seeking a data pipeline rebuild",
        "selectionCriteria-criteresSelection-eng": "3.1 Reliability clearance required",
        **overrides,
    }
    return Notice.from_csv_row(row, "open", NOW)


def write_profile(root, member_id, evidence=None, **overrides):
    data = {
        "member_id": member_id,
        "name": member_id.title(),
        "regions": ["Ontario", "Canada"],
        "service_lines": [
            {"label": "Data", "unspsc": [], "gsin": [], "naics": [],
             "keywords": ["data pipeline"]}
        ],
        "evidence": evidence or {},
        **overrides,
    }
    d = root / member_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.yml").write_text(yaml.safe_dump(data), encoding="utf-8")


def write_verdicts(root, date, records):
    d = root / date
    d.mkdir(parents=True, exist_ok=True)
    (d / "verdicts.json").write_text(json.dumps(records), encoding="utf-8")


def make_verdict_record(**overrides):
    record = {
        "reference": REFERENCE,
        "subject": "alex",
        "subject_kind": "profile",
        "score": 82,
        "recommendation": "bid",
        "low_barrier": {"is_low_barrier": False, "kind": "none"},
        "requirements": [
            {"text": "3.1 Reliability clearance required", "kind": "mandatory",
             "status": "met", "covered_by": "alex", "note": "Reliability on file"},
        ],
        "reasoning": "Strong fit, all mandatories met.",
        "deal_breakers": [],
    }
    record.update(overrides)
    return record


@pytest.fixture
def env(tmp_path):
    notices_dir = tmp_path / "notices"
    profiles_dir = tmp_path / "profiles"
    matches_dir = tmp_path / "matches"
    bids_dir = tmp_path / "bids"
    profiles_dir.mkdir()
    NoticeStore(notices_dir).save(make_notice())
    write_profile(profiles_dir, "alex", evidence={"resume": "evidence/alex-resume.pdf"})
    write_verdicts(matches_dir, "2026-08-01", [make_verdict_record()])
    return {
        "notices": str(notices_dir),
        "profiles": str(profiles_dir),
        "matches": str(matches_dir),
        "bids": str(bids_dir),
        "tmp_path": tmp_path,
    }


def run_apply(env, notice_id=REFERENCE, extra_args=None):
    args = [
        "--notices", env["notices"], "apply", notice_id,
        "--profiles", env["profiles"], "--matches", env["matches"],
        "--bids", env["bids"],
    ]
    if extra_args:
        args += extra_args
    return main(args)


def test_apply_writes_scaffold_with_resolved_evidence(env):
    rc = run_apply(env)
    assert rc == 0
    scaffold_path = pathlib.Path(env["bids"]) / REFERENCE / "scaffold.json"
    scaffold = json.loads(scaffold_path.read_text(encoding="utf-8"))
    assert scaffold["notice"]["reference"] == REFERENCE
    assert scaffold["verdict"]["subject"] == "alex"
    assert scaffold["verdict"]["score"] == 82
    req = scaffold["requirements"][0]
    assert req["covered_by"] == "alex"
    expected_evidence_path = str(
        pathlib.Path(env["profiles"]) / "alex" / "evidence" / "alex-resume.pdf"
    )
    assert req["evidence"]["resume"] == expected_evidence_path


def test_apply_fails_when_no_verdict_exists(env, capsys):
    rc = run_apply(env, extra_args=["--matches", str(pathlib.Path(env["tmp_path"]) / "empty")])
    assert rc == 1
    assert "no verdict found" in capsys.readouterr().err


def test_apply_fails_when_notice_missing(env, capsys):
    write_verdicts(pathlib.Path(env["matches"]), "2026-08-02",
                    [make_verdict_record(reference="cb-does-not-exist")])
    rc = run_apply(env, notice_id="cb-does-not-exist")
    assert rc == 1
    assert "no notice found" in capsys.readouterr().err


def test_apply_requires_disambiguation_when_multiple_subjects(env, capsys):
    write_verdicts(pathlib.Path(env["matches"]), "2026-08-01", [
        make_verdict_record(subject="alex"),
        make_verdict_record(subject="priya", score=55),
    ])
    rc = run_apply(env)
    assert rc == 1
    assert "multiple subjects" in capsys.readouterr().err


def test_apply_profile_flag_selects_the_right_verdict(env):
    write_verdicts(pathlib.Path(env["matches"]), "2026-08-01", [
        make_verdict_record(subject="alex"),
        make_verdict_record(subject="priya", score=55),
    ])
    rc = run_apply(env, extra_args=["--profile", "priya"])
    assert rc == 0
    scaffold = json.loads(
        (pathlib.Path(env["bids"]) / REFERENCE / "scaffold.json").read_text(encoding="utf-8")
    )
    assert scaffold["verdict"]["subject"] == "priya"
    assert scaffold["verdict"]["score"] == 55


def test_apply_fails_when_verdict_names_unknown_member(env, capsys):
    write_verdicts(pathlib.Path(env["matches"]), "2026-08-01", [
        make_verdict_record(requirements=[
            {"text": "3.1 Reliability clearance required", "kind": "mandatory",
             "status": "met", "covered_by": "ghost", "note": ""},
        ]),
    ])
    rc = run_apply(env)
    assert rc == 1
    assert "ghost" in capsys.readouterr().err


def test_apply_warns_but_proceeds_when_notice_needs_rematch(env, capsys):
    notice = make_notice()
    notice.needs_rematch = True
    NoticeStore(pathlib.Path(env["notices"])).save(notice)
    rc = run_apply(env)
    assert rc == 0
    assert "amended after" in capsys.readouterr().err


def test_apply_rejects_both_profile_and_team(env, capsys):
    rc = run_apply(env, extra_args=["--profile", "alex", "--team", "core"])
    assert rc == 1
    assert "not both" in capsys.readouterr().err


def test_apply_leaves_evidence_empty_when_requirement_is_a_gap(env):
    write_verdicts(pathlib.Path(env["matches"]), "2026-08-01", [
        make_verdict_record(requirements=[
            {"text": "3.2 Standing offer required", "kind": "mandatory",
             "status": "gap", "covered_by": None, "note": "nobody holds one"},
        ]),
    ])
    rc = run_apply(env)
    assert rc == 0
    scaffold = json.loads(
        (pathlib.Path(env["bids"]) / REFERENCE / "scaffold.json").read_text(encoding="utf-8")
    )
    assert scaffold["requirements"][0]["evidence"] == {}
    assert scaffold["requirements"][0]["status"] == "gap"


def test_apply_sanitizes_notice_id_for_the_bids_directory_name(tmp_path):
    notices_dir = tmp_path / "notices"
    profiles_dir = tmp_path / "profiles"
    matches_dir = tmp_path / "matches"
    bids_dir = tmp_path / "bids"
    profiles_dir.mkdir()
    ref = "SSC-26-00034400:T"
    NoticeStore(notices_dir).save(make_notice(**{"referenceNumber-numeroReference": ref}))
    write_profile(profiles_dir, "alex", evidence={"resume": "evidence/alex-resume.pdf"})
    write_verdicts(matches_dir, "2026-08-01", [make_verdict_record(reference=ref)])
    rc = main([
        "--notices", str(notices_dir), "apply", ref,
        "--profiles", str(profiles_dir), "--matches", str(matches_dir),
        "--bids", str(bids_dir),
    ])
    assert rc == 0
    assert (bids_dir / safe_filename(ref) / "scaffold.json").exists()
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_apply_cli.py -v`
Expected: FAIL — `argparse` error / `SystemExit` (`apply` is not a recognized subcommand yet)

- [ ] **Step 5: Write the implementation**

In `canadabuys/cli.py`, update the imports at the top:

```python
from canadabuys.fetch import FEEDS, fetch_feed, ingest
from canadabuys.store import NoticeStore, safe_filename
from matching.filter import FilterConfig, filter_all
from matching.lowbarrier import classify
from matching.profile import load_profiles
from matching.verdict import VerdictError, load_verdict
```

Add `cmd_apply` after `cmd_filter` (before `def main(`):

```python
def cmd_apply(args) -> int:
    """Assemble bids/<notice-id>/scaffold.json from an existing verdict.

    This is the deterministic half of /apply: resolving the verdict, the
    notice, and each covering member's evidence file paths. The /apply
    command (an LLM step) reads this scaffold plus the evidence files to
    write the actual matrix, checklist, and draft prose -- see
    .claude/commands/apply.md.
    """
    if args.profile and args.team:
        print("ERROR: pass --profile or --team, not both", file=sys.stderr)
        return 1
    subject = args.profile or args.team

    try:
        verdict = load_verdict(pathlib.Path(args.matches), args.notice_id, subject)
    except VerdictError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    notice = NoticeStore(pathlib.Path(args.notices)).load(args.notice_id)
    if notice is None:
        print(f"ERROR: no notice found for reference {args.notice_id!r}", file=sys.stderr)
        return 1

    if notice.needs_rematch:
        print(
            f"WARNING: notice {args.notice_id!r} was amended after the "
            f"{verdict.matches_date} verdict was written; the matrix may be "
            f"stale. Consider re-running /rank first.",
            file=sys.stderr,
        )

    profiles_root = pathlib.Path(args.profiles)
    profiles, errors = load_profiles(profiles_root, collect_errors=True)
    if errors:
        print("ERROR: one or more profiles failed to load; refusing to resolve "
              "evidence with partial profile data:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    by_id = {p.member_id: p for p in profiles}

    requirements = []
    missing_members = set()
    for req in verdict.requirements:
        evidence = {}
        if req.covered_by:
            member = by_id.get(req.covered_by)
            if member is None:
                missing_members.add(req.covered_by)
            else:
                evidence = {
                    label: str(profiles_root / member.member_id / rel_path)
                    for label, rel_path in member.evidence.items()
                }
        requirements.append({
            "text": req.text,
            "kind": req.kind,
            "status": req.status,
            "covered_by": req.covered_by,
            "note": req.note,
            "evidence": evidence,
        })
    if missing_members:
        print(
            f"ERROR: verdict names member(s) not found in {profiles_root}: "
            f"{', '.join(sorted(missing_members))}",
            file=sys.stderr,
        )
        return 1

    scaffold = {
        "notice": {
            "reference": notice.reference,
            "title": notice.title,
            "entity": notice.entity,
            "closing": notice.closing.isoformat() if notice.closing else None,
            "description": notice.description,
            "selection_criteria": notice.selection_criteria,
            "notice_url": notice.notice_url,
            "attachments": notice.attachments,
            "needs_rematch": notice.needs_rematch,
        },
        "verdict": {
            "subject": verdict.subject,
            "subject_kind": verdict.subject_kind,
            "score": verdict.score,
            "recommendation": verdict.recommendation,
            "low_barrier": {
                "is_low_barrier": verdict.low_barrier.is_low_barrier,
                "kind": verdict.low_barrier.kind,
            },
            "reasoning": verdict.reasoning,
            "deal_breakers": verdict.deal_breakers,
            "matches_date": verdict.matches_date,
        },
        "requirements": requirements,
    }

    out_path = pathlib.Path(args.bids) / safe_filename(args.notice_id) / "scaffold.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scaffold, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path}")
    return 0
```

Add the subparser in `main()`, after the `p_filter` block and before `args = parser.parse_args(argv)`:

```python
    p_apply = sub.add_parser("apply", help="assemble the bid scaffold for a judged notice")
    p_apply.add_argument("notice_id", help="notice reference number")
    p_apply.add_argument("--profile", help="disambiguate by member id")
    p_apply.add_argument("--team", help="disambiguate by team id")
    p_apply.add_argument("--profiles", default="profiles")
    p_apply.add_argument("--matches", default="matches")
    p_apply.add_argument("--bids", default="bids")
    p_apply.set_defaults(func=cmd_apply)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_apply_cli.py -v`
Expected: 10 passed

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: 125 passed (106 existing + 9 verdict + 10 apply)

- [ ] **Step 8: Commit**

```bash
git add canadabuys/store.py canadabuys/cli.py tests/test_apply_cli.py
git commit -m "feat: add canadabuys apply subcommand"
```

---

### Task 3: `tender-assistant` skill

**Files:**
- Create: `.claude/skills/tender-assistant/SKILL.md`

**Interfaces:**
- Consumes: nothing from earlier tasks (it's read by the LLM, not imported by code).
- Produces: the writing-style/draft-structure guide Task 4's `apply.md` instructs Claude to read before drafting prose.

- [ ] **Step 1: Write the skill**

Create `.claude/skills/tender-assistant/SKILL.md`:

```markdown
---
name: tender-assistant
description: Use when drafting bid response prose for /apply -- writing style, section structure, and how to turn verdict data into a submission-ready draft.
---

# Tender assistant — drafting bid responses

`/apply` reads this skill after the deterministic scaffold (`bids/<notice-id>/scaffold.json`)
is written. Your job here is prose: turning per-requirement evidence into response text a
procurement officer will actually read.

## Writing style

- Plain, factual, first person plural ("we"). No marketing language — "leverage," "synergy,"
  "best-in-class," "world-class" are banned. Say what was done and what the result was.
- Every claim traces to evidence. If a requirement is met, cite the specific resume line or
  past-performance entry it comes from (`scaffold.json`'s `requirements[].evidence` gives you
  the file). Do not write a stronger claim than the evidence supports.
- Match the notice's own numbering. If the solicitation numbers its criteria "3.2.1," your
  response section is headed "3.2.1" — not renumbered, not reordered.
- Short paragraphs. One requirement, one section, one clear statement of how it's met — not a
  narrative essay.
- Never paper over a gap. If a requirement's `status` is `gap` or `unclear` in the scaffold,
  say so plainly in the draft rather than writing around it — gap requirements need a human
  decision (partner, subcontract, or no-bid on this criterion), not disguised prose. Flag them
  clearly, e.g. **[GAP — no covering member; needs a decision before submission]**.
- Thin past performance is the group's real constraint. Do not inflate a single small
  engagement into a "track record." State the actual scope and value, then let capability and
  approach carry the rest of the response.

## Draft structure

Standard sections, in this order, each written as its own file under `bids/<notice-id>/`:

1. **`cover-letter.md`** — one page. States what's being bid on (title + reference), who's
   bidding (member or team name), and a one-paragraph summary of fit. Save score/reasoning
   language for internal use; the cover letter doesn't say "we scored an 82."
2. **`matrix.md`** — the requirements-to-response table (see `.claude/commands/apply.md` for
   the exact table shape). This is the compliance spine every other file expands on.
3. **`technical-response.md`** — one subsection per requirement, in the notice's own order,
   each opening with the requirement text (or its number) as a heading, then the response prose.
4. **`past-performance.md`** — one entry per past-performance record actually cited in the
   matrix: client, value, dates, description, and how it relates to this solicitation's
   requirements. Do not pad this section with performance records that weren't cited anywhere
   in the matrix — irrelevant history reads as generic.
5. **`checklist.md`** — unchecked compliance checklist. Read the notice's `description` and
   `selection_criteria` (in the scaffold) for submission logistics — page limits, required
   forms, delivery method/deadline, number of copies, mandatory attachments — and list each as
   an unchecked item. This is a checklist of what must be assembled and submitted, not a filled
   form: leave every box unchecked.

Skip a section entirely if it doesn't apply (e.g. no past-performance record was cited) rather
than writing a section with nothing in it.

## What this skill does not cover

Profile methodology (how to build `profiles/<member>/profile.yml`) lives in
`.claude/commands/profile.md`, not here. Stage-2 scoring rubric lives in
`.claude/skills/tender-matcher/`. This skill is drafting only, and only runs after a verdict
already exists.
```

- [ ] **Step 2: Verify the frontmatter parses**

Run: `python -c "import yaml, pathlib; text = pathlib.Path('.claude/skills/tender-assistant/SKILL.md').read_text(encoding='utf-8'); front = text.split('---')[1]; data = yaml.safe_load(front); assert data['name'] == 'tender-assistant'; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/tender-assistant/SKILL.md
git commit -m "docs: add tender-assistant skill for bid drafting style"
```

---

### Task 4: `/apply` slash command

**Files:**
- Create: `.claude/commands/apply.md`

**Interfaces:**
- Consumes: `canadabuys apply <notice-id> [--profile M | --team T] --notices --profiles --matches --bids` (Task 2, via the `--notices` global-flag-before-subcommand convention already documented in `rank.md`); `bids/<notice-id>/scaffold.json`'s shape (Task 2: `notice.{reference,title,entity,closing,description,selection_criteria,notice_url,attachments,needs_rematch}`, `verdict.{subject,subject_kind,score,recommendation,low_barrier,reasoning,deal_breakers,matches_date}`, `requirements[].{text,kind,status,covered_by,note,evidence}`); `.claude/skills/tender-assistant/SKILL.md` (Task 3).
- Produces: `bids/<notice-id>/{cover-letter,matrix,technical-response,past-performance,checklist}.md` (per `tender-assistant`'s draft structure).

- [ ] **Step 1: Write the command**

Create `.claude/commands/apply.md`:

```markdown
---
description: Build the bid draft in bids/<notice-id>/ from an existing verdict
argument-hint: <notice-id> [--profile <member> | --team <team>]
---

Build the bid draft for notice `$1`. Requires that `/rank` has already produced a verdict for
this notice — `/apply` never judges fit itself, it only drafts a response to a verdict that
already exists.

## 1. Assemble the scaffold

Run: `canadabuys --notices notices apply $1 --profiles profiles --matches matches --bids bids`

Pass `--profile <member>` or `--team <team>` (append to `$ARGUMENTS` as given) when the notice
has verdicts for more than one subject — the command will tell you if disambiguation is needed
rather than guessing.

(Same argument-order rule as `/rank`: `--notices` is a top-level flag and must come *before*
the subcommand.)

If this fails with `no verdict found`, stop and tell the user to run `/rank` first — do not
attempt to judge the notice yourself. If it fails with `has verdicts for multiple subjects`,
re-run with `--profile` or `--team` naming one of the subjects listed in the error. If stderr
contains a `WARNING: ... was amended after the ... verdict was written` line, say so plainly
to the user before continuing and ask whether to proceed with the possibly-stale verdict or to
re-run `/rank` first.

## 2. Read the scaffold and evidence

Read `bids/<notice-id>/scaffold.json`. For each requirement row with `covered_by` set, read
every file path listed in its `evidence` object (resume, capability statement, etc.) — these
are the real documents behind the claim, not inlined content. Skip rows with an empty
`evidence` object; there is nothing to read for a `gap` requirement.

Read `.claude/skills/tender-assistant/` for writing style and draft structure before writing
anything.

## 3. Write the draft

Follow `tender-assistant`'s draft structure exactly: `cover-letter.md`, `matrix.md`,
`technical-response.md`, `past-performance.md`, `checklist.md`, all under `bids/<notice-id>/`.
Skip a file entirely if its section doesn't apply, per the skill.

For `matrix.md`, one row per scaffold requirement, in scaffold order:

```
| # | Requirement | Kind | Status | Covered by | Evidence |
|---|---|---|---|---|---|
```

Number rows sequentially starting at 1. The scaffold does not carry a separate solicitation
numbering field — if the notice numbered its criteria, that numbering is already inside `text`
(stage 2 was instructed to quote it). Do not invent a second numbering scheme.

For attachments the notice lists (`scaffold.json`'s `notice.attachments`) that you have not
read, note this explicitly in `checklist.md` rather than guessing at their contents — per the
design's error-handling policy, an unenriched attachment is reported at `/apply` time, not
silently skipped.

## 4. Report

Tell the user: which files were written, how many requirements are `gap` or `unclear` (these
need a human decision before submission), and whether the notice needs a re-run of `/rank` due
to `needs_rematch`.
```

- [ ] **Step 2: Verify the frontmatter parses**

Run: `python -c "import yaml, pathlib; text = pathlib.Path('.claude/commands/apply.md').read_text(encoding='utf-8'); front = text.split('---')[1]; data = yaml.safe_load(front); assert 'description' in data; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Manual smoke test**

This step is not automatable (it's an LLM-driven command, like `/rank`), so verify by hand in a
scratch scenario before treating the feature as done:

1. In a scratch directory (not the real `profiles`/`matches`/`bids`), create a minimal
   `profiles/alex/profile.yml` (copy `profiles/_example/profile.yml`, fill in `member_id: alex`)
   and `profiles/alex/evidence/resume.md` with a couple of sentences.
2. Create a notice JSON under `notices/2026-08/` by hand (or via `canadabuys fetch --file` on a
   trimmed CSV) and a `matches/2026-08-04/verdicts.json` by hand matching the schema in
   `.claude/skills/tender-matcher/SKILL.md`, with `covered_by: "alex"` on at least one
   requirement.
3. Run `/apply <reference>` and confirm: `bids/<reference>/scaffold.json` is written, the five
   draft files appear, `matrix.md` has one row per verdict requirement, `checklist.md` has
   unchecked items, and the gap requirement (if you included one) is flagged rather than
   glossed over in `technical-response.md`.
4. Confirm running `canadabuys apply` a second time on the same notice is safe (overwrites
   `scaffold.json` cleanly, no crash, no duplicate directories).

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/apply.md
git commit -m "feat: add /apply slash command"
```

---

### Task 5: Update README status

**Files:**
- Modify: `README.md:24` (pipeline diagram)
- Modify: `README.md:57` (status table)

**Interfaces:**
- Consumes: nothing (text-only change reflecting Tasks 1–4 being done).
- Produces: nothing consumed elsewhere.

- [ ] **Step 1: Update the pipeline diagram**

In `README.md`, change line 24 from:

```
/scrape              /rank                        /apply  (not built yet)
```

to:

```
/scrape              /rank                        /apply
```

- [ ] **Step 2: Update the status table**

In `README.md`, change line 57 from:

```
| `/apply` — assembled response draft | **Not built** — a second plan, written against the matcher's real output |
```

to:

```
| `/apply` — assembled response draft | Built |
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: mark /apply as built in README"
```

---

## Final verification

- [ ] Run `pytest -q` — expect 125 passed, 0 failed.
- [ ] Run `git log --oneline -5` — expect five new commits, one per task above.
- [ ] Confirm `git status` is clean (no stray scratch files from the Task 4 manual smoke test
      left in the real `profiles/`, `notices/`, `matches/`, or `bids/` — those are git-ignored
      but should still be cleaned up if the smoke test used real paths instead of a scratch dir).
