# Changelog

Notable changes to tendersearch. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- MIT licence, contribution and security policies, PR template, and a shared
  `.claude/settings.json` so a fresh clone runs without per-command prompting.
- CI on every push and pull request: `pytest` across Python 3.11–3.13 on Linux, frontmatter
  linting for commands and skills (`tools/lint_skills.py`), and a job asserting that no real
  profile or team data is tracked.

## [0.1.0] — 2026-08-04

First working version. Ingests CanadaBuys tender notices, filters them against member
capability profiles, judges the survivors, and drafts bid responses.

### Added
- **Ingestion** (`canadabuys/`) — CanadaBuys open-data CSV feeds with amendment-aware upsert.
  Notices are identified by reference number; an amendment updates in place and flags the
  notice for re-judging when the closing date, description, or selection criteria changed.
- **Stage-1 filter** (`matching/filter.py`) — deterministic, no LLM. Biased toward recall:
  absent or ambiguous data lets a notice through, because anything dropped here is invisible
  forever.
- **Stage-2 rubric** (`.claude/skills/tender-matcher/`) — LLM judgment over survivors,
  producing per-requirement gap attribution and a bid/no-bid recommendation. Editable markdown.
- **Low-barrier track** (`matching/lowbarrier.py`) — supply arrangements, standing offers,
  ACANs, and subcontracting classified separately from open competitions, with a confidence
  flag distinguishing structured signals from the description heuristic.
- **Profiles and teams** (`matching/profile.py`) — members are the primitive; teams are
  declared unions whose capabilities resolve at read time, so a profile edit propagates.
  Empty past performance is valid and never disqualifying.
- **Commands** — `/scrape`, `/rank`, `/profile`, `/team`, `/apply`.
- **Archive tooling** (`tools/archive_report.py`) — offline analysis over fiscal-year archives
  for filter reach and market mapping.

### Known limitations
- **Scoring bands are uncalibrated.** They have never been tested against real notices. Annex B
  Pass 4 — reading 50–100 verdicts and correcting the systematic errors — is what makes a score
  mean anything.
- **Recall has not been measured.** Annex B Pass 3 samples what stage 1 rejected; until it runs,
  the miss rate is unknown.
- **`/outcome` is not built.** Its schema is specified; the commands are not. Without it there
  is no record of decisions, and so no path to outcome-driven tuning.
- **No estimated contract value.** The feed carries no value column, so value cannot be filtered
  on and the low-barrier track keys off notice type and procurement method instead.

### Measured feed facts
Captured from the live `openTenderNotice` feed on 2026-08-03 (896 open notices), and encoded in
`.agents/skills/canadabuys-search/url-reference.md`:
- UNSPSC present on 84% of notices, GSIN on 4%; **15% carry no procurement code at all** and are
  reachable only by keyword.
- `noticeType` empty on 13%, so low-barrier classification falls back to `procurementMethod`.
- Multi-value fields are `*`-prefixed and newline-separated; the file carries a UTF-8 BOM.
