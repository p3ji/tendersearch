# tendersearch — Agent Guide

Finds and triages Canadian federal tender opportunities for a small consulting group.

## Layout

- `canadabuys/` — feed ingestion. All network and file I/O. **No judgment logic.**
- `matching/` — stage-1 filter. Pure functions, no I/O, no LLM.
- `.claude/skills/tender-matcher/` — stage-2 rubric (markdown, human-edited).
- `docs/superpowers/specs/` — the design. Read before changing behaviour.

## Non-negotiables

- **Never commit `profiles/`, `teams/`, or `outcomes.jsonl`** — real resumes and client names.
- **Tests never hit the network.** Fixtures live in `tests/fixtures/`.
- **Stage 1 errs toward letting notices through.** It is a recall gate: anything it drops is
  never judged and never seen again. Precision failures self-correct at stage 2; recall
  failures are permanent and silent.
- **Feed gotchas** (BOM, `*`-prefixed multi-values, no value column, 15% of notices carry no
  procurement code) are documented in `.agents/skills/canadabuys-search/url-reference.md`.
  Read it before touching ingestion.

## Commands

    canadabuys fetch     # pull open notices into notices/
    pytest               # full suite, offline

## Daily workflow

    /scrape     # pull new notices (canadabuys fetch)
    /rank       # filter, judge, write matches/<date>/digest.md
    /profile <member>   # build or update a member profile
    /team <name>        # declare a team

Scheduling: see `docs/scheduling.md`.

## Annex B archive passes

Offline analyses over historical notices, from the spec's Annex B. Download an
archive into `archives/` (git-ignored), then:

    python tools/archive_report.py archives/<file>.csv

Covers Pass 2 (filter reach and volume) and Pass 5 (market map). Passes 1, 3,
and 4 are LLM-driven — Pass 1 runs inside `/profile`; Passes 3 and 4 are manual
reads described in the spec.
