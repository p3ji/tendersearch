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
- **any** amended notice with an existing verdict (its `needs_rematch` flag is
  set) — the criteria or deadline may have moved under a decision already made
- a tracked bid whose deadline is within a week

Do not notify on an ordinary quiet day. The digest is written regardless and can
be read on demand; a notification that fires daily stops being read.

## Failure behaviour

A failed fetch or a feed schema change **must notify**. A silent failure looks
exactly like a quiet day and costs a deadline — this is the single failure mode
the design treats as unacceptable.
