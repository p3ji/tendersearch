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
