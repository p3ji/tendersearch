import csv
import datetime
from canadabuys.notice import Notice

FIXTURE = "tests/fixtures/open_sample.csv"
NOW = "2026-08-03T12:00:00+00:00"


def load_rows():
    with open(FIXTURE, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_parses_every_fixture_row_without_error():
    rows = load_rows()
    notices = [Notice.from_csv_row(r, "open", NOW) for r in rows]
    assert len(notices) == len(rows)
    assert all(n.reference for n in notices), "every notice must have a reference number"


def test_amendment_is_an_int_not_a_string():
    # "000" and "001" must compare numerically; string compare breaks at "010".
    n = Notice.from_csv_row(
        {**load_rows()[0], "amendmentNumber-numeroModification": "010"}, "open", NOW
    )
    assert n.amendment == 10


def test_missing_amendment_defaults_to_zero():
    n = Notice.from_csv_row(
        {**load_rows()[0], "amendmentNumber-numeroModification": ""}, "open", NOW
    )
    assert n.amendment == 0


def test_multivalue_fields_are_lists():
    n = Notice.from_csv_row(
        {**load_rows()[0], "unspsc": "*12160000\n*12350000"}, "open", NOW
    )
    assert n.unspsc == ["12160000", "12350000"]


def test_roundtrip_through_dict_is_lossless():
    original = Notice.from_csv_row(load_rows()[0], "open", NOW)
    restored = Notice.from_dict(original.to_dict())
    assert restored == original


def test_to_dict_is_json_serializable():
    import json
    d = Notice.from_csv_row(load_rows()[0], "open", NOW).to_dict()
    json.loads(json.dumps(d))  # raises if a date leaked through unserialized


def test_searchable_text_includes_title_description_and_code_descriptions():
    n = Notice.from_csv_row(
        {
            **load_rows()[0],
            "title-titre-eng": "Advisory Services",
            "tenderDescription-descriptionAppelOffres-eng": "Organizational readiness",
            "selectionCriteria-criteresSelection-eng": "Lowest price",
            "unspscDescription-eng": "*Management consulting",
        },
        "open",
        NOW,
    )
    text = n.searchable_text()
    assert "advisory services" in text
    assert "organizational readiness" in text
    assert "lowest price" in text
    assert "management consulting" in text
    assert text == text.lower(), "searchable text must be lowercased for matching"


def test_is_open_reflects_status():
    row = load_rows()[0]
    assert Notice.from_csv_row(
        {**row, "tenderStatus-appelOffresStatut-eng": "Open"}, "open", NOW
    ).is_open()
    for closed in ("Expired", "Cancelled", ""):
        assert not Notice.from_csv_row(
            {**row, "tenderStatus-appelOffresStatut-eng": closed}, "open", NOW
        ).is_open()


def test_closing_datetime_is_timezone_aware():
    n = Notice.from_csv_row(
        {**load_rows()[0], "tenderClosingDate-appelOffresDateCloture": "2026-08-19T14:00:00"},
        "open",
        NOW,
    )
    assert n.closing.tzinfo is not None
    assert n.closing.hour == 14


def test_first_seen_and_source_feed_recorded():
    n = Notice.from_csv_row(load_rows()[0], "open", NOW)
    assert n.first_seen == NOW
    assert n.last_updated == NOW
    assert n.source_feed == "open"
    assert n.needs_rematch is False


def test_comma_joined_attachments_become_separate_urls():
    # 273 of 920 live notices pack multiple PDFs into one comma-joined entry.
    # Treating that as a single attachment breaks anything that fetches them.
    n = Notice.from_csv_row(
        {
            **load_rows()[0],
            "attachment-piecesJointes-eng": "https://x.ca/a.pdf,https://x.ca/b.pdf",
        },
        "open",
        NOW,
    )
    assert n.attachments == ["https://x.ca/a.pdf", "https://x.ca/b.pdf"]
