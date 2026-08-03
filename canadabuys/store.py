"""On-disk notice storage with amendment-aware upsert.

Notices are identified by reference number alone. An amendment updates the
existing record; it never creates a second one. When an amendment changes a
field that could change a verdict, the notice is flagged for re-matching --
keeping a stale verdict after criteria or deadlines move is a correctness bug.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
from typing import Iterator

from canadabuys.notice import Notice

# Changes to these invalidate any existing verdict.
REMATCH_FIELDS: tuple[str, ...] = ("closing", "description", "selection_criteria")


@dataclasses.dataclass
class UpsertResult:
    reference: str
    action: str  # "created" | "amended" | "unchanged"
    needs_rematch: bool
    changed_fields: list[str]


class NoticeStore:
    def __init__(self, root: pathlib.Path):
        self.root = pathlib.Path(root)

    def path_for(self, reference: str, first_seen: str) -> pathlib.Path:
        month = first_seen[:7]  # "2026-08"
        return self.root / month / f"{reference}.json"

    def _find(self, reference: str) -> pathlib.Path | None:
        matches = sorted(self.root.glob(f"*/{reference}.json"))
        return matches[0] if matches else None

    def load(self, reference: str) -> Notice | None:
        path = self._find(reference)
        if path is None:
            return None
        return Notice.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, notice: Notice) -> None:
        path = self.path_for(notice.reference, notice.first_seen)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(notice.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def upsert(self, incoming: Notice, now_iso: str) -> UpsertResult:
        existing = self.load(incoming.reference)

        if existing is None:
            incoming.needs_rematch = True  # never judged
            self.save(incoming)
            return UpsertResult(incoming.reference, "created", True, [])

        if incoming.amendment < existing.amendment:
            # Feeds can carry an older revision; never regress.
            return UpsertResult(incoming.reference, "unchanged", False, [])

        changed = [
            f
            for f in REMATCH_FIELDS
            if getattr(incoming, f) != getattr(existing, f)
        ]
        any_change = changed or incoming.amendment != existing.amendment or (
            _comparable(incoming) != _comparable(existing)
        )

        if not any_change:
            return UpsertResult(incoming.reference, "unchanged", False, [])

        incoming.first_seen = existing.first_seen  # discovery time, not last touch
        incoming.last_updated = now_iso
        incoming.needs_rematch = existing.needs_rematch or bool(changed)
        self.save(incoming)
        return UpsertResult(incoming.reference, "amended", bool(changed), changed)

    def all(self) -> Iterator[Notice]:
        for path in sorted(self.root.glob("*/*.json")):
            yield Notice.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _comparable(n: Notice) -> dict:
    """Notice content ignoring local bookkeeping fields."""
    d = n.to_dict()
    for k in ("first_seen", "last_updated", "source_feed", "needs_rematch"):
        d.pop(k, None)
    return d
