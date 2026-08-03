# tendersearch — Design

**Date:** 2026-08-03
**Status:** Approved (design). Not yet implemented.

## Purpose

A tool for a small consulting group bidding on Canadian federal procurement. Three jobs:

1. Build and maintain tailored service profiles for each member of the group, and for teams formed from them.
2. Ingest CanadaBuys tender opportunities daily and match them against those profiles.
3. Assist the application process — bid/no-bid triage first, then an assembled first draft of the response.

Inspired by the `aijobsearch` project in this Projects folder, which supplies the structural pattern: portable Python portal-search CLIs under `.agents/skills/`, LLM methodology as markdown skills under `.claude/skills/`, workflows as slash commands under `.claude/commands/`, and files on disk as the datastore. No database, no service to operate.

Primary source: CanadaBuys open tender notices (https://canadabuys.canada.ca/en/tender-opportunities).

## Decisions

Recorded so they are not relitigated during implementation.

| Decision | Choice | Rationale |
|---|---|---|
| Profile scope | Multi-profile, one per member | The group is several people with differing technical skills, not one bidder. |
| Profile authoring | Evidence ingest + interview | Members hold documents (resumes, prior work) but not uniform procurement history. Typing profiles from scratch is the main barrier to the tool ever being used. |
| Team model | Members are the primitive; teams are declared unions of members | Most winnable federal consulting work is won by a team that collectively clears the mandatories. The gap report ("we meet 6 of 8, missing X and Y, and Alex covers criterion 3") is the tool's highest-value output and requires member attribution. |
| Application depth | Triage gate, then assembled first draft. No filled forms. | A good no-bid is the highest-ROI output. Filled SACC/procurement forms are brittle and unforgiving; a wrong clause reference is worse than none. Revisit after several real submissions reveal which forms recur. |
| Run model | Scheduled daily + digest, with notification on threshold | Tender windows are short (often 10–15 business days). A manual-only workflow surfaces the good opportunity on day 12. |
| Web dashboard | Out of scope for v1 | Additive later; the digest is written as structured data specifically so rendering it to HTML is a small step. |
| Past-performance posture | Thin past performance is expected and must not be treated as disqualifying | The binding constraint on what this group can win is procurement track record, not skill. |
| Profile privacy | `profiles/` and `teams/` git-ignored; committed `_example/` shows schema | They hold members' resumes and possibly client names. |
| Spec location | `docs/superpowers/specs/` in-repo | User preference, chosen over the Projects-root convention of routing architecture rationale to the Brain note. |

**Explicitly excluded from v1:** filled procurement forms, pricing tables, SACC clause handling, web dashboard, non-CanadaBuys sources (provincial portals, MERX), automated submission of anything.

## Architecture

Three layers, one-way data flow. Each is independently testable and can fail without corrupting the others.

```
CanadaBuys  ──▶  Ingestion  ──▶  notices/   (raw, immutable)
                (Python, no LLM)      │
                                      ▼
                            Matching stage 1 (code filter)
                                      │
                            Matching stage 2 (LLM judgment)
                                      │
                                      ▼
                                 matches/    (verdicts, regenerable)
                                      │
                                      ▼
                            Application (LLM, on demand)
                                      │
                                      ▼
                                  bids/      (your working documents)
```

`notices/` and `matches/` are disposable — delete and rebuild. Only `bids/` holds work that would hurt to lose. A matcher bug is therefore fixed by re-running, never by hand-repair.

### Layer 1 — Ingestion

`.agents/skills/canadabuys-search/cli`, a Python CLI. The only layer that touches the network, so it is the only layer that breaks when CanadaBuys changes.

- `fetch` — pull the CanadaBuys open tender notices CSV feed, normalize rows to the notice schema, dedupe against `notices/` by notice ID, write new records. Idempotent.
- `enrich <notice-id>` — fetch the notice detail page for full description text and attachment URLs, merge into the existing record.

Performs no judgment. Tested against saved fixtures with no network access.

**Open risk — resolve first.** This design assumes the CanadaBuys open-data CSV feed exists, is refreshed daily, and carries enough per-notice detail to filter on (at minimum: id, title, buying org, UNSPSC/category, region, closing date, description or a detail URL). This has not been verified. **Implementation step one is confirming the feed's URL, schema, and refresh cadence, and pinning a real response as a test fixture.** If the feed proves inadequate, the fallback is HTML-scraping the tender-opportunities search UI — slower, more fragile, and subject to the site's crawl policy, but it changes nothing in the layers above. That isolation is the reason ingestion is a separate layer.

### Layer 2 — Matching

**Stage 1, deterministic filter (code, runs over everything).** Drops a notice when any holds:

- Closing date has passed, or is inside the minimum-turnaround threshold (config, default 5 business days) — a bid that cannot physically be written is not a match.
- Region is outside every active profile's geographic ability.
- Zero UNSPSC/NAICS overlap **and** zero service-line keyword hits against every active profile.

Deliberately generous. A false positive costs a few cents of LLM judgment; a false negative costs a contract. Cuts a few hundred daily notices to a handful, which is what makes a daily scheduled run affordable.

**Stage 2, LLM judgment (survivors only).** For each surviving notice, against each active profile and each active team:

- Extract mandatory and rated criteria from the notice description and attachments.
- Attribute each criterion to a covering member, or mark it a gap or unclear.
- Score fit, and emit a bid/no-bid recommendation with reasoning.
- Set the low-barrier flag (below).

The rubric and scoring weights live in `.claude/skills/tender-matcher/` as editable markdown, to be tuned against real outcomes rather than guessed up front.

**Low-barrier policy.** Given thin past performance, the matcher runs a second track. Notices that are standing offers, supply arrangements, sub-threshold contracts, or that name subcontracting opportunities are flagged and surfaced even at moderate fit. Large open competitions with heavy past-performance mandatories are scored honestly and will usually land as no-bid. The digest presents these as two separate sections, never one ranked list — "we could realistically get onto this vehicle" and "we should spend three weeks bidding this" are different decisions and must not be blended into a single ordering.

### Layer 3 — Application

`/apply` operates only on a notice that already has a verdict. Produces, in `bids/<notice-id>/`:

- A requirements→response matrix keyed to the solicitation's own criteria numbering.
- Per criterion, the covering member's relevant resume excerpt and past-performance entry, pulled by reading the referenced evidence files.
- Draft prose sections in the group's writing style (defined in `.claude/skills/tender-assistant/`).
- An unchecked compliance checklist: what the solicitation requires submitted, as a list. Not filled forms.

Member attribution flows from the verdict, which is why it is stored per-requirement rather than flattened to a notice-level score.

## Repository layout

```
tendersearch/
  AGENTS.md
  CLAUDE.md                → @AGENTS.md
  GEMINI.md                → @AGENTS.md
  README.md
  .gitignore                          # profiles/, teams/, notices/, matches/, bids/
  .agents/skills/canadabuys-search/
      SKILL.md
      url-reference.md                # feed URLs, schema notes, what does/doesn't work
      cli/
  .claude/skills/
      tender-assistant/               # profile methodology, writing style, draft structure
      tender-matcher/                 # scoring rubric, bid/no-bid policy, low-barrier rules
  .claude/commands/                   # profile, team, scrape, rank, apply, outcome
  profiles/                           # GIT-IGNORED
      _example/                       # committed; fake data; schema reference
          profile.yml
          evidence/
      <member>/
          profile.yml
          evidence/                   # resumes, past proposals, capability statements
  teams/                              # GIT-IGNORED, with committed _example.yml
      <team>.yml
  notices/YYYY-MM/<notice-id>.json
  matches/YYYY-MM-DD/
      digest.md
      verdicts.json
  bids/<notice-id>/
  outcomes.jsonl
  config.yml                          # thresholds, regions, active profiles/teams, schedule
  tools/
  tests/
```

## Data model

Profiles are YAML rather than markdown prose — a deliberate divergence from `aijobsearch`, which keeps its single candidate profile as prose because one LLM reads it whole. Here, stage-1 filtering is code that must iterate mechanically over codes and regions, and teams must union capabilities programmatically. Both require structure. The prose that genuinely matters — writing style, differentiators, how the group describes its work — stays as markdown under `evidence/` and in the tender-assistant skill.

### Member profile — `profiles/<member>/profile.yml`

- **Identity and legal status:** name, incorporated or sole proprietor, business number, PSPC supplier registration number if any, GST/HST registration.
- **Clearance:** security clearance level held, and status (active/lapsed/eligible).
- **Service lines:** each with a label, NAICS codes, UNSPSC codes, and keywords.
- **Skills:** name, depth, years.
- **Certifications:** name, issuer, expiry.
- **Past performance:** list of {client, value, start, end, description, reference contact}. **May be empty.** The matcher must handle an empty list without treating it as disqualifying.
- **Geography:** regions able to serve, on-site willingness.
- **Capacity:** availability, concurrent-engagement limit.
- **Vehicles:** standing offers, supply arrangements, or other procurement instruments held.
- **Evidence:** paths to resume and document files under `evidence/`, referenced not inlined, so `/apply` pulls the real document.

### Team — `teams/<name>.yml`

Name, member list, designated prime, and any attributes that exist only jointly (JV registration, combined bonding capacity). Capabilities are **never** copied in — they are unioned from member profiles at match time, so editing one profile propagates everywhere.

### Notice — `notices/YYYY-MM/<id>.json`

Normalized CanadaBuys fields: id, title, buying organization, procurement category, UNSPSC codes, region, publication date, closing date, estimated value where given, solicitation type, description, attachment URLs, source URL. Plus ingest metadata: first-seen timestamp, last-enriched timestamp, source feed.

### Verdict — within `matches/YYYY-MM-DD/verdicts.json`

One per notice per profile-or-team: subject (profile or team id), score, recommendation, low-barrier flag, reasoning, and a list of requirement rows. Each requirement row carries the requirement text, its status (met / gap / unclear), and the covering member id when met. Member attribution on the row is what makes the gap report actionable and what `/apply` reads to decide whose resume goes where.

### Outcome — `outcomes.jsonl`

Append-only: notice id, decision (bid/no-bid), result (won/lost/no-award/pending), date, notes. Feeds rubric tuning and, over time, becomes past-performance evidence.

## Commands

| Command | Behaviour |
|---|---|
| `/profile <member>` | Ingest documents from `evidence/`, extract what it can, interview to fill the rest, write `profile.yml`. Re-runnable to update. |
| `/team <name>` | Declare or edit a team. |
| `/scrape` | Ingest new notices. Idempotent; safe to re-run. |
| `/rank` | Run both matcher stages, write today's digest. Called by the daily schedule. |
| `/apply <notice-id> [--profile <m>\|--team <t>]` | Build the bid draft in `bids/<notice-id>/`. Requires an existing verdict. |
| `/outcome <notice-id>` | Record what happened. |

**Schedule:** `/scrape` then `/rank`, weekday mornings. Notify only when a notice clears the score threshold, or when a tracked bid's deadline approaches.

## Error handling

Failures are loud. The one unacceptable failure mode is silently writing an empty digest, because it costs a deadline while looking like a normal quiet day.

- CSV schema change or unparseable feed → abort the run, notify, leave prior state untouched. Never write a partial or empty digest as if it were a real result.
- Network failure during `fetch` → retry with backoff; on exhaustion, abort and notify.
- `enrich` failure on a single notice → record the notice as un-enriched and continue; stage 1 still filters on CSV fields, and the digest marks the notice as detail-unavailable.
- Malformed `profile.yml` → fail that profile with a clear message, continue with others, and say in the digest which profiles were skipped.
- Stage-2 verdict failing schema validation → retry once, then record as an error entry visible in the digest rather than dropping the notice.

## Testing

- **Ingestion:** against saved CSV and HTML fixtures, no network. A fixture captured from the real feed is the schema contract; a change that breaks it should break the tests.
- **Stage-1 filter:** unit tests with synthetic notices and profiles. Required cases: empty past performance, member with no UNSPSC codes, notice closing tomorrow, notice already closed, region mismatch, team unioning coverage that no single member has.
- **Stage-2 judgment:** a small set of hand-labelled real notices as a regression check — expected recommendation and expected gap list.
- **Team unioning:** verified directly, since it is the mechanism the whole team model rests on.

## Implementation order

1. Verify the CanadaBuys feed; pin fixtures; write `url-reference.md`. **Gate — the ingestion design depends on this.**
2. Notice schema + `fetch`/`enrich` CLI, with fixture tests.
3. Profile and team schemas + `_example/`; `.gitignore`.
4. `/profile` and `/team`.
5. Stage-1 filter with unit tests.
6. Stage-2 rubric skill and verdict schema; `/rank` and the digest.
7. Scheduling and notification.
8. `/apply`.
9. `/outcome`.

Steps 1–6 constitute a useful tool on their own: it will tell the group what to bid on. Steps 8–9 remove drudgery afterwards.
