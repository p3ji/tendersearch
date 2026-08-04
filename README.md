# tendersearch

*Federal tender triage that runs on your machine.*

Finds Canadian federal tender opportunities that match a small consulting group's
capabilities, and tells you which are actually worth bidding. Built on
[Claude Code](https://claude.com/claude-code), modelled on the structure of
[ai-job-search](https://github.com/MadsLorentzen/ai-job-search) — portable search CLIs,
markdown skills for judgment, files on disk as the datastore. No database, no service
to operate, no API key.

> Independent open-source project, not affiliated with or endorsed by Anthropic or the
> Government of Canada. It reads public open data and does not submit anything on your behalf.

---

## What this is

A daily pipeline over the CanadaBuys open-data feed. It ingests every open tender notice,
filters them against per-member capability profiles, judges the survivors against a rubric
you control, and writes a digest telling you what to bid on and what to skip.

```
/scrape              /rank                        /apply  (not built yet)
  |                    |                            |
  v                    v                            v
Pull open          Stage 1: code filter         Assemble a draft
notices from       (deterministic, no LLM)      response from the
CanadaBuys              |                       verdict's gap report
  |                     v                            |
  v                Stage 2: LLM judgment             v
notices/           against your rubric          bids/<notice-id>/
(raw, immutable)        |
                        v
                   matches/<date>/digest.md
                   - open competitions
                   - low-barrier track
                   - gaps worth fixing
```

The thing it is actually optimised for is **not bidding**. A good no-bid is the highest-value
output here — federal proposals cost weeks, and most of them you cannot win. The gap report
("we meet 6 of 8 mandatories; Alex covers criterion 3; nobody holds the clearance") is the
product.

## Status

The matching engine is built and tested. The application assistant is not.

| Piece | State |
|---|---|
| Feed ingestion, amendment handling | Built — 106 tests, all offline |
| Stage-1 filter, low-barrier classification | Built |
| Stage-2 rubric + `/rank` digest | Built |
| Member profiles, teams | Built |
| Archive analysis tooling | Built |
| `/apply` — assembled response draft | **Not built** — a second plan, written against the matcher's real output |
| `/outcome` — decision + result recording | **Not built** — schema is specified, commands are not |

## Prerequisites

- [Claude Code](https://claude.com/claude-code)
- Python 3.11+
- Nothing else. Dependencies are `requests`, `PyYAML`, and `pytest`.

## Quick start

### 1. Install

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
pytest                             # 106 tests, no network
```

### 2. Pull the notices

```bash
canadabuys fetch --feed open
```

Writes to `notices/<YYYY-MM>/<reference>.json`. Idempotent — safe to re-run. Roughly 900
notices are open at any time, of which a handful are new each day.

### 3. Build a profile

In Claude Code:

```
/profile alex
```

Drop resumes, capability statements, or past proposals into `profiles/alex/evidence/` first
and they get read. The command interviews you for the rest and writes `profiles/alex/profile.yml`.

**Do not skip the vocabulary-mining step.** Procurement officers do not describe your work
the way you do — "change management" is advertised as "business transformation advisory
services." Measured on the live feed: UNSPSC codes appear on 84% of notices, GSIN on 4%, and
**15% carry no procurement code at all**. Those are reachable only by keyword.

### 4. Declare a team (optional)

```
/team delivery
```

A team is a list of member IDs. Capabilities are unioned from the member profiles at read
time and never copied into the team file, so editing one profile propagates everywhere.

### 5. Rank

```
/rank
```

Runs both stages and writes `matches/<today>/digest.md` plus `verdicts.json`.

## Commands

| Command | What it does |
|---|---|
| `/scrape` | Pull the latest notices. Wraps `canadabuys fetch`. |
| `/rank` | Filter, judge, write today's digest. This is what the daily schedule calls. |
| `/profile <member>` | Build or update a member profile from evidence plus interview. |
| `/team <name>` | Declare or edit a team. |

CLI, underneath:

```bash
canadabuys fetch [--feed open|new] [--file PATH]
canadabuys stats
canadabuys filter --profiles profiles [--json PATH] [--include-rejected]
canadabuys --notices DIR fetch          # note: --notices goes BEFORE the subcommand
```

## How matching works

**Stage 1 is deterministic code and runs over everything.** It drops notices that are closed,
closing sooner than you could write a bid, outside your regions, or that share no code and no
keyword with any profile.

It is deliberately generous, because **it is a recall gate**: anything it drops is never judged,
never appears in a digest, and is invisible to you forever. Precision failures self-correct at
stage 2 — a bad candidate costs a few cents of judgment. Recall failures are permanent and
silent. So when data is absent or ambiguous, the notice passes.

**Stage 2 is LLM judgment over survivors only.** It extracts the notice's mandatory and rated
criteria, attributes each to the member who covers it or marks it a gap, scores fit, and
recommends. The rubric lives in [`.claude/skills/tender-matcher/SKILL.md`](.claude/skills/tender-matcher/SKILL.md)
as editable markdown — it is meant to be tuned, and the scoring bands there are a starting
point, not settled.

### The low-barrier track

Notices are also classified into a second track: supply arrangements, standing offers, ACANs,
and subcontracting. For a group with thin procurement history, these are the realistic entry
path, and they are judged on a different question — *could we get onto this vehicle?* rather
than *could we win a full competition?* The digest keeps them in a separate section, never
merged into one ranked list.

Each classification carries a confidence. `high` comes from the structured `noticeType` /
`procurementMethod` fields. `low` comes from a description-keyword rule for subcontracting
that, measured against real feed data, produced 30 false positives out of 30 — 26 of them the
same Indigenous Business Directory boilerplate clause. The rule is kept so those notices stay
visible for manual checking; the digest labels and de-ranks them.

## Working with the archives

CanadaBuys publishes fiscal-year archives with the same columns as the live feed. They are
never fetched by the daily run — they exist so you can tune the matcher offline against
thousands of real notices before trusting it.

```bash
python tools/archive_report.py archives/2024-2025-TenderNotice-AvisAppelOffres.csv
```

Reports filter reach (how many notices per week would survive — the number that tells you
whether your codes and keywords are too broad or too narrow) and a market map (which
departments actually buy your service lines, through which procurement methods, and how it
varies across the fiscal year).

The archives contain the *asks*, not the *outcomes* — no winner, no awarded value. So they
cannot tell you whether a high score predicts a win. They calibrate against your judgment and
against observable volume, nothing more. The full methodology is Annex B of the
[design spec](docs/superpowers/specs/2026-08-03-tendersearch-design.md).

## File structure

```
canadabuys/        Feed ingestion. All network and file I/O. No judgment logic.
matching/          Stage-1 filter, profiles, teams, low-barrier. Pure functions.
tools/             Offline archive analysis.
tests/             106 tests. Fixtures are real feed data; nothing hits the network.

.claude/skills/tender-matcher/     The stage-2 rubric. Markdown, meant to be edited.
.claude/commands/                  /scrape /rank /profile /team
.agents/skills/canadabuys-search/  Portable portal skill + feed reference

profiles/<member>/     GIT-IGNORED. profile.yml + evidence/ (resumes, past work)
teams/<name>.yml       GIT-IGNORED
notices/               Raw notices, regenerable
matches/<date>/        Verdicts and digests, regenerable
config.yml             Thresholds, active profiles
```

`notices/` and `matches/` are disposable — delete and rebuild them. That asymmetry is
deliberate: a matcher bug is fixed by re-running, never by hand-repair.

## Privacy

`profiles/` and `teams/` are git-ignored and must stay that way. They hold your colleagues'
resumes and, once you record past performance, real client names. Only
[`profiles/_example/profile.yml`](profiles/_example/profile.yml) is committed, as schema
documentation with fake data.

## Customization

- **Scoring** — [`.claude/skills/tender-matcher/SKILL.md`](.claude/skills/tender-matcher/SKILL.md).
  Edit the rubric and the bands. Tune them from an archive read first, then from real outcomes.
- **Thresholds** — `config.yml`: `min_turnaround_days` (how little notice you can still bid on),
  `notify_score_threshold`, `active_profiles`.
- **Keywords and codes** — `profiles/<member>/profile.yml`. This is the highest-leverage file
  in the repo: it decides what stage 1 can see at all.
- **Feed handling** — `.agents/skills/canadabuys-search/url-reference.md` documents the feed's
  measured gotchas (BOM, `*`-prefixed newline-separated multi-values, no contract-value column,
  amendments in place). Read it before touching ingestion.

## Deliberately not here

- **Automated submission of anything.** The tool never submits a bid or emails a contracting
  authority. A human reviews and sends, every time.
- **Filled procurement forms and SACC clause handling.** A wrong clause reference is worse than
  none. Revisit after several real submissions reveal which forms actually recur.
- **Fabricated capability claims.** Gaps are reported honestly, because the gap report is the
  whole point.

Deferred items — dashboard, award intelligence, semantic retrieval, outcome-driven rubric
learning — are specified in the design spec's appendix, each with the trigger that should
prompt building it.

## Design documents

- [Design spec](docs/superpowers/specs/2026-08-03-tendersearch-design.md) — architecture,
  decisions and why, the archive methodology, deferred functionality.
- [Implementation plan](docs/superpowers/plans/2026-08-03-tendersearch-matching-engine.md) —
  the task-by-task build of the matching engine.
- [`AGENTS.md`](AGENTS.md) — agent operating guide. Start here if you are using Codex,
  Gemini CLI, or another tool.

## Data source

[CanadaBuys tender notices](https://open.canada.ca/data/en/dataset/6abd20d4-7a1c-4b38-baa2-9525d0bb2fd2)
on the Open Government Portal. Open tender notices refresh daily between 07:00 and 08:30
(UTC-0500); new notices refresh every two hours.
