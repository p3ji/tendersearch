import csv
import io
import pathlib
import pytest
from canadabuys.fetch import parse_csv_bytes, ingest, FEEDS
from canadabuys.store import NoticeStore

NOW = "2026-08-03T12:00:00+00:00"
LATER = "2026-08-04T12:00:00+00:00"
FIXTURE = pathlib.Path("tests/fixtures/open_sample.csv")


@pytest.fixture
def raw():
    return FIXTURE.read_bytes()


def test_feeds_are_https_canadabuys_urls():
    assert set(FEEDS) == {"open", "new"}
    assert all(u.startswith("https://canadabuys.canada.ca/") for u in FEEDS.values())


def test_parse_handles_the_utf8_bom(raw):
    notices = parse_csv_bytes(raw, "open", NOW)
    assert len(notices) == 80
    # A BOM read as utf-8 corrupts the first column name, emptying every title.
    assert any(n.title for n in notices)
    assert all(n.reference for n in notices)


def test_ingest_creates_all_on_first_run(raw, tmp_path):
    summary = ingest(raw, NoticeStore(tmp_path), "open", NOW)
    assert summary.created == 80
    assert summary.amended == 0
    assert len(summary.rematch_needed) == 80


def test_ingest_is_idempotent(raw, tmp_path):
    store = NoticeStore(tmp_path)
    ingest(raw, store, "open", NOW)
    second = ingest(raw, store, "open", LATER)
    assert second.created == 0
    assert second.unchanged == 80
    assert len(list(store.all())) == 80


def test_malformed_csv_raises_rather_than_writing_nothing(tmp_path):
    # Silently writing an empty result is the one unacceptable failure --
    # it looks like a quiet day and costs a deadline.
    with pytest.raises(ValueError, match="expected column"):
        ingest(b"not,a,tender,feed\n1,2,3,4\n", NoticeStore(tmp_path), "open", NOW)


def test_empty_feed_raises(tmp_path):
    with pytest.raises(ValueError):
        ingest(b"", NoticeStore(tmp_path), "open", NOW)


@pytest.mark.parametrize("column", [
    "unspsc",
    "gsin-nibs",
    "unspscDescription-eng",
    "gsinDescription-nibsDescription-eng",
    "regionsOfDelivery-regionsLivraison-eng",
    "tenderDescription-descriptionAppelOffres-eng",
    "selectionCriteria-criteresSelection-eng",
    "noticeType-avisType-eng",
    "procurementMethod-methodeApprovisionnement-eng",
])
def test_missing_matching_critical_column_raises(raw, column):
    # If CanadaBuys renames any of these, row.get() silently returns None,
    # every notice loses its codes/text, stage 1 rejects everything, and
    # `canadabuys filter` prints "passed: 0" and exits 0 -- the exact
    # "quiet day" failure the design forbids. This must fail loudly instead.
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [f for f in reader.fieldnames if f != column]
    assert len(fieldnames) == len(reader.fieldnames) - 1, (
        f"fixture must contain {column!r} for this test to be meaningful"
    )
    rows = list(reader)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    mutated = buf.getvalue().encode("utf-8-sig")
    with pytest.raises(ValueError, match=column):
        parse_csv_bytes(mutated, "open", NOW)
