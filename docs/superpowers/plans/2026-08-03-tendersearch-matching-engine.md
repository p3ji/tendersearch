# tendersearch Matching Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working tool that ingests CanadaBuys tender notices daily, filters them against per-member consulting profiles, and produces a ranked digest of what to bid on.

**Architecture:** Three isolated layers with one-way data flow. A Python CLI (`canadabuys`) owns all network and file I/O and contains zero judgment logic. A deterministic stage-1 filter (pure functions, no LLM) reduces the notice set. Stage-2 LLM judgment and the digest are driven by markdown skills and slash commands, consuming the CLI's JSON output. Nothing above ingestion touches the network.

**Tech Stack:** Python 3.11+, standard library only where possible (`csv`, `json`, `pathlib`, `dataclasses`, `datetime`), `PyYAML` for profiles, `requests` for fetching, `pytest` for tests. No database. No web framework.

**Scope:** This plan covers spec implementation steps 1–7 (ingestion through scheduling). `/apply` and `/outcome` (steps 8–9) are a separate plan, written after this one lands so it can be built against the matcher's real output rather than a predicted shape. The outcome *schema* is already specified; only its commands are deferred.

**Source spec:** `docs/superpowers/specs/2026-08-03-tendersearch-design.md`. Where this plan and the spec disagree, the spec wins — raise the conflict rather than silently diverging.

## Global Constraints

- **Python 3.11+.** Uses `datetime.fromisoformat` on full ISO datetimes and `tomllib`-era stdlib behaviour.
- **Dependencies limited to:** `requests`, `PyYAML`, `pytest`. Adding any other dependency requires justification in the commit message.
- **No network in tests.** Every test runs offline against fixtures in `tests/fixtures/`. A test that calls out is a bug.
- **`profiles/`, `teams/`, `notices/`, `matches/`, `bids/`, `archives/` are git-ignored.** Only `profiles/_example/` and `teams/_example.yml` are committed. Never commit real profile data — it contains members' resumes and client names.
- **Ingestion contains no judgment.** No scoring, filtering-for-relevance, or LLM calls in `canadabuys/`. Date and status filtering belong to stage 1, not ingestion.
- **Stage 1 errs toward letting notices through.** It is a recall gate; a dropped notice is invisible forever. When a rule is ambiguous, pass the notice.
- **All CSV multi-value fields are `*`-prefixed, newline-separated.** `"*12160000\n*12350000"` → `["12160000", "12350000"]`. Single values carry the prefix too: `"*Canada"` → `["Canada"]`.
- **Notice identity is `referenceNumber`.** Amendments update the existing record in place; they never create a second one.
- **Encoding is `utf-8-sig`.** The feed carries a BOM. Reading with plain `utf-8` corrupts the first column name.
- **Timezone is UTC-0500** for all feed timestamps (they carry no offset).
- **Commit after every task.** Conventional commit prefixes (`feat:`, `test:`, `fix:`, `docs:`, `chore:`).

## File Structure

```
canadabuys/                       # the Python package — all I/O, no judgment
    __init__.py
    fields.py                     # column-name constants + multi-value/date parsing
    notice.py                     # Notice dataclass, from_csv_row, to/from JSON
    store.py                      # notices/ read+upsert, amendment detection
    fetch.py                      # HTTP retrieval of the feeds
    cli.py                        # argparse entry point: fetch / list / stats

matching/                         # stage 1 — pure functions, no I/O, no LLM
    __init__.py
    profile.py                    # Profile/ServiceLine/Team loading + validation
    filter.py                     # the stage-1 rules
    lowbarrier.py                 # low-barrier track classification

tests/
    fixtures/
        open_sample.csv           # ~40 real rows from the live feed
        amended_v0.csv            # a notice at amendment 000
        amended_v1.csv            # same notice at amendment 001, changed closing date
    test_fields.py
    test_notice.py
    test_store.py
    test_profile.py
    test_filter.py
    test_lowbarrier.py

profiles/_example/profile.yml     # committed schema reference, fake data
teams/_example.yml
config.yml
.claude/skills/tender-matcher/SKILL.md      # stage-2 rubric
.claude/commands/{scrape,rank,profile,team}.md
.agents/skills/canadabuys-search/{SKILL.md,url-reference.md}
AGENTS.md, CLAUDE.md, GEMINI.md, README.md, .gitignore, pyproject.toml
```

Split rationale: `canadabuys/` is the only package that changes when the feed changes; `matching/` is the only one that changes when match policy changes. `fields.py` is separate from `notice.py` because column names are feed trivia that will churn, while the `Notice` shape is a stable contract the whole system depends on.

---

### Task 1: Repo scaffold and fixtures

Establishes the skeleton and captures the real-data fixtures every later task tests against. Fixture capture is spec implementation step 1.

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`
- Create: `canadabuys/__init__.py`, `matching/__init__.py`, `tests/__init__.py`
- Create: `tests/fixtures/open_sample.csv`
- Create: `.agents/skills/canadabuys-search/url-reference.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the fixture path `tests/fixtures/open_sample.csv`, used by every later test.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "tendersearch"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.31", "PyYAML>=6.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
canadabuys = "canadabuys.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/

