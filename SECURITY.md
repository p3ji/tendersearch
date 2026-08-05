# Security Policy

## Reporting a vulnerability

Open a [private security advisory](https://github.com/p3ji/tendersearch/security/advisories/new)
rather than a public issue. If that is unavailable to you, open an issue saying only that you
have a security report and asking for a contact route — do not include the details.

Expect an acknowledgement within a week. This is a small project maintained in spare time;
there is no bounty.

## Threat model, honestly stated

This repository ships code that runs on your machine, with pre-approved permissions, against
your colleagues' personal data. That is the shape of the risk. Being specific about it:

**What this project holds that is worth protecting.** `profiles/<member>/` contains real
resumes, employment history, security-clearance levels, and — once past performance is
recorded — real client names, contract values, and referee contact details. `teams/` names who
works with whom. For a consulting group this is both personal data and commercially sensitive.
None of it is encrypted; it is protected only by living on your machine and being git-ignored.

**The `.gitignore` allowlist is load-bearing.** `profiles/*` and `teams/*` are ignored except
`profiles/_example/` and `teams/_example.yml`. Widening those rules — or adding a real profile
under a path the allowlist happens to permit — publishes personal data the moment you push. It
cannot be undone by a revert, because it is already public. CI asserts that nothing beyond the
two example files is tracked; do not weaken that job.

**Pre-approved permissions.** `.claude/settings.json` allowlists commands that then run without
prompting. Every entry is a standing grant. Read a diff to that file the way you would read a
diff to `sudoers`.

**Third-party source skills are code execution.** The architecture invites new source skills
under `.agents/skills/`, and copying one from another fork means running someone else's code on
your machine against the data described above. Before you run one: read all of it, confirm the
only network calls go to the portal it claims to search, confirm it adds no dependencies and no
package lifecycle scripts, confirm it writes nothing outside its own folder, and run its tests
offline. A well-built source skill passes with no network access at all.

**Prompt injection is a real surface here.** Stage-2 judgment reads `tenderDescription` text
straight from a government feed and passes it to an LLM. That text is data, not instructions.
It is untrusted in the specific sense that it is written by third parties and never validated
by this project. A notice whose description contained instructions aimed at the model would be
attempting injection. The mitigations that matter are architectural: the matcher only ever
writes verdicts to disk, nothing in the daily path can submit a bid, contact a buyer, or send
mail, and every outbound action is a human step. Keep it that way — see below.

**What this project deliberately cannot do.** It holds no credentials and needs no API key. It
reads one public open-data feed over HTTPS. It never submits a bid, emails a contracting
authority, or transmits your profile data anywhere. Any change that adds an outbound action to
an automated path is a security change, not a feature, and should be treated as such in review.

## Scope notes

**In scope:** anything that leaks profile or team data; anything that widens the `.gitignore`
allowlist or the permission allowlist without it being obvious; a path that lets untrusted feed
content cause an action rather than a verdict; a dependency with a known vulnerability.

**Not in scope:** the matcher scoring a tender wrongly — that is a correctness bug, and the
scoring bands are explicitly uncalibrated until the Annex B passes are run. The CanadaBuys feed
itself. Claude Code and its own permission model.
