# tendersearch — Agent Guide

Finds and triages Canadian federal tender opportunities for a small consulting group.

## Layout

- `canadabuys/` — feed ingestion. All network and file I/O. **No judgment logic.**
  Other sources are sibling packages following the same contract — see
  `/add-source` and `.claude/commands/add-source.md`.
- `matching/` — stage-1 filter. Pure functions, no I/O, no LLM.
- `.claude/skills/tender-matcher/` — stage-2 rubric (markdown, human-edited).
- `.claude/skills/tender-assistant/` — `/apply` drafting style and structure (markdown, human-edited).
- `docs/superpowers/specs/` — the design. Read before changing behaviour.

## Non-negotiables

- **Never commit `profiles/`, `teams/`, or `outcomes.jsonl`** — real resumes and client names.
- **Tests never hit the network.** Fixtures live in `tests/fixtures/`.
- **Stage 1 errs toward letting notices through.** It is a recall gate: anything it drops is
  never judged and never seen again. Precision failures self-correct at stage 2; recall
  failures are permanent and silent.
- **Feed gotchas** (BOM, `*`-prefixed multi-values, no value column, 10–15% of notices carry no
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
    /add-source [url]   # build a source skill for another portal or jurisdiction

Scheduling: see `docs/scheduling.md`.

## Per-notice, after a bid/no-bid decision

    /apply <notice-id>  # assemble a bid draft in bids/<notice-id>/ from an existing verdict

Not part of the daily scheduled run — run it by hand for a specific notice once `/rank` has
already produced a verdict for it. Uses the `tender-assistant` skill for drafting style and
structure. `/outcome` (recording the decision and result) is specified but not yet built.

## Annex B archive passes

Offline analyses over historical notices, from the spec's Annex B. Download an
archive into `archives/` (git-ignored), then:

    python tools/archive_report.py archives/<file>.csv

Covers Pass 2 (filter reach and volume) and Pass 5 (market map).

Pass 4 (score face validity) builds its review sheet from a `/rank` run, not an
archive:

    python tools/pass4_review.py                    # newest run in matches/
    python tools/pass4_review.py matches/2026-08-04 # a specific run

It writes `pass4-review.md` into that run's directory — a stratified sample of
verdicts for a human to read and correct. Every verdict at or above
`--detail-above` gets a full write-up; `--sample` low scorers get the same
treatment, because that is where a wrong call is invisible.

Passes 1 and 3 remain LLM-driven — Pass 1 runs inside `/profile`; Pass 3 is a
manual read described in the spec.