# Real data — never commit. Contains members' resumes and client names.
profiles/*
!profiles/_example/
teams/*
!teams/_example.yml
notices/
matches/
bids/
archives/
outcomes.jsonl
```

- [ ] **Step 3: Create package init files**

Create three empty files: `canadabuys/__init__.py`, `matching/__init__.py`, `tests/__init__.py`.

- [ ] **Step 4: Capture the fixture from the live feed**

Run this once. It downloads the open feed and keeps a 40-row sample with the header intact.

```bash
python -c "
import csv, io, urllib.request
url='https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv'
raw=urllib.request.urlopen(url, timeout=180).read().decode('utf-8-sig')
rows=list(csv.DictReader(io.StringIO(raw)))
keep=rows[:40]
import pathlib; pathlib.Path('tests/fixtures').mkdir(parents=True, exist_ok=True)
with open('tests/fixtures/open_sample.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(keep)
print('wrote', len(keep), 'rows,', len(rows[0]), 'columns')
"
```

Expected: `wrote 40 rows, 68 columns`. If the column count differs from 68, the feed schema changed — stop and reconcile with the spec's column list before continuing.

- [ ] **Step 5: Verify the fixture has the variety later tests need**

```bash
python -c "
import csv
r=list(csv.DictReader(open('tests/fixtures/open_sample.csv',encoding='utf-8-sig')))
print('rows', len(r))
print('with unspsc', sum(1 for x in r if x['unspsc']))
print('no code at all', sum(1 for x in r if not x['unspsc'] and not x['gsin-nibs']))
print('multivalue unspsc', sum(1 for x in r if x['unspsc'].count('*')>1))
"
```

Expected: 40 rows, most with `unspsc`, at least one with no code, at least one multi-value. If "no code at all" is 0, re-capture with more rows (`rows[:80]`) — Task 5 needs a codeless notice to test against.

- [ ] **Step 6: Write `.agents/skills/canadabuys-search/url-reference.md`**

```markdown
# CanadaBuys feeds — reference

Dataset: https://open.canada.ca/data/en/dataset/6abd20d4-7a1c-4b38-baa2-9525d0bb2fd2
Field docs: https://donnees-data.tpsgc-pwgsc.gc.ca/ba2/ac-cb/soutien-support-eng.html

| Feed | URL | Refresh (UTC-0500) |
|---|---|---|
| New | `https://canadabuys.canada.ca/opendata/pub/newTenderNotice-nouvelAvisAppelOffres.csv` | every 2h, 06:15–22:15 |
| Open | `https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv` | daily, 07:00–08:30 |
| FY archive | `https://canadabuys.canada.ca/opendata/pub/<FY>-TenderNotice-AvisAppelOffres.csv` | daily |
| Legacy 2009–2022 | `https://canadabuys.canada.ca/opendata/pub/2009-2022-tenderNoticeHistorical-AvisAppelOffresHistorique.csv` | static |

`openTenderNotice` is the authority on what is open and drives the daily run.

## Gotchas — measured 2026-08-03 against the live open feed (896 notices)

1. **Encoding is `utf-8-sig`.** The file has a BOM; plain `utf-8` corrupts the first column name.
2. **Multi-value fields are `*`-prefixed, newline-separated:** `"*12160000\n*12350000"`.
   Single values keep the prefix: `"*Canada"`.
3. **No estimated-value column exists.** Do not design around contract value.
4. **Code coverage is partial:** `unspsc` on 757/896 (84%), `gsin` on 39/896 (4%),
   **no code at all on 139/896 (15%)**. Keyword matching is the only way to see that 15%.
5. **`noticeType` is empty on 115/896 (13%).** Low-barrier classification must not assume it.
6. **Notices are amended in place.** Identity is `referenceNumber`; `amendmentNumber` is a
   zero-padded string (`"000"`, `"001"`) — compare as int, not string.
7. **Closing dates are naive ISO datetimes** (`2026-08-19T14:00:00`) in UTC-0500.
8. **Volume is modest** — 896 open, ~3 new/day. Stage-2 cost is not a constraint at this scale.
```

- [ ] **Step 7: Write `README.md`**

```markdown
# tendersearch

Finds Canadian federal tender opportunities matching a small consulting group's
capabilities, and helps decide which are worth bidding.

See `docs/superpowers/specs/2026-08-03-tendersearch-design.md` for the design.

## Setup

    python -m venv .venv && .venv/Scripts/activate   # Windows
    pip install -e ".[dev]"

## Use

    canadabuys fetch          # pull the latest open notices
    /profile <member>         # build or update a member profile (in Claude Code)
    /rank                     # filter, judge, and write today's digest

Real profiles live in `profiles/<member>/` and are git-ignored.
See `profiles/_example/profile.yml` for the schema.
```

- [ ] **Step 8: Write `AGENTS.md` and the pointer files**

`AGENTS.md`:

```markdown
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
```

`CLAUDE.md` and `GEMINI.md` both contain exactly: `@AGENTS.md`

- [ ] **Step 9: Verify the scaffold installs**

Run: `pip install -e ".[dev]" && pytest --collect-only`
Expected: install succeeds; pytest reports "no tests ran" (there are none yet). An import error means a package `__init__.py` is missing.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml .gitignore README.md AGENTS.md CLAUDE.md GEMINI.md canadabuys/ matching/ tests/ .agents/
git commit -m "chore: scaffold repo, capture live feed fixture"
```

---

### Task 2: Field parsing

The feed's two format quirks — `*`-prefixed multi-values and naive timestamps — isolated so nothing else has to know about them.

**Files:**
- Create: `canadabuys/fields.py`
- Test: `tests/test_fields.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `split_multi(raw: str | None) -> list[str]`
  - `parse_date(raw: str | None) -> datetime.date | None`
  - `parse_datetime(raw: str | None) -> datetime.datetime | None` — returns tz-aware, UTC-0500
  - `FEED_TZ: datetime.timezone`
  - Column-name constants (`COL_TITLE`, `COL_REF`, etc.)

- [ ] **Step 1: Write the failing test**

`tests/test_fields.py`:

```python
import datetime
import pytest
from canadabuys.fields import split_multi, parse_date, parse_datetime, FEED_TZ


def test_split_multi_single_value_strips_star():
    assert split_multi("*Canada") == ["Canada"]


def test_split_multi_newline_separated():
    assert split_multi("*12160000\n*12350000") == ["12160000", "12350000"]


def test_split_multi_handles_carriage_returns():
    assert split_multi("*A\r\n*B") == ["A", "B"]


def test_split_multi_empty_is_empty_list():
    assert split_multi("") == []
    assert split_multi(None) == []


def test_split_multi_value_without_star_still_parsed():
    # Defensive: the feed always prefixes, but a missing star must not lose data.
    assert split_multi("Canada") == ["Canada"]


def test_parse_date():
    assert parse_date("2026-08-03") == datetime.date(2026, 8, 3)


def test_parse_date_empty_is_none():
    assert parse_date("") is None
    assert parse_date(None) is None


def test_parse_datetime_attaches_feed_timezone():
    got = parse_datetime("2026-08-19T14:00:00")
    assert got == datetime.datetime(2026, 8, 19, 14, 0, tzinfo=FEED_TZ)
    assert got.tzinfo is not None, "naive datetimes cause wrong deadline math"


def test_parse_datetime_empty_is_none():
    assert parse_datetime("") is None


def test_parse_datetime_malformed_raises():
    with pytest.raises(ValueError):
        parse_datetime("19 August 2026")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_fields.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'canadabuys.fields'`

- [ ] **Step 3: Write the implementation**

`canadabuys/fields.py`:

```python
"""Parsing for CanadaBuys CSV field formats.

Isolated here because these are feed trivia that will churn; the rest of the
system should never need to know about star prefixes or missing timezones.
"""
import datetime

# The feed publishes naive timestamps in UTC-0500. See url-reference.md.
FEED_TZ = datetime.timezone(datetime.timedelta(hours=-5))

COL_TITLE = "title-titre-eng"
COL_REF = "referenceNumber-numeroReference"
COL_AMENDMENT = "amendmentNumber-numeroModification"
COL_SOLICITATION = "solicitationNumber-numeroSollicitation"
COL_PUBLISHED = "publicationDate-datePublication"
COL_CLOSING = "tenderClosingDate-appelOffresDateCloture"
COL_AMENDED_DATE = "amendmentDate-dateModification"
COL_STATUS = "tenderStatus-appelOffresStatut-eng"
COL_GSIN = "gsin-nibs"
COL_GSIN_DESC = "gsinDescription-nibsDescription-eng"
COL_UNSPSC = "unspsc"
COL_UNSPSC_DESC = "unspscDescription-eng"
COL_CATEGORY = "procurementCategory-categorieApprovisionnement"
COL_NOTICE_TYPE = "noticeType-avisType-eng"
COL_PROC_METHOD = "procurementMethod-methodeApprovisionnement-eng"
COL_SELECTION = "selectionCriteria-criteresSelection-eng"
COL_REGIONS_DELIVERY = "regionsOfDelivery-regionsLivraison-eng"
COL_REGIONS_OPPORTUNITY = "regionsOfOpportunity-regionAppelOffres-eng"
COL_ENTITY = "contractingEntityName-nomEntitContractante-eng"
COL_END_USER = "endUserEntitiesName-nomEntitesUtilisateurFinal-eng"
COL_DESCRIPTION = "tenderDescription-descriptionAppelOffres-eng"
COL_DESCRIPTION_FR = "tenderDescription-descriptionAppelOffres-fra"
COL_NOTICE_URL = "noticeURL-URLavis-eng"
COL_ATTACHMENT = "attachment-piecesJointes-eng"
COL_CONTACT_NAME = "contactInfoName-informationsContactNom"
COL_CONTACT_EMAIL = "contactInfoEmail-informationsContactCourriel"


def split_multi(raw: str | None) -> list[str]:
    """Split a `*`-prefixed, newline-separated multi-value field.

    "*12160000\\n*12350000" -> ["12160000", "12350000"]
    "*Canada"               -> ["Canada"]
    """
    if not raw:
        return []
    parts = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return [p.lstrip("*").strip() for p in parts if p.strip().strip("*")]


def parse_date(raw: str | None) -> datetime.date | None:
    if not raw or not raw.strip():
        return None
    return datetime.date.fromisoformat(raw.strip())


def parse_datetime(raw: str | None) -> datetime.datetime | None:
    """Parse a naive feed timestamp and attach the feed's timezone.

    Returning tz-aware values is deliberate: deadline arithmetic against a
    naive datetime silently computes in local time and can be hours wrong.
    """
    if not raw or not raw.strip():
        return None
    return datetime.datetime.fromisoformat(raw.strip()).replace(tzinfo=FEED_TZ)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_fields.py -v`
Expected: all 10 PASS.

- [ ] **Step 5: Verify the constants match the real fixture**

```bash
python -c "
import csv
from canadabuys import fields
cols=set(next(csv.reader(open('tests/fixtures/open_sample.csv',encoding='utf-8-sig'))))
missing=[v for k,v in vars(fields).items() if k.startswith('COL_') and v not in cols]
print('MISSING:', missing or 'none')
"
```

Expected: `MISSING: none`. Any miss is a typo in a column constant — fix before proceeding, because a wrong constant reads as a silently empty field rather than an error.

- [ ] **Step 6: Commit**

```bash
git add canadabuys/fields.py tests/test_fields.py
git commit -m "feat: parse CanadaBuys field formats (star-prefixed multi-values, feed timezone)"
```

---

### Task 3: The Notice model

The stable contract every later layer depends on.

**Files:**
- Create: `canadabuys/notice.py`
- Test: `tests/test_notice.py`

**Interfaces:**
- Consumes: everything from `canadabuys.fields`.
- Produces:
  - `Notice` dataclass with fields: `reference` (str), `amendment` (int), `solicitation` (str), `title` (str), `entity` (str), `end_user` (str), `category` (list[str]), `notice_type` (str), `procurement_method` (str), `unspsc` (list[str]), `unspsc_desc` (list[str]), `gsin` (list[str]), `gsin_desc` (list[str]), `selection_criteria` (str), `regions_delivery` (list[str]), `regions_opportunity` (list[str]), `published` (date|None), `closing` (datetime|None), `amended_date` (date|None), `status` (str), `description` (str), `description_fr` (str), `notice_url` (str), `attachments` (list[str]), `contact_name` (str), `contact_email` (str), `first_seen` (str), `last_updated` (str), `source_feed` (str), `needs_rematch` (bool)
  - `Notice.from_csv_row(row: dict, source_feed: str, now_iso: str) -> Notice`
  - `Notice.to_dict() -> dict` / `Notice.from_dict(d: dict) -> Notice`
  - `Notice.searchable_text() -> str` — title + description + selection criteria + code descriptions, lowercased, for keyword matching
  - `Notice.is_open() -> bool`

- [ ] **Step 1: Write the failing test**

`tests/test_notice.py`:

```python
import csv
import datetime
from canadabuys.notice import Notice

FIXTURE = "tests/fixtures/open_sample.csv"
NOW = "2026-08-03T12:00:00+00:00"


def load_rows():
    with open(FIXTURE, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_parses_every_fixture_row_without_error():
    rows = load_rows()
    notices = [Notice.from_csv_row(r, "open", NOW) for r in rows]
    assert len(notices) == len(rows)
    assert all(n.reference for n in notices), "every notice must have a reference number"


def test_amendment_is_an_int_not_a_string():
    # "000" and "001" must compare numerically; string compare breaks at "010".
    n = Notice.from_csv_row(
        {**load_rows()[0], "amendmentNumber-numeroModification": "010"}, "open", NOW
    )
    assert n.amendment == 10


def test_missing_amendment_defaults_to_zero():
    n = Notice.from_csv_row(
        {**load_rows()[0], "amendmentNumber-numeroModification": ""}, "open", NOW
    )
    assert n.amendment == 0


def test_multivalue_fields_are_lists():
    n = Notice.from_csv_row(
        {**load_rows()[0], "unspsc": "*12160000\n*12350000"}, "open", NOW
    )
    assert n.unspsc == ["12160000", "12350000"]


def test_roundtrip_through_dict_is_lossless():
    original = Notice.from_csv_row(load_rows()[0], "open", NOW)
    restored = Notice.from_dict(original.to_dict())
    assert restored == original


def test_to_dict_is_json_serializable():
    import json
    d = Notice.from_csv_row(load_rows()[0], "open", NOW).to_dict()
    json.loads(json.dumps(d))  # raises if a date leaked through unserialized


def test_searchable_text_includes_title_description_and_code_descriptions():
    n = Notice.from_csv_row(
        {
            **load_rows()[0],
            "title-titre-eng": "Advisory Services",
            "tenderDescription-descriptionAppelOffres-eng": "Organizational readiness",
            "selectionCriteria-criteresSelection-eng": "Lowest price",
            "unspscDescription-eng": "*Management consulting",
        },
        "open",
        NOW,
    )
    text = n.searchable_text()
    assert "advisory services" in text
    assert "organizational readiness" in text
    assert "lowest price" in text
    assert "management consulting" in text
    assert text == text.lower(), "searchable text must be lowercased for matching"


def test_is_open_reflects_status():
    row = load_rows()[0]
    assert Notice.from_csv_row(
        {**row, "tenderStatus-appelOffresStatut-eng": "Open"}, "open", NOW
    ).is_open()
    for closed in ("Expired", "Cancelled", ""):
        assert not Notice.from_csv_row(
            {**row, "tenderStatus-appelOffresStatut-eng": closed}, "open", NOW
        ).is_open()


def test_closing_datetime_is_timezone_aware():
    n = Notice.from_csv_row(
        {**load_rows()[0], "tenderClosingDate-appelOffresDateCloture": "2026-08-19T14:00:00"},
        "open",
        NOW,
    )
    assert n.closing.tzinfo is not None
    assert n.closing.hour == 14


def test_first_seen_and_source_feed_recorded():
    n = Notice.from_csv_row(load_rows()[0], "open", NOW)
    assert n.first_seen == NOW
    assert n.last_updated == NOW
    assert n.source_feed == "open"
    assert n.needs_rematch is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_notice.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'canadabuys.notice'`

- [ ] **Step 3: Write the implementation**

`canadabuys/notice.py`:

```python
"""The Notice model — the stable contract the rest of the system depends on.

Ingestion normalizes the feed into this shape once; nothing downstream reads
raw CSV columns.
"""
from __future__ import annotations

import dataclasses
import datetime

from canadabuys import fields as F

OPEN_STATUS = "open"


@dataclasses.dataclass(eq=True)
class Notice:
    reference: str
    amendment: int
    solicitation: str
    title: str
    entity: str
    end_user: str
    category: list[str]
    notice_type: str
    procurement_method: str
    unspsc: list[str]
    unspsc_desc: list[str]
    gsin: list[str]
    gsin_desc: list[str]
    selection_criteria: str
    regions_delivery: list[str]
    regions_opportunity: list[str]
    published: datetime.date | None
    closing: datetime.datetime | None
    amended_date: datetime.date | None
    status: str
    description: str
    description_fr: str
    notice_url: str
    attachments: list[str]
    contact_name: str
    contact_email: str
    first_seen: str
    last_updated: str
    source_feed: str
    needs_rematch: bool = False

    @classmethod
    def from_csv_row(cls, row: dict, source_feed: str, now_iso: str) -> "Notice":
        def txt(col: str) -> str:
            return (row.get(col) or "").strip()

        raw_amendment = txt(F.COL_AMENDMENT)
        return cls(
            reference=txt(F.COL_REF),
            # Zero-padded in the feed ("000"); int so "010" > "009" compares right.
            amendment=int(raw_amendment) if raw_amendment.isdigit() else 0,
            solicitation=txt(F.COL_SOLICITATION),
            title=txt(F.COL_TITLE),
            entity=txt(F.COL_ENTITY),
            end_user=txt(F.COL_END_USER),
            category=F.split_multi(row.get(F.COL_CATEGORY)),
            notice_type=txt(F.COL_NOTICE_TYPE),
            procurement_method=txt(F.COL_PROC_METHOD),
            unspsc=F.split_multi(row.get(F.COL_UNSPSC)),
            unspsc_desc=F.split_multi(row.get(F.COL_UNSPSC_DESC)),
            gsin=F.split_multi(row.get(F.COL_GSIN)),
            gsin_desc=F.split_multi(row.get(F.COL_GSIN_DESC)),
            selection_criteria=txt(F.COL_SELECTION),
            regions_delivery=F.split_multi(row.get(F.COL_REGIONS_DELIVERY)),
            regions_opportunity=F.split_multi(row.get(F.COL_REGIONS_OPPORTUNITY)),
            published=F.parse_date(row.get(F.COL_PUBLISHED)),
            closing=F.parse_datetime(row.get(F.COL_CLOSING)),
            amended_date=F.parse_date(row.get(F.COL_AMENDED_DATE)),
            status=txt(F.COL_STATUS),
            description=txt(F.COL_DESCRIPTION),
            description_fr=txt(F.COL_DESCRIPTION_FR),
            notice_url=txt(F.COL_NOTICE_URL),
            attachments=F.split_multi(row.get(F.COL_ATTACHMENT)),
            contact_name=txt(F.COL_CONTACT_NAME),
            contact_email=txt(F.COL_CONTACT_EMAIL),
            first_seen=now_iso,
            last_updated=now_iso,
            source_feed=source_feed,
            needs_rematch=False,
        )

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["published"] = self.published.isoformat() if self.published else None
        d["closing"] = self.closing.isoformat() if self.closing else None
        d["amended_date"] = self.amended_date.isoformat() if self.amended_date else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Notice":
        d = dict(d)
        d["published"] = datetime.date.fromisoformat(d["published"]) if d["published"] else None
        d["closing"] = (
            datetime.datetime.fromisoformat(d["closing"]) if d["closing"] else None
        )
        d["amended_date"] = (
            datetime.date.fromisoformat(d["amended_date"]) if d["amended_date"] else None
        )
        return cls(**d)

    def searchable_text(self) -> str:
        """All free text a keyword match should search, lowercased.

        Includes code *descriptions* because 15% of notices carry no code at
        all and many that do use codes the profile does not list.
        """
        parts = [
            self.title,
            self.description,
            self.selection_criteria,
            " ".join(self.unspsc_desc),
            " ".join(self.gsin_desc),
        ]
        return " ".join(p for p in parts if p).lower()

    def is_open(self) -> bool:
        return self.status.strip().lower() == OPEN_STATUS
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_notice.py -v`
Expected: all 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add canadabuys/notice.py tests/test_notice.py
git commit -m "feat: add Notice model with lossless JSON roundtrip"
```

---

### Task 4: Notice store with amendment handling

Persistence and the amendment logic the spec calls a correctness requirement: a stale verdict surviving an amendment is a bug, because amendments change criteria and deadlines.

**Files:**
- Create: `canadabuys/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `Notice` from `canadabuys.notice`.
- Produces:
  - `NoticeStore(root: pathlib.Path)`
  - `.path_for(reference: str, first_seen: str) -> Path` — `notices/<YYYY-MM>/<reference>.json`, month taken from the `first_seen` ISO timestamp
  - `.load(reference: str) -> Notice | None`
  - `.save(notice: Notice) -> None`
  - `.upsert(notice: Notice, now_iso: str) -> UpsertResult`
  - `.all() -> Iterator[Notice]`
  - `UpsertResult` dataclass: `.action` (`"created"` | `"amended"` | `"unchanged"`), `.needs_rematch` (bool), `.changed_fields` (list[str])
  - `REMATCH_FIELDS: tuple[str, ...]` = `("closing", "description", "selection_criteria")`

- [ ] **Step 1: Write the failing test**

`tests/test_store.py`:

```python
import csv
import dataclasses
import datetime
import pytest
from canadabuys.notice import Notice
from canadabuys.store import NoticeStore, REMATCH_FIELDS

T0 = "2026-08-01T09:00:00+00:00"
T1 = "2026-08-05T09:00:00+00:00"


def base_row():
    with open("tests/fixtures/open_sample.csv", encoding="utf-8-sig", newline="") as f:
        return next(csv.DictReader(f))


def make(**overrides) -> Notice:
    row = {**base_row(), **overrides}
    return Notice.from_csv_row(row, "open", overrides.pop("_now", T0))


@pytest.fixture
def store(tmp_path):
    return NoticeStore(tmp_path)


def test_save_then_load_roundtrip(store):
    n = make()
    store.save(n)
    assert store.load(n.reference) == n


def test_load_missing_returns_none(store):
    assert store.load("cb-does-not-exist") is None


def test_upsert_new_notice_reports_created(store):
    result = store.upsert(make(), T0)
    assert result.action == "created"
    assert result.needs_rematch is True, "a new notice has never been matched"


def test_upsert_identical_notice_is_unchanged(store):
    n = make()
    store.upsert(n, T0)
    result = store.upsert(n, T1)
    assert result.action == "unchanged"
    assert result.needs_rematch is False


def test_reingesting_does_not_create_duplicates(store):
    n = make()
    store.upsert(n, T0)
    store.upsert(n, T1)
    assert len(list(store.all())) == 1


def test_amendment_updates_in_place_not_as_new_file(store):
    store.upsert(make(**{"amendmentNumber-numeroModification": "000"}), T0)
    store.upsert(make(**{"amendmentNumber-numeroModification": "001"}), T1)
    all_notices = list(store.all())
    assert len(all_notices) == 1, "amendment must update the existing record"
    assert all_notices[0].amendment == 1


def test_amendment_changing_closing_date_sets_needs_rematch(store):
    store.upsert(make(**{
        "amendmentNumber-numeroModification": "000",
        "tenderClosingDate-appelOffresDateCloture": "2026-09-01T14:00:00",
    }), T0)
    result = store.upsert(make(**{
        "amendmentNumber-numeroModification": "001",
        "tenderClosingDate-appelOffresDateCloture": "2026-09-15T14:00:00",
    }), T1)
    assert result.action == "amended"
    assert result.needs_rematch is True
    assert "closing" in result.changed_fields
    assert store.load(result_ref(store)).needs_rematch is True


def result_ref(store):
    return next(store.all()).reference


def test_amendment_changing_description_sets_needs_rematch(store):
    store.upsert(make(**{
        "amendmentNumber-numeroModification": "000",
        "tenderDescription-descriptionAppelOffres-eng": "original scope",
    }), T0)
    result = store.upsert(make(**{
        "amendmentNumber-numeroModification": "001",
        "tenderDescription-descriptionAppelOffres-eng": "expanded scope",
    }), T1)
    assert result.needs_rematch is True
    assert "description" in result.changed_fields


def test_amendment_changing_only_contact_does_not_force_rematch(store):
    store.upsert(make(**{
        "amendmentNumber-numeroModification": "000",
        "contactInfoName-informationsContactNom": "A. Smith",
    }), T0)
    result = store.upsert(make(**{
        "amendmentNumber-numeroModification": "001",
        "contactInfoName-informationsContactNom": "B. Jones",
    }), T1)
    assert result.action == "amended"
    assert result.needs_rematch is False, "a contact change does not invalidate a verdict"


def test_older_amendment_does_not_overwrite_newer(store):
    store.upsert(make(**{"amendmentNumber-numeroModification": "002"}), T0)
    result = store.upsert(make(**{"amendmentNumber-numeroModification": "001"}), T1)
    assert result.action == "unchanged"
    assert next(store.all()).amendment == 2, "must not regress to an older amendment"


def test_first_seen_preserved_across_amendment(store):
    store.upsert(make(**{"amendmentNumber-numeroModification": "000"}), T0)
    store.upsert(make(**{"amendmentNumber-numeroModification": "001"}), T1)
    n = next(store.all())
    assert n.first_seen == T0, "first_seen records discovery, not last touch"
    assert n.last_updated == T1


def test_rematch_fields_are_the_three_the_spec_names():
    assert set(REMATCH_FIELDS) == {"closing", "description", "selection_criteria"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'canadabuys.store'`

- [ ] **Step 3: Write the implementation**

`canadabuys/store.py`:

```python
"""On-disk notice storage with amendment-aware upsert.

Notices are identified by reference number alone. An amendment updates the
existing record; it never creates a second one. When an amendment changes a
field that could change a verdict, the notice is flagged for re-matching --
keeping a stale verdict after criteria or deadlines move is a correctness bug.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
from typing import Iterator

from canadabuys.notice import Notice

# Changes to these invalidate any existing verdict.
REMATCH_FIELDS: tuple[str, ...] = ("closing", "description", "selection_criteria")


@dataclasses.dataclass
class UpsertResult:
    reference: str
    action: str  # "created" | "amended" | "unchanged"
    needs_rematch: bool
    changed_fields: list[str]


class NoticeStore:
    def __init__(self, root: pathlib.Path):
        self.root = pathlib.Path(root)

    def path_for(self, reference: str, first_seen: str) -> pathlib.Path:
        month = first_seen[:7]  # "2026-08"
        return self.root / month / f"{reference}.json"

    def _find(self, reference: str) -> pathlib.Path | None:
        matches = sorted(self.root.glob(f"*/{reference}.json"))
        return matches[0] if matches else None

    def load(self, reference: str) -> Notice | None:
        path = self._find(reference)
        if path is None:
            return None
        return Notice.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, notice: Notice) -> None:
        path = self.path_for(notice.reference, notice.first_seen)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(notice.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def upsert(self, incoming: Notice, now_iso: str) -> UpsertResult:
        existing = self.load(incoming.reference)

        if existing is None:
            incoming.needs_rematch = True  # never judged
            self.save(incoming)
            return UpsertResult(incoming.reference, "created", True, [])

        if incoming.amendment < existing.amendment:
            # Feeds can carry an older revision; never regress.
            return UpsertResult(incoming.reference, "unchanged", False, [])

        changed = [
            f
            for f in REMATCH_FIELDS
            if getattr(incoming, f) != getattr(existing, f)
        ]
        any_change = changed or incoming.amendment != existing.amendment or (
            _comparable(incoming) != _comparable(existing)
        )

        if not any_change:
            return UpsertResult(incoming.reference, "unchanged", False, [])

        incoming.first_seen = existing.first_seen  # discovery time, not last touch
        incoming.last_updated = now_iso
        incoming.needs_rematch = existing.needs_rematch or bool(changed)
        self.save(incoming)
        action = "amended" if incoming.amendment != existing.amendment else "updated"
        return UpsertResult(incoming.reference, action, bool(changed), changed)

    def all(self) -> Iterator[Notice]:
        for path in sorted(self.root.glob("*/*.json")):
            yield Notice.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _comparable(n: Notice) -> dict:
    """Notice content ignoring local bookkeeping fields."""
    d = n.to_dict()
    for k in ("first_seen", "last_updated", "source_feed", "needs_rematch"):
        d.pop(k, None)
    return d
```

Note: `test_amendment_changing_only_contact_does_not_force_rematch` expects `action == "amended"` — the implementation returns `"amended"` whenever the amendment number changed, which that test does. Confirm this passes; if the returned action is `"updated"`, the amendment number was not actually different in the test data and the test needs the amendment override checked.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_store.py -v`
Expected: all 13 PASS. If `test_older_amendment_does_not_overwrite_newer` fails, `amendment` is being compared as a string — return to Task 3.

- [ ] **Step 5: Commit**

```bash
git add canadabuys/store.py tests/test_store.py
git commit -m "feat: notice store with amendment-aware upsert and rematch flagging"
```

---

### Task 5: Fetch and CLI

Puts real notices on disk. First point the tool touches the network.

**Files:**
- Create: `canadabuys/fetch.py`, `canadabuys/cli.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: `NoticeStore`, `Notice`.
- Produces:
  - `FEEDS: dict[str, str]` — keys `"open"`, `"new"`
  - `parse_csv_bytes(raw: bytes, source_feed: str, now_iso: str) -> list[Notice]`
  - `fetch_feed(name: str, timeout: int = 180) -> bytes` — network
  - `ingest(raw: bytes, store: NoticeStore, source_feed: str, now_iso: str) -> IngestSummary`
  - `IngestSummary` dataclass: `.created`, `.amended`, `.unchanged` (ints), `.rematch_needed` (list[str])
  - CLI: `canadabuys fetch [--feed open|new] [--file PATH]`, `canadabuys stats`

- [ ] **Step 1: Write the failing test**

`tests/test_fetch.py`:

```python
import pathlib
import pytest
from canadabuys.fetch import parse_csv_bytes, ingest, FEEDS
from canadabuys.store import NoticeStore

NOW = "2026-08-03T12:00:00+00:00"
LATER = "2026-08-04T12:00:00+00:00"
FIXTURE = pathlib.Path("tests/fixtures/open_sample.csv")


@pytest.fixture
def raw():
    return FIXTURE.read_bytes()


def test_feeds_are_https_canadabuys_urls():
    assert set(FEEDS) == {"open", "new"}
    assert all(u.startswith("https://canadabuys.canada.ca/") for u in FEEDS.values())


def test_parse_handles_the_utf8_bom(raw):
    notices = parse_csv_bytes(raw, "open", NOW)
    assert len(notices) == 40
    # A BOM read as utf-8 corrupts the first column name, emptying every title.
    assert any(n.title for n in notices)
    assert all(n.reference for n in notices)


def test_ingest_creates_all_on_first_run(raw, tmp_path):
    summary = ingest(raw, NoticeStore(tmp_path), "open", NOW)
    assert summary.created == 40
    assert summary.amended == 0
    assert len(summary.rematch_needed) == 40


def test_ingest_is_idempotent(raw, tmp_path):
    store = NoticeStore(tmp_path)
    ingest(raw, store, "open", NOW)
    second = ingest(raw, store, "open", LATER)
    assert second.created == 0
    assert second.unchanged == 40
    assert len(list(store.all())) == 40


def test_malformed_csv_raises_rather_than_writing_nothing(tmp_path):
    # Silently writing an empty result is the one unacceptable failure --
    # it looks like a quiet day and costs a deadline.
    with pytest.raises(ValueError, match="expected column"):
        ingest(b"not,a,tender,feed\n1,2,3,4\n", NoticeStore(tmp_path), "open", NOW)


def test_empty_feed_raises(tmp_path):
    with pytest.raises(ValueError):
        ingest(b"", NoticeStore(tmp_path), "open", NOW)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_fetch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'canadabuys.fetch'`

- [ ] **Step 3: Write `canadabuys/fetch.py`**

```python
"""Feed retrieval and ingestion. The only module that touches the network."""
from __future__ import annotations

import csv
import dataclasses
import io
import pathlib

import requests

from canadabuys import fields as F
from canadabuys.notice import Notice
from canadabuys.store import NoticeStore

FEEDS = {
    "open": "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv",
    "new": "https://canadabuys.canada.ca/opendata/pub/newTenderNotice-nouvelAvisAppelOffres.csv",
}

# If these are absent the file is not a tender feed. Fail loudly rather than
# writing an empty digest that reads as "nothing today".
REQUIRED_COLUMNS = (F.COL_REF, F.COL_TITLE, F.COL_CLOSING, F.COL_STATUS)


@dataclasses.dataclass
class IngestSummary:
    created: int = 0
    amended: int = 0
    unchanged: int = 0
    rematch_needed: list[str] = dataclasses.field(default_factory=list)


def fetch_feed(name: str, timeout: int = 180) -> bytes:
    response = requests.get(FEEDS[name], timeout=timeout)
    response.raise_for_status()
    return response.content


def parse_csv_bytes(raw: bytes, source_feed: str, now_iso: str) -> list[Notice]:
    text = raw.decode("utf-8-sig")  # the feed carries a BOM
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("feed is empty: no CSV header found")
    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise ValueError(
            f"feed schema changed: expected column(s) {missing} not found. "
            f"Refusing to ingest. See .agents/skills/canadabuys-search/url-reference.md"
        )
    return [Notice.from_csv_row(row, source_feed, now_iso) for row in reader]


def ingest(raw: bytes, store: NoticeStore, source_feed: str, now_iso: str) -> IngestSummary:
    summary = IngestSummary()
    for notice in parse_csv_bytes(raw, source_feed, now_iso):
        result = store.upsert(notice, now_iso)
        if result.action == "created":
            summary.created += 1
        elif result.action == "unchanged":
            summary.unchanged += 1
        else:
            summary.amended += 1
        if result.needs_rematch:
            summary.rematch_needed.append(result.reference)
    return summary
```

- [ ] **Step 4: Write `canadabuys/cli.py`**

```python
"""Command-line entry point."""
from __future__ import annotations

import argparse
import datetime
import pathlib
import sys

from canadabuys.fetch import FEEDS, fetch_feed, ingest
from canadabuys.store import NoticeStore


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def cmd_fetch(args) -> int:
    store = NoticeStore(pathlib.Path(args.notices))
    if args.file:
        raw = pathlib.Path(args.file).read_bytes()
    else:
        raw = fetch_feed(args.feed)
    try:
        summary = ingest(raw, store, args.feed, _now_iso())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"created={summary.created} amended={summary.amended} "
        f"unchanged={summary.unchanged} needs_rematch={len(summary.rematch_needed)}"
    )
    return 0


