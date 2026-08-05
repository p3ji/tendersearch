---
description: Record a bid/no-bid decision and, later, its result
argument-hint: <notice-id> [--profile <member> | --team <team>]
---

Record what happened on notice `$1`. **Run this for no-bids too, not only for notices you
actually bid on.** No-bid decisions accumulate weekly; bid outcomes take a quarter; wins are
rarer still and double as past-performance evidence. The no-bid record is the highest-value
signal this file collects — see the design spec's Outcome section for why.

**This command never adjusts the rubric.** It writes one record. A human reads accumulated
records later, spots a pattern, and edits `.claude/skills/tender-matcher/SKILL.md` by hand.
Automating that proposal step is deferred (A5 in the design spec's appendix) until enough
records exist to separate a real pattern from noise.

## 1. Find the verdict

Load the verdict for `$1` the same way `/apply` does — from `matches/<date>/verdicts.json`,
disambiguated by `--profile`/`--team` if more than one subject has a verdict for this notice.
You need its `score`, `recommendation`, and `subject`/`subject_kind`. If no verdict exists,
stop and say so — do not record an outcome for a notice `/rank` never judged.

## 2. Ask what was decided, one question at a time

1. **Decision** — `bid` or `no-bid`.
2. **Reason code** — offer the controlled vocabulary from `matching/outcome.py`:
   `capability-gap`, `clearance`, `past-performance`, `capacity`, `timeline`, `poor-fit`,
   `incumbent-entrenched`, `price-uncompetitive`, `scope-too-large`, `not-actually-our-work`.
   **Do not accept free text here** — if none of these genuinely fits, say so and ask whether a
   new code belongs in the vocabulary (that is a design change, not something to paper over
   with prose). Free-form detail goes in notes, not the code.
3. **Notes** — why, in the user's own words. A no-bid reading *"scored 78, no-bid,
   `clearance` — the requirement was fatal"* is worth more than ten unexplained losses, because
   it isolates a specific rubric error. Push for that level of specificity.

If the decision is `no-bid`, you have everything you need — skip to Step 4.

## 3. If it was a bid, ask about the result

Only ask this if the user already knows — do not chase them for a status that has not happened
yet. Offer: `won`, `lost`, `no-award`, `pending`.

- **If `lost`** — ask for a result reason in the user's words, and flag when it sounds like
  `price-uncompetitive` or `incumbent-entrenched`. Both mean a well-fitted bid lost on
  something the rubric could not have predicted; recording it as such matters, because a future
  rubric-tuning pass must exclude these from fit-related adjustments rather than learn to score
  down work this group is genuinely suited for.
- **If `won`** — this is the valuable case. Ask for exactly what `matching.outcome.WinDetails`
  needs, because it becomes past-performance evidence and this group's profiles are short on
  it: client name, contract value, start date, end date, and a reference contact (name and
  email) if the client has agreed to be one. Capture these now, while they are known — do not
  defer and lose them.

## 4. Write the record

Run:

```
canadabuys record-outcome $1 \
  --subject <id> --subject-kind <profile|team> \
  --score <verdict score> --recommendation <verdict recommendation> \
  --decision <bid|no-bid> --reason-code <code> --notes "<notes>" \
  [--result <won|lost|no-award|pending> --result-reason "<...>"] \
  [--win-client "<...>" --win-value <n> --win-start <date> --win-end <date> \
   --win-reference-name "<...>" --win-reference-email "<...>"]
```

If it rejects a `won` result for missing win details, that is a stop, not a bug to route
around — go back and ask for the missing fields rather than retrying with `--result pending`.

## 5. If it was a win, offer to update the profile

Ask whether to add the new past-performance entry to `profiles/<member>/profile.yml`'s
`past_performance` list, in the shape `profiles/_example/profile.yml` shows. This is the one
place a win pays forward: the next `/rank` run can cite it. Do this only with the user's
confirmation — do not edit a profile unasked.

## 6. Report

Confirm what was recorded, in one line: notice, decision, reason code, and result if any.
