import csv
import datetime
import pytest
from canadabuys.notice import Notice
from matching.profile import ServiceLine
from matching.filter import (
    FilterConfig, filter_notice,
    REASON_CLOSED, REASON_TOO_SOON, REASON_REGION, REASON_NO_SIGNAL, REASON_PASS,
)

NOW = datetime.datetime(2026, 8, 3, 12, 0, tzinfo=datetime.timezone.utc)
CONFIG = FilterConfig(min_turnaround_days=5, now=NOW)
INGEST_TS = "2026-08-03T12:00:00+00:00"


def base_row():
    with open("tests/fixtures/open_sample.csv", encoding="utf-8-sig", newline="") as f:
        return next(csv.DictReader(f))


def notice(**overrides) -> Notice:
    row = {
        **base_row(),
        "tenderStatus-appelOffresStatut-eng": "Open",
        "tenderClosingDate-appelOffresDateCloture": "2026-09-30T14:00:00",
        "regionsOfDelivery-regionsLivraison-eng": "*Ontario",
        "unspsc": "*81111500",
        "unspscDescription-eng": "*Software development",
        "gsin-nibs": "",
        "title-titre-eng": "Untitled",
        "tenderDescription-descriptionAppelOffres-eng": "",
        "selectionCriteria-criteresSelection-eng": "",
        **overrides,
    }
    return Notice.from_csv_row(row, "open", INGEST_TS)


LINE = ServiceLine(label="Data", unspsc=["81111500"], keywords=["data pipeline"])
REGIONS = ["Ontario"]


def test_passes_when_code_matches():
    r = filter_notice(notice(), [LINE], REGIONS, CONFIG)
    assert r.passed
    assert r.reason == REASON_PASS
    assert r.matched_codes == ["81111500"]
    assert r.matched_service_lines == ["Data"]


def test_passes_when_only_a_keyword_matches():
    # The 15% of notices with no procurement code are reachable only this way.
    r = filter_notice(
        notice(unspsc="", **{"tenderDescription-descriptionAppelOffres-eng":
                             "Seeking a data pipeline rebuild"}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed
    assert r.matched_keywords == ["data pipeline"]
    assert r.matched_codes == []


def test_keyword_matches_inside_the_selection_criteria_field():
    r = filter_notice(
        notice(unspsc="", **{"selectionCriteria-criteresSelection-eng":
                             "Bidder must demonstrate DATA PIPELINE experience"}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed, "keyword search must cover selection criteria, not just description"


def test_keyword_match_is_case_insensitive():
    r = filter_notice(
        notice(unspsc="", **{"title-titre-eng": "DATA PIPELINE Modernization"}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed


def test_keyword_matches_in_the_code_description():
    r = filter_notice(
        notice(unspsc="*99999999", **{"unspscDescription-eng": "*Data pipeline services"}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed


def test_rejects_when_no_code_and_no_keyword():
    r = filter_notice(
        notice(unspsc="*99999999", **{"unspscDescription-eng": "*Bulk cement",
                                      "title-titre-eng": "Cement supply"}),
        [LINE], REGIONS, CONFIG,
    )
    assert not r.passed
    assert r.reason == REASON_NO_SIGNAL


def test_rejects_a_closed_notice():
    r = filter_notice(
        notice(**{"tenderStatus-appelOffresStatut-eng": "Cancelled"}),
        [LINE], REGIONS, CONFIG,
    )
    assert not r.passed
    assert r.reason == REASON_CLOSED


def test_ignore_status_allows_closed_notices_through():
    cancelled = notice(**{"tenderStatus-appelOffresStatut-eng": "Cancelled"})

    default_result = filter_notice(cancelled, [LINE], REGIONS, CONFIG)
    assert not default_result.passed
    assert default_result.reason == REASON_CLOSED

    ignoring_status_config = FilterConfig(
        min_turnaround_days=5, now=NOW, ignore_status=True,
    )
    ignoring_result = filter_notice(cancelled, [LINE], REGIONS, ignoring_status_config)
    assert ignoring_result.passed
    assert ignoring_result.reason == REASON_PASS


def test_rejects_a_notice_closing_inside_the_turnaround_window():
    r = filter_notice(
        notice(**{"tenderClosingDate-appelOffresDateCloture": "2026-08-05T14:00:00"}),
        [LINE], REGIONS, CONFIG,
    )
    assert not r.passed
    assert r.reason == REASON_TOO_SOON


def test_accepts_a_notice_closing_exactly_at_the_threshold():
    # Boundary: 5 days out with min_turnaround_days=5 is biddable.
    r = filter_notice(
        notice(**{"tenderClosingDate-appelOffresDateCloture": "2026-08-08T13:00:00"}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed


def test_rejects_a_notice_in_an_unserved_region():
    r = filter_notice(
        notice(**{"regionsOfDelivery-regionsLivraison-eng": "*Nunavut Territory"}),
        [LINE], REGIONS, CONFIG,
    )
    assert not r.passed
    assert r.reason == REASON_REGION


def test_canada_wide_notice_matches_any_region():
    r = filter_notice(
        notice(**{"regionsOfDelivery-regionsLivraison-eng": "*Canada"}),
        [LINE], ["Ontario"], CONFIG,
    )
    assert r.passed, "a Canada-wide notice is deliverable from any province"


def test_notice_with_no_region_stated_passes():
    # Recall gate: 13% of notices omit fields. Absent data must not mean rejected.
    r = filter_notice(
        notice(**{"regionsOfDelivery-regionsLivraison-eng": ""}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed


def test_notice_with_no_closing_date_passes():
    r = filter_notice(
        notice(**{"tenderClosingDate-appelOffresDateCloture": ""}),
        [LINE], REGIONS, CONFIG,
    )
    assert r.passed, "missing closing date must not silently hide a notice"


def test_matches_against_any_service_line_not_all():
    other = ServiceLine(label="Change", unspsc=["80101500"], keywords=["change management"])
    r = filter_notice(notice(), [other, LINE], REGIONS, CONFIG)
    assert r.passed
    assert r.matched_service_lines == ["Data"]


def test_gsin_code_also_matches():
    line = ServiceLine(label="Services", gsin=["F059A"], keywords=[])
    r = filter_notice(
        notice(unspsc="", **{"gsin-nibs": "*F059A"}), [line], REGIONS, CONFIG,
    )
    assert r.passed
    assert r.matched_codes == ["F059A"]


def test_empty_service_lines_rejects_everything_rather_than_crashing():
    r = filter_notice(notice(), [], REGIONS, CONFIG)
    assert not r.passed
    assert r.reason == REASON_NO_SIGNAL


def test_empty_profile_regions_passes_rather_than_rejecting():
    # Recall gate: an empty profile-side regions list must read as "unspecified",
    # never as "serves nowhere". A YAML typo or half-filled profile that ends up
    # with regions=[] must not silently and permanently drop every notice that
    # states a region for that member. Do not "fix" this back to rejecting --
    # matching/profile.py separately guards against regions=[] at load time.
    r = filter_notice(notice(), [LINE], [], CONFIG)
    assert r.passed
