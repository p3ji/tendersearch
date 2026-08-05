"""Command-line entry point."""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import sys

import yaml

from canadabuys.enrich import enrich_reference
from canadabuys.fetch import FEEDS, fetch_feed, ingest
from canadabuys.store import NoticeStore, safe_filename
from matching.filter import FilterConfig, filter_all
from matching.lowbarrier import classify
from matching.outcome import REASON_CODES, Outcome, OutcomeError, WinDetails, append as append_outcome
from matching.profile import load_profiles
from matching.verdict import VerdictError, load_verdict


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def cmd_fetch(args) -> int:
    store = NoticeStore(pathlib.Path(args.notices))
    if args.file:
        raw = pathlib.Path(args.file).read_bytes()
    else:
        raw = fetch_feed(args.feed)
    try:
        summary = ingest(raw, store, args.feed, _now_iso())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"created={summary.created} amended={summary.amended} "
        f"unchanged={summary.unchanged} needs_rematch={len(summary.rematch_needed)}"
    )
    return 0


def cmd_stats(args) -> int:
    notices = list(NoticeStore(pathlib.Path(args.notices)).all())
    if not notices:
        # A store of zeros reads as a broken tool rather than an empty one.
        # This is the first command a new user runs, so name the next step.
        print(
            f"no notices stored yet in {args.notices}/ -- run `canadabuys fetch` "
            f"(or /scrape in Claude Code) first"
        )
        return 0
    print(f"stored: {len(notices)}")
    print(f"open: {sum(1 for n in notices if n.is_open())}")
    print(f"needing rematch: {sum(1 for n in notices if n.needs_rematch)}")
    print(f"with no procurement code: {sum(1 for n in notices if not n.unspsc and not n.gsin)}")
    return 0


