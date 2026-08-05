---
description: Generate and verify a new procurement-source skill for another portal or jurisdiction
argument-hint: [portal-url | --list]
---

Build a source skill for a procurement portal this repo does not yet cover — a
provincial or municipal tender site, MERX, a departmental page, or another
country's federal portal.

This generator is **jurisdiction-agnostic**. What it produces is specific to one
portal and normally lives in your fork; the generator is the upstream feature,
its output is yours. See CONTRIBUTING.md for what gets merged.

`$ARGUMENTS` may hold a portal URL, `--list`, or nothing.

The whole reason this is cheap: everything above ingestion is source-agnostic
already. A source skill's only job is to turn a portal into `Notice` records and
hand them to `NoticeStore.upsert()`. Stage 1, the rubric, the digest, and
`/apply` then need **no changes at all**. If you find yourself editing
`matching/` to make a new source work, the normalization is wrong — fix it in
the source, not downstream.

---

## Step 0: Parse arguments

- `--list`: Glob `.agents/skills/*/SKILL.md`, print a table (skill name,
  jurisdiction from the description, feed URL from `url-reference.md`), stop.
- A URL: carry it into Step 1 as the portal URL.
- Otherwise: start the interview.

---

## Step 1: Interview

Ask, one question at a time, skipping anything `$ARGUMENTS` already answered:

1. **Portal URL** — the public tender site (e.g. `https://ontariotenders.app.jaggaer.com`).
2. **Skill name** — kebab-case, suffixed `-search` (`ontario-tenders-search`,
   `merx-search`). Must not collide with a folder in `.agents/skills/`.
3. **Jurisdiction and language** — which government and what language notices are
   published in. Drives the `SKILL.md` description and, if the portal is
   French-first, which field maps to `description` versus `description_fr`.
4. **CLI command name** — the console script (`ontariotenders`). Must not collide
   with `canadabuys` or anything on the user's PATH.
5. **A realistic test query or category** — used to eyeball the first live fetch.

---

## Step 2: Investigate before writing any code

Never generate a parser from a guess about a feed's shape. Fetch first.

1. **Look for bulk open data before scraping HTML.** Many portals publish a CSV
   or JSON feed of open notices; that path is stabler, faster, and unambiguous
   about terms of use. Check the jurisdiction's open-data catalogue before you
   consider parsing search-result pages.
2. **Fetch one real response** and record: the field carrying the unique
   reference number, title, buyer, closing date, status, description, and
   whatever classification codes exist (UNSPSC, GSIN, CPV, NIGP, a local
   taxonomy, or none).
3. **Establish how amendments appear.** This is the question people get wrong.
   Does the portal republish a notice in place, bump a revision number, or emit
   a separate "amendment" record? `NoticeStore.upsert()` assumes amendments
   arrive as the same reference with a non-decreasing amendment number.
4. **Measure code coverage on real data.** What share of notices carry a usable
   classification code? On CanadaBuys it is 84% UNSPSC, 4% GSIN, and 15% carry
   none at all. Write the measured number into `url-reference.md` — it tells a
   profile author how much weight keywords have to pull for this source.
5. **Check access.** Fetch `robots.txt`. If listings require a login, **stop** —
   this pattern only works on public data; suggest looking for an official API.
   If robots.txt or the terms restrict automated access, say so plainly and let
   the user decide. If they proceed, the generated `SKILL.md` must carry a
   prominent personal-use-only warning.
6. **Record the quirks as you hit them.** Encoding and BOM, multi-value
   delimiters, timezone (stated or assumed), date formats, HTML embedded in
   description text, pagination limits, rate limiting. These go in
   `url-reference.md` verbatim. On CanadaBuys this list was a BOM, `*`-prefixed
   newline-separated multi-values, no contract-value column, notices amended in
   place, and a 403 on any non-browser User-Agent — none of which were
   documented anywhere.

---

## Step 3: Scaffold

**Canonical reference: read `canadabuys/` and `.agents/skills/canadabuys-search/`
before generating.** Copy the architecture, not the CanadaBuys field names.

```
<source>/                       # Python package, sibling to canadabuys/
├── __init__.py
├── cli.py                      # argparse entry point
├── fetch.py                    # the ONLY module that touches the network
├── fields.py                   # this portal's parsing trivia, isolated
└── store.py                    # reuse canadabuys.store.NoticeStore; do not fork it

.agents/skills/<name>/
├── SKILL.md                    # triggers, commands, rules
└── url-reference.md            # endpoints, refresh windows, measured gotchas

tests/test_<source>_*.py
tests/fixtures/<source>_sample.csv    # a real trimmed response, committed
```

### The source contract — every source skill MUST honour this

**1. Emit `canadabuys.notice.Notice` and store through `NoticeStore`.** Do not
invent a parallel record type and do not fork the store. Amendment handling,
`needs_rematch`, and the on-disk layout are already correct; a second
implementation will drift.

**2. Namespace the reference number.** `NoticeStore` keys on `reference` alone
and globs across all months, so two sources emitting `2026-001` will silently
overwrite each other. Prefix every reference with the source id — `on:2026-001`.
`safe_filename()` already handles the colon.

**3. `status` must lowercase to exactly `open` for open notices.**
`Notice.is_open()` compares `status.strip().lower() == "open"`. A portal that
says `Active` or `Ouvert` must be mapped, or stage 1 drops every notice as
`not-open` and the digest is silently empty. Map it in `fields.py`.

**4. `closing` must be timezone-aware.** Stage 1 compares it against a
tz-aware UTC `now`; a naive datetime raises `TypeError` mid-filter. If the
portal publishes naive timestamps, attach the portal's zone explicitly the way
`canadabuys/fields.py` does with `FEED_TZ`, and record in `url-reference.md`
how you determined that zone.