def cmd_stats(args) -> int:
    notices = list(NoticeStore(pathlib.Path(args.notices)).all())
    print(f"stored: {len(notices)}")
    print(f"open: {sum(1 for n in notices if n.is_open())}")
    print(f"needing rematch: {sum(1 for n in notices if n.needs_rematch)}")
    print(f"with no procurement code: {sum(1 for n in notices if not n.unspsc and not n.gsin)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="canadabuys")
    parser.add_argument("--notices", default="notices", help="notice store root")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="pull a feed into the notice store")
    p_fetch.add_argument("--feed", choices=sorted(FEEDS), default="open")
    p_fetch.add_argument("--file", help="ingest a local CSV instead of fetching")
    p_fetch.set_defaults(func=cmd_fetch)

    p_stats = sub.add_parser("stats", help="summarize the notice store")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_fetch.py -v`
Expected: all 6 PASS.

- [ ] **Step 6: Verify the CLI works offline against the fixture**

```bash
canadabuys --notices .tmp-notices fetch --file tests/fixtures/open_sample.csv
canadabuys --notices .tmp-notices stats
```

Expected: `created=40 amended=0 unchanged=0 needs_rematch=40`, then a stats summary.
Then remove the scratch dir: `rm -rf .tmp-notices`

- [ ] **Step 7: Run one live fetch to confirm the network path**

```bash
canadabuys fetch --feed open
```

Expected: `created=<~900> ...`. This is the only live-network step in the plan. If it fails, the feed URL or schema changed — check `url-reference.md`.

- [ ] **Step 8: Commit**

```bash
git add canadabuys/fetch.py canadabuys/cli.py tests/test_fetch.py
git commit -m "feat: fetch and ingest CanadaBuys feeds via CLI"
```

---

### Task 6: Profile and team models

**Files:**
- Create: `matching/profile.py`, `profiles/_example/profile.yml`, `teams/_example.yml`, `config.yml`
- Test: `tests/test_profile.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `ServiceLine` dataclass: `.label`, `.naics` (list[str]), `.unspsc` (list[str]), `.gsin` (list[str]), `.keywords` (list[str])
  - `Profile` dataclass: `.member_id`, `.name`, `.clearance`, `.service_lines` (list[ServiceLine]), `.skills`, `.certifications`, `.past_performance` (list, **may be empty**), `.regions` (list[str]), `.vehicles`, `.evidence` (dict)
  - `Team` dataclass: `.team_id`, `.name`, `.members` (list[str]), `.prime` (str)
  - `load_profile(path) -> Profile`, `load_profiles(root) -> list[Profile]`
  - `load_team(path, profiles) -> Team`
  - `Team.service_lines(profiles) -> list[ServiceLine]` — union across members
  - `Team.regions(profiles) -> set[str]`
  - `ProfileError` exception

