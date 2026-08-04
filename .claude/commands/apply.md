---
description: Build the bid draft in bids/<notice-id>/ from an existing verdict
argument-hint: <notice-id> [--profile <member> | --team <team>]
---

Build the bid draft for notice `$1`. Requires that `/rank` has already produced a verdict for
this notice — `/apply` never judges fit itself, it only drafts a response to a verdict that
already exists.

## 1. Assemble the scaffold

Run: `canadabuys --notices notices apply $1 --profiles profiles --matches matches --bids bids`

Pass `--profile <member>` or `--team <team>` (append to `$ARGUMENTS` as given) when the notice
has verdicts for more than one subject — the command will tell you if disambiguation is needed
rather than guessing.

(Same argument-order rule as `/rank`: `--notices` is a top-level flag and must come *before*
the subcommand.)

If this fails with `no verdict found`, stop and tell the user to run `/rank` first — do not
attempt to judge the notice yourself. If it fails with `has verdicts for multiple subjects`,
re-run with `--profile` or `--team` naming one of the subjects listed in the error. If stderr
contains a `WARNING: ... was amended after the ... verdict was written` line, say so plainly
to the user before continuing and ask whether to proceed with the possibly-stale verdict or to
re-run `/rank` first.

## 2. Read the scaffold and evidence

Read `bids/<notice-id>/scaffold.json`. For each requirement row with `covered_by` set, read
every file path listed in its `evidence` object (resume, capability statement, etc.) — these
are the real documents behind the claim, not inlined content. Skip rows with an empty
`evidence` object; there is nothing to read for a `gap` requirement.

Read `.claude/skills/tender-assistant/` for writing style and draft structure before writing
anything.

## 3. Write the draft

Follow `tender-assistant`'s draft structure exactly: `cover-letter.md`, `matrix.md`,
`technical-response.md`, `past-performance.md`, `checklist.md`, all under `bids/<notice-id>/`.
Skip a file entirely if its section doesn't apply, per the skill.

For `matrix.md`, one row per scaffold requirement, in scaffold order:

```
| # | Requirement | Kind | Status | Covered by | Evidence |
|---|---|---|---|---|---|
```

Number rows sequentially starting at 1. The scaffold does not carry a separate solicitation
numbering field — if the notice numbered its criteria, that numbering is already inside `text`
(stage 2 was instructed to quote it). Do not invent a second numbering scheme.

For attachments the notice lists (`scaffold.json`'s `notice.attachments`) that you have not
read, note this explicitly in `checklist.md` rather than guessing at their contents — per the
design's error-handling policy, an unenriched attachment is reported at `/apply` time, not
silently skipped.

## 4. Report

Tell the user: which files were written, how many requirements are `gap` or `unclear` (these
need a human decision before submission), and whether the notice needs a re-run of `/rank` due
to `needs_rematch`.
