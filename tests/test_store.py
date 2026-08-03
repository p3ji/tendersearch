import csv
import dataclasses
import datetime
import pytest
from canadabuys.notice import Notice
from canadabuys.store import NoticeStore, REMATCH_FIELDS

T0 = "2026-08-01T09:00:00+00:00"
T1 = "2026-08-05T09:00:00+00:00"


def base_row():
    with open("tests/fixtures/open_sample.csv", encoding="utf-8-sig", newline="") as f:
        return next(csv.DictReader(f))


def make(**overrides) -> Notice:
    row = {**base_row(), **overrides}
    return Notice.from_csv_row(row, "open", overrides.pop("_now", T0))


@pytest.fixture
def store(tmp_path):
    return NoticeStore(tmp_path)


def test_save_then_load_roundtrip(store):
    n = make()
    store.save(n)
    assert store.load(n.reference) == n


def test_load_missing_returns_none(store):
    assert store.load("cb-does-not-exist") is None


def test_upsert_new_notice_reports_created(store):
    result = store.upsert(make(), T0)
    assert result.action == "created"
    assert result.needs_rematch is True, "a new notice has never been matched"


def test_upsert_identical_notice_is_unchanged(store):
    n = make()
    store.upsert(n, T0)
    result = store.upsert(n, T1)
    assert result.action == "unchanged"
    assert result.needs_rematch is False


def test_reingesting_does_not_create_duplicates(store):
    n = make()
    store.upsert(n, T0)
    store.upsert(n, T1)
    assert len(list(store.all())) == 1


def test_amendment_updates_in_place_not_as_new_file(store):
    store.upsert(make(**{"amendmentNumber-numeroModification": "000"}), T0)
    store.upsert(make(**{"amendmentNumber-numeroModification": "001"}), T1)
    all_notices = list(store.all())
    assert len(all_notices) == 1, "amendment must update the existing record"
    assert all_notices[0].amendment == 1


def test_amendment_changing_closing_date_sets_needs_rematch(store):
    store.upsert(make(**{
        "amendmentNumber-numeroModification": "000",
        "tenderClosingDate-appelOffresDateCloture": "2026-09-01T14:00:00",
    }), T0)
    result = store.upsert(make(**{
        "amendmentNumber-numeroModification": "001",
        "tenderClosingDate-appelOffresDateCloture": "2026-09-15T14:00:00",
    }), T1)
    assert result.action == "amended"
    assert result.needs_rematch is True
    assert "closing" in result.changed_fields
    assert store.load(result_ref(store)).needs_rematch is True


def result_ref(store):
    return next(store.all()).reference


def test_amendment_changing_description_sets_needs_rematch(store):
    store.upsert(make(**{
        "amendmentNumber-numeroModification": "000",
        "tenderDescription-descriptionAppelOffres-eng": "original scope",
    }), T0)
    result = store.upsert(make(**{
        "amendmentNumber-numeroModification": "001",
        "tenderDescription-descriptionAppelOffres-eng": "expanded scope",
    }), T1)
    assert result.needs_rematch is True
    assert "description" in result.changed_fields


def test_amendment_changing_only_contact_does_not_force_rematch(store):
    store.upsert(make(**{
        "amendmentNumber-numeroModification": "000",
        "contactInfoName-informationsContactNom": "A. Smith",
    }), T0)
    result = store.upsert(make(**{
        "amendmentNumber-numeroModification": "001",
        "contactInfoName-informationsContactNom": "B. Jones",
    }), T1)
    assert result.action == "amended"
    assert result.needs_rematch is False, "a contact change does not invalidate a verdict"


def test_older_amendment_does_not_overwrite_newer(store):
    store.upsert(make(**{"amendmentNumber-numeroModification": "002"}), T0)
    result = store.upsert(make(**{"amendmentNumber-numeroModification": "001"}), T1)
    assert result.action == "unchanged"
    assert next(store.all()).amendment == 2, "must not regress to an older amendment"


def test_first_seen_preserved_across_amendment(store):
    store.upsert(make(**{"amendmentNumber-numeroModification": "000"}), T0)
    store.upsert(make(**{"amendmentNumber-numeroModification": "001"}), T1)
    n = next(store.all())
    assert n.first_seen == T0, "first_seen records discovery, not last touch"
    assert n.last_updated == T1


def test_rematch_fields_are_the_three_the_spec_names():
    assert set(REMATCH_FIELDS) == {"closing", "description", "selection_criteria"}
