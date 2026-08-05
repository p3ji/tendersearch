import csv
import pathlib

import pytest
import requests

from canadabuys import enrich as E
from canadabuys.notice import Notice
from canadabuys.store import NoticeStore

NOW = "2026-08-05T12:00:00+00:00"


def base_row():
    with open("tests/fixtures/open_sample.csv", encoding="utf-8-sig", newline="") as f:
        return next(csv.DictReader(f))


def notice(attachments: str, reference: str = "cb-1-000") -> Notice:
    return Notice.from_csv_row(
        {
            **base_row(),
            "referenceNumber-numeroReference": reference,
            "attachment-piecesJointes-eng": attachments,
        },
        "open",
        NOW,
    )


class FakeResponse:
    def __init__(self, body: bytes = b"pdf-bytes", status: int = 200, headers=None):
        self._body = body
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]


def test_filename_for_a_normal_pdf_url():
    assert E.filename_for("https://x.ca/a/b/100023064_npp_e.pdf") == "100023064_npp_e.pdf"


def test_filename_for_an_opaque_download_endpoint():
    # Some sources hand out a GUID with no filename. It must still produce
    # something openable rather than an empty name.
    name = E.filename_for(
        "https://sscp2pspc.ssc-spc.gc.ca/page.aspx/en/fil/download/FDBB4786-3FAA-4866"
    )
    assert name
    assert "/" not in name


def test_filename_for_url_with_no_path_falls_back():
    assert E.filename_for("https://x.ca") == "attachment"


def test_downloads_every_attachment(tmp_path, monkeypatch):
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: FakeResponse())
    n = notice("https://x.ca/a.pdf,https://x.ca/b.pdf")
    result = E.enrich(n, tmp_path)

    assert result.ok
    assert [f.status for f in result.files] == ["downloaded", "downloaded"]
    assert {p.name for p in result.directory.iterdir()} == {"a.pdf", "b.pdf"}


def test_a_second_run_uses_the_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: FakeResponse())
    n = notice("https://x.ca/a.pdf")
    E.enrich(n, tmp_path)

    def explode(*a, **k):
        raise AssertionError("should not re-download an attachment already on disk")

    monkeypatch.setattr(E.requests, "get", explode)
    assert [f.status for f in E.enrich(n, tmp_path).files] == ["cached"]


def test_one_failed_attachment_does_not_lose_the_others(tmp_path, monkeypatch):
    # A solicitation package is usually several files; the useful one may
    # still arrive even when a sibling 404s.
    def get(url, *a, **k):
        return FakeResponse(status=404) if "bad" in url else FakeResponse()

    monkeypatch.setattr(E.requests, "get", get)
    result = E.enrich(notice("https://x.ca/bad.pdf,https://x.ca/good.pdf"), tmp_path)

    statuses = {f.url: f.status for f in result.files}
    assert statuses["https://x.ca/bad.pdf"] == "failed"
    assert statuses["https://x.ca/good.pdf"] == "downloaded"
    assert not result.ok, "a failure must be visible, not swallowed"


def test_oversized_attachment_is_skipped_by_declared_length(tmp_path, monkeypatch):
    huge = {"Content-Length": str(E.MAX_BYTES + 1)}
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: FakeResponse(headers=huge))
    result = E.enrich(notice("https://x.ca/huge.zip"), tmp_path)
    assert result.files[0].status == "skipped"
    assert not (result.directory / "huge.zip").exists()


def test_oversized_attachment_is_stopped_mid_download(tmp_path, monkeypatch):
    # A server that declares no Content-Length must not be able to fill the disk.
    body = b"x" * (E.MAX_BYTES + 1024)
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: FakeResponse(body=body))
    result = E.enrich(notice("https://x.ca/huge.bin"), tmp_path)
    assert result.files[0].status == "skipped"
    assert not (result.directory / "huge.bin").exists(), "partial file must be removed"


def test_notice_with_no_attachments_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: FakeResponse())
    result = E.enrich(notice(""), tmp_path)
    assert result.files == []
    assert result.ok


def test_reference_containing_a_colon_gets_a_safe_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: FakeResponse())
    result = E.enrich(notice("https://x.ca/a.pdf", reference="SSC-22-00020507:T"), tmp_path)
    assert ":" not in result.directory.name
    assert (result.directory / "a.pdf").exists()


def test_enrich_reference_reports_an_unknown_notice(tmp_path):
    with pytest.raises(KeyError, match="canadabuys fetch"):
        E.enrich_reference("cb-does-not-exist", NoticeStore(tmp_path))


def test_cli_names_the_contact_when_there_is_nothing_to_download(tmp_path, capsys):
    # The feed lists no attachment for 4 of the 14 notices that survived triage
    # on a real run. Telling the user "no attachments" without saying who holds
    # the documents leaves them at a dead end.
    from canadabuys import cli
    store = NoticeStore(tmp_path)
    n = notice("", reference="cb-9-000")
    n.contact_name = "Senior Procurement Specialist"
    n.contact_email = "procurement@example.gc.ca"
    store.save(n)

    args = type("A", (), {"notices": str(tmp_path), "notice_id": "cb-9-000"})()
    assert cli.cmd_enrich(args) == 0

    out = capsys.readouterr().out
    assert "no attachments" in out
    assert "procurement@example.gc.ca" in out
    assert "never emails a buyer" in out


def test_cli_warns_when_a_lone_attachment_may_be_an_advertisement(tmp_path, capsys, monkeypatch):
    # The single highest-scoring notice of the 2026-08-04 run had exactly one
    # attachment, and it was a poster saying "obtain documents from <email>",
    # not the solicitation package.
    from canadabuys import cli
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: FakeResponse())
    store = NoticeStore(tmp_path)
    n = notice("https://x.ca/advert.pdf", reference="cb-9-001")
    n.contact_email = "procurement@example.gc.ca"
    store.save(n)

    args = type("A", (), {"notices": str(tmp_path), "notice_id": "cb-9-001"})()
    assert cli.cmd_enrich(args) == 0

    out = capsys.readouterr().out
    assert "advertisement" in out
    assert "procurement@example.gc.ca" in out
