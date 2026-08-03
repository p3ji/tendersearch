import datetime
import pytest
from canadabuys.fields import split_multi, parse_date, parse_datetime, FEED_TZ


def test_split_multi_single_value_strips_star():
    assert split_multi("*Canada") == ["Canada"]


def test_split_multi_newline_separated():
    assert split_multi("*12160000\n*12350000") == ["12160000", "12350000"]


def test_split_multi_handles_carriage_returns():
    assert split_multi("*A\r\n*B") == ["A", "B"]


def test_split_multi_empty_is_empty_list():
    assert split_multi("") == []
    assert split_multi(None) == []


def test_split_multi_value_without_star_still_parsed():
    # Defensive: the feed always prefixes, but a missing star must not lose data.
    assert split_multi("Canada") == ["Canada"]


def test_parse_date():
    assert parse_date("2026-08-03") == datetime.date(2026, 8, 3)


def test_parse_date_empty_is_none():
    assert parse_date("") is None
    assert parse_date(None) is None


def test_parse_datetime_attaches_feed_timezone():
    got = parse_datetime("2026-08-19T14:00:00")
    assert got == datetime.datetime(2026, 8, 19, 14, 0, tzinfo=FEED_TZ)
    assert got.tzinfo is not None, "naive datetimes cause wrong deadline math"


def test_parse_datetime_empty_is_none():
    assert parse_datetime("") is None


def test_parse_datetime_malformed_raises():
    with pytest.raises(ValueError):
        parse_datetime("19 August 2026")