- [ ] **Step 1: Write the failing test**

`tests/test_profile.py`:

```python
import pytest
import yaml
from matching.profile import (
    Profile, ServiceLine, Team, load_profile, load_profiles, load_team, ProfileError
)

MINIMAL = {
    "member_id": "alex",
    "name": "Alex Chen",
    "clearance": {"level": "Reliability", "status": "active"},
    "service_lines": [
        {"label": "Data engineering", "unspsc": ["81111500"], "gsin": [],
         "naics": ["541512"], "keywords": ["data pipeline", "etl"]}
    ],
    "skills": [{"name": "Python", "depth": "expert", "years": 8}],
    "certifications": [],
    "past_performance": [],
    "regions": ["Ontario", "Canada"],
    "vehicles": [],
    "evidence": {"resume": "evidence/alex-resume.pdf"},
}


def write(tmp_path, data, name="profile.yml"):
    d = tmp_path / data["member_id"]
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


def test_loads_a_minimal_profile(tmp_path):
    p = load_profile(write(tmp_path, MINIMAL))
    assert p.member_id == "alex"
    assert p.service_lines[0].keywords == ["data pipeline", "etl"]


def test_empty_past_performance_is_valid(tmp_path):
    # The binding constraint for this group. An empty list must never be an error.
    p = load_profile(write(tmp_path, {**MINIMAL, "past_performance": []}))
    assert p.past_performance == []


def test_missing_required_field_raises_with_a_useful_message(tmp_path):
    bad = {k: v for k, v in MINIMAL.items() if k != "service_lines"}
    with pytest.raises(ProfileError, match="service_lines"):
        load_profile(write(tmp_path, bad))


def test_service_line_with_no_keywords_and_no_codes_is_rejected(tmp_path):
    # Such a line can never match anything; silently useless is worse than loud.
    bad = {**MINIMAL, "service_lines": [
        {"label": "Vague", "unspsc": [], "gsin": [], "naics": [], "keywords": []}
    ]}
    with pytest.raises(ProfileError, match="no codes and no keywords"):
        load_profile(write(tmp_path, bad))


def test_load_profiles_skips_the_example_directory(tmp_path):
    write(tmp_path, MINIMAL)
    write(tmp_path, {**MINIMAL, "member_id": "_example"})
    ids = {p.member_id for p in load_profiles(tmp_path)}
    assert ids == {"alex"}


def test_load_profiles_reports_a_bad_profile_without_losing_good_ones(tmp_path):
    write(tmp_path, MINIMAL)
    bad_dir = tmp_path / "broken"
    bad_dir.mkdir()
    (bad_dir / "profile.yml").write_text("not: [a, valid, profile]", encoding="utf-8")
    profiles, errors = load_profiles(tmp_path, collect_errors=True)
    assert {p.member_id for p in profiles} == {"alex"}
    assert any("broken" in e for e in errors)


def test_team_unions_service_lines_across_members(tmp_path):
    write(tmp_path, MINIMAL)
    write(tmp_path, {**MINIMAL, "member_id": "priya", "name": "Priya S",
                     "service_lines": [{"label": "Change mgmt", "unspsc": ["80101500"],
                                        "gsin": [], "naics": [], "keywords": ["change"]}]})
    profiles = load_profiles(tmp_path)
    team_file = tmp_path / "delivery.yml"
    team_file.write_text(yaml.safe_dump(
        {"team_id": "delivery", "name": "Delivery", "members": ["alex", "priya"],
         "prime": "alex"}), encoding="utf-8")
    team = load_team(team_file, profiles)
    labels = {sl.label for sl in team.service_lines(profiles)}
    assert labels == {"Data engineering", "Change mgmt"}


def test_team_referencing_an_unknown_member_raises(tmp_path):
    write(tmp_path, MINIMAL)
    profiles = load_profiles(tmp_path)
    team_file = tmp_path / "ghost.yml"
    team_file.write_text(yaml.safe_dump(
        {"team_id": "ghost", "name": "Ghost", "members": ["alex", "nobody"],
         "prime": "alex"}), encoding="utf-8")
    with pytest.raises(ProfileError, match="nobody"):
        load_team(team_file, profiles)


def test_team_capabilities_are_not_copied_into_the_team_file(tmp_path):
    # Editing a member profile must propagate; a snapshot in the team file would rot.
    write(tmp_path, MINIMAL)
    profiles = load_profiles(tmp_path)
    team_file = tmp_path / "solo.yml"
    team_file.write_text(yaml.safe_dump(
        {"team_id": "solo", "name": "Solo", "members": ["alex"], "prime": "alex"}),
        encoding="utf-8")
    team = load_team(team_file, profiles)
    assert not hasattr(team, "keywords")
    profiles[0].service_lines[0].keywords.append("newly added")
    assert "newly added" in team.service_lines(profiles)[0].keywords
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'matching.profile'`