**5. `regions_delivery` must use vocabulary profiles actually contain, or be
left empty.** `_region_ok()` passes when the list is empty and drops when it is
populated but unmatched. Emitting a region string nobody's profile uses is
therefore *worse than emitting nothing*. When unsure, emit nothing.

**6. Unmapped fields are `""` or `[]`, never invented.** A portal with no
`selection_criteria` gets `""`. Do not synthesize a value, and do not put a
placeholder string in a text field — `searchable_text()` concatenates those and
a placeholder becomes a keyword that matches everything.

**7. Absent data must never cause a rejection.** Stage 1 is a recall gate: what
it drops is never judged and never seen again. If your parser cannot determine
a field, leave it empty and let the notice through. This overrides tidiness
every time.

**8. A schema change aborts the run.** Mirror `REQUIRED_COLUMNS` in
`canadabuys/fetch.py`: list the fields whose silent disappearance would gut
matching, and raise on any that is missing. Never loosen that check to make an
error go away — a loud ingest failure is the whole point, because an empty
digest reads exactly like a quiet day and costs a deadline.

**9. Set `source_feed`** to the source id so provenance survives into
`notices/` and the digest.

**10. Ingestion performs no judgment.** No scoring, no relevance filtering, no
LLM in the source package. That separation is what lets a feed change break
ingestion without corrupting anything downstream.

### File specifics

- **`SKILL.md` frontmatter:** `name`, and a `description` written for triggering
  that names the portal and the jurisdiction. Describe *when to use it*, not what
  it does.
- **`SKILL.md` body:** command reference, the rules above restated for this
  source, and a Notes section with the Step 2 quirks.
- **`url-reference.md`:** endpoints, refresh window, the measured code-coverage
  numbers, and every quirk. This is the file a maintainer needs when the portal
  changes — it is the most valuable artifact you produce, more than the parser.
- **`pyproject.toml`:** add the package to `[tool.setuptools.packages.find]`
  `include`, and the CLI to `[project.scripts]`.

---

## Step 4: Test offline, then verify against live data (MANDATORY)

**Tests never hit the network.** Save a real trimmed response from Step 2 as a
fixture in `tests/fixtures/` and drive every test from it. A source skill that
needs the internet to pass its tests is broken; the whole suite must run on a
plane.

Cover at minimum:
1. A fixture row parses into a `Notice` with reference, title, closing, and
   status populated.
2. `closing` is timezone-aware — assert `tzinfo is not None`. This is the trap
   that surfaces as a `TypeError` a week later, in `/rank`, on someone else's
   machine.
3. `is_open()` is true for a notice the portal considers open. Assert on the
   portal's real status string, not on `"open"`.
4. A missing optional field yields `""`/`[]` and the notice still passes stage 1
   — the recall-gate case, and the one worth writing first.
5. A response missing a required field raises, with the field named.
6. Re-ingesting the same fixture is idempotent: `created` then `unchanged`.
7. An amended fixture sets `needs_rematch`.

Then run it for real, once:

```bash
pytest -q
<cli> fetch                 # a single live pull
canadabuys stats            # confirm the notices landed in the shared store
canadabuys filter --profiles profiles
```

Read actual output before declaring success. Check that titles are real text and
not HTML fragments, that closing dates are plausible, and that the filter's
reject histogram is not `not-open: <everything>` — that reads as rule 3 above
having been missed. Keep the live volume to a handful of requests.

Do not proceed until the suite passes offline and one live fetch has been eyeballed.

---

## Step 5: Register and document

1. Add the package to `pyproject.toml` (`packages.find` include, `project.scripts`).
2. Reinstall so the console script exists: `pip install -e ".[dev]"`.
3. Add the source to `AGENTS.md` under Layout, and to the README's file structure.
4. Update `/scrape` (`.claude/commands/scrape.md`) to call the new CLI alongside
   `canadabuys fetch`, and to report its counts separately — a failure in one
   source must not be reported as a quiet day for all of them.
5. The skill auto-triggers from its `SKILL.md` description; no other wiring.

---

## Step 6: Confirm

Present:

> **Source skill `<name>` generated and verified.**
>
> - Package: `<source>/` · Skill: `.agents/skills/<name>/`
> - Offline suite: N tests passing, no network
> - Live check: `<cli> fetch` created N notices; stage-1 pass rate M%
> - Code coverage measured on this feed: X% coded, Y% keyword-only
> - Quirks recorded in `url-reference.md`: <list>
> - Access: <robots.txt / terms finding, personal-use warning if applicable>
>
> Nothing in `matching/`, the rubric, the digest, or `/apply` was changed.

If that last line is not true, say which downstream file you had to touch and
why. It means the normalization is incomplete, and it is worth fixing before the
source is used in anger.

---

## Design principles

- **Investigate, then generate.** Step 2 fetches real responses; Step 4 verifies
  against live data. Parsers are never written from assumptions about a feed.
- **The source contract is what makes sources interchangeable.** Normalize into
  `Notice` and everything downstream is free. Break the contract and you have
  forked the project.
- **Absent data passes.** Every ambiguity in a source skill resolves toward
  letting the notice through, because stage 1's failures are silent and permanent.
- **`url-reference.md` outlives the parser.** Portals change their markup; the
  record of what the feed actually does is what makes the next fix cheap.
- **Access rules are surfaced, not bypassed.** Login-walled portals are declined,
  robots.txt and terms restrictions are reported, restricted sources carry a
  visible personal-use warning.
