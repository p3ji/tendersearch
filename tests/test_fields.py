import datetime
import pytest
from canadabuys.fields import split_multi, split_urls, parse_date, parse_datetime, FEED_TZ


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


def test_split_urls_handles_comma_separated_attachments():
    # Attachments do NOT follow the star/newline convention every other
    # multi-value field uses -- they are comma-joined. Measured on the live
    # feed: 273 of 920 notices carry more than one URL in a single entry.
    raw = "https://x.ca/a.pdf,https://x.ca/b.pdf,https://x.ca/c.pdf"
    assert split_urls(raw) == ["https://x.ca/a.pdf", "https://x.ca/b.pdf", "https://x.ca/c.pdf"]


def test_split_urls_handles_a_single_url():
    assert split_urls("https://x.ca/a.pdf") == ["https://x.ca/a.pdf"]


def test_split_urls_handles_the_star_prefix_too():
    # Belt and braces: the feed prefixes some multi-values with *.
    assert split_urls("*https://x.ca/a.pdf") == ["https://x.ca/a.pdf"]


def test_split_urls_handles_both_separators_together():
    raw = "*https://x.ca/a.pdf,https://x.ca/b.pdf\n*https://x.ca/c.pdf"
    assert split_urls(raw) == ["https://x.ca/a.pdf", "https://x.ca/b.pdf", "https://x.ca/c.pdf"]


def test_split_urls_empty_is_empty_list():
    assert split_urls("") == []
    assert split_urls(None) == []


def test_split_urls_drops_fragments_that_are_not_urls():
    # A trailing comma or stray token must not become a bogus "URL".
    assert split_urls("https://x.ca/a.pdf,") == ["https://x.ca/a.pdf"]
