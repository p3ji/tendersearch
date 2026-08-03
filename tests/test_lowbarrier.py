import csv
from canadabuys.notice import Notice
from matching.lowbarrier import (
    classify, KIND_NONE, KIND_SUPPLY_ARRANGEMENT, KIND_STANDING_OFFER,
    KIND_ACAN, KIND_SUBCONTRACT, CONFIDENCE_HIGH, CONFIDENCE_LOW,
)

TS = "2026-08-03T12:00:00+00:00"


def notice(**overrides) -> Notice:
    with open("tests/fixtures/open_sample.csv", encoding="utf-8-sig", newline="") as f:
        row = next(csv.DictReader(f))
    row = {**row, "noticeType-avisType-eng": "Request for Proposal",
           "procurementMethod-methodeApprovisionnement-eng": "Competitive - Open bidding",
           "tenderDescription-descriptionAppelOffres-eng": "", **overrides}
    return Notice.from_csv_row(row, "open", TS)


def test_supply_arrangement_detected():
    r = classify(notice(**{"noticeType-avisType-eng": "Request for Supply Arrangement"}))
    assert r.is_low_barrier
    assert r.kind == KIND_SUPPLY_ARRANGEMENT


def test_rfp_against_supply_arrangement_detected():
    r = classify(notice(**{"noticeType-avisType-eng": "RFP against Supply Arrangement"}))
    assert r.is_low_barrier
    assert r.kind == KIND_SUPPLY_ARRANGEMENT


def test_standing_offer_detected():
    r = classify(notice(**{"noticeType-avisType-eng": "Request for Standing Offer"}))
    assert r.is_low_barrier
    assert r.kind == KIND_STANDING_OFFER


def test_acan_detected_by_notice_type():
    r = classify(notice(**{"noticeType-avisType-eng": "Advance Contract Award Notice"}))
    assert r.is_low_barrier
    assert r.kind == KIND_ACAN


def test_acan_detected_by_procurement_method_when_notice_type_is_blank():
    # noticeType is empty on 13% of notices; the method field is the fallback.
    r = classify(notice(**{
        "noticeType-avisType-eng": "",
        "procurementMethod-methodeApprovisionnement-eng": "Advance contract award notice",
    }))
    assert r.is_low_barrier
    assert r.kind == KIND_ACAN


def test_subcontracting_detected_in_description():
    r = classify(notice(**{
        "tenderDescription-descriptionAppelOffres-eng":
            "Prime contractors are encouraged to identify subcontracting opportunities.",
    }))
    assert r.is_low_barrier
    assert r.kind == KIND_SUBCONTRACT
    assert "subcontract" in r.evidence.lower()


def test_ordinary_open_rfp_is_not_low_barrier():
    r = classify(notice())
    assert not r.is_low_barrier
    assert r.kind == KIND_NONE


def test_blank_notice_type_and_method_is_not_low_barrier():
    r = classify(notice(**{"noticeType-avisType-eng": "",
                           "procurementMethod-methodeApprovisionnement-eng": ""}))
    assert not r.is_low_barrier


def test_classification_is_case_insensitive():
    r = classify(notice(**{"noticeType-avisType-eng": "REQUEST FOR STANDING OFFER"}))
    assert r.is_low_barrier


def test_notice_type_wins_over_description_heuristic():
    r = classify(notice(**{
        "noticeType-avisType-eng": "Request for Standing Offer",
        "tenderDescription-descriptionAppelOffres-eng": "subcontracting opportunities exist",
    }))
    assert r.kind == KIND_STANDING_OFFER, "explicit notice type beats a description keyword"


def test_structured_signals_are_high_confidence():
    # Structured noticeType and procurementMethod signals are high-confidence.
    r1 = classify(notice(**{"noticeType-avisType-eng": "Request for Supply Arrangement"}))
    assert r1.confidence == CONFIDENCE_HIGH

    r2 = classify(notice(**{"noticeType-avisType-eng": "Request for Standing Offer"}))
    assert r2.confidence == CONFIDENCE_HIGH

    r3 = classify(notice(**{"noticeType-avisType-eng": "Advance Contract Award Notice"}))
    assert r3.confidence == CONFIDENCE_HIGH

    # procurementMethod fallback is also high-confidence.
    r4 = classify(notice(**{
        "noticeType-avisType-eng": "",
        "procurementMethod-methodeApprovisionnement-eng": "Advance contract award notice",
    }))
    assert r4.confidence == CONFIDENCE_HIGH


def test_description_derived_subcontract_is_low_confidence():
    # Description-keyword heuristic is low-confidence.
    r = classify(notice(**{
        "tenderDescription-descriptionAppelOffres-eng":
            "Prime contractors are encouraged to identify subcontracting opportunities.",
    }))
    assert r.confidence == CONFIDENCE_LOW
    assert r.kind == KIND_SUBCONTRACT


def test_kind_none_result_has_a_confidence_value():
    # Non-low-barrier results still carry a valid confidence value.
    r = classify(notice())
    assert r.kind == KIND_NONE
    assert r.confidence == CONFIDENCE_HIGH
