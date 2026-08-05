# Changelog

Notable changes to tendersearch. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- **`/outcome`** and `canadabuys record-outcome` — the last unbuilt piece from the original
  design. Appends one validated JSON line per decision to `outcomes.jsonl`; never touches the
  rubric itself. Controlled-vocabulary reason codes so patterns are countable, a required
  score/recommendation snapshot so a later rubric edit can't make history unrecoverable, and a
  hard stop on `result: won` with no captured client/value/dates/reference — a win is this
  group's only path to real past-performance evidence and must not be lost to a skipped field.
- **`canadabuys enrich`** — on-demand download of a notice's attachments, serving the
  `investigate` verdict. Measured against the 14 notices that survived triage on a real run:
  only 6 had a genuine solicitation package; 4 were a one-page advertisement pointing at a
  contracting officer, including the single highest-scoring notice of that run; 4 had nothing
  at all. The CLI now names the contact when there is nothing to download, and warns that a
  lone attachment may be an ad rather than the package — it never emails anyone itself.
- **`/add-source`** — a generator for source skills covering other procurement portals. Walks
  interview, feed investigation, scaffolding, and verification, and enforces an eleven-rule
  source contract. Most of that contract is the set of mistakes that fail *silently*: colliding
  reference numbers, naive closing datetimes, an unmapped or blank `status`, region strings no
  profile uses, and vehicle types that never reach the low-barrier track.
- **`tools/pass4_review.py`** — Annex B Pass 4. Turns a `/rank` run into a stratified review
  sheet for checking scores against your own judgment: every high scorer in full, plus a sample
  of low scorers, because a wrong call there is invisible.
- MIT licence, contribution and security policies, PR template, and a shared
  `.claude/settings.json` so a fresh clone runs without per-command prompting.
- CI on every push and pull request: `pytest` across Python 3.11–3.13 on Linux, frontmatter
  linting for commands and skills (`tools/lint_skills.py`), and a job asserting that no real
  profile or team data is tracked.
- Project logo in the README header.

### Changed
- **Quick start now works on a machine that is not the author's.** Added the missing `git clone`
  step, the PowerShell activation line, and a note that the venv must be re-activated in every
  new terminal session. `config.yml` is a documented step rather than a passing mention, and
  Customization states which files are yours to edit and which are regenerated output.
- The CI privacy job now also covers `bids/` and `archives/`, not just `profiles/`, `teams/`,
  and `outcomes.jsonl`. `bids/` is the one directory that cannot be regenerated.
- Feed code-coverage figures are quoted as dated ranges (84–85% UNSPSC, 4% GSIN, 10–15% no
  code). Re-measurement a day apart moved the no-code share 15% → 11%; the constant implied a
  precision the feed does not have.

### Fixed
- `canadabuys stats` on an empty store printed four zeros, which reads as a broken tool rather
  than an empty one. It now names the next step.

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