- [ ] **Step 3: Write `matching/profile.py`**

```python
"""Member profiles and teams.

Teams are declared unions of members. Capabilities are never copied into a
team file -- they are unioned at read time so editing one profile propagates
everywhere.
"""
from __future__ import annotations

import dataclasses
import pathlib

import yaml

REQUIRED_PROFILE_FIELDS = (
    "member_id", "name", "service_lines", "regions",
)


class ProfileError(Exception):
    pass


@dataclasses.dataclass
class ServiceLine:
    label: str
    naics: list[str] = dataclasses.field(default_factory=list)
    unspsc: list[str] = dataclasses.field(default_factory=list)
    gsin: list[str] = dataclasses.field(default_factory=list)
    keywords: list[str] = dataclasses.field(default_factory=list)

    def has_any_signal(self) -> bool:
        return bool(self.naics or self.unspsc or self.gsin or self.keywords)


@dataclasses.dataclass
class Profile:
    member_id: str
    name: str
    regions: list[str]
    service_lines: list[ServiceLine]
    clearance: dict = dataclasses.field(default_factory=dict)
    skills: list = dataclasses.field(default_factory=list)
    certifications: list = dataclasses.field(default_factory=list)
    past_performance: list = dataclasses.field(default_factory=list)
    vehicles: list = dataclasses.field(default_factory=list)
    evidence: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Team:
    team_id: str
    name: str
    members: list[str]
    prime: str

    def service_lines(self, profiles: list[Profile]) -> list[ServiceLine]:
        by_id = {p.member_id: p for p in profiles}
        out: list[ServiceLine] = []
        for member in self.members:
            out.extend(by_id[member].service_lines)
        return out

    def regions(self, profiles: list[Profile]) -> set[str]:
        by_id = {p.member_id: p for p in profiles}
        return {r for m in self.members for r in by_id[m].regions}


def load_profile(path: pathlib.Path) -> Profile:
    path = pathlib.Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{path}: expected a mapping at the top level")

    missing = [f for f in REQUIRED_PROFILE_FIELDS if f not in data]
    if missing:
        raise ProfileError(f"{path}: missing required field(s): {', '.join(missing)}")

    lines = []
    for raw in data["service_lines"]:
        line = ServiceLine(
            label=raw.get("label", ""),
            naics=raw.get("naics") or [],
            unspsc=[str(c) for c in (raw.get("unspsc") or [])],
            gsin=[str(c) for c in (raw.get("gsin") or [])],
            keywords=[k.lower() for k in (raw.get("keywords") or [])],
        )
        if not line.has_any_signal():
            raise ProfileError(
                f"{path}: service line {line.label!r} has no codes and no keywords, "
                f"so it can never match anything"
            )
        lines.append(line)

    return Profile(
        member_id=data["member_id"],
        name=data["name"],
        regions=data["regions"],
        service_lines=lines,
        clearance=data.get("clearance") or {},
        skills=data.get("skills") or [],
        certifications=data.get("certifications") or [],
        past_performance=data.get("past_performance") or [],
        vehicles=data.get("vehicles") or [],
        evidence=data.get("evidence") or {},
    )


def load_profiles(root, collect_errors: bool = False):
    root = pathlib.Path(root)
    profiles, errors = [], []
    for path in sorted(root.glob("*/profile.yml")):
        if path.parent.name.startswith("_"):
            continue  # _example/ is a schema reference, not a real member
        try:
            profiles.append(load_profile(path))
        except ProfileError as exc:
            errors.append(str(exc))
    if collect_errors:
        return profiles, errors
    if errors:
        raise ProfileError("; ".join(errors))
    return profiles


def load_team(path, profiles: list[Profile]) -> Team:
    path = pathlib.Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    known = {p.member_id for p in profiles}
    unknown = [m for m in data["members"] if m not in known]
    if unknown:
        raise ProfileError(f"{path}: unknown member(s): {', '.join(unknown)}")
    return Team(
        team_id=data["team_id"],
        name=data["name"],
        members=data["members"],
        prime=data.get("prime", data["members"][0]),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_profile.py -v`
Expected: all 9 PASS.

- [ ] **Step 5: Write `profiles/_example/profile.yml`**

```yaml
# Schema reference. Fake data — safe to commit.
# Real profiles live in profiles/<member>/ and are git-ignored.
member_id: example
name: Jordan Example
clearance:
  level: Reliability        # None | Reliability | Secret | Top Secret
  status: active            # active | lapsed | eligible

regions:                    # must match CanadaBuys regionsOfDelivery values
  - Ontario
  - Canada

service_lines:
  - label: Data engineering and analytics
    naics: ["541512"]
    unspsc: ["81111500", "81112200"]   # primary code path — 84% feed coverage
    gsin: []                            # sparse (4%), but free to carry
    keywords:                           # not optional: 15% of notices carry no code
      - data pipeline
      - data warehouse
      - business intelligence
      # Run /profile to expand these with vocabulary mined from real notices.

skills:
  - {name: Python, depth: expert, years: 8}
  - {name: dbt, depth: working, years: 3}

certifications:
  - {name: PMP, issuer: PMI, expiry: "2028-01-31"}

# MAY BE EMPTY. Thin past performance is expected and is never disqualifying.
past_performance:
  - client: Example Corp
    value: 85000
    start: "2024-03-01"
    end: "2024-11-30"
    description: Built a reporting pipeline consolidating four source systems.
    reference: {name: Sam Reference, email: sam@example.com}

vehicles: []      # standing offers / supply arrangements held

evidence:
  resume: evidence/jordan-resume.pdf
  capability_statement: evidence/capability.pdf
```

- [ ] **Step 6: Write `teams/_example.yml` and `config.yml`**

`teams/_example.yml`:

```yaml
# Schema reference. Capabilities are NEVER listed here — they are unioned from
# member profiles at match time so profile edits propagate automatically.
team_id: example-team
name: Example Delivery Team
members: [example]
prime: example
```

`config.yml`:

```yaml
# Minimum days before closing for a bid to be considered writable.
# Stage 1 drops anything closing sooner. See spec, Layer 2 stage 1.
min_turnaround_days: 5

# Notification threshold for the daily digest. Set this from the Annex B
# Pass 4 score distribution, not from a round number.
notify_score_threshold: 70

active_profiles: []   # empty means all profiles found
active_teams: []
```

- [ ] **Step 7: Verify the committed example actually loads**

```bash
python -c "
from matching.profile import load_profile, load_team, load_profiles
p = load_profile('profiles/_example/profile.yml')
print('profile ok:', p.member_id, len(p.service_lines), 'service line(s)')
print('team ok:', load_team('teams/_example.yml', [p]).team_id)
"
```

Expected: both print ok. A committed example that doesn't parse is worse than none — it teaches the wrong schema.

- [ ] **Step 8: Commit**

```bash
git add matching/profile.py tests/test_profile.py profiles/_example/ teams/_example.yml config.yml
git commit -m "feat: profile and team models with capability unioning"
```

---

### Task 7: Stage-1 filter

The recall gate. Every rule here can permanently hide a tender, so each is tested for both directions.

**Files:**
- Create: `matching/filter.py`
- Test: `tests/test_filter.py`

**Interfaces:**
- Consumes: `Notice`, `Profile`, `Team`, `ServiceLine`.
- Produces:
  - `FilterConfig` dataclass: `.min_turnaround_days` (int, default 5), `.now` (datetime)
  - `FilterResult` dataclass: `.passed` (bool), `.reason` (str), `.matched_codes` (list[str]), `.matched_keywords` (list[str]), `.matched_service_lines` (list[str])
  - `filter_notice(notice, service_lines, regions, config) -> FilterResult`
  - `filter_all(notices, profiles, teams, config) -> dict[str, FilterResult]` keyed by reference
  - `REASON_CLOSED`, `REASON_TOO_SOON`, `REASON_REGION`, `REASON_NO_SIGNAL`, `REASON_PASS` constants

- [ ] **Step 1: Write the failing test**

`tests/test_filter.py`:

```python
import csv
import datetime
import pytest
from canadabuys.notice import Notice
from matching.profile import ServiceLine
from matching.filter import (
    FilterConfig, filter_notice,
    REASON_CLOSED, REASON_TOO_SOON, REASON_REGION, REASON_NO_SIGNAL, REASON_PASS,
)

NOW = datetime.datetime(2026, 8, 3, 12, 0, tzinfo=datetime.timezone.utc)
CONFIG = FilterConfig(min_turnaround_days=5, now=NOW)
INGEST_TS = "2026-08-03T12:00:00+00:00"


def base_row():
    with open("tests/fixtures/open_sample.csv", encoding="utf-8-sig", newline="") as f:
        return next(csv.DictReader(f))


def notice(**overrides) -> Notice:
    row = {
        **base_row(),
        "tenderStatus-appelOffresStatut-eng": "Open",
        "tenderClosingDate-appelOffresDateCloture": "2026-09-30T14:00:00",
        "regionsOfDelivery-regionsLivraison-eng": "*Ontario",
        "unspsc": "*81111500",
        "unspscDescription-eng": "*Software development",
        "gsin-nibs": "",
        "title-titre-eng": "Untitled",
        "tenderDescription-descriptionAppelOffres-eng": "",
        "selectionCriteria-criteresSelection-eng": "",
        **overrides,
    }
    return Notice.from_csv_row(row, "open", INGEST_TS)


LINE = ServiceLine(label="Data", unspsc=["81111500"], keywords=["data pipeline"])
REGIONS = ["Ontario"]


def test_passes_when_code_matches():
    r = filter_notice(notice(), [LINE], REGIONS, CONFIG)
    assert r.passed
    assert r.reason == REASON_PASS
    assert r.matched_codes == ["81111500"]
    assert r.matched_service_lines == ["Data"]


def test_passes_when_only_a_keyword_matches():
    # The 15% of notices with no procurement code are reachable only this way.
    r = filter_notice(
        notice(unspsc="", **{"tenderDescription-descriptionAppelOffres-eng":
                             "Seeking a data pipeline rebuild"}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed
    assert r.matched_keywords == ["data pipeline"]
    assert r.matched_codes == []


def test_keyword_matches_inside_the_selection_criteria_field():
    r = filter_notice(
        notice(unspsc="", **{"selectionCriteria-criteresSelection-eng":
                             "Bidder must demonstrate DATA PIPELINE experience"}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed, "keyword search must cover selection criteria, not just description"


def test_keyword_match_is_case_insensitive():
    r = filter_notice(
        notice(unspsc="", **{"title-titre-eng": "DATA PIPELINE Modernization"}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed


def test_keyword_matches_in_the_code_description():
    r = filter_notice(
        notice(unspsc="*99999999", **{"unspscDescription-eng": "*Data pipeline services"}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed


def test_rejects_when_no_code_and_no_keyword():
    r = filter_notice(
        notice(unspsc="*99999999", **{"unspscDescription-eng": "*Bulk cement",
                                      "title-titre-eng": "Cement supply"}),
        [LINE], REGIONS, CONFIG,
    )
    assert not r.passed
    assert r.reason == REASON_NO_SIGNAL


def test_rejects_a_closed_notice():
    r = filter_notice(
        notice(**{"tenderStatus-appelOffresStatut-eng": "Cancelled"}),
        [LINE], REGIONS, CONFIG,
    )
    assert not r.passed
    assert r.reason == REASON_CLOSED


def test_rejects_a_notice_closing_inside_the_turnaround_window():
    r = filter_notice(
        notice(**{"tenderClosingDate-appelOffresDateCloture": "2026-08-05T14:00:00"}),
        [LINE], REGIONS, CONFIG,
    )
    assert not r.passed
    assert r.reason == REASON_TOO_SOON


def test_accepts_a_notice_closing_exactly_at_the_threshold():
    # Boundary: 5 days out with min_turnaround_days=5 is biddable.
    r = filter_notice(
        notice(**{"tenderClosingDate-appelOffresDateCloture": "2026-08-08T13:00:00"}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed


def test_rejects_a_notice_in_an_unserved_region():
    r = filter_notice(
        notice(**{"regionsOfDelivery-regionsLivraison-eng": "*Nunavut Territory"}),
        [LINE], REGIONS, CONFIG,
    )
    assert not r.passed
    assert r.reason == REASON_REGION


def test_canada_wide_notice_matches_any_region():
    r = filter_notice(
        notice(**{"regionsOfDelivery-regionsLivraison-eng": "*Canada"}),
        [LINE], ["Ontario"], CONFIG,
    )
    assert r.passed, "a Canada-wide notice is deliverable from any province"


def test_notice_with_no_region_stated_passes():
    # Recall gate: 13% of notices omit fields. Absent data must not mean rejected.
    r = filter_notice(
        notice(**{"regionsOfDelivery-regionsLivraison-eng": ""}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed


def test_notice_with_no_closing_date_passes():
    r = filter_notice(
        notice(**{"tenderClosingDate-appelOffresDateCloture": ""}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed, "missing closing date must not silently hide a notice"


def test_matches_against_any_service_line_not_all():
    other = ServiceLine(label="Change", unspsc=["80101500"], keywords=["change management"])
    r = filter_notice(notice(), [other, LINE], REGIONS, CONFIG)
    assert r.passed
    assert r.matched_service_lines == ["Data"]


def test_gsin_code_also_matches():
    line = ServiceLine(label="Services", gsin=["F059A"], keywords=[])
    r = filter_notice(
        notice(unspsc="", **{"gsin-nibs": "*F059A"}), [line], REGIONS, CONFIG,
    )
    assert r.passed
    assert r.matched_codes == ["F059A"]


def test_empty_service_lines_rejects_everything_rather_than_crashing():
    r = filter_notice(notice(), [], REGIONS, CONFIG)
    assert not r.passed
    assert r.reason == REASON_NO_SIGNAL
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_filter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'matching.filter'`

- [ ] **Step 3: Write `matching/filter.py`**

```python
"""Stage-1 deterministic filter.

THIS IS A RECALL GATE. A notice dropped here is never judged, never appears in
a digest, and is invisible forever. Precision failures self-correct at stage 2;
recall failures are permanent and silent.

Consequence for every rule below: when data is absent or ambiguous, PASS the
notice. Absent data must never read as disqualifying.
"""
from __future__ import annotations

import dataclasses
import datetime

from canadabuys.notice import Notice
from matching.profile import ServiceLine

REASON_PASS = "pass"
REASON_CLOSED = "not-open"
REASON_TOO_SOON = "closing-too-soon"
REASON_REGION = "region-not-served"
REASON_NO_SIGNAL = "no-code-or-keyword-match"

# A notice deliverable anywhere in Canada is deliverable from any province.
NATIONAL_REGIONS = {"canada", "national capital region"}


@dataclasses.dataclass
class FilterConfig:
    min_turnaround_days: int = 5
    now: datetime.datetime = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


@dataclasses.dataclass
class FilterResult:
    passed: bool
    reason: str
    matched_codes: list[str] = dataclasses.field(default_factory=list)
    matched_keywords: list[str] = dataclasses.field(default_factory=list)
    matched_service_lines: list[str] = dataclasses.field(default_factory=list)


def _region_ok(notice: Notice, regions: list[str]) -> bool:
    if not notice.regions_delivery:
        return True  # not stated -> do not hide it
    served = {r.strip().lower() for r in regions}
    if served & NATIONAL_REGIONS:
        return True
    for region in notice.regions_delivery:
        r = region.strip().lower()
        if r in NATIONAL_REGIONS or r in served:
            return True
    return False


def filter_notice(
    notice: Notice,
    service_lines: list[ServiceLine],
    regions: list[str],
    config: FilterConfig,
) -> FilterResult:
    if notice.status and not notice.is_open():
        return FilterResult(False, REASON_CLOSED)

    if notice.closing is not None:
        deadline = config.now + datetime.timedelta(days=config.min_turnaround_days)
        if notice.closing < deadline:
            return FilterResult(False, REASON_TOO_SOON)

    if not _region_ok(notice, regions):
        return FilterResult(False, REASON_REGION)

    notice_codes = {c.strip().upper() for c in (notice.unspsc + notice.gsin) if c.strip()}
    text = notice.searchable_text()

    codes, keywords, lines = [], [], []
    for line in service_lines:
        line_codes = {c.strip().upper() for c in (line.unspsc + line.gsin) if c.strip()}
        hit_codes = sorted(notice_codes & line_codes)
        hit_keywords = sorted({k for k in line.keywords if k and k in text})
        if hit_codes or hit_keywords:
            codes.extend(hit_codes)
            keywords.extend(hit_keywords)
            lines.append(line.label)

    if not codes and not keywords:
        return FilterResult(False, REASON_NO_SIGNAL)

    return FilterResult(
        True, REASON_PASS,
        matched_codes=sorted(set(codes)),
        matched_keywords=sorted(set(keywords)),
        matched_service_lines=lines,
    )


def filter_all(notices, profiles, teams, config: FilterConfig) -> dict[str, FilterResult]:
    """Filter each notice against the union of all active profiles.

    A notice passes if ANY profile could want it; per-subject scoring is
    stage 2's job, not stage 1's.
    """
    all_lines = [sl for p in profiles for sl in p.service_lines]
    all_regions = sorted({r for p in profiles for r in p.regions})
    return {
        n.reference: filter_notice(n, all_lines, all_regions, config) for n in notices
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_filter.py -v`
Expected: all 16 PASS.

- [ ] **Step 5: Commit**

```bash
git add matching/filter.py tests/test_filter.py
git commit -m "feat: stage-1 recall-biased filter"
```

---

### Task 8: Low-barrier classification

The second track. Measured on the live feed, ~28% of open notices are supply arrangements, standing offers, or ACANs — the realistic entry path for a group with thin past performance.

**Files:**
- Create: `matching/lowbarrier.py`
- Test: `tests/test_lowbarrier.py`

**Interfaces:**
- Consumes: `Notice`.
- Produces:
  - `LowBarrierResult` dataclass: `.is_low_barrier` (bool), `.kind` (str), `.evidence` (str)
  - `classify(notice: Notice) -> LowBarrierResult`
  - `KIND_NONE`, `KIND_SUPPLY_ARRANGEMENT`, `KIND_STANDING_OFFER`, `KIND_ACAN`, `KIND_SUBCONTRACT` constants

- [ ] **Step 1: Write the failing test**

`tests/test_lowbarrier.py`:

```python
import csv
from canadabuys.notice import Notice
from matching.lowbarrier import (
    classify, KIND_NONE, KIND_SUPPLY_ARRANGEMENT, KIND_STANDING_OFFER,
    KIND_ACAN, KIND_SUBCONTRACT,
)

TS = "2026-08-03T12:00:00+00:00"


def notice(**overrides) -> Notice:
    with open("tests/fixtures/open_sample.csv", encoding="utf-8-sig", newline="") as f:
        row = next(csv.DictReader(f))
    row = {**row, "noticeType-avisType-eng": "Request for Proposal",
           "procurementMethod-methodeApprovisionnement-eng": "Competitive - Open bidding",
           "tenderDescription-descriptionAppelOffres-eng": "", **overrides}
    return Notice.from_csv_row(row, "open", TS)


def test_supply_arrangement_detected():
    r = classify(notice(**{"noticeType-avisType-eng": "Request for Supply Arrangement"}))
    assert r.is_low_barrier
    assert r.kind == KIND_SUPPLY_ARRANGEMENT


def test_rfp_against_supply_arrangement_detected():
    r = classify(notice(**{"noticeType-avisType-eng": "RFP against Supply Arrangement"}))
    assert r.is_low_barrier
    assert r.kind == KIND_SUPPLY_ARRANGEMENT


def test_standing_offer_detected():
    r = classify(notice(**{"noticeType-avisType-eng": "Request for Standing Offer"}))
    assert r.is_low_barrier
    assert r.kind == KIND_STANDING_OFFER


def test_acan_detected_by_notice_type():
    r = classify(notice(**{"noticeType-avisType-eng": "Advance Contract Award Notice"}))
    assert r.is_low_barrier
    assert r.kind == KIND_ACAN


def test_acan_detected_by_procurement_method_when_notice_type_is_blank():
    # noticeType is empty on 13% of notices; the method field is the fallback.
    r = classify(notice(**{
        "noticeType-avisType-eng": "",
        "procurementMethod-methodeApprovisionnement-eng": "Advance contract award notice",
    }))
    assert r.is_low_barrier
    assert r.kind == KIND_ACAN


def test_subcontracting_detected_in_description():
    r = classify(notice(**{
        "tenderDescription-descriptionAppelOffres-eng":
            "Prime contractors are encouraged to identify subcontracting opportunities.",
    }))
    assert r.is_low_barrier
    assert r.kind == KIND_SUBCONTRACT
    assert "subcontract" in r.evidence.lower()


def test_ordinary_open_rfp_is_not_low_barrier():
    r = classify(notice())
    assert not r.is_low_barrier
    assert r.kind == KIND_NONE


def test_blank_notice_type_and_method_is_not_low_barrier():
    r = classify(notice(**{"noticeType-avisType-eng": "",
                           "procurementMethod-methodeApprovisionnement-eng": ""}))
    assert not r.is_low_barrier


def test_classification_is_case_insensitive():
    r = classify(notice(**{"noticeType-avisType-eng": "REQUEST FOR STANDING OFFER"}))
    assert r.is_low_barrier


def test_notice_type_wins_over_description_heuristic():
    r = classify(notice(**{
        "noticeType-avisType-eng": "Request for Standing Offer",
        "tenderDescription-descriptionAppelOffres-eng": "subcontracting opportunities exist",
    }))
    assert r.kind == KIND_STANDING_OFFER, "explicit notice type beats a description keyword"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_lowbarrier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'matching.lowbarrier'`