def cmd_filter(args) -> int:
    """Run stage 1 and report what survived and what was dropped, by reason.

    This is Annex B Pass 2 (filter tuning): the reject histogram is how you
    tell an over-broad keyword list from an over-narrow one.
    """
    # A malformed profile must not silently narrow the recall gate: if ANY
    # profile fails to load, this is a hard stop, not a warning. Proceeding
    # on partial profile data would drop notices only the broken member
    # could have won, and those notices are never judged and never seen
    # again.
    profiles, errors = load_profiles(pathlib.Path(args.profiles), collect_errors=True)
    if errors:
        print("ERROR: one or more profiles failed to load; refusing to filter with "
              "partial profile data:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    if not profiles:
        print("ERROR: no usable profiles found", file=sys.stderr)
        return 1

    cfg_data = {}
    if pathlib.Path(args.config).exists():
        try:
            cfg_data = yaml.safe_load(pathlib.Path(args.config).read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            print(f"ERROR: could not parse config file {args.config}: {exc}", file=sys.stderr)
            return 1

    active_profiles = cfg_data.get("active_profiles") or []
    if active_profiles:
        by_id = {p.member_id: p for p in profiles}
        missing = [pid for pid in active_profiles if pid not in by_id]
        if missing:
            print(
                f"ERROR: active_profiles names unknown member(s): {', '.join(missing)}",
                file=sys.stderr,
            )
            return 1
        profiles = [by_id[pid] for pid in active_profiles]

    config = FilterConfig(
        min_turnaround_days=cfg_data.get("min_turnaround_days", 5),
        now=datetime.datetime.now(datetime.timezone.utc),
    )

    notices = list(NoticeStore(pathlib.Path(args.notices)).all())
    results = filter_all(notices, profiles, config)
    counts = collections.Counter(r.reason for r in results.values())
    passed = counts.get("pass", 0)

    print(f"notices: {len(notices)}")
    print(f"passed:  {passed}")
    for reason, count in counts.most_common():
        if reason != "pass":
            print(f"  dropped [{reason}]: {count}")
    if len(notices):
        print(f"pass rate: {passed / len(notices):.1%}")

    if args.json:
        records = []
        for n in notices:
            result = results[n.reference]
            if not result.passed and not args.include_rejected:
                continue
            lb = classify(n)
            records.append({
                "reference": n.reference,
                "title": n.title,
                "entity": n.entity,
                "closing": n.closing.isoformat() if n.closing else None,
                "needs_rematch": n.needs_rematch,
                "passed": result.passed,
                "reason": result.reason,
                "matched_codes": result.matched_codes,
                "matched_keywords": result.matched_keywords,
                "matched_service_lines": result.matched_service_lines,
                "low_barrier": {
                    "kind": lb.kind,
                    "confidence": lb.confidence,
                    "is_low_barrier": lb.is_low_barrier,
                },
            })
        out_path = pathlib.Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    return 0


def cmd_enrich(args) -> int:
    """Download a notice's attachments so the real criteria can be read.

    Serves the `investigate` verdict. The feed answers "am I structurally
    eligible?"; the solicitation documents answer "can I clear the specific
    bar?". Only the handful of notices that survive triage need the second.
    """
    store = NoticeStore(pathlib.Path(args.notices))
    try:
        result = enrich_reference(args.notice_id, store)
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    notice = store.load(args.notice_id)

    if not result.files:
        print(f"{result.reference}: no attachments listed on this notice.")
        print("The feed description is everything CanadaBuys carries for it.")
        _print_contact(notice)
        return 0

    for f in result.files:
        detail = f" ({f.detail})" if f.detail else ""
        name = f.path.name if f.path else f.url.rsplit("/", 1)[-1]
        print(f"  {f.status:<11} {name}{detail}")

    print(f"\n{result.directory}")

    # An attachment is often just a one-page advertisement pointing at a
    # procurement officer, not the solicitation package. Measured on the
    # 2026-08-04 run, that was 4 of the 14 notices that survived triage --
    # including the highest-scoring one. Read what came down before assuming
    # the criteria are in it.
    if len(result.files) == 1:
        print(
            "\nOnly one attachment. On this feed a lone file is often an advertisement\n"
            "rather than the solicitation package - read it before assuming the\n"
            "mandatory criteria are in there."
        )
        _print_contact(notice)

    if not result.ok:
        print("Some attachments could not be fetched - see above.", file=sys.stderr)
        return 1
    return 0


def _print_contact(notice) -> None:
    """Show who to ask when the documents are not published.

    Requesting a solicitation package is a human step, deliberately: automated
    contact with a contracting authority is permanently out of scope.
    """
    if notice is None:
        return
    contact = " / ".join(x for x in (notice.contact_name, notice.contact_email) if x)
    if contact:
        print(f"\nContact for documents: {contact}")
        print("Requesting them is a human step - this tool never emails a buyer.")


def cmd_outcome(args) -> int:
    """Append one decision record to outcomes.jsonl. Never edits the rubric.

    This is the deterministic half of /outcome: validating and writing the
    record. The interview -- which reason code, what happened, capturing win
    details while they are known -- is the LLM step in .claude/commands/outcome.md.
    Record no-bids here as diligently as bids; see matching/outcome.py.
    """
    win_details = None
    if args.result == "won":
        missing = [
            name for name, value in (
                ("--win-client", args.win_client),
                ("--win-value", args.win_value),
                ("--win-start", args.win_start),
                ("--win-end", args.win_end),
            )
            if not value
        ]
        if missing:
            print(
                f"ERROR: result is 'won' but missing {', '.join(missing)} -- "
                f"capture these now, while they are known. A win becomes this "
                f"group's past-performance evidence.",
                file=sys.stderr,
            )
            return 1
        win_details = WinDetails(
            client=args.win_client,
            value=float(args.win_value),
            start=args.win_start,
            end=args.win_end,
            reference_name=args.win_reference_name,
            reference_email=args.win_reference_email,
        )

    outcome = Outcome(
        reference=args.notice_id,
        subject=args.subject,
        subject_kind=args.subject_kind,
        date=args.date or datetime.date.today().isoformat(),
        score_at_decision=args.score,
        recommendation_at_decision=args.recommendation,
        decision=args.decision,
        reason_code=args.reason_code,
        notes=args.notes or "",
        result=args.result,
        result_reason=args.result_reason or "",
        debrief_notes=args.debrief_notes or "",
        win_details=win_details,
    )

    try:
        append_outcome(pathlib.Path(args.outcomes), outcome)
    except OutcomeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"recorded: {outcome.reference} | {outcome.decision} | {outcome.reason_code}")
    if win_details:
        print("win details captured -- consider adding this to the member's past_performance")
    return 0


def cmd_apply(args) -> int:
    """Assemble bids/<notice-id>/scaffold.json from an existing verdict.

    This is the deterministic half of /apply: resolving the verdict, the
    notice, and each covering member's evidence file paths. The /apply
    command (an LLM step) reads this scaffold plus the evidence files to
    write the actual matrix, checklist, and draft prose -- see
    .claude/commands/apply.md.
    """
    if args.profile and args.team:
        print("ERROR: pass --profile or --team, not both", file=sys.stderr)
        return 1
    subject = args.profile or args.team

    try:
        verdict = load_verdict(pathlib.Path(args.matches), args.notice_id, subject)
    except VerdictError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    notice = NoticeStore(pathlib.Path(args.notices)).load(args.notice_id)
    if notice is None:
        print(f"ERROR: no notice found for reference {args.notice_id!r}", file=sys.stderr)
        return 1

    if notice.needs_rematch:
        print(
            f"WARNING: notice {args.notice_id!r} was amended after the "
            f"{verdict.matches_date} verdict was written; the matrix may be "
            f"stale. Consider re-running /rank first.",
            file=sys.stderr,
        )

    profiles_root = pathlib.Path(args.profiles)
    profiles, errors = load_profiles(profiles_root, collect_errors=True)
    if errors:
        print("ERROR: one or more profiles failed to load; refusing to resolve "
              "evidence with partial profile data:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    by_id = {p.member_id: p for p in profiles}

    def _resolve_evidence(member) -> dict:
        return {
            label: str(profiles_root / member.member_id / rel_path)
            for label, rel_path in member.evidence.items()
        }

    requirements = []
    missing_members = set()
    covering_member_ids = set()
    for req in verdict.requirements:
        evidence = {}
        if req.covered_by:
            member = by_id.get(req.covered_by)
            if member is None:
                missing_members.add(req.covered_by)
            else:
                covering_member_ids.add(member.member_id)
                evidence = _resolve_evidence(member)
        requirements.append({
            "text": req.text,
            "kind": req.kind,
            "status": req.status,
            "covered_by": req.covered_by,
            "note": req.note,
            "evidence": evidence,
        })
    if missing_members:
        print(
            f"ERROR: verdict names member(s) not found in {profiles_root}: "
            f"{', '.join(sorted(missing_members))}",
            file=sys.stderr,
        )
        return 1

    # Structured past-performance records for each covering member, keyed by
    # member id so a member covering several requirements isn't duplicated
    # onto every row. Only members actually cited by some requirement's
    # covered_by are included. An empty past_performance list is normal (thin
    # procurement history by design) and is not an error.
    members = {
        member_id: {
            "name": by_id[member_id].name,
            "past_performance": by_id[member_id].past_performance,
            "evidence": _resolve_evidence(by_id[member_id]),
        }
        for member_id in sorted(covering_member_ids)
    }

    scaffold = {
        "notice": {
            "reference": notice.reference,
            "title": notice.title,
            "entity": notice.entity,
            "closing": notice.closing.isoformat() if notice.closing else None,
            "description": notice.description,
            "selection_criteria": notice.selection_criteria,
            "notice_url": notice.notice_url,
            "attachments": notice.attachments,
            "needs_rematch": notice.needs_rematch,
        },
        "verdict": {
            "subject": verdict.subject,
            "subject_kind": verdict.subject_kind,
            "score": verdict.score,
            "recommendation": verdict.recommendation,
            "low_barrier": {
                "is_low_barrier": verdict.low_barrier.is_low_barrier,
                "kind": verdict.low_barrier.kind,
            },
            "reasoning": verdict.reasoning,
            "deal_breakers": verdict.deal_breakers,
            "matches_date": verdict.matches_date,
        },
        "requirements": requirements,
        "members": members,
    }

    bid_dir = pathlib.Path(args.bids) / safe_filename(args.notice_id)
    out_path = bid_dir / "scaffold.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scaffold, indent=2, ensure_ascii=False), encoding="utf-8")
    # The notice id is sanitized for the directory name (colons and other
    # filesystem-unsafe characters -- see safe_filename), so state the
    # resolved directory explicitly rather than let a reader reconstruct
    # bids/<notice-id>/ from the raw reference, which would diverge on
    # references like "SSC-26-00034400:T".
    print(f"bid directory: {bid_dir}")
    print(f"wrote {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="canadabuys")
    parser.add_argument("--notices", default="notices", help="notice store root")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="pull a feed into the notice store")
    p_fetch.add_argument("--feed", choices=sorted(FEEDS), default="open")
    p_fetch.add_argument("--file", help="ingest a local CSV instead of fetching")
    p_fetch.set_defaults(func=cmd_fetch)

    p_stats = sub.add_parser("stats", help="summarize the notice store")
    p_stats.set_defaults(func=cmd_stats)

    p_filter = sub.add_parser("filter", help="run stage 1 and report the outcome")
    p_filter.add_argument("--profiles", default="profiles")
    p_filter.add_argument("--config", default="config.yml")
    p_filter.add_argument("--json", help="write stage-1 results (passing notices) to this path")
    p_filter.add_argument(
        "--include-rejected", action="store_true",
        help="include rejected notices in --json output (Annex B recall audit)",
    )
    p_filter.set_defaults(func=cmd_filter)

    p_enrich = sub.add_parser(
        "enrich", help="download one notice's attachments for a closer read"
    )
    p_enrich.add_argument("notice_id", help="notice reference number")
    p_enrich.set_defaults(func=cmd_enrich)

    p_apply = sub.add_parser("apply", help="assemble the bid scaffold for a judged notice")
    p_apply.add_argument("notice_id", help="notice reference number")
    p_apply.add_argument("--profile", help="disambiguate by member id")
    p_apply.add_argument("--team", help="disambiguate by team id")
    p_apply.add_argument("--profiles", default="profiles")
    p_apply.add_argument("--matches", default="matches")
    p_apply.add_argument("--bids", default="bids")
    p_apply.set_defaults(func=cmd_apply)

    p_outcome = sub.add_parser(
        "record-outcome", help="append one bid/no-bid decision to outcomes.jsonl"
    )
    p_outcome.add_argument("notice_id", help="notice reference number")
    p_outcome.add_argument("--subject", required=True, help="profile or team id")
    p_outcome.add_argument("--subject-kind", required=True, choices=("profile", "team"))
    p_outcome.add_argument("--score", required=True, type=int, help="score at decision time")
    p_outcome.add_argument("--recommendation", required=True,
                            help="recommendation at decision time, e.g. bid/no-bid/investigate")
    p_outcome.add_argument("--decision", required=True, choices=("bid", "no-bid"))
    p_outcome.add_argument("--reason-code", required=True, choices=REASON_CODES)
    p_outcome.add_argument("--notes", default="")
    p_outcome.add_argument("--date", help="ISO date; defaults to today")
    p_outcome.add_argument("--result", choices=("won", "lost", "no-award", "pending"))
    p_outcome.add_argument("--result-reason", default="")
    p_outcome.add_argument("--debrief-notes", default="")
    p_outcome.add_argument("--win-client")
    p_outcome.add_argument("--win-value")
    p_outcome.add_argument("--win-start")
    p_outcome.add_argument("--win-end")
    p_outcome.add_argument("--win-reference-name")
    p_outcome.add_argument("--win-reference-email")
    p_outcome.add_argument("--outcomes", default="outcomes.jsonl")
    p_outcome.set_defaults(func=cmd_outcome)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
