import json
import pathlib

import pytest

from matching.verdict import VerdictError, load_verdict, load_verdicts

REFERENCE = "cb-450-77537023"


def write_verdicts(root: pathlib.Path, date: str, records: list[dict]) -> None:
    d = root / date
    d.mkdir(parents=True, exist_ok=True)
    (d / "verdicts.json").write_text(json.dumps(records), encoding="utf-8")


def make_record(**overrides) -> dict:
    record = {
        "reference": REFERENCE,
        "subject": "alex",
        "subject_kind": "profile",
        "score": 82,
        "recommendation": "bid",
        "low_barrier": {"is_low_barrier": False, "kind": "none"},
        "requirements": [
            {"text": "3.1 valid security clearance", "kind": "mandatory",
             "status": "met", "covered_by": "alex", "note": "Reliability on file"},
        ],
        "reasoning": "Strong fit, all mandatories met.",
        "deal_breakers": [],
    }
    record.update(overrides)
    return record


def test_load_verdict_returns_the_only_candidate(tmp_path):
    write_verdicts(tmp_path, "2026-08-01", [make_record()])
    verdict = load_verdict(tmp_path, REFERENCE)
    assert verdict.subject == "alex"
    assert verdict.score == 82
    assert verdict.requirements[0].covered_by == "alex"
    assert verdict.matches_date == "2026-08-01"


def test_load_verdict_raises_when_none_exists(tmp_path):
    with pytest.raises(VerdictError, match="no verdict found"):
        load_verdict(tmp_path, REFERENCE)


def test_load_verdict_raises_when_matches_root_does_not_exist(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(VerdictError, match="no verdict found"):
        load_verdict(missing, REFERENCE)


def test_load_verdict_disambiguates_by_subject(tmp_path):
    write_verdicts(tmp_path, "2026-08-01", [
        make_record(subject="alex"),
        make_record(subject="priya", score=55),
    ])
    verdict = load_verdict(tmp_path, REFERENCE, subject="priya")
    assert verdict.subject == "priya"
    assert verdict.score == 55


def test_load_verdict_raises_when_ambiguous_without_subject(tmp_path):
    write_verdicts(tmp_path, "2026-08-01", [
        make_record(subject="alex"),
        make_record(subject="priya"),
    ])
    with pytest.raises(VerdictError, match="multiple subjects"):
        load_verdict(tmp_path, REFERENCE)


def test_load_verdict_raises_when_subject_not_found(tmp_path):
    write_verdicts(tmp_path, "2026-08-01", [make_record(subject="alex")])
    with pytest.raises(VerdictError, match="no verdict found"):
        load_verdict(tmp_path, REFERENCE, subject="priya")


def test_load_verdict_prefers_the_most_recent_date_for_the_same_subject(tmp_path):
    write_verdicts(tmp_path, "2026-07-01", [make_record(score=40)])
    write_verdicts(tmp_path, "2026-08-01", [make_record(score=90)])
    verdict = load_verdict(tmp_path, REFERENCE)
    assert verdict.score == 90
    assert verdict.matches_date == "2026-08-01"


def test_load_verdicts_returns_every_matching_record_across_dates(tmp_path):
    write_verdicts(tmp_path, "2026-07-01", [make_record(score=40)])
    write_verdicts(tmp_path, "2026-08-01", [make_record(score=90)])
    verdicts = load_verdicts(tmp_path, REFERENCE)
    assert [v.matches_date for v in verdicts] == ["2026-08-01", "2026-07-01"]


def test_load_verdict_raises_a_clear_error_on_malformed_json(tmp_path):
    d = tmp_path / "2026-08-01"
    d.mkdir(parents=True)
    (d / "verdicts.json").write_text("not json", encoding="utf-8")
    with pytest.raises(VerdictError, match="could not read verdicts"):
        load_verdict(tmp_path, REFERENCE)
