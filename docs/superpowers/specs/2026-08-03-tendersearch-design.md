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

**Source — verified 2026-08-03.** Open Government dataset *CanadaBuys tender notices*
(https://open.canada.ca/data/en/dataset/6abd20d4-7a1c-4b38-baa2-9525d0bb2fd2). Two live feeds plus history:

| Feed | URL | Refresh |
|---|---|---|
| New tender notices | `https://canadabuys.canada.ca/opendata/pub/newTenderNotice-nouvelAvisAppelOffres.csv` | every 2h, 6:15–22:15 (UTC-0500) |
| Open tender notices | `https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv` | daily, 07:00–08:30 (UTC-0500) |
| Fiscal-year archives (2022-23 → current) | `.../pub/<FY>-TenderNotice-AvisAppelOffres.csv` | daily |
| Legacy archive 2009–2022 | `.../pub/2009-2022-tenderNoticeHistorical-AvisAppelOffresHistorique.csv` | static |

Field reference: `https://donnees-data.tpsgc-pwgsc.gc.ca/ba2/ac-cb/soutien-support-eng.html`.

`openTenderNotice` is the authority on what is currently open and drives the daily run.
`newTenderNotice` is polled for same-day freshness when a faster cadence is wanted.
The archives are not part of the daily path; they exist to calibrate the stage-2 rubric against
thousands of real past notices and to see which organizations actually buy each service line.

Commands:

- `fetch` — pull the feed, normalize rows to the notice schema, upsert into `notices/`. Idempotent.
- `enrich <notice-id>` — fetch attachment contents from the notice's `attachment` / `noticeURL`
  values. **Not required for matching** (see below); used by `/apply`.

Performs no judgment. Tested against saved fixtures with no network access.

**The CSV carries the full `tenderDescription`**, so stage-1 filtering and stage-2 judgment both run
entirely off the feed with no per-notice page fetches. Detail fetching is therefore off the daily
path completely — the fragile part of ingestion only runs on demand, for a notice already chosen.

**Columns** (all bilingual, `-eng` / `-fra` suffixes, normalize to English and retain the French
description): `title`, `referenceNumber`, `amendmentNumber`, `solicitationNumber`,
`publicationDate`, `tenderClosingDate`, `amendmentDate`, `expectedContractStartDate`,
`expectedContractEndDate`, `tenderStatus`, `gsin` + `gsinDescription`, `unspsc` +
`unspscDescription`, `procurementCategory`, `noticeType`, `procurementMethod`,
`selectionCriteria`, `limitedTenderingReason`, `tradeAgreements`, `regionsOfOpportunity`,
`regionsOfDelivery`, `contractingEntityName` + address, `endUserEntitiesName` + address,
`contactInfo*`, `noticeURL`, `attachment`, `tenderDescription`.

Three consequences that the rest of this design depends on:

- **There is no estimated-value column.** Contract value cannot be filtered on. Where value matters
  it must be inferred from `tenderDescription`, and treated as advisory only. The low-barrier track
  keys off `noticeType` and `procurementMethod` instead, which is more reliable regardless.
- **Both `gsin` and `unspsc` are populated.** GSIN is the older PWGSC scheme and is widely used in
  this feed; matching on UNSPSC alone would miss notices. Profiles carry both.
- **Notices are amended in place.** The identity key is `referenceNumber` + `amendmentNumber`.
  `fetch` upserts: an amendment updates the stored notice, and if `tenderClosingDate`,
  `tenderDescription`, or `selectionCriteria` changed, the notice is re-queued for matching and the
  digest flags it as amended. Silently keeping a stale verdict after an amendment is a correctness
  bug, not a nicety — amendments routinely change criteria and deadlines.

### Layer 2 — Matching

**Stage 1, deterministic filter (code, runs over everything).** Drops a notice when any holds:

- Closing date has passed, or is inside the minimum-turnaround threshold (config, default 5 business days) — a bid that cannot physically be written is not a match.
- `tenderStatus` is not Open (Expired, Cancelled).
- `regionsOfDelivery` is outside every active profile's geographic ability.
- Zero GSIN/UNSPSC/NAICS code overlap **and** zero service-line keyword hits against every active
  profile, searching `title`, `tenderDescription`, `selectionCriteria`, and the code descriptions.

Deliberately generous. A false positive costs a few cents of LLM judgment; a false negative costs a contract. Cuts a few hundred daily notices to a handful, which is what makes a daily scheduled run affordable.

**Stage 2, LLM judgment (survivors only).** For each surviving notice, against each active profile and each active team:

- Extract mandatory and rated criteria from the notice description and attachments.
- Attribute each criterion to a covering member, or mark it a gap or unclear.
- Score fit, and emit a bid/no-bid recommendation with reasoning.
- Set the low-barrier flag (below).

The rubric and scoring weights live in `.claude/skills/tender-matcher/` as editable markdown, to be tuned against real outcomes rather than guessed up front.

**Low-barrier policy.** Given thin past performance, the matcher runs a second track, keyed off
`noticeType` and `procurementMethod` rather than contract value (which the feed does not provide).
Notices that are standing offers, supply arrangements, advance contract award notices, or that name
subcontracting opportunities in the description are flagged and surfaced even at moderate fit. Large open competitions with heavy past-performance mandatories are scored honestly and will usually land as no-bid. The digest presents these as two separate sections, never one ranked list — "we could realistically get onto this vehicle" and "we should spend three weeks bidding this" are different decisions and must not be blended into a single ordering.

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
- **Service lines:** each with a label, NAICS codes, **GSIN codes, UNSPSC codes**, and keywords.
  Both GSIN and UNSPSC are required — the feed populates both and they do not map cleanly onto
  each other, so carrying only one loses notices.
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

Normalized CanadaBuys fields, English-primary with the French description retained: reference
number, amendment number, solicitation number, title, contracting entity, end-user entity,
procurement category, notice type, procurement method, GSIN and UNSPSC codes with descriptions,
selection criteria, trade agreements, regions of opportunity and delivery, publication date,
closing date, amendment date, expected contract start/end, status, description, contact info,
notice URL, attachment URLs. There is no estimated-value field in the source.

Plus local metadata: first-seen timestamp, last-updated timestamp, source feed, amendment history,
and a `needs_rematch` flag set when an amendment changes closing date, description, or criteria.

File path uses the reference number; amendments update the same file rather than creating a new one.

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
- `enrich` failure on a single notice → report it during `/apply`. It cannot affect the daily run,
  since matching never calls it.
- Malformed `profile.yml` → fail that profile with a clear message, continue with others, and say in the digest which profiles were skipped.
- Stage-2 verdict failing schema validation → retry once, then record as an error entry visible in the digest rather than dropping the notice.

## Testing

- **Ingestion:** against saved CSV fixtures, no network. A fixture captured from the real feed is
  the schema contract; a change that breaks it should break the tests. Required cases: bilingual
  column normalization, an amendment updating an existing notice, an amendment that changes the
  closing date (must set `needs_rematch`), and a re-run producing no duplicates.
- **Stage-1 filter:** unit tests with synthetic notices and profiles. Required cases: empty past
  performance, a notice matching on GSIN but not UNSPSC (and the reverse), notice closing tomorrow,
  notice already closed, `tenderStatus` cancelled, region mismatch, and team unioning coverage that
  no single member has.
- **Stage-2 judgment:** a small set of hand-labelled real notices as a regression check — expected recommendation and expected gap list.
- **Team unioning:** verified directly, since it is the mechanism the whole team model rests on.

## Implementation order

1. Capture a live `openTenderNotice` CSV as a test fixture; write `url-reference.md` recording the
   feeds, refresh windows, column list, and the three gotchas (no value column, dual GSIN/UNSPSC,
   amendments-in-place). *The feed itself is verified — this is fixture capture, not a gate.*
2. Notice schema + `fetch` with upsert/amendment handling, against fixtures.
3. Profile and team schemas + `_example/`; `.gitignore`.
4. `/profile` and `/team`.
5. Stage-1 filter with unit tests.
6. Stage-2 rubric skill and verdict schema; `/rank` and the digest.
7. Scheduling and notification.
8. `/apply`, and `enrich` for attachment contents.
9. `/outcome`.

Steps 1–6 constitute a useful tool on their own: it will tell the group what to bid on. Steps 8–9
remove drudgery afterwards.

**Rubric calibration (after step 6).** Before trusting scores, run the matcher over a fiscal-year
archive file and inspect what it would have flagged. This is cheap, uses no live quota, and is the
only honest way to tune weights — my priors about what scores well are guesses until tested against
notices that really existed.
