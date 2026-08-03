import pytest
import yaml
from matching.profile import (
    Profile, ServiceLine, Team, load_profile, load_profiles, load_team, ProfileError
)

MINIMAL = {
    "member_id": "alex",
    "name": "Alex Chen",
    "clearance": {"level": "Reliability", "status": "active"},
    "service_lines": [
        {"label": "Data engineering", "unspsc": ["81111500"], "gsin": [],
         "naics": ["541512"], "keywords": ["data pipeline", "etl"]}
    ],
    "skills": [{"name": "Python", "depth": "expert", "years": 8}],
    "certifications": [],
    "past_performance": [],
    "regions": ["Ontario", "Canada"],
    "vehicles": [],
    "evidence": {"resume": "evidence/alex-resume.pdf"},
}


def write(tmp_path, data, name="profile.yml"):
    d = tmp_path / data["member_id"]
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


def test_loads_a_minimal_profile(tmp_path):
    p = load_profile(write(tmp_path, MINIMAL))
    assert p.member_id == "alex"
    assert p.service_lines[0].keywords == ["data pipeline", "etl"]


def test_empty_past_performance_is_valid(tmp_path):
    # The binding constraint for this group. An empty list must never be an error.
    p = load_profile(write(tmp_path, {**MINIMAL, "past_performance": []}))
    assert p.past_performance == []


def test_missing_required_field_raises_with_a_useful_message(tmp_path):
    bad = {k: v for k, v in MINIMAL.items() if k != "service_lines"}
    with pytest.raises(ProfileError, match="service_lines"):
        load_profile(write(tmp_path, bad))


def test_service_line_with_no_keywords_and_no_codes_is_rejected(tmp_path):
    # Such a line can never match anything; silently useless is worse than loud.
    bad = {**MINIMAL, "service_lines": [
        {"label": "Vague", "unspsc": [], "gsin": [], "naics": [], "keywords": []}
    ]}
    with pytest.raises(ProfileError, match="no codes and no keywords"):
        load_profile(write(tmp_path, bad))


def test_empty_regions_list_is_rejected(tmp_path):
    # An empty regions list is not a valid configuration -- it must fail loudly
    # at load time rather than be silently reinterpreted at match time.
    bad = {**MINIMAL, "regions": []}
    with pytest.raises(ProfileError, match="regions"):
        load_profile(write(tmp_path, bad))


def test_load_profiles_skips_the_example_directory(tmp_path):
    write(tmp_path, MINIMAL)
    write(tmp_path, {**MINIMAL, "member_id": "_example"})
    ids = {p.member_id for p in load_profiles(tmp_path)}
    assert ids == {"alex"}


def test_load_profiles_reports_a_bad_profile_without_losing_good_ones(tmp_path):
    write(tmp_path, MINIMAL)
    bad_dir = tmp_path / "broken"
    bad_dir.mkdir()
    (bad_dir / "profile.yml").write_text("not: [a, valid, profile]", encoding="utf-8")
    profiles, errors = load_profiles(tmp_path, collect_errors=True)
    assert {p.member_id for p in profiles} == {"alex"}
    assert any("broken" in e for e in errors)


def test_team_unions_service_lines_across_members(tmp_path):
    write(tmp_path, MINIMAL)
    write(tmp_path, {**MINIMAL, "member_id": "priya", "name": "Priya S",
                     "service_lines": [{"label": "Change mgmt", "unspsc": ["80101500"],
                                        "gsin": [], "naics": [], "keywords": ["change"]}]})
    profiles = load_profiles(tmp_path)
    team_file = tmp_path / "delivery.yml"
    team_file.write_text(yaml.safe_dump(
        {"team_id": "delivery", "name": "Delivery", "members": ["alex", "priya"],
         "prime": "alex"}), encoding="utf-8")
    team = load_team(team_file, profiles)
    labels = {sl.label for sl in team.service_lines(profiles)}
    assert labels == {"Data engineering", "Change mgmt"}


def test_team_referencing_an_unknown_member_raises(tmp_path):
    write(tmp_path, MINIMAL)
    profiles = load_profiles(tmp_path)
    team_file = tmp_path / "ghost.yml"
    team_file.write_text(yaml.safe_dump(
        {"team_id": "ghost", "name": "Ghost", "members": ["alex", "nobody"],
         "prime": "alex"}), encoding="utf-8")
    with pytest.raises(ProfileError, match="nobody"):
        load_team(team_file, profiles)


def test_team_capabilities_are_not_copied_into_the_team_file(tmp_path):
    # Editing a member profile must propagate; a snapshot in the team file would rot.
    write(tmp_path, MINIMAL)
    profiles = load_profiles(tmp_path)
    team_file = tmp_path / "solo.yml"
    team_file.write_text(yaml.safe_dump(
        {"team_id": "solo", "name": "Solo", "members": ["alex"], "prime": "alex"}),
        encoding="utf-8")
    team = load_team(team_file, profiles)
    assert not hasattr(team, "keywords")
    profiles[0].service_lines[0].keywords.append("newly added")
    assert "newly added" in team.service_lines(profiles)[0].keywords
