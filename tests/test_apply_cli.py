import csv
import json
import pathlib

import pytest
import yaml

from canadabuys.cli import main
from canadabuys.notice import Notice
from canadabuys.store import NoticeStore, safe_filename

FIXTURE = pathlib.Path("tests/fixtures/open_sample.csv")
NOW = "2026-08-03T12:00:00+00:00"
REFERENCE = "cb-450-77537023"


def base_row():
    with open(FIXTURE, encoding="utf-8-sig", newline="") as f:
        return next(csv.DictReader(f))


def make_notice(**overrides) -> Notice:
    row = {
        **base_row(),
        "referenceNumber-numeroReference": REFERENCE,
        "tenderStatus-appelOffresStatut-eng": "Open",
        "tenderClosingDate-appelOffresDateCloture": "2026-09-30T14:00:00",
        "title-titre-eng": "Data pipeline modernization",
        "tenderDescription-descriptionAppelOffres-eng": "Seeking a data pipeline rebuild",
        "selectionCriteria-criteresSelection-eng": "3.1 Reliability clearance required",
        **overrides,
    }
    return Notice.from_csv_row(row, "open", NOW)


def write_profile(root, member_id, evidence=None, past_performance=None, **overrides):
    data = {
        "member_id": member_id,
        "name": member_id.title(),
        "regions": ["Ontario", "Canada"],
        "service_lines": [
            {"label": "Data", "unspsc": [], "gsin": [], "naics": [],
             "keywords": ["data pipeline"]}
        ],
        "evidence": evidence or {},
        "past_performance": past_performance if past_performance is not None else [],
        **overrides,
    }
    d = root / member_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.yml").write_text(yaml.safe_dump(data), encoding="utf-8")


def write_verdicts(root, date, records):
    d = root / date
    d.mkdir(parents=True, exist_ok=True)
    (d / "verdicts.json").write_text(json.dumps(records), encoding="utf-8")


def make_verdict_record(**overrides):
    record = {
        "reference": REFERENCE,
        "subject": "alex",
        "subject_kind": "profile",
        "score": 82,
        "recommendation": "bid",
        "low_barrier": {"is_low_barrier": False, "kind": "none"},
        "requirements": [
            {"text": "3.1 Reliability clearance required", "kind": "mandatory",
             "status": "met", "covered_by": "alex", "note": "Reliability on file"},
        ],
        "reasoning": "Strong fit, all mandatories met.",
        "deal_breakers": [],
    }
    record.update(overrides)
    return record


@pytest.fixture
def env(tmp_path):
    notices_dir = tmp_path / "notices"
    profiles_dir = tmp_path / "profiles"
    matches_dir = tmp_path / "matches"
    bids_dir = tmp_path / "bids"
    profiles_dir.mkdir()
    NoticeStore(notices_dir).save(make_notice())
    write_profile(profiles_dir, "alex", evidence={"resume": "evidence/alex-resume.pdf"})
    write_verdicts(matches_dir, "2026-08-01", [make_verdict_record()])
    return {
        "notices": str(notices_dir),
        "profiles": str(profiles_dir),
        "matches": str(matches_dir),
        "bids": str(bids_dir),
        "tmp_path": tmp_path,
    }


def run_apply(env, notice_id=REFERENCE, extra_args=None):
    args = [
        "--notices", env["notices"], "apply", notice_id,
        "--profiles", env["profiles"], "--matches", env["matches"],
        "--bids", env["bids"],
    ]
    if extra_args:
        args += extra_args
    return main(args)


def test_apply_writes_scaffold_with_resolved_evidence(env):
    rc = run_apply(env)
    assert rc == 0
    scaffold_path = pathlib.Path(env["bids"]) / REFERENCE / "scaffold.json"
    scaffold = json.loads(scaffold_path.read_text(encoding="utf-8"))
    assert scaffold["notice"]["reference"] == REFERENCE
    assert scaffold["verdict"]["subject"] == "alex"
    assert scaffold["verdict"]["score"] == 82
    req = scaffold["requirements"][0]
    assert req["covered_by"] == "alex"
    expected_evidence_path = str(
        pathlib.Path(env["profiles"]) / "alex" / "evidence" / "alex-resume.pdf"
    )
    assert req["evidence"]["resume"] == expected_evidence_path


def test_apply_fails_when_no_verdict_exists(env, capsys):
    rc = run_apply(env, extra_args=["--matches", str(pathlib.Path(env["tmp_path"]) / "empty")])
    assert rc == 1
    assert "no verdict found" in capsys.readouterr().err


def test_apply_fails_when_notice_missing(env, capsys):
    write_verdicts(pathlib.Path(env["matches"]), "2026-08-02",
                    [make_verdict_record(reference="cb-does-not-exist")])
    rc = run_apply(env, notice_id="cb-does-not-exist")
    assert rc == 1
    assert "no notice found" in capsys.readouterr().err


def test_apply_requires_disambiguation_when_multiple_subjects(env, capsys):
    write_verdicts(pathlib.Path(env["matches"]), "2026-08-01", [
        make_verdict_record(subject="alex"),
        make_verdict_record(subject="priya", score=55),
    ])
    rc = run_apply(env)
    assert rc == 1
    assert "multiple subjects" in capsys.readouterr().err


def test_apply_profile_flag_selects_the_right_verdict(env):
    write_verdicts(pathlib.Path(env["matches"]), "2026-08-01", [
        make_verdict_record(subject="alex"),
        make_verdict_record(subject="priya", score=55),
    ])
    rc = run_apply(env, extra_args=["--profile", "priya"])
    assert rc == 0
    scaffold = json.loads(
        (pathlib.Path(env["bids"]) / REFERENCE / "scaffold.json").read_text(encoding="utf-8")
    )
    assert scaffold["verdict"]["subject"] == "priya"
    assert scaffold["verdict"]["score"] == 55


