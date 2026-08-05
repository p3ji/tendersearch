"""On-disk notice storage with amendment-aware upsert.

Notices are identified by reference number alone. An amendment updates the
existing record; it never creates a second one. When an amendment changes a
field that could change a verdict, the notice is flagged for re-matching --
keeping a stale verdict after criteria or deadlines move is a correctness bug.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
from typing import Iterator

from canadabuys.notice import Notice

# Changes to these invalidate any existing verdict.
REMATCH_FIELDS: tuple[str, ...] = ("closing", "description", "selection_criteria")

# Characters that are invalid (or, on Windows, silently form an alternate
# data stream rather than a real file -- e.g. a ":" in "SSC-26-00034400:T")
# in a filesystem path component. Some feed reference numbers contain a
# colon, so this is not hypothetical.
_INVALID_FS_CHARS = '<>:"/\\|?*'


def safe_filename(reference: str) -> str:
    sanitized = "".join("_" if c in _INVALID_FS_CHARS else c for c in reference)
    if sanitized == reference:
        return sanitized
    # Sanitization changed the string, e.g. "ABC:T" -> "ABC_T", which could
    # collide with a genuinely different reference like "ABC_T". Append a
    # short deterministic hash of the original so distinct references never
    # land on the same file. References needing no sanitization are
    # unaffected, so existing stored files still resolve.
    digest = hashlib.sha1(reference.encode("utf-8")).hexdigest()[:8]
    return f"{sanitized}_{digest}"


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
        return self.root / month / f"{safe_filename(reference)}.json"

    def _find(self, reference: str) -> pathlib.Path | None:
        matches = sorted(self.root.glob(f"*/{safe_filename(reference)}.json"))
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

    def clear_rematch(self, reference: str) -> None:
        """Clear needs_rematch after a verdict has been written for this notice.

        Call this only after the verdict is durably written (e.g. to
        matches/<today>/verdicts.json) -- clearing first and getting
        interrupted would silently lose the flag and the notice would never
        be re-judged despite the amendment.
        """
        notice = self.load(reference)
        if notice is None:
            return
        if notice.needs_rematch:
            notice.needs_rematch = False
            self.save(notice)

    def all(self) -> Iterator[Notice]:
        """Every stored notice, one record per reference.

        Deduplicates deliberately. A change to the filename scheme can leave an
        orphaned file beside the canonical one -- when sanitized references
        gained a hash suffix, 18 of 920 live notices ended up written twice.
        A plain glob then yields the same reference more than once, silently
        inflating every count downstream and letting a stale copy be judged
        alongside the current one.

        The canonical filename wins; failing that, the most recently updated.
        """
        best: dict[str, tuple[bool, str, Notice]] = {}

        for path in sorted(self.root.glob("*/*.json")):
            notice = Notice.from_dict(json.loads(path.read_text(encoding="utf-8")))
            is_canonical = path.name == f"{safe_filename(notice.reference)}.json"
            candidate = (is_canonical, notice.last_updated or "", notice)
            existing = best.get(notice.reference)
            if existing is None or candidate[:2] > existing[:2]:
                best[notice.reference] = candidate

        for _, _, notice in sorted(best.values(), key=lambda item: item[2].reference):
            yield notice


def _comparable(n: Notice) -> dict:
    """Notice content ignoring local bookkeeping fields."""
    d = n.to_dict()
    for k in ("first_seen", "last_updated", "source_feed", "needs_rematch"):
        d.pop(k, None)
    return d
