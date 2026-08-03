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

This is the step that makes stage 1 work, so do not skip it. It is not
optional polish: measured on the live feed, UNSPSC codes are present on only
84% of notices, GSIN on just 4%, and **15% of notices carry no procurement
code at all**. Those notices are reachable only by keyword match — skipping
this step means the group silently never sees them.

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
