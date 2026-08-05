<p align="center">
  <img src="docs/assets/tendersearch-logo.png" alt="tendersearch" width="520">
</p>

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
/scrape              /rank                        /apply
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

## Prerequisites

- [Claude Code](https://claude.com/claude-code)
- Python 3.11+
- Git
- Nothing else. Dependencies are `requests`, `PyYAML`, and `pytest`.

## Quick start

Steps 1 and 2 are shell commands. Steps 3 to 5 are Claude Code slash commands —
open Claude Code in this folder and type them at its prompt, not in a terminal.

### 1. Install

```bash
git clone https://github.com/p3ji/tendersearch.git
cd tendersearch
python -m venv .venv
```

Activate it, using the line for your shell:

```bash
source .venv/Scripts/activate      # Windows Git Bash
.venv\Scripts\Activate.ps1         # Windows PowerShell
source .venv/bin/activate          # macOS / Linux
```

If PowerShell refuses to run the activate script, allow it for that window only:
`Set-ExecutionPolicy -Scope Process RemoteSigned`.

```bash
pip install -e ".[dev]"
pytest                             # full suite, no network
```

**Re-run the activate line in every new terminal session.** Without it, `canadabuys`
is not on your PATH and `/scrape` and `/rank` will fail.

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
services." Measured on the live feed across two snapshots (2026-08-03 and 2026-08-04): UNSPSC
codes appear on 84–85% of notices, GSIN on 4%, and **10–15% carry no procurement code at all**.
Those are reachable only by keyword. The exact share moves week to week; the shape does not.

### 4. Declare a team (optional)

```
/team delivery
```

A team is a list of member IDs. Capabilities are unioned from the member profiles at read
time and never copied into the team file, so editing one profile propagates everywhere.

### 5. Set your thresholds

Open `config.yml` in any text editor. Four settings, all safe to change at any time —
nothing is recomputed from them until the next `/rank`.

| Setting | Default | What it does |
|---|---|---|
| `min_turnaround_days` | `5` | Stage 1 drops anything closing sooner than this. Raise it if you keep seeing bids you had no time to write; lower it if the digest looks thin. On a typical day this is the second-largest reject bucket. |
| `notify_score_threshold` | `70` | Score at or above which the digest lists a notice first, and the daily schedule notifies you. Set it from what real verdicts look like after a week, not from a round number. |
| `active_profiles` | `[]` | Empty means every profile in `profiles/`. Name member IDs here to rank for a subset — e.g. `["alex", "sam"]`. Naming an unknown ID is a hard error, not a silent skip. |
| `active_teams` | `[]` | Empty means every team. Used by `/rank` at stage 2 only; the stage-1 filter ignores it. |

### 6. Rank

```
/rank
```

Requires `/scrape` to have run at least once. Runs both stages and writes
`matches/<today>/digest.md` plus `verdicts.json`.

Stage 2 judges every notice that survives stage 1 — currently around 85 of 920.
Expect several minutes and a meaningful chunk of your Claude Code usage. Stage 1
alone is free and instant, so if you only want to sanity-check a profile, run
`canadabuys filter --profiles profiles` in the terminal instead.

A thinner digest than you expected is usually `config.yml`, not the rubric:
`min_turnaround_days` drops everything closing sooner than that many days out,
which is the second-largest reject bucket on a typical day.

## Commands

| Command | What it does |
|---|---|
| `/scrape` | Pull the latest notices. Wraps `canadabuys fetch`. |
| `/rank` | Filter, judge, write today's digest. This is what the daily schedule calls. |
| `/profile <member>` | Build or update a member profile from evidence plus interview. |
| `/team <name>` | Declare or edit a team. |
| `/apply <notice-id>` | Assemble a bid draft for a notice that already has a verdict from `/rank`. Run per-notice, not part of the daily schedule. |
| `/add-source [url]` | Build a source skill for another procurement portal — a province, a municipality, another country. Interviews you, investigates the feed, scaffolds the package, and verifies it before registering. `--list` shows what is installed. |

If more than one profile or team has a verdict for the same notice, `/apply` needs
to be told which one to draft for — pass `--profile <id>` or `--team <id>` (one or
the other, never both).

CLI, underneath:

```bash
canadabuys fetch [--feed open|new] [--file PATH]
canadabuys stats
canadabuys filter --profiles profiles [--config config.yml] [--json PATH] [--include-rejected]
canadabuys apply <notice-id> [--profile ID | --team ID]
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
Once `/rank` has produced verdicts, Pass 4 checks the scores against your own judgment:

```bash
python tools/pass4_review.py
```

It writes `pass4-review.md` into the newest `matches/<date>/`, sampling verdicts for you to
read and correct — every high scorer in full, plus a sample of low scorers, because a good
opportunity wrongly scored 8 looks exactly like the fifty that deserved it. This is what turns
the uncalibrated bands in the rubric into something earned.

The archives contain the *asks*, not the *outcomes* — no winner, no awarded value. So they
cannot tell you whether a high score predicts a win. They calibrate against your judgment and
against observable volume, nothing more. The full methodology is Annex B of the
[design spec](docs/superpowers/specs/2026-08-03-tendersearch-design.md).

## File structure

```
canadabuys/        Feed ingestion. All network and file I/O. No judgment logic.
matching/          Stage-1 filter, profiles, teams, low-barrier. Pure functions.
tools/             Offline archive analysis.
tests/             Full suite. Fixtures are real feed data; nothing hits the network.

.claude/skills/tender-matcher/     The stage-2 rubric. Markdown, meant to be edited.
.claude/skills/tender-assistant/   Bid-drafting style and structure for /apply.
.claude/commands/                  /scrape /rank /profile /team /apply /add-source
.agents/skills/canadabuys-search/  Portable portal skill + feed reference

profiles/<member>/     GIT-IGNORED. profile.yml + evidence/ (resumes, past work)
teams/<name>.yml       GIT-IGNORED
notices/               Raw notices, regenerable
matches/<date>/        Verdicts and digests, regenerable
bids/<notice-id>/      GIT-IGNORED. Your bid drafts — back these up yourself.
archives/              GIT-IGNORED. Downloaded fiscal-year CSVs for offline tuning.
outcomes.jsonl         GIT-IGNORED. Recorded decisions and results (not yet built).
config.yml             Thresholds, active profiles
```

`notices/` and `matches/` are disposable — delete and rebuild them. That asymmetry is
deliberate: a matcher bug is fixed by re-running, never by hand-repair.

## Privacy

`profiles/` and `teams/` are git-ignored and must stay that way. They hold your colleagues'
resumes and, once you record past performance, real client names. Only
[`profiles/_example/profile.yml`](profiles/_example/profile.yml) is committed, as schema
documentation with fake data.

`bids/` is git-ignored for the same reason, with one consequence worth stating plainly:
it is the only directory holding work that cannot be regenerated, and git is not backing
it up. Copy it somewhere you trust.

## Customization

Everything the tool does is steered by four files you edit by hand. Nothing else is
meant to be hand-edited — `notices/`, `matches/`, and `bids/scaffold.json` are written
by the tool, and changes to them are overwritten on the next run.

| File | Edit it to change | How often |
|---|---|---|
| `profiles/<member>/profile.yml` | Which notices stage 1 can see at all — codes, keywords, regions, clearance. **The highest-leverage file in the repo.** | When someone's capabilities change, or when the digest keeps missing work you should have seen |
| `config.yml` | Thresholds and which profiles/teams are active. See [step 5](#5-set-your-thresholds) for each setting. | Early on, weekly; then rarely |
| [`.claude/skills/tender-matcher/SKILL.md`](.claude/skills/tender-matcher/SKILL.md) | How stage 2 scores — the rubric, the weights, the bands, what counts as a deal-breaker. Plain markdown, no code. | Once you have read real verdicts and disagree with them |
| [`.claude/skills/tender-assistant/SKILL.md`](.claude/skills/tender-assistant/SKILL.md) | The voice and section structure `/apply` drafts in. | Once you have seen a draft you would not have sent |

Prefer `/profile <member>` over editing `profile.yml` directly — it mines keywords from
real notice text, which is the part people get wrong by hand.

One file you should read before editing and generally should not touch:
`.agents/skills/canadabuys-search/url-reference.md` documents the feed's measured gotchas
(BOM, `*`-prefixed newline-separated multi-values, no contract-value column, amendments in
place). It is a record of what the feed actually does, not a setting.

## Extending it: sources, rubrics, service lines

Three extension points, none of which require changing the core:

1. **Source skills.** `.agents/skills/canadabuys-search/` is a self-contained folder — a CLI,
   a `SKILL.md`, and a `url-reference.md` recording the feed's measured quirks. A new source
   (a provincial portal, MERX, a departmental page) is a new folder following the same
   contract: normalize into the existing notice schema and the matcher, digest, and `/apply`
   need no changes at all. That isolation is the whole point of the layering.

   **`/add-source` builds one with you.** It interviews you about the portal, fetches real
   responses before writing any parser, scaffolds the package against the source contract,
   and refuses to register anything until the offline suite passes and one live fetch has
   been eyeballed. The contract it enforces — namespaced references, timezone-aware closing
   dates, a status that normalizes to `open`, absent data passing rather than rejecting — is
   the set of things that are silent bugs rather than loud ones if you get them wrong.
2. **The scoring rubric.** [`.claude/skills/tender-matcher/SKILL.md`](.claude/skills/tender-matcher/SKILL.md)
   is markdown, not code. Weights, bands, and what counts as a deal-breaker are yours to edit,
   and they are *meant* to be edited once you have read real verdicts.
3. **Service lines.** Codes and keywords in `profiles/<member>/profile.yml` decide what stage 1
   can see. No code involved, and it carries more weight than anything else in the repo.

### Community forks and adaptations

This is built for a Canadian federal consulting group, but nothing above the ingestion layer
is specific to that. The same structure fits provincial and municipal procurement, other
countries' tender portals, or an entirely different matching domain — swap the source skill
and the rubric, keep the two-stage architecture.

If you fork it for another jurisdiction or market, open a
[fork index](https://github.com/p3ji/tendersearch/discussions/1) and say so. A source skill
someone has already written and tested against a real feed is worth far more than a second
person rediscovering that feed's quirks from scratch — which, on CanadaBuys alone, meant a
BOM, `*`-prefixed newline-separated multi-values, no contract-value column, notices amended
in place, and 10–15% of notices carrying no procurement code at all.

**Before running a source skill from someone else's fork:** read its code. These CLIs run on
your machine against your colleagues' data. Confirm the only network calls go to the portal it
claims to search, that it adds no dependencies you did not expect, and that it writes nothing
outside its own folder. Then run its tests offline — a well-built source skill passes with no
network access at all.

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

## Acknowledgements

Structure and workflow modelled on
[ai-job-search](https://github.com/MadsLorentzen/ai-job-search) by Mads Lorentzen — portable
search skills, markdown-as-methodology, files on disk as the datastore. The
[Canadian fork](https://github.com/p3ji/ai-job-search-ca) is where the pattern was first
adapted for federal-sector use.

Built with [Claude Code](https://claude.com/claude-code).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) first — it explains what gets merged, what belongs in a
fork, and the one rule everything else follows from (stage 1 is a recall gate, so absent data
must never cause a rejection).

[SECURITY.md](SECURITY.md) states the threat model plainly. The short version: this repo runs
code on your machine, with pre-approved permissions, against your colleagues' resumes and real
client names. The `.gitignore` allowlist is the only thing keeping that data private, and a
leak cannot be undone by a revert.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, adapt it for another jurisdiction.

## Support

If this saved you a weekend you would have spent on an unwinnable bid, you can
[buy me a coffee](https://ko-fi.com/pejia).

There is **no affiliated cryptocurrency, token, or paid sponsorship programme** attached to
this project. Anything claiming otherwise is not mine and should be treated as a scam.



## Status

The matching engine and the application assistant are built and tested. Outcome recording is not.

| Piece | State |
|---|---|
| Feed ingestion, amendment handling | Built — fully tested, all offline |
| Stage-1 filter, low-barrier classification | Built |
| Stage-2 rubric + `/rank` digest | Built |
| Member profiles, teams | Built |
| Archive analysis tooling | Built |
| `/apply` — assembled response draft | Built |
| `/outcome` — decision + result recording | **Not built** — schema is specified, commands are not |

