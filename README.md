# tendersearch

Finds Canadian federal tender opportunities matching a small consulting group's
capabilities, and helps decide which are worth bidding.

See `docs/superpowers/specs/2026-08-03-tendersearch-design.md` for the design.

## Setup

    python -m venv .venv && .venv/Scripts/activate   # Windows
    pip install -e ".[dev]"

## Use

    canadabuys fetch          # pull the latest open notices
    /profile <member>         # build or update a member profile (in Claude Code)
    /rank                     # filter, judge, and write today's digest

Real profiles live in `profiles/<member>/` and are git-ignored.
See `profiles/_example/profile.yml` for the schema.
