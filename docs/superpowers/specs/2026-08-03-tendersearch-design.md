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

**Explicitly excluded from v1:** filled procurement forms, pricing tables, SACC clause handling
(A2), web dashboard (A1), non-CanadaBuys sources (A3), award intelligence (A4), outcome-driven
rubric learning (A5). Automated submission of anything is excluded permanently (A6).

Each is specified in the **Appendix — Deferred functionality**, with the rationale for waiting and
the trigger that should prompt building it.

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

---

# Appendix — Deferred functionality

Each item below was considered and deliberately left out of v1. This appendix records what the
thing is, what it would take, why it waits, and **the trigger that should make us build it**.
Nothing here is a commitment; it exists so a later session can pick an item up cold and so we don't
relitigate settled reasoning.

Read the triggers as the operative part. "Later" without a trigger is how deferred work quietly
becomes never-built work, or worse, gets built early because someone forgot why it waited.

## A1 — Shared web dashboard

**What.** A generated HTML view of the pipeline — current open matches by score, upcoming
deadlines, bids in progress and their owners, win/loss history — so members can see the state of
play without running Claude Code or having access to the repo.

**Shape.** A `/dashboard` command renders `matches/*/verdicts.json`, `bids/`, and `outcomes.jsonl`
into a single self-contained HTML file. No server, no build step, no external assets. Published
either as a Claude Artifact or dropped into a static host. The daily schedule regenerates it after
`/rank`.

**Why v1 already accommodates it.** Verdicts and digests are written as structured JSON, not prose,
specifically so a renderer can consume them. That constraint is honoured in v1 and costs nothing.
Building the renderer later is additive — no data migration, no changes to matching.

**Why deferred.** The digest is a markdown file that reads fine in a terminal or editor, and until
several people are actively working bids there is nothing to coordinate. Building a dashboard for
one user is decoration.

**Privacy note that must be settled before building.** Profiles are git-ignored because they hold
members' resumes and client names. A dashboard renders derived data that can leak the same
information — a gap report naming who lacks a clearance is sensitive. Decide the audience and
redaction rules *before* the first render, not after it is shared.

**Trigger.** Two or more members are working bids concurrently, or someone asks "what's in the
pipeline?" more than once.

## A2 — Full submission package

**What.** Beyond the v1 draft: filled procurement forms, structured pricing tables, and
solicitation-specific compliance handling including SACC clause references.

**Shape.** A form-template library keyed by solicitation type; a pricing model driven by member
rate cards (a profile field v1 does not yet have); a compliance engine that maps a solicitation's
cited clauses to required responses. `/apply --package` produces submission-ready artifacts.

**Why deferred — the strongest deferral in this document.** Federal forms and SACC clauses are
brittle and unforgiving, and a *wrong* clause reference is materially worse than no clause
reference: it signals inexperience to an evaluator and can render a bid non-compliant. Generating
this content confidently and incorrectly is the worst outcome the tool could produce. It also
cannot be built credibly from documentation alone — you need to know which forms actually recur for
your service lines, and that knowledge only comes from having submitted.

**Precondition.** At least three completed real submissions, with the actual forms retained. Build
the template library from those, not from guesses.

**Trigger.** The same form has been filled by hand three times.

**Scope guard.** Even when built, this generates artifacts for a human to review and submit.
Automated submission to CanadaBuys is permanently out of scope — see A6.

## A3 — Additional procurement sources

**What.** Provincial and municipal portals (BC Bid, Biddingo, MERX, SEAO), and any buyer whose
notices never reach CanadaBuys.

**Shape.** One new skill per source under `.agents/skills/<source>-search/`, each normalizing into
the *existing* notice schema. The matcher, digest, and `/apply` need no changes — this is precisely
what the layered architecture buys. Sources without open-data feeds require HTML scraping and must
honour each site's crawl policy; `aijobsearch`'s portal skills are the working pattern, including
its convention of recording in `url-reference.md` what was tried and why it doesn't work.

**Why deferred.** CanadaBuys alone produces more qualified notices than a small group can bid.
Adding sources before the matcher is calibrated multiplies noise, not opportunity.

**Trigger.** The daily digest is consistently thin — fewer than a couple of genuine matches a week
after calibration — or a specific known buyer is confirmed to publish elsewhere.

## A4 — Award and competitive intelligence

**What.** Use historical award data to answer questions v1 cannot: who actually wins this
organization's work, at what values, how many bidders typically compete, and whether an incumbent
is entrenched. Feeds both bid/no-bid judgment and pricing.

**Shape.** Ingest contract-award / proactive-disclosure data (the Open Government portal publishes
contract history; **the exact dataset and its schema must be verified before designing against it**
— do not assume it joins cleanly to tender notices, since award records and tender notices are
maintained separately and may share no reliable key). Join what can be joined; where a join is
impossible, match on organization and category as a weaker signal and label it as such in the
output.

**Why deferred.** High analytical value but entirely dependent on a data join that may not exist.
Investigating it is a research task with an uncertain answer, and the tool is useful without it.

**Trigger.** The group is regularly making close bid/no-bid calls where incumbency is the deciding
unknown.

## A5 — Learning from outcomes

**What.** Close the loop: use `outcomes.jsonl` to automatically adjust rubric weights, so the
matcher improves as real results accumulate.

**Shape.** Periodic review comparing predicted scores against actual bid/no-bid decisions and
results, surfacing systematic bias ("we consistently over-score notices where the mandatory is a
certification we lack"). Output is a proposed rubric edit **for human approval** — never a silent
weight change, because an opaque scorer that drifts is worse than a crude one you understand.

**Why deferred.** Needs data. With fewer than roughly twenty recorded outcomes, any adjustment is
overfitting to noise.

**Why v1 accommodates it.** `outcomes.jsonl` is captured from day one specifically to make this
possible later. Recording outcomes has standalone value — it becomes past-performance evidence,
which is this group's binding constraint.

**Trigger.** Twenty-plus recorded outcomes.

## A6 — Permanently out of scope

Not deferred. Excluded by intent, recorded so nobody proposes them as a natural next step.

- **Automated submission of a bid.** The tool never submits anything to CanadaBuys or emails a
  buyer. A human reviews and submits every time. An automated submission that is wrong is an
  irreversible, reputationally costly error against a government buyer.
- **Automated contact with contracting authorities.** Draft the question; a human sends it.
- **Fabricated past performance or capability claims.** The matcher reports gaps honestly. A tool
  that papers over a gap to raise a score is actively harmful — misrepresentation in a federal bid
  carries consequences well beyond losing it. Gaps are the point of the gap report.
