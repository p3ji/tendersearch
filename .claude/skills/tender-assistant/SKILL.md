---
name: tender-assistant
description: Use when drafting bid response prose for /apply -- writing style, section structure, and how to turn verdict data into a submission-ready draft.
---

# Tender assistant — drafting bid responses

`/apply` reads this skill after the deterministic scaffold (`bids/<notice-id>/scaffold.json`)
is written. Your job here is prose: turning per-requirement evidence into response text a
procurement officer will actually read.

## Writing style

- Plain, factual, first person plural ("we"). No marketing language — "leverage," "synergy,"
  "best-in-class," "world-class" are banned. Say what was done and what the result was.
- Every claim traces to evidence. If a requirement is met, cite the specific resume line or
  past-performance entry it comes from (`scaffold.json`'s `requirements[].evidence` gives you
  the file). Do not write a stronger claim than the evidence supports.
- Match the notice's own numbering. If the solicitation numbers its criteria "3.2.1," your
  response section is headed "3.2.1" — not renumbered, not reordered.
- Short paragraphs. One requirement, one section, one clear statement of how it's met — not a
  narrative essay.
- Never paper over a gap. If a requirement's `status` is `gap` or `unclear` in the scaffold,
  say so plainly in the draft rather than writing around it — gap requirements need a human
  decision (partner, subcontract, or no-bid on this criterion), not disguised prose. Flag them
  clearly, e.g. **[GAP — no covering member; needs a decision before submission]**.
- Thin past performance is the group's real constraint. Do not inflate a single small
  engagement into a "track record." State the actual scope and value, then let capability and
  approach carry the rest of the response.

## Draft structure

Standard sections, in this order, each written as its own file under `bids/<notice-id>/`:

1. **`cover-letter.md`** — one page. States what's being bid on (title + reference), who's
   bidding (member or team name), and a one-paragraph summary of fit. Save score/reasoning
   language for internal use; the cover letter doesn't say "we scored an 82."
2. **`matrix.md`** — the requirements-to-response table (see `.claude/commands/apply.md` for
   the exact table shape). This is the compliance spine every other file expands on.
3. **`technical-response.md`** — one subsection per requirement, in the notice's own order,
   each opening with the requirement text (or its number) as a heading, then the response prose.
4. **`past-performance.md`** — one entry per past-performance record actually cited in the
   matrix: client, value, dates, description, and how it relates to this solicitation's
   requirements. Do not pad this section with performance records that weren't cited anywhere
   in the matrix — irrelevant history reads as generic.
5. **`checklist.md`** — unchecked compliance checklist. Read the notice's `description` and
   `selection_criteria` (in the scaffold) for submission logistics — page limits, required
   forms, delivery method/deadline, number of copies, mandatory attachments — and list each as
   an unchecked item. This is a checklist of what must be assembled and submitted, not a filled
   form: leave every box unchecked.

Skip a section entirely if it doesn't apply (e.g. no past-performance record was cited) rather
than writing a section with nothing in it.

## What this skill does not cover

Profile methodology (how to build `profiles/<member>/profile.yml`) lives in
`.claude/commands/profile.md`, not here. Stage-2 scoring rubric lives in
`.claude/skills/tender-matcher/`. This skill is drafting only, and only runs after a verdict
already exists.