- [ ] **Step 3: Write `matching/lowbarrier.py`**

```python
"""Low-barrier track classification.

For a group with thin past performance, the realistic entry path is vehicles
rather than large open competitions. Measured on the live feed (2026-08-03),
~28% of open notices qualify.

Keyed off noticeType and procurementMethod, NOT contract value -- the feed has
no value column.
"""
from __future__ import annotations

import dataclasses

from canadabuys.notice import Notice

KIND_NONE = "none"
KIND_SUPPLY_ARRANGEMENT = "supply-arrangement"
KIND_STANDING_OFFER = "standing-offer"
KIND_ACAN = "acan"
KIND_SUBCONTRACT = "subcontract"

# Checked in order; the first match wins. Explicit notice types beat heuristics.
_TYPE_RULES = (
    ("supply arrangement", KIND_SUPPLY_ARRANGEMENT),
    ("standing offer", KIND_STANDING_OFFER),
    ("advance contract award", KIND_ACAN),
)

_DESCRIPTION_HINTS = ("subcontract", "sub-contract", "subcontracting")


@dataclasses.dataclass
class LowBarrierResult:
    is_low_barrier: bool
    kind: str
    evidence: str = ""


def classify(notice: Notice) -> LowBarrierResult:
    notice_type = notice.notice_type.strip().lower()
    method = notice.procurement_method.strip().lower()

    for needle, kind in _TYPE_RULES:
        if needle in notice_type:
            return LowBarrierResult(True, kind, f"noticeType: {notice.notice_type}")

    # noticeType is blank on ~13% of notices; fall back to the method field.
    for needle, kind in _TYPE_RULES:
        if needle in method:
            return LowBarrierResult(
                True, kind, f"procurementMethod: {notice.procurement_method}"
            )

    description = notice.description.lower()
    for hint in _DESCRIPTION_HINTS:
        if hint in description:
            return LowBarrierResult(True, KIND_SUBCONTRACT, f"description mentions {hint!r}")

    return LowBarrierResult(False, KIND_NONE)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_lowbarrier.py -v`
Expected: all 10 PASS.

- [ ] **Step 5: Sanity-check the rate against real data**

```bash
canadabuys --notices .tmp-lb fetch --file tests/fixtures/open_sample.csv >/dev/null
python -c "
from canadabuys.store import NoticeStore
from matching.lowbarrier import classify
import collections, pathlib
ns=list(NoticeStore(pathlib.Path('.tmp-lb')).all())
c=collections.Counter(classify(n).kind for n in ns)
print(c)
"
```

Expected: a mix, with `none` the plurality and at least one vehicle kind present. If everything is `none`, the fixture sample happens to lack vehicles — re-check against a live fetch before assuming the classifier is broken. Clean up: `rm -rf .tmp-lb`

- [ ] **Step 6: Commit**

```bash
git add matching/lowbarrier.py tests/test_lowbarrier.py
git commit -m "feat: low-barrier track classification"
```

---

### Task 9: Full-suite green and the archive tooling

Wires the pieces into the offline analyses Annex B needs, and proves the suite runs clean end to end.

**Files:**
- Create: `tools/archive_report.py`
- Modify: `canadabuys/cli.py` (add `filter` subcommand)
- Test: run the whole suite

**Interfaces:**
- Consumes: everything above.
- Produces: `canadabuys filter --profiles DIR [--config config.yml]` printing pass/reject counts by reason; `tools/archive_report.py` for Annex B passes 2 and 5.

- [ ] **Step 1: Add the `filter` subcommand to `canadabuys/cli.py`**

Add these imports at the top of `canadabuys/cli.py`:

```python
import collections
import yaml
from matching.filter import FilterConfig, filter_all
from matching.profile import load_profiles
```

Add this function:

```python
def cmd_filter(args) -> int:
    """Run stage 1 and report what survived and what was dropped, by reason.

    This is Annex B Pass 2 (filter tuning): the reject histogram is how you
    tell an over-broad keyword list from an over-narrow one.
    """
    profiles, errors = load_profiles(pathlib.Path(args.profiles), collect_errors=True)
    for err in errors:
        print(f"WARNING: skipping unreadable profile: {err}", file=sys.stderr)
    if not profiles:
        print("ERROR: no usable profiles found", file=sys.stderr)
        return 1

    cfg_data = {}
    if pathlib.Path(args.config).exists():
        cfg_data = yaml.safe_load(pathlib.Path(args.config).read_text(encoding="utf-8")) or {}
    config = FilterConfig(
        min_turnaround_days=cfg_data.get("min_turnaround_days", 5),
        now=datetime.datetime.now(datetime.timezone.utc),
    )

    notices = list(NoticeStore(pathlib.Path(args.notices)).all())
    results = filter_all(notices, profiles, [], config)
    counts = collections.Counter(r.reason for r in results.values())
    passed = counts.get("pass", 0)

    print(f"notices: {len(notices)}")
    print(f"passed:  {passed}")
    for reason, count in counts.most_common():
        if reason != "pass":
            print(f"  dropped [{reason}]: {count}")
    if len(notices):
        print(f"pass rate: {passed / len(notices):.1%}")
    return 0
```

Register it in `main()`, immediately before `args = parser.parse_args(argv)`:

```python
    p_filter = sub.add_parser("filter", help="run stage 1 and report the outcome")
    p_filter.add_argument("--profiles", default="profiles")
    p_filter.add_argument("--config", default="config.yml")
    p_filter.set_defaults(func=cmd_filter)
```

- [ ] **Step 2: Verify the filter subcommand runs**

```bash
canadabuys --notices .tmp-f fetch --file tests/fixtures/open_sample.csv
canadabuys --notices .tmp-f filter --profiles profiles
```

Expected: counts printed, no traceback. The example profile is fake, so a low pass rate is correct here. Clean up: `rm -rf .tmp-f`

- [ ] **Step 3: Write `tools/archive_report.py`**

```python
"""Offline archive analysis for Annex B passes 2 and 5.

Pass 2 (filter tuning): survivor volume per week.
Pass 5 (market map): which organizations buy your service lines, via which methods.

Usage:
    python tools/archive_report.py archives/2024-2025-TenderNotice-AvisAppelOffres.csv
"""
from __future__ import annotations

import collections
import datetime
import pathlib
import sys

import yaml

from canadabuys.fetch import parse_csv_bytes
from matching.filter import FilterConfig, filter_all
from matching.lowbarrier import classify
from matching.profile import load_profiles

NOW_ISO = "2000-01-01T00:00:00+00:00"  # archives are historical; ingest time is irrelevant


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    archive = pathlib.Path(argv[1])
    profiles = load_profiles(pathlib.Path("profiles"))
    cfg = yaml.safe_load(pathlib.Path("config.yml").read_text(encoding="utf-8")) or {}

    notices = parse_csv_bytes(archive.read_bytes(), "archive", NOW_ISO)
    print(f"archive: {archive.name}  notices: {len(notices)}")

    # Pass 2 — volume. Date and status rules are meaningless on historical data,
    # so use a far-past `now` to neutralize them and isolate code/keyword reach.
    config = FilterConfig(
        min_turnaround_days=cfg.get("min_turnaround_days", 5),
        now=datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc),
    )
    results = filter_all(notices, profiles, [], config)
    survivors = [n for n in notices if results[n.reference].passed]
    print(f"\n--- Pass 2: filter reach ---")
    print(f"survivors: {len(survivors)} ({len(survivors)/max(len(notices),1):.1%})")
    print(f"per week:  {len(survivors)/52:.1f}")
    reasons = collections.Counter(r.reason for r in results.values())
    for reason, count in reasons.most_common():
        print(f"  {reason}: {count}")

    matched_by_line = collections.Counter(
        label for r in results.values() for label in r.matched_service_lines
    )
    print("\nsurvivors by service line:")
    for label, count in matched_by_line.most_common():
        print(f"  {label}: {count}")

    # Pass 5 — market map.
    print(f"\n--- Pass 5: market map (survivors only) ---")
    print("top buying organizations:")
    for entity, count in collections.Counter(n.entity for n in survivors).most_common(15):
        print(f"  {count:4d}  {entity}")
    print("\nby procurement method:")
    for method, count in collections.Counter(
        n.procurement_method or "(blank)" for n in survivors
    ).most_common():
        print(f"  {count:4d}  {method}")
    print("\nlow-barrier share:")
    for kind, count in collections.Counter(classify(n).kind for n in survivors).most_common():
        print(f"  {count:4d}  {kind}")
    print("\nby month published:")
    for month, count in sorted(collections.Counter(
        n.published.strftime("%Y-%m") for n in survivors if n.published
    ).items()):
        print(f"  {month}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS (roughly 64 across six test modules). Zero network calls — if a test hangs, something is fetching.

- [ ] **Step 5: Confirm no real profile data is staged**

```bash
git status --short
git check-ignore -v profiles/realmember 2>/dev/null || echo "NOT IGNORED - fix .gitignore before committing"
```

Expected: only intended files listed; `profiles/_example/` is the sole tracked profile path.

- [ ] **Step 6: Commit**

```bash
git add canadabuys/cli.py tools/archive_report.py
git commit -m "feat: add stage-1 filter CLI and archive analysis tooling"
```

---

### Task 10: Stage-2 rubric skill and the slash commands

The LLM-facing half. These are markdown instruction files, not code — but they are the product surface, so they get the same care.

**Files:**
- Create: `.claude/skills/tender-matcher/SKILL.md`
- Create: `.claude/commands/scrape.md`, `.claude/commands/rank.md`, `.claude/commands/profile.md`, `.claude/commands/team.md`
- Create: `.agents/skills/canadabuys-search/SKILL.md`

**Interfaces:**
- Consumes: the CLI (`canadabuys fetch`, `canadabuys filter`), `matching.filter`, `matching.lowbarrier`.
- Produces: `matches/YYYY-MM-DD/verdicts.json` and `digest.md`.

- [ ] **Step 1: Write `.claude/skills/tender-matcher/SKILL.md`**

````markdown
---
name: tender-matcher
description: Use when judging whether a CanadaBuys tender notice is worth bidding — scoring fit against member profiles and teams, extracting mandatory criteria, and producing bid/no-bid verdicts.
---

# Tender matcher — stage-2 judgment

Stage 1 has already filtered. Everything you see here passed a code or keyword
test and is open and biddable. Your job is judgment, not filtering.

## The verdict you produce

For each notice, against each active profile and team, emit an object matching:

```json
{
  "reference": "cb-450-77537023",
  "subject": "alex",
  "subject_kind": "profile",
  "score": 0,
  "recommendation": "bid | no-bid | investigate",
  "low_barrier": {"is_low_barrier": false, "kind": "none"},
  "requirements": [
    {"text": "...", "kind": "mandatory | rated",
     "status": "met | gap | unclear", "covered_by": "alex | null",
     "note": "..."}
  ],
  "reasoning": "2-4 sentences",
  "deal_breakers": ["..."]
}
```

## How to judge

1. **Extract the real criteria** from `description` and `selection_criteria`.
   Quote the notice's own numbering where it has one. If the notice does not
   state criteria — many do not, deferring to attachments — say so in
   `reasoning` and set `recommendation` to `investigate` rather than inventing
   criteria. **Never fabricate structure the notice does not contain.** This is
   the most damaging error available to you: everything downstream is built on
   this extraction.

2. **Attribute each requirement** to the member who covers it, by name. For a
   team, check every member. Mark `gap` when nobody covers it, `unclear` when
   the notice is too vague to tell — do not resolve genuine ambiguity in the
   group's favour.

3. **Identify deal-breakers.** A required security clearance nobody holds, a
   mandatory certification, a required existing standing offer — these are
   fatal regardless of how well everything else fits. A notice with a
   deal-breaker is `no-bid` even at high surface fit, and the reasoning must
   name it.

4. **Score fit 0-100** on what the group can actually deliver and actually
   win. Weight mandatories far above rated criteria — failing one mandatory is
   disqualifying, while losing points on a rated criterion is survivable.

5. **Be honest about thin past performance.** This group has little procurement
   history. A large open competition with heavy past-performance requirements is
   a realistic no-bid; say so plainly rather than encouraging a hopeless bid.
   **Never paper over a gap to raise a score** — the gap report is the product.

## Scoring guide

| Range | Meaning |
|---|---|
| 85-100 | Strong fit, all mandatories met, credible win |
| 70-84 | Good fit, minor gaps, worth serious consideration |
| 50-69 | Partial fit — real gaps; usually only worth it on the low-barrier track |
| 25-49 | Weak fit; no-bid absent a specific reason |
| 0-24 | Not our work |

**These bands are a starting point, not settled.** Revise them from Annex B
Pass 4 (read 50-100 archived verdicts and correct the systematic errors), then
from real outcomes. Edit this file when you do — it is the single source of
scoring truth, and it is meant to be edited.

## The low-barrier track

Notices classified low-barrier (supply arrangements, standing offers, ACANs,
subcontracting) are judged on a different question: *could this group
realistically get onto this vehicle?* — not *could it win a full competition?*
A 60 on the low-barrier track can be more actionable than an 80 on the open
track. Never merge the two into one ranked list.
````

- [ ] **Step 2: Write `.claude/commands/scrape.md`**

````markdown
---
description: Pull the latest CanadaBuys tender notices into the local store
---

Run the ingestion CLI and report what changed.

1. Run: `canadabuys fetch --feed open`
2. If it exits non-zero, STOP and show the error. A schema-change error means
   the feed changed — read `.agents/skills/canadabuys-search/url-reference.md`
   and reconcile before touching anything else. **Do not** work around it by
   loosening the column check; that trades a loud failure for a silent one.
3. Report created / amended / needs-rematch counts.
4. If any notices need rematching, say so and suggest running `/rank`.
````

- [ ] **Step 3: Write `.claude/commands/rank.md`**

````markdown
---
description: Filter and judge open notices, then write today's digest
---

Produce today's tender digest.

## 1. Filter

Run: `canadabuys filter --profiles profiles`

Report the pass rate and the reject histogram. If the pass rate looks wrong —
near zero, or nearly everything — say so before continuing. That is a profile
problem, not a judgment problem, and running stage 2 on top of it wastes effort.

## 2. Judge

For each notice that passed, load it from `notices/` and apply the
`tender-matcher` skill against every active profile and team (from `config.yml`;
empty lists mean all). Skip any notice that already has a verdict in a previous
`matches/` directory **unless** its `needs_rematch` flag is true — an amendment
may have changed the criteria or the deadline.

Write all verdicts to `matches/<today>/verdicts.json`.

## 3. Write the digest

Write `matches/<today>/digest.md` with **two separate sections, never merged
into one ranked list**:

```markdown
# Tender digest — YYYY-MM-DD

