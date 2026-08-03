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
