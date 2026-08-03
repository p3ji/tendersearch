"""Member profiles and teams.

Teams are declared unions of members. Capabilities are never copied into a
team file -- they are unioned at read time so editing one profile propagates
everywhere.
"""
from __future__ import annotations

import dataclasses
import pathlib

import yaml

REQUIRED_PROFILE_FIELDS = (
    "member_id", "name", "service_lines", "regions",
)


class ProfileError(Exception):
    pass


@dataclasses.dataclass
class ServiceLine:
    label: str
    naics: list[str] = dataclasses.field(default_factory=list)
    unspsc: list[str] = dataclasses.field(default_factory=list)
    gsin: list[str] = dataclasses.field(default_factory=list)
    keywords: list[str] = dataclasses.field(default_factory=list)

    def has_any_signal(self) -> bool:
        return bool(self.naics or self.unspsc or self.gsin or self.keywords)


@dataclasses.dataclass
class Profile:
    member_id: str
    name: str
    regions: list[str]
    service_lines: list[ServiceLine]
    clearance: dict = dataclasses.field(default_factory=dict)
    skills: list = dataclasses.field(default_factory=list)
    certifications: list = dataclasses.field(default_factory=list)
    past_performance: list = dataclasses.field(default_factory=list)
    vehicles: list = dataclasses.field(default_factory=list)
    evidence: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Team:
    team_id: str
    name: str
    members: list[str]
    prime: str

    def service_lines(self, profiles: list[Profile]) -> list[ServiceLine]:
        by_id = {p.member_id: p for p in profiles}
        out: list[ServiceLine] = []
        for member in self.members:
            out.extend(by_id[member].service_lines)
        return out

    def regions(self, profiles: list[Profile]) -> set[str]:
        by_id = {p.member_id: p for p in profiles}
        return {r for m in self.members for r in by_id[m].regions}


def load_profile(path: pathlib.Path) -> Profile:
    path = pathlib.Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{path}: expected a mapping at the top level")

    missing = [f for f in REQUIRED_PROFILE_FIELDS if f not in data]
    if missing:
        raise ProfileError(f"{path}: missing required field(s): {', '.join(missing)}")

    if not data["regions"]:
        raise ProfileError(
            f"{path}: 'regions' is present but empty, which is not a valid configuration"
        )

    lines = []
    for raw in data["service_lines"]:
        line = ServiceLine(
            label=raw.get("label", ""),
            naics=raw.get("naics") or [],
            unspsc=[str(c) for c in (raw.get("unspsc") or [])],
            gsin=[str(c) for c in (raw.get("gsin") or [])],
            keywords=[k.lower() for k in (raw.get("keywords") or [])],
        )
        if not line.has_any_signal():
            raise ProfileError(
                f"{path}: service line {line.label!r} has no codes and no keywords, "
                f"so it can never match anything"
            )
        lines.append(line)

    return Profile(
        member_id=data["member_id"],
        name=data["name"],
        regions=data["regions"],
        service_lines=lines,
        clearance=data.get("clearance") or {},
        skills=data.get("skills") or [],
        certifications=data.get("certifications") or [],
        past_performance=data.get("past_performance") or [],
        vehicles=data.get("vehicles") or [],
        evidence=data.get("evidence") or {},
    )


def load_profiles(root, collect_errors: bool = False):
    root = pathlib.Path(root)
    profiles, errors = [], []
    for path in sorted(root.glob("*/profile.yml")):
        if path.parent.name.startswith("_"):
            continue  # _example/ is a schema reference, not a real member
        try:
            profiles.append(load_profile(path))
        except ProfileError as exc:
            errors.append(str(exc))
    if collect_errors:
        return profiles, errors
    if errors:
        raise ProfileError("; ".join(errors))
    return profiles


def load_team(path, profiles: list[Profile]) -> Team:
    path = pathlib.Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    known = {p.member_id for p in profiles}
    unknown = [m for m in data["members"] if m not in known]
    if unknown:
        raise ProfileError(f"{path}: unknown member(s): {', '.join(unknown)}")
    return Team(
        team_id=data["team_id"],
        name=data["name"],
        members=data["members"],
        prime=data.get("prime", data["members"][0]),
    )
