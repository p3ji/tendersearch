import csv
import json
import pathlib

import pytest
import yaml

from canadabuys.cli import main
from canadabuys.notice import Notice
from canadabuys.store import NoticeStore

FIXTURE = pathlib.Path("tests/fixtures/open_sample.csv")
NOW = "2026-08-03T12:00:00+00:00"


def base_row():
    with open(FIXTURE, encoding="utf-8-sig", newline="") as f:
        return next(csv.DictReader(f))


def make_notice(**overrides) -> Notice:
    row = {
        **base_row(),
        "tenderStatus-appelOffresStatut-eng": "Open",
        "tenderClosingDate-appelOffresDateCloture": "2026-09-30T14:00:00",
        "regionsOfDelivery-regionsLivraison-eng": "*Ontario",
        "unspsc": "",
        "gsin-nibs": "",
        "title-titre-eng": "Data pipeline modernization",
        "tenderDescription-descriptionAppelOffres-eng": "Seeking a data pipeline rebuild",
        "selectionCriteria-criteresSelection-eng": "",
        **overrides,
    }
    return Notice.from_csv_row(row, "open", NOW)


def write_profile(root, member_id, **overrides):
    data = {
        "member_id": member_id,
        "name": member_id.title(),
        "regions": ["Ontario", "Canada"],
        "service_lines": [
            {"label": "Data", "unspsc": [], "gsin": [], "naics": [],
             "keywords": ["data pipeline"]}
        ],
        **overrides,
    }
    d = root / member_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.yml").write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.fixture
def env(tmp_path):
    notices_dir = tmp_path / "notices"
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    store = NoticeStore(notices_dir)
    store.save(make_notice())
    write_profile(profiles_dir, "alex")
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.safe_dump({"min_turnaround_days": 5, "active_profiles": []}),
                            encoding="utf-8")
    return {
        "notices": str(notices_dir),
        "profiles": str(profiles_dir),
        "config": str(config_path),
        "tmp_path": tmp_path,
    }


def run_filter(env, extra_args=None):
    args = ["--notices", env["notices"], "filter", "--profiles", env["profiles"],
            "--config", env["config"]]
    if extra_args:
        args += extra_args
    return main(args)


def test_filter_fails_when_any_profile_is_broken(env, capsys):
    (pathlib.Path(env["profiles"]) / "broken").mkdir()
    (pathlib.Path(env["profiles"]) / "broken" / "profile.yml").write_text(
        "not: [a, valid, profile]", encoding="utf-8"
    )
    rc = run_filter(env)
    assert rc == 1
    err = capsys.readouterr().err
    assert "broken" in err


def test_filter_succeeds_when_all_profiles_are_valid(env):
    assert run_filter(env) == 0


def test_filter_json_writes_only_passing_notices_by_default(env):
    out = pathlib.Path(env["tmp_path"]) / "stage1.json"
    rc = run_filter(env, ["--json", str(out)])
    assert rc == 0
    records = json.loads(out.read_text(encoding="utf-8"))
    assert len(records) == 1
    rec = records[0]
    assert rec["passed"] is True
    assert rec["matched_keywords"] == ["data pipeline"]
    assert "low_barrier" in rec and "kind" in rec["low_barrier"]
    assert rec["entity"]
    assert rec["closing"]


def test_filter_json_include_rejected_writes_all(env):
    store = NoticeStore(pathlib.Path(env["notices"]))
    store.save(make_notice(**{
        "referenceNumber-numeroReference": "cb-no-match",
        "title-titre-eng": "Cement supply",
        "tenderDescription-descriptionAppelOffres-eng": "Bulk cement delivery",
    }))
    out = pathlib.Path(env["tmp_path"]) / "stage1_full.json"
    rc = run_filter(env, ["--json", str(out), "--include-rejected"])
    assert rc == 0
    records = json.loads(out.read_text(encoding="utf-8"))
    assert len(records) == 2
    assert any(not r["passed"] for r in records)


def test_active_profiles_restricts_to_named_profiles(env):
    write_profile(pathlib.Path(env["profiles"]), "priya",
                  service_lines=[{"label": "Change", "unspsc": [], "gsin": [], "naics": [],
                                   "keywords": ["change management"]}])
    cfg = pathlib.Path(env["config"])
    cfg.write_text(yaml.safe_dump({"min_turnaround_days": 5, "active_profiles": ["priya"]}),
                    encoding="utf-8")
    # The stored notice only matches alex's "data pipeline" keyword, not
    # priya's "change management" -- so restricting to priya alone should
    # drop it.
    out = pathlib.Path(env["tmp_path"]) / "stage1.json"
    rc = run_filter(env, ["--json", str(out)])
    assert rc == 0
    records = json.loads(out.read_text(encoding="utf-8"))
    assert records == []


def test_active_profiles_naming_unknown_member_is_an_error(env):
    cfg = pathlib.Path(env["config"])
    cfg.write_text(yaml.safe_dump({"min_turnaround_days": 5, "active_profiles": ["ghost"]}),
                    encoding="utf-8")
    rc = run_filter(env)
    assert rc == 1
