"""Generate a face-validity review sheet from a /rank run (Annex B, Pass 4).

Pass 4 is the only thing that makes a score mean anything. The scoring bands in
`.claude/skills/tender-matcher/SKILL.md` start as guesses; this turns a set of
real verdicts into something a human can read and correct in one sitting.

What it cannot do: tell you whether a high score predicts a win. Nothing here
knows who won anything. This checks the rubric against your judgment, which is
the best available signal until outcomes accumulate.

Sampling is stratified deliberately. Every verdict at or above the detail
threshold gets a full write-up, because a wrong call there costs a real
opportunity. Below it, a sample gets the same treatment, because that is where
a wrong call is *invisible* -- a genuine opportunity scored 8 looks exactly like
the 46 notices that deserve an 8.

Usage:
    python tools/pass4_review.py                      # newest run in matches/
    python tools/pass4_review.py matches/2026-08-04   # a specific run
    python tools/pass4_review.py --detail-above 30 --sample 20
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

STATUS_MARK = {"met": "[x]", "gap": "[ ]", "unclear": "[?]"}


def newest_run(matches_root: pathlib.Path) -> pathlib.Path | None:
    runs = sorted(p for p in matches_root.glob("*") if (p / "verdicts.json").exists())
    return runs[-1] if runs else None


def load_notices(repo: pathlib.Path) -> dict:
    """Reference -> Notice, for titles and buyers. Empty dict if unavailable."""
    sys.path.insert(0, str(repo))
    try:
        from canadabuys.store import NoticeStore
    except ImportError:
        return {}
    store_root = repo / "notices"
    if not store_root.exists():
        return {}
    return {n.reference: n for n in NoticeStore(store_root).all()}


def evenly_spaced(items: list, count: int) -> list:
    """Take `count` items spread across the list rather than the first N."""
    if count >= len(items):
        return items
    step = len(items) / count
    return [items[int(i * step)] for i in range(count)]


def write_verdict(out: list[str], v: dict, notices: dict, index: int) -> None:
    ref = v.get("reference", "?")
    notice = notices.get(ref)
    title = notice.title if notice else "(notice not in local store)"
    buyer = notice.entity if notice else "?"
    closing = notice.closing.date().isoformat() if notice and notice.closing else "?"
    lb = v.get("low_barrier") or {}

    out.append(f"### {index}. `{ref}` — score {v.get('score')} — **{v.get('recommendation')}**")
    out.append("")
    out.append(f"**{title}**")
    out.append("")
    out.append(f"- Buyer: {buyer}")
    out.append(f"- Closes: {closing}")
    if lb.get("is_low_barrier"):
        out.append(f"- Low-barrier: {lb.get('kind')} (confidence: {lb.get('confidence')})")
    out.append("")
    out.append(f"> {v.get('reasoning') or '(no reasoning recorded)'}")
    out.append("")

    requirements = v.get("requirements") or []
    if requirements:
        out.append("| | Requirement | Kind | Covered by | Note |")
        out.append("|---|---|---|---|---|")
        for r in requirements:
            mark = STATUS_MARK.get(r.get("status"), "[?]")
            text = (r.get("text") or "").replace("|", "\\|")[:150]
            note = (r.get("note") or "").replace("|", "\\|")[:90]
            out.append(
                f"| {mark} | {text} | {r.get('kind', '?')} | "
                f"{r.get('covered_by') or '—'} | {note} |"
            )
        out.append("")
    else:
        out.append("*No criteria extracted.* If the notice does state criteria, that is an")
        out.append("extraction failure — the most damaging error available, since everything")
        out.append("downstream is built on it.")
        out.append("")

    deal_breakers = v.get("deal_breakers") or []
    if deal_breakers:
        out.append("**Deal-breakers:** " + "; ".join(deal_breakers))
        out.append("")

    out.append("**Your call:** ☐ agree ☐ too high ☐ too low ☐ criteria wrong ☐ attribution wrong")
    out.append("")
    out.append("**Why / what the rubric should have done:**")
    out.append("")
    out.append("---")
    out.append("")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run", nargs="?", help="matches/<date> directory")
    parser.add_argument("--detail-above", type=int, default=20,
                        help="write full detail for every verdict at or above this score")
    parser.add_argument("--sample", type=int, default=15,
                        help="how many low-scoring verdicts to also detail")
    args = parser.parse_args(argv)

    run = pathlib.Path(args.run) if args.run else newest_run(REPO / "matches")
    if run is None or not (run / "verdicts.json").exists():
        print("No /rank run found. Run /rank first.", file=sys.stderr)
        return 1

    verdicts = json.loads((run / "verdicts.json").read_text(encoding="utf-8"))
    verdicts.sort(key=lambda v: -int(v.get("score") or 0))
    notices = load_notices(REPO)

    high = [v for v in verdicts if int(v.get("score") or 0) >= args.detail_above]
    low = [v for v in verdicts if int(v.get("score") or 0) < args.detail_above]
    sampled = evenly_spaced(low, args.sample)

    out: list[str] = []
    out.append(f"# Pass 4 — face-validity review of `{run.name}`")
    out.append("")
    out.append(f"{len(verdicts)} verdicts. {len(high)} scored {args.detail_above}+ and are all")
    out.append(f"detailed below; {len(sampled)} of the {len(low)} lower-scoring ones are sampled")
    out.append("across the range.")
    out.append("")
    out.append("## How to read this")
    out.append("")
    out.append("Work down the list and mark each call. In priority order, you are checking:")
    out.append("")
    out.append("1. **Criteria extraction** — are the listed requirements actually the notice's")
    out.append("   requirements, or did the model invent structure the notice does not contain?")
    out.append("   Everything else is worthless if this is wrong.")
    out.append("2. **Attribution** — is each covered requirement credited to someone who genuinely")
    out.append("   covers it?")
    out.append("3. **Gap honesty** — are real gaps reported as gaps, not softened to *unclear*?")
    out.append("4. **Score ordering** — ignore the absolute numbers. Is the *ranking* right?")
    out.append("   Anything high you would refuse to bid? Anything low you would have wanted?")
    out.append("5. **Low-barrier separation** — are vehicles surfaced separately from open")
    out.append("   competitions, and are `confidence: low` entries treated as unverified?")
    out.append("")
    out.append("Errors here are usually **systematic, not random** — a rubric that over-weights")
    out.append("title matches, treats a *preferred* qualification as a hard fail, or under-weights")
    out.append("a clearance requirement that is in fact fatal. Each systematic error is one edit to")
    out.append("`.claude/skills/tender-matcher/SKILL.md`. Note the pattern, not just the instance.")
    out.append("")
    out.append("**The one thing this cannot tell you** is whether a high score predicts a win.")
    out.append("Nothing here knows who won anything. You are checking the rubric against your own")
    out.append("judgment, which is the best available signal until real outcomes accumulate.")
    out.append("")
    out.append("---")
    out.append("")
    out.append(f"## A. Everything scoring {args.detail_above} or above")
    out.append("")
    out.append("A wrong call here costs a real opportunity.")
    out.append("")

    index = 1
    for v in high:
        write_verdict(out, v, notices, index)
        index += 1

    out.append(f"## B. Sample of those below {args.detail_above}")
    out.append("")
    out.append("A wrong call here is *invisible* — a genuine opportunity scored 8 looks exactly")
    out.append("like the ones that deserve an 8. This is the half most worth reading carefully.")
    out.append("")

    for v in sampled:
        write_verdict(out, v, notices, index)
        index += 1

    out.append("## C. All verdicts")
    out.append("")
    out.append("| Score | Rec | Reference | Title | Low-barrier |")
    out.append("|---|---|---|---|---|")
    for v in verdicts:
        ref = v.get("reference", "?")
        notice = notices.get(ref)
        title = (notice.title if notice else "?").replace("|", "\\|")[:70]
        lb = v.get("low_barrier") or {}
        kind = lb.get("kind", "none")
        mark = kind if lb.get("is_low_barrier") else "—"
        out.append(f"| {v.get('score')} | {v.get('recommendation')} | `{ref}` | {title} | {mark} |")
    out.append("")
    out.append("## What to change")
    out.append("")
    out.append("Systematic patterns you found, and the rubric edit each one implies:")
    out.append("")
    out.append("1. ")
    out.append("2. ")
    out.append("3. ")
    out.append("")
    out.append("Then edit `.claude/skills/tender-matcher/SKILL.md`, re-run `/rank`, and")
    out.append("regenerate this sheet to see whether the corrections took.")
    out.append("")

    target = run / "pass4-review.md"
    target.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {target}")
    print(f"  {len(verdicts)} verdicts | {len(high)} detailed at {args.detail_above}+ | "
          f"{len(sampled)} sampled below")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
