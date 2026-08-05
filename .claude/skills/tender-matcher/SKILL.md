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

## What the three recommendations mean

They are instructions, not grades. Each says what happens next.

| | Meaning | Next step |
|---|---|---|
| `no-bid` | Structurally ineligible or clearly outside scope. Decided. | Nothing. Do not spend more on it. |
| `bid` | Eligible, well-fitted, and nothing further is needed to commit. | `/apply` |
| `investigate` | **The feed does not contain enough to decide.** | `canadabuys enrich <ref>`, read the documents, re-judge |

**`investigate` is the honest answer, not a hedge.** The feed's description
answers *am I structurally eligible?* — and it answers it well: on a real run,
65 of 85 deal-breakers were identifiable from the description alone. What it
usually cannot answer is *can I clear the specific bar?*, because minimum years,
required reference projects, and named certifications live in the attached
solicitation documents.

So when the notice plainly states the criteria, judge them. When it defers to
attachments, say `investigate` and name in `reasoning` **what specifically you
would need to see** — "mandatory quals and any Indigenous-supplier restriction
are not in the notice text" is actionable; "needs more information" is not.

Do not inflate an `investigate` into a `bid` because the fit looks good, and do
not deflate it into a `no-bid` because past performance is thin. Both throw away
the one thing that makes the verdict useful: knowing which question is still open.

One caveat worth stating in `reasoning` when relevant: some CanadaBuys entries
attach only the notice-of-proposed-procurement advertisement, and the real
package must be requested from the contracting authority by email. `enrich` will
fetch a one-page ad in that case, and the next step is a human sending an email.

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
