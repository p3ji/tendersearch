"""On-demand download of a notice's attachments.

Deliberately NOT on the daily path. Stage 1 and stage 2 both run entirely off
the feed, because the feed carries enough to decide the question that matters
most: am I structurally eligible? Measured on a real run, 65 of 85 verdicts
identified their deal-breaker from the description alone -- "not a TBIPS SA
holder", "restricted to named suppliers", "wrong specialty". None of that
needs a PDF.

What the feed cannot answer is the *second* question -- can I clear the
specific bar? Minimum years, reference projects, named certifications. Those
live in the solicitation documents. On that same run only 11 of 85 notices
reached the point where it mattered, and the rubric had already marked 9 of
them `investigate` rather than guessing.

So this exists to serve `investigate`, one notice at a time. Putting it on the
daily path would pay the fragility cost of network I/O over ~900 notices to
answer a question that arises for about eleven.

**What it will and will not get you.** Measured against the 14 notices that
survived triage on the 2026-08-04 run:

    6 of 14   attachments are a real solicitation package -- criteria answered
    4 of 14   attachment is a one-page advertisement, and the package itself is
              obtained by emailing the contracting authority
    4 of 14   no attachments at all; the feed is everything there is

So this closes the loop for under half the notices that reach it. The ad-only
case is not an edge case -- it caught the single highest-scoring notice of that
run, a WSCC survey RFP whose entire attachment was a poster ending "interested
parties may obtain documents from: Procurementmailbox@wscc.nt.ca".

When there is nothing useful to download, the CLI prints the notice's contact
details, because the next step is a human emailing the buyer. That step stays
human by design: automated contact with contracting authorities is permanently
out of scope. See SECURITY.md.

Files are downloaded, not parsed. Claude Code reads PDFs natively, and adding a
PDF text-extraction dependency to serve a handful of notices per week is not a
trade worth making.
"""

from __future__ import annotations

import dataclasses
import pathlib
import urllib.parse

import requests

from canadabuys.fetch import _USER_AGENT
from canadabuys.notice import Notice
from canadabuys.store import NoticeStore, safe_filename

# A solicitation package is rarely large. Anything past this is more likely a
# drawing set or a data dump than something worth reading before a bid/no-bid,
# so it is skipped loudly rather than silently filling the disk.
MAX_BYTES = 50 * 1024 * 1024


@dataclasses.dataclass
class Downloaded:
    url: str
    path: pathlib.Path | None
    status: str          # "downloaded" | "cached" | "skipped" | "failed"
    detail: str = ""


@dataclasses.dataclass
class EnrichResult:
    reference: str
    directory: pathlib.Path
    files: list[Downloaded]

    @property
    def ok(self) -> bool:
        return all(f.status in ("downloaded", "cached") for f in self.files)


def filename_for(url: str) -> str:
    """A safe local filename for an attachment URL.

    Some sources hand out opaque download endpoints with no filename
    (`.../page.aspx/en/fil/download/FDBB4786-...`), so fall back to the last
    path segment and let the caller open it by inspection.
    """
    path = urllib.parse.urlparse(url).path
    name = pathlib.PurePosixPath(path).name or "attachment"
    return safe_filename(urllib.parse.unquote(name))[:120]


def attachment_dir(root: pathlib.Path, reference: str) -> pathlib.Path:
    return pathlib.Path(root) / "attachments" / safe_filename(reference)


def download(url: str, dest: pathlib.Path, timeout: int = 120) -> Downloaded:
    if dest.exists() and dest.stat().st_size > 0:
        return Downloaded(url, dest, "cached")

    try:
        response = requests.get(
            url, timeout=timeout, headers={"User-Agent": _USER_AGENT}, stream=True
        )
        response.raise_for_status()

        declared = response.headers.get("Content-Length")
        if declared and int(declared) > MAX_BYTES:
            return Downloaded(url, None, "skipped", f"{int(declared) // 1024 // 1024} MB, over limit")

        dest.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with open(dest, "wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                written += len(chunk)
                if written > MAX_BYTES:
                    handle.close()
                    dest.unlink(missing_ok=True)
                    return Downloaded(url, None, "skipped", "exceeded size limit mid-download")
                handle.write(chunk)
        return Downloaded(url, dest, "downloaded", f"{written // 1024} KB")

    except requests.RequestException as exc:
        # One bad attachment must not lose the others -- a solicitation package
        # is usually several files and the useful one may still arrive.
        return Downloaded(url, None, "failed", str(exc)[:160])


def enrich(notice: Notice, root: pathlib.Path, timeout: int = 120) -> EnrichResult:
    directory = attachment_dir(root, notice.reference)
    files = [
        download(url, directory / filename_for(url), timeout=timeout)
        for url in notice.attachments
    ]
    return EnrichResult(notice.reference, directory, files)


def enrich_reference(reference: str, store: NoticeStore, timeout: int = 120) -> EnrichResult:
    notice = store.load(reference)
    if notice is None:
        raise KeyError(f"{reference} is not in the notice store - run `canadabuys fetch` first")
    return enrich(notice, store.root, timeout=timeout)
