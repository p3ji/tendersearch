# Contributing

## The one rule everything follows from

**Stage 1 is a recall gate.** A notice it drops is never judged, never appears in a digest, and
is invisible to the user forever. Precision failures self-correct at stage 2 — a bad candidate
costs a few cents of judgment. Recall failures are permanent and silent.

So: when data is absent or ambiguous, the notice passes. If a change you are making rejects a
notice on a missing field, it is wrong, and the tests that assert otherwise are the point of
the tests. Two real bugs of exactly this shape have already shipped and been fixed — an empty
profile-side region list rejecting everything, and a status gate that ignored the
archive-analysis override. Assume there are more.

## What gets merged

- Bug fixes with a failing test that demonstrates the bug first.
- Feed-handling fixes when CanadaBuys changes something — with a fixture captured from the real
  feed, since the fixture is the schema contract.
- Improvements to the stage-2 rubric that are backed by verdicts you actually read, not by
  intuition about what ought to score well.
- Documentation that corrects something measurably wrong.

## What gets declined

- **Anything that adds an outbound action to an automated path.** No bid submission, no email to
  a contracting authority, no posting anywhere. A human reviews and sends, every time. This is
  not a roadmap item; it is permanently out of scope.
- **Anything that widens the `.gitignore` allowlist** for `profiles/` or `teams/`, or that
  weakens the CI privacy job.
- **Appendix items whose trigger has not fired.** The design spec's appendix lists deferred
  functionality — dashboard, award intelligence, semantic retrieval, outcome-driven rubric
  learning — each with an explicit trigger. Building one early means carrying its complexity on
  faith. If you think a trigger *has* fired, say which, and show the measurement.
- **Scoring changes justified by reasoning alone.** The bands are uncalibrated by admission.
  Change them from evidence — Annex B Pass 4, or recorded outcomes — and say what you read.

## New sources belong in forks first

A source skill for a provincial portal, MERX, or another country's tender system is the main
thing people will want to add.

**Check two things before you start, because either can end the project.** Surveyed 2026-08:

- **Does an open feed exist at all?** CanadaBuys is unusually generous. Ontario's open-data
  catalogue carries only a three-year *planned* outlook, not live notices; BC Bid runs on a
  commercial platform with no open feed. Most portals mean HTML scraping, with the
  crawl-policy and fragility that implies.
- **How often does it republish, and how long are the windows?** The two only matter
  together. Quebec's SEAO publishes weekly, which sounds worse than CanadaBuys' daily until you
  measure the windows: median 27 days, and 1 of 185 notices closing inside 14. Weekly is
  comfortable there. A monthly feed against 10-day windows would not be. Measure both before
  deciding, and record them in `url-reference.md`.

`/add-source` asks both questions first. Reporting back "this portal has no usable feed" is a
useful result, not a failed attempt.

**Run `/add-source` in Claude Code** — it walks the steps below,
investigates the feed before writing any parser, and enforces the source contract (namespaced
references, timezone-aware closing dates, a status that normalizes to `open`, absent data
passing rather than rejecting). Those are the failures that are silent rather than loud, which
is why the command exists instead of a checklist.

Whether you use it or build by hand, the result must be:

- One self-contained folder under `.agents/skills/<source>-search/` — a CLI, a `SKILL.md`, and a
  `url-reference.md` recording the feed's measured quirks (the CanadaBuys one documents a BOM,
  `*`-prefixed newline-separated multi-values, no contract-value column, in-place amendments,
  and 15% of notices carrying no procurement code — expect your feed to have its own set).
- Normalize into the existing `Notice` schema. If you do, the matcher, digest, and `/apply` need
  no changes at all. If you cannot, say why in the PR — that is a real finding about the schema.
- Tests against checked-in fixtures, passing with no network access.

Then post it to the [fork index](https://github.com/p3ji/tendersearch/discussions/1) so others can find
it. A tested source skill is worth far more than someone rediscovering a feed's quirks from
scratch. Upstreaming is possible for sources with broad reach, but a fork plus a Discussion post
is the expected path and needs no permission.

## Claims get verified

State what you ran and paste the output. "Tests pass" is not evidence; the command and its
result are. If you changed feed parsing, say which fixture proves it. If you fixed a filter bug,
show the test failing before and passing after.

This matters more than usual here because several of this project's bugs were invisible by
construction. A path bug once wrote notices into NTFS alternate data streams, losing 10 of 80
records with no error raised — and a naive round-trip test still passed, because Windows
resolves an exact-path lookup straight into the stream. Only a directory listing exposed it. If
your test cannot fail, it is not testing anything.

## Practical notes

Before opening a PR:

```bash
pytest                          # full suite, offline
python tools/lint_skills.py     # command and skill frontmatter
```

CI runs both across Python 3.11–3.13 on Linux, plus a check that no personal data is tracked.

- **Never commit anything under `profiles/` or `teams/`** beyond the two example files. They
  hold real resumes and client names. See [SECURITY.md](SECURITY.md).
- Tests never touch the network. A test that does is a bug in the test.
- `canadabuys/` owns all I/O and contains no judgment. `matching/` is pure functions — no I/O,
  no LLM. Judgment lives in markdown skills. Keep those boundaries; they are what make the feed
  layer replaceable.
- Conventional commit prefixes (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`).
