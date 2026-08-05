import json

import pytest

from matching.outcome import (
    DECISIONS,
    EXCLUDED_FROM_FIT_TUNING,
    REASON_CODES,
    RESULTS,
    Outcome,
    OutcomeError,
    WinDetails,
    append,
    load_all,
    validate,
)


def make(**overrides) -> Outcome:
    base = dict(
        reference="cb-1-000",
        subject="pjiao",
        subject_kind="profile",
        date="2026-08-05",
        score_at_decision=70,
        recommendation_at_decision="bid",
        decision="bid",
        reason_code="poor-fit",
        notes="",
    )
    base.update(overrides)
    return Outcome(**base)


def test_a_valid_no_bid_passes_validation():
    validate(make(decision="no-bid", reason_code="clearance"))


def test_unknown_reason_code_is_rejected():
    with pytest.raises(OutcomeError, match="controlled vocabulary"):
        validate(make(reason_code="vibes"))


def test_unknown_decision_is_rejected():
    with pytest.raises(OutcomeError, match="decision"):
        validate(make(decision="maybe"))


def test_empty_reference_is_rejected():
    with pytest.raises(OutcomeError, match="reference"):
        validate(make(reference=""))


def test_invalid_subject_kind_is_rejected():
    with pytest.raises(OutcomeError, match="subject_kind"):
        validate(make(subject_kind="squad"))


def test_result_pending_is_valid_without_win_details():
    validate(make(decision="bid", result="pending"))


def test_result_won_without_win_details_is_rejected():
    # A win with no captured details is a lost opportunity to build the one
    # thing this group's profiles are short on: real past-performance evidence.
    with pytest.raises(OutcomeError, match="win_details"):
        validate(make(decision="bid", result="won"))


def test_result_won_with_win_details_passes():
    validate(make(
        decision="bid", result="won",
        win_details=WinDetails(value=85000, start="2026-01-01", end="2026-06-01",
                                client="Example Corp", reference_name="Sam",
                                reference_email="sam@example.com"),
    ))


def test_unknown_result_is_rejected():
    with pytest.raises(OutcomeError, match="result"):
        validate(make(result="withdrawn"))


def test_no_bid_never_requires_win_details():
    validate(make(decision="no-bid", reason_code="capability-gap", result=None))


def test_append_writes_one_json_line(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    append(path, make())
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["reference"] == "cb-1-000"
    assert record["decision"] == "bid"


def test_append_is_append_only_across_multiple_calls(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    append(path, make(reference="cb-1-000"))
    append(path, make(reference="cb-1-001"))
    append(path, make(reference="cb-1-002"))
    records = load_all(path)
    assert [r.reference for r in records] == ["cb-1-000", "cb-1-001", "cb-1-002"]


def test_append_validates_before_writing(tmp_path):
    # An invalid record must never reach disk -- outcomes.jsonl is the only
    # path to ever calibrating the rubric, and a bad record poisons that
    # analysis invisibly rather than raising later.
    path = tmp_path / "outcomes.jsonl"
    with pytest.raises(OutcomeError):
        append(path, make(reason_code="not-a-real-code"))
    assert not path.exists()


def test_load_all_on_missing_file_is_empty_not_an_error(tmp_path):
    assert load_all(tmp_path / "does-not-exist.jsonl") == []


def test_load_all_roundtrips_win_details(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    wd = WinDetails(value=42000, start="2026-02-01", end="2026-05-01",
                     client="Corp", reference_name="R", reference_email="r@x.ca")
    append(path, make(decision="bid", result="won", win_details=wd))
    loaded = load_all(path)[0]
    assert loaded.win_details == wd


def test_load_all_roundtrips_a_record_with_no_win_details(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    append(path, make(decision="no-bid"))
    loaded = load_all(path)[0]
    assert loaded.win_details is None


def test_load_all_reports_the_line_number_of_a_malformed_record(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    append(path, make(reference="cb-1-000"))
    with open(path, "a", encoding="utf-8") as f:
        f.write("not valid json\n")
    with pytest.raises(OutcomeError, match=":2:"):
        load_all(path)


def test_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    path.write_text(json.dumps(make().to_dict()) + "\n\n\n", encoding="utf-8")
    assert len(load_all(path)) == 1


def test_price_uncompetitive_and_incumbent_entrenched_are_valid_reason_codes():
    # These specifically mark competitive losses on well-fitted work; excluded
    # from fit-tuning, not from the vocabulary itself.
    validate(make(decision="bid", result="lost", reason_code="poor-fit",
                  result_reason="price-uncompetitive"))
    assert "price-uncompetitive" in REASON_CODES
    assert "incumbent-entrenched" in REASON_CODES


def test_excluded_from_fit_tuning_is_a_subset_of_reason_codes():
    # The two lists live next to each other specifically so they cannot drift
    # apart; assert that invariant rather than trusting eyeballing it.
    assert set(EXCLUDED_FROM_FIT_TUNING) <= set(REASON_CODES)


def test_decisions_and_results_are_exactly_the_documented_sets():
    assert set(DECISIONS) == {"bid", "no-bid"}
    assert set(RESULTS) == {"won", "lost", "no-award", "pending"}
