---
description: Filter and judge open notices, then write today's digest
---

Produce today's tender digest.

## 1. Filter

Run: `canadabuys filter --profiles profiles --json matches/<today>/stage1.json`

(Note the argument order: `--notices` is a top-level flag and must come
*before* the subcommand, e.g. `canadabuys --notices notices filter ...` —
`canadabuys filter --notices notices` fails.)

Report the pass rate and the reject histogram. If the pass rate looks wrong —
near zero, or nearly everything — say so before continuing. That is a profile
problem, not a judgment problem, and running stage 2 on top of it wastes effort.

## 2. Judge

Read `matches/<today>/stage1.json` — each entry is a notice that passed
stage 1, with its reference, title, buyer, closing date, `needs_rematch`,
matched codes/keywords/service lines, and low-barrier classification. For
each entry, load the full notice from `notices/` (by reference) and apply the
`tender-matcher` skill against every active profile and team (from `config.yml`;
empty lists mean all). Skip any notice that already has a verdict in a previous
`matches/` directory **unless** its `needs_rematch` flag is true — an amendment
may have changed the criteria or the deadline.

Write all verdicts to `matches/<today>/verdicts.json` as a JSON array of verdict records —
`[{...}, {...}, ...]` at the top level, not wrapped in an object (e.g. not `{"verdicts": [...]}`).
`matching/verdict.py` reads this file and requires the top level to be a list; anything else
raises a `VerdictError` naming the file and the type it found.

After a notice's verdict is durably written to `matches/<today>/verdicts.json`,
call `NoticeStore.clear_rematch(reference)` for that notice. Do this **after**
the verdict is written, not before — clearing first and getting interrupted
would lose the flag and the notice would never be re-judged despite the
amendment.

## 3. Write the digest

Write `matches/<today>/digest.md` with **two separate sections, never merged
into one ranked list**:

```markdown
# Tender digest — YYYY-MM-DD

## Open competitions
| Score | Closes | Notice | Buyer | Subject | Recommendation |

## Low-barrier track (vehicles, ACANs, subcontracting)
| Score | Closes | Notice | Buyer | Kind | Confidence | Recommendation |

## Gaps worth noting
Requirements that blocked otherwise-good matches — these are what to fix.

## Amended since last run
Notices whose criteria or deadline changed. Re-read these; a prior decision
may no longer hold.
```

Sort the open-competitions section by score descending. The low-barrier
section sorts by confidence first, then by score descending within each
confidence group (see "Low-barrier confidence" below). For anything scoring
at or above `notify_score_threshold` in `config.yml`, list it first and state
the days remaining until closing.

### Low-barrier confidence

`matching.lowbarrier.classify()` returns a `confidence` of `high` or `low`
alongside `kind`. `high` confidence comes from structured `noticeType` /
`procurementMethod` signals (supply arrangements, standing offers, ACANs).
`low` confidence comes from a description-keyword rule for subcontracting
clauses that was measured against real feed data and produced 30 out of 30
false positives — 26 of them the identical Indigenous Business Directory
boilerplate clause. No genuine positives were observed in the measured
sample. The rule is retained by explicit decision of the project owner so
these notices stay visible for manual verification rather than being
silently dropped, not because it has demonstrated any true positives.

Within the low-barrier section:
- Sort `confidence == "high"` entries above `confidence == "low"` entries
  (score descending within each group).
- Add a `Confidence` column to the table (`high` / `low`).
- Include an explicit note directly under the section heading: low-confidence
  entries are unverified description-keyword matches that frequently hit
  boilerplate clause text, and must be checked against the actual notice
  before acting on them.

Close with a one-line summary: how many judged, how many recommended.
