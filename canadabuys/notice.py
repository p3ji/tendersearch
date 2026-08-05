"""The Notice model — the stable contract the rest of the system depends on.

Ingestion normalizes the feed into this shape once; nothing downstream reads
raw CSV columns.
"""
from __future__ import annotations

import dataclasses
import datetime

from canadabuys import fields as F

OPEN_STATUS = "open"


@dataclasses.dataclass(eq=True)
class Notice:
    reference: str
    amendment: int
    solicitation: str
    title: str
    entity: str
    end_user: str
    category: list[str]
    notice_type: str
    procurement_method: str
    unspsc: list[str]
    unspsc_desc: list[str]
    gsin: list[str]
    gsin_desc: list[str]
    selection_criteria: str
    regions_delivery: list[str]
    regions_opportunity: list[str]
    published: datetime.date | None
    closing: datetime.datetime | None
    amended_date: datetime.date | None
    status: str
    description: str
    description_fr: str
    notice_url: str
    attachments: list[str]
    contact_name: str
    contact_email: str
    first_seen: str
    last_updated: str
    source_feed: str
    needs_rematch: bool = False

    @classmethod
    def from_csv_row(cls, row: dict, source_feed: str, now_iso: str) -> "Notice":
        def txt(col: str) -> str:
            return (row.get(col) or "").strip()

        raw_amendment = txt(F.COL_AMENDMENT)
        return cls(
            reference=txt(F.COL_REF),
            # Zero-padded in the feed ("000"); int so "010" > "009" compares right.
            amendment=int(raw_amendment) if raw_amendment.isdigit() else 0,
            solicitation=txt(F.COL_SOLICITATION),
            title=txt(F.COL_TITLE),
            entity=txt(F.COL_ENTITY),
            end_user=txt(F.COL_END_USER),
            category=F.split_multi(row.get(F.COL_CATEGORY)),
            notice_type=txt(F.COL_NOTICE_TYPE),
            procurement_method=txt(F.COL_PROC_METHOD),
            unspsc=F.split_multi(row.get(F.COL_UNSPSC)),
            unspsc_desc=F.split_multi(row.get(F.COL_UNSPSC_DESC)),
            gsin=F.split_multi(row.get(F.COL_GSIN)),
            gsin_desc=F.split_multi(row.get(F.COL_GSIN_DESC)),
            selection_criteria=txt(F.COL_SELECTION),
            regions_delivery=F.split_multi(row.get(F.COL_REGIONS_DELIVERY)),
            regions_opportunity=F.split_multi(row.get(F.COL_REGIONS_OPPORTUNITY)),
            published=F.parse_date(row.get(F.COL_PUBLISHED)),
            closing=F.parse_datetime(row.get(F.COL_CLOSING)),
            amended_date=F.parse_date(row.get(F.COL_AMENDED_DATE)),
            status=txt(F.COL_STATUS),
            description=txt(F.COL_DESCRIPTION),
            description_fr=txt(F.COL_DESCRIPTION_FR),
            notice_url=txt(F.COL_NOTICE_URL),
            # Attachments are comma-joined, not star/newline separated. See split_urls.
            attachments=F.split_urls(row.get(F.COL_ATTACHMENT)),
            contact_name=txt(F.COL_CONTACT_NAME),
            contact_email=txt(F.COL_CONTACT_EMAIL),
            first_seen=now_iso,
            last_updated=now_iso,
            source_feed=source_feed,
            needs_rematch=False,
        )

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["published"] = self.published.isoformat() if self.published else None
        d["closing"] = self.closing.isoformat() if self.closing else None
        d["amended_date"] = self.amended_date.isoformat() if self.amended_date else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Notice":
        d = dict(d)
        d["published"] = datetime.date.fromisoformat(d["published"]) if d["published"] else None
        d["closing"] = (
            datetime.datetime.fromisoformat(d["closing"]) if d["closing"] else None
        )
        d["amended_date"] = (
            datetime.date.fromisoformat(d["amended_date"]) if d["amended_date"] else None
        )
        return cls(**d)

    def searchable_text(self) -> str:
        """All free text a keyword match should search, lowercased.

        Includes code *descriptions* because 15% of notices carry no code at
        all and many that do use codes the profile does not list.
        """
        parts = [
            self.title,
            self.description,
            self.selection_criteria,
            " ".join(self.unspsc_desc),
            " ".join(self.gsin_desc),
        ]
        return " ".join(p for p in parts if p).lower()

    def is_open(self) -> bool:
        return self.status.strip().lower() == OPEN_STATUS
