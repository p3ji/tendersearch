<!-- Adding a source skill for another portal or jurisdiction? Those live in
     forks — see CONTRIBUTING.md — and get found via the Discussions board.
     You do not need permission and you do not need to upstream it. -->

## What changed and why

## Failing case (for fixes)
<!-- What was broken, and the test that demonstrates it. If the bug was silent
     — no error raised — say how your test would fail if the fix were reverted. -->

## Verification
<!-- Paste the commands and their output, not a summary.
     pytest
     python tools/lint_skills.py -->

## Checklist

- [ ] Tests pass offline; no test reaches the network
- [ ] Nothing under `profiles/` or `teams/` is committed beyond the example files
- [ ] If this touches stage 1: absent or ambiguous data still lets a notice through
- [ ] If this adds an outbound action, it is on a human-triggered path, not an automated one