## Open competitions
| Score | Closes | Notice | Buyer | Subject | Recommendation |

## Low-barrier track (vehicles, ACANs, subcontracting)
| Score | Closes | Notice | Buyer | Kind | Recommendation |

## Gaps worth noting
Requirements that blocked otherwise-good matches — these are what to fix.

## Amended since last run
Notices whose criteria or deadline changed. Re-read these; a prior decision
may no longer hold.
```

Sort each section by score descending. For anything scoring at or above
`notify_score_threshold` in `config.yml`, list it first and state the days
remaining until closing.

Close with a one-line summary: how many judged, how many recommended.
````

- [ ] **Step 4: Write `.claude/commands/profile.md`**

````markdown
---
description: Build or update a member profile from evidence and interview
argument-hint: <member-id>
---

Build `profiles/$1/profile.yml`. Use `profiles/_example/profile.yml` as the schema.

## 1. Ingest evidence

Read everything in `profiles/$1/evidence/` — resumes, capability statements,
past proposals. Extract: skills with depth and years, certifications with
expiry, past performance (client, value, dates, description, reference),
clearance level, and candidate service lines.

## 2. Interview for the rest

Ask about what the documents do not show, ONE question at a time: legal status
and business number, PSPC supplier registration, clearance status, regions
served, capacity, and any procurement vehicles held.

**Empty `past_performance` is expected and fine.** Do not press, and do not
imply it disqualifies anything — it is the normal starting state here.

## 3. Mine the vocabulary (Annex B Pass 1)

This is the step that makes stage 1 work, so do not skip it.

For each service line, if an archive exists in `archives/`, find notices whose
codes fall in that line's UNSPSC/GSIN list and extract the recurring terms from
their titles and descriptions — the words procurement officers actually use.
They differ systematically from how consultants describe themselves: "change
management" appears in notices as "business transformation advisory services"
or "organizational readiness support".

If no archive is present, say so and suggest downloading one; then propose
keywords from your own knowledge of federal procurement phrasing, clearly
labelled as unverified.

**Present proposed keywords for approval. Never write them silently** — an
over-broad keyword list degrades stage 1 for every member, and stage 1 is the
recall gate.

## 4. Write and verify

Write the YAML, then confirm it loads:

```bash
python -c "from matching.profile import load_profile; print(load_profile('profiles/$1/profile.yml').member_id)"
```

Remind the user that `profiles/` is git-ignored and must stay that way.
````

- [ ] **Step 5: Write `.claude/commands/team.md`**

````markdown
---
description: Declare or edit a team of members
argument-hint: <team-id>
---

Create or update `teams/$1.yml` using `teams/_example.yml` as the schema.

Ask which members are on the team and who is prime. Verify every member has a
profile in `profiles/`.

**Never copy capabilities into the team file.** Teams list member IDs only;
service lines and regions are unioned from the member profiles at match time,
so a profile edit propagates automatically. A snapshot here would silently rot.

Verify it loads:

```bash
python -c "
from matching.profile import load_profiles, load_team
print(load_team('teams/$1.yml', load_profiles('profiles')).members)"
```
````

- [ ] **Step 6: Write `.agents/skills/canadabuys-search/SKILL.md`**

````markdown
---
name: canadabuys-search
description: Use when fetching Canadian federal tender notices from CanadaBuys open data — ingesting the daily feed, handling amendments, or analyzing historical tender archives.
---

# CanadaBuys search

Ingests CanadaBuys tender notices into the local store. See `url-reference.md`
for feed URLs, refresh windows, and the measured data gotchas — **read it before
changing any parsing code.**

## Commands

    canadabuys fetch --feed open      # daily authority on what is open
    canadabuys fetch --feed new       # same-day freshness, refreshed every 2h
    canadabuys fetch --file PATH      # ingest a local CSV (archives, fixtures)
    canadabuys stats                  # summarize the store
    canadabuys filter --profiles profiles   # run stage 1, report the histogram

## Rules

- **Ingestion performs no judgment.** No scoring, no relevance filtering, no LLM.
- **A schema change aborts the run.** Never loosen `REQUIRED_COLUMNS` to make an
  error go away — writing an empty digest that reads as "a quiet day" is the one
  failure mode that silently costs a deadline.
- **Amendments update in place** and set `needs_rematch` when the closing date,
  description, or selection criteria changed.
- Archives are for offline analysis only (see Annex B). Never fetch them in the
  daily path.
````

- [ ] **Step 7: Verify every command file has valid frontmatter**

```bash
python -c "
import pathlib, sys
for p in sorted(pathlib.Path('.claude/commands').glob('*.md')) + \
         sorted(pathlib.Path('.claude/skills').rglob('SKILL.md')) + \
         sorted(pathlib.Path('.agents/skills').rglob('SKILL.md')):
    text = p.read_text(encoding='utf-8')
    ok = text.startswith('---') and text.count('---') >= 2
    print(('OK  ' if ok else 'BAD '), p)
    if not ok: sys.exit(1)
"
```

Expected: every line `OK`.

- [ ] **Step 8: Commit**

```bash
git add .claude/ .agents/skills/canadabuys-search/SKILL.md
git commit -m "feat: add stage-2 rubric skill and scrape/rank/profile/team commands"
```

---

### Task 11: Scheduling and documentation

**Files:**
- Create: `docs/scheduling.md`
- Modify: `AGENTS.md` (add the workflow section)

**Interfaces:**
- Consumes: `/scrape`, `/rank`.
- Produces: documented daily-run setup.

- [ ] **Step 1: Write `docs/scheduling.md`**

````markdown
# Daily run

The daily job is `/scrape` then `/rank`, on weekdays. The open feed refreshes
between 07:00 and 08:30 UTC-0500, so schedule after 09:00 Eastern.

Set it up with the `schedule` skill in Claude Code:

> Every weekday at 9:15am, run /scrape then /rank, and notify me only if
> something scores at or above the notify_score_threshold in config.yml, or if
> a notice I have an open bid on was amended.

## What "notify" should mean

Notify on:
- a new notice at or above `notify_score_threshold`
- **any** amended notice with an existing verdict — the criteria or deadline
  may have moved under a decision already made
- a tracked bid whose deadline is within a week

Do not notify on an ordinary quiet day. The digest is written regardless and can
be read on demand; a notification that fires daily stops being read.

## Failure behaviour

A failed fetch or a feed schema change **must notify**. A silent failure looks
exactly like a quiet day and costs a deadline — this is the single failure mode
the design treats as unacceptable.
````

- [ ] **Step 2: Add the workflow section to `AGENTS.md`**

Append:

```markdown
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
```

- [ ] **Step 3: Verify the whole suite is still green**

Run: `pytest`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add docs/scheduling.md AGENTS.md
git commit -m "docs: document daily scheduling and archive analysis workflow"
```

---

## After this plan

The tool now ingests, filters, judges, and reports. Before relying on scores:

1. Build real profiles with `/profile` (Annex B Pass 1 runs inside it).
2. Download a fiscal-year archive and run `tools/archive_report.py` — that is
   Pass 2, and it tells you whether the filter's reach is sane.
3. Run the Pass 3 recall audit on rejected notices. This decides whether A7
   (semantic retrieval) is needed, and it is the pass most likely to be skipped.
4. Run the Pass 4 face-validity read and edit the rubric in
   `.claude/skills/tender-matcher/SKILL.md`.
5. Set the notification threshold from the observed score distribution.

Then write the second plan: `/apply` and `/outcome` (spec steps 8-9), against
the matcher's real output rather than a predicted shape.
