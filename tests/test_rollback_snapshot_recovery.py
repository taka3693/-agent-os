import json

from tools.lib.rollback_store import inspect_latest_snapshot, load_best_snapshot, repair_latest_from_best_snapshot


def test_load_best_snapshot_falls_back_to_versioned_when_latest_is_broken(tmp_path):
    from tools.lib.rollback_store import load_best_snapshot

    rollback_dir = tmp_path / "state" / "rollback"
    rollback_dir.mkdir(parents=True)

    latest = rollback_dir / "rollback.latest.json"
    latest.write_text(
        json.dumps({"deploy_artifact": None}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    versioned = rollback_dir / "rollback.20260328T000000Z.json"
    versioned.write_text(
        json.dumps(
            {
                "deploy_artifact": {
                    "json_path": "/tmp/good.json",
                    "markdown_path": "/tmp/good.md",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def validator(payload):
        return isinstance(payload, dict) and isinstance(payload.get("deploy_artifact"), dict)

    snap = load_best_snapshot(tmp_path, validator=validator)

    assert snap["ok"] is True
    assert snap["selected_kind"] == "versioned"
    assert snap["selected_path"].endswith("rollback.20260328T000000Z.json")
    assert isinstance(snap["payload"]["deploy_artifact"], dict)

def test_load_best_snapshot_falls_back_to_fallback_when_latest_and_versioned_are_broken(tmp_path):
    from tools.lib.rollback_store import load_best_snapshot

    rollback_dir = tmp_path / "state" / "rollback"
    rollback_dir.mkdir(parents=True)

    (rollback_dir / "rollback.latest.json").write_text(
        json.dumps({"deploy_artifact": None}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (rollback_dir / "rollback.20260328T000000Z.json").write_text(
        "{broken json",
        encoding="utf-8",
    )

    (rollback_dir / "rollback.fallback.json").write_text(
        json.dumps(
            {
                "deploy_artifact": {
                    "json_path": "/tmp/fallback.json",
                    "markdown_path": "/tmp/fallback.md",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def validator(payload):
        return isinstance(payload, dict) and isinstance(payload.get("deploy_artifact"), dict)

    snap = load_best_snapshot(tmp_path, validator=validator)

    assert snap["ok"] is True
    assert snap["selected_kind"] == "fallback"
    assert snap["selected_path"].endswith("rollback.fallback.json")
    assert isinstance(snap["payload"]["deploy_artifact"], dict)

def test_repair_latest_from_best_snapshot_restores_latest_from_versioned(tmp_path):
    from tools.lib.rollback_store import inspect_latest_snapshot, repair_latest_from_best_snapshot

    rollback_dir = tmp_path / "state" / "rollback"
    rollback_dir.mkdir(parents=True)

    (rollback_dir / "rollback.latest.json").write_text(
        json.dumps({"deploy_artifact": None}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (rollback_dir / "rollback.20260328T000000Z.json").write_text(
        json.dumps(
            {
                "deploy_artifact": {
                    "json_path": "/tmp/good.json",
                    "markdown_path": "/tmp/good.md",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def validator(payload):
        return isinstance(payload, dict) and isinstance(payload.get("deploy_artifact"), dict)

    before = inspect_latest_snapshot(tmp_path, validator=validator)
    assert before["ok"] is False

    repair = repair_latest_from_best_snapshot(tmp_path, validator=validator)
    assert repair["ok"] is True
    assert repair["repaired"] is True
    assert repair["selected_kind"] == "versioned"

    after = inspect_latest_snapshot(tmp_path, validator=validator)
    assert after["ok"] is True
    assert isinstance(after["payload"]["deploy_artifact"], dict)