def test_apply_fails_when_verdict_names_unknown_member(env, capsys):
    write_verdicts(pathlib.Path(env["matches"]), "2026-08-01", [
        make_verdict_record(requirements=[
            {"text": "3.1 Reliability clearance required", "kind": "mandatory",
             "status": "met", "covered_by": "ghost", "note": ""},
        ]),
    ])
    rc = run_apply(env)
    assert rc == 1
    assert "ghost" in capsys.readouterr().err


def test_apply_warns_but_proceeds_when_notice_needs_rematch(env, capsys):
    notice = make_notice()
    notice.needs_rematch = True
    NoticeStore(pathlib.Path(env["notices"])).save(notice)
    rc = run_apply(env)
    assert rc == 0
    assert "amended after" in capsys.readouterr().err


def test_apply_rejects_both_profile_and_team(env, capsys):
    rc = run_apply(env, extra_args=["--profile", "alex", "--team", "core"])
    assert rc == 1
    assert "not both" in capsys.readouterr().err


def test_apply_leaves_evidence_empty_when_requirement_is_a_gap(env):
    write_verdicts(pathlib.Path(env["matches"]), "2026-08-01", [
        make_verdict_record(requirements=[
            {"text": "3.2 Standing offer required", "kind": "mandatory",
             "status": "gap", "covered_by": None, "note": "nobody holds one"},
        ]),
    ])
    rc = run_apply(env)
    assert rc == 0
    scaffold = json.loads(
        (pathlib.Path(env["bids"]) / REFERENCE / "scaffold.json").read_text(encoding="utf-8")
    )
    assert scaffold["requirements"][0]["evidence"] == {}
    assert scaffold["requirements"][0]["status"] == "gap"
    assert scaffold["members"] == {}


def test_apply_sanitizes_notice_id_for_the_bids_directory_name(tmp_path, capsys):
    notices_dir = tmp_path / "notices"
    profiles_dir = tmp_path / "profiles"
    matches_dir = tmp_path / "matches"
    bids_dir = tmp_path / "bids"
    profiles_dir.mkdir()
    ref = "SSC-26-00034400:T"
    NoticeStore(notices_dir).save(make_notice(**{"referenceNumber-numeroReference": ref}))
    write_profile(profiles_dir, "alex", evidence={"resume": "evidence/alex-resume.pdf"})
    write_verdicts(matches_dir, "2026-08-01", [make_verdict_record(reference=ref)])
    rc = main([
        "--notices", str(notices_dir), "apply", ref,
        "--profiles", str(profiles_dir), "--matches", str(matches_dir),
        "--bids", str(bids_dir),
    ])
    assert rc == 0
    expected_dir = bids_dir / safe_filename(ref)
    assert (expected_dir / "scaffold.json").exists()
    # Finding 2: the printed output must state the actual (sanitized) bid
    # directory unambiguously -- a reader must not need to reconstruct
    # bids/<notice-id>/ from the raw reference, which would go wrong for a
    # reference containing ":" like this one.
    out = capsys.readouterr().out
    assert f"bid directory: {expected_dir}" in out
    assert str(bids_dir / ref) not in out


def test_apply_scaffold_includes_past_performance_for_covering_members(env):
    write_profile(
        pathlib.Path(env["profiles"]), "alex",
        evidence={"resume": "evidence/alex-resume.pdf"},
        past_performance=[
            {"client": "Acme Corp", "value": 50000, "start": "2024-01-01",
             "end": "2024-06-30", "description": "Built a reporting pipeline.",
             "reference": {"name": "Sam Ref", "email": "sam@example.com"}},
        ],
    )
    rc = run_apply(env)
    assert rc == 0
    scaffold = json.loads(
        (pathlib.Path(env["bids"]) / REFERENCE / "scaffold.json").read_text(encoding="utf-8")
    )
    assert "members" in scaffold
    assert set(scaffold["members"].keys()) == {"alex"}
    alex = scaffold["members"]["alex"]
    assert alex["name"] == "Alex"
    assert alex["past_performance"] == [
        {"client": "Acme Corp", "value": 50000, "start": "2024-01-01",
         "end": "2024-06-30", "description": "Built a reporting pipeline.",
         "reference": {"name": "Sam Ref", "email": "sam@example.com"}},
    ]
    assert alex["evidence"]["resume"] == str(
        pathlib.Path(env["profiles"]) / "alex" / "evidence" / "alex-resume.pdf"
    )
    # existing per-requirement evidence key must be unchanged
    assert scaffold["requirements"][0]["evidence"]["resume"] == alex["evidence"]["resume"]


def test_apply_scaffold_omits_members_not_covering_any_requirement(env):
    # priya has a profile but covers nothing on this notice -- must not
    # appear in the scaffold's members block.
    write_profile(pathlib.Path(env["profiles"]), "priya")
    rc = run_apply(env)
    assert rc == 0
    scaffold = json.loads(
        (pathlib.Path(env["bids"]) / REFERENCE / "scaffold.json").read_text(encoding="utf-8")
    )
    assert set(scaffold["members"].keys()) == {"alex"}


def test_apply_scaffold_allows_empty_past_performance(env):
    # alex's profile (from the env fixture) has no past_performance set --
    # this must not be an error, and must show up as an empty list, not be
    # silently dropped from the members block.
    rc = run_apply(env)
    assert rc == 0
    scaffold = json.loads(
        (pathlib.Path(env["bids"]) / REFERENCE / "scaffold.json").read_text(encoding="utf-8")
    )
    assert scaffold["members"]["alex"]["past_performance"] == []
