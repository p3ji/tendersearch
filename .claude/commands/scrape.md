---
description: Pull the latest CanadaBuys tender notices into the local store
---

Run the ingestion CLI and report what changed.

1. Run: `canadabuys fetch --feed open`
2. If it exits non-zero, STOP and show the error. A schema-change error means
   the feed changed — read `.agents/skills/canadabuys-search/url-reference.md`
   and reconcile before touching anything else. **Do not** work around it by
   loosening the column check; that trades a loud failure for a silent one.
3. Report created / amended / needs-rematch counts.
4. If any notices need rematching, say so and suggest running `/rank`.
