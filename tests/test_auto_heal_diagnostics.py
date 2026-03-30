import json
from pathlib import Path

import tools.run_agent_os_request as mod


def test_detect_state_anomalies_empty_on_normal_deploy_shape():
    result = {
        "next_action": "deploy",
        "executed_action": "deploy",
        "deploy_artifact": {"json_path": "/tmp/a.json", "markdown_path": "/tmp/a.md"},
        "rollback_info": {"restored_from": "/tmp/x", "snapshot_kind": "latest"},
        "execution_log": "deploy executed: /tmp/a.json",
    }
    anomalies = mod._detect_state_anomalies(result)
    assert anomalies == []

def test_auto_heal_partial_restores_deploy_state_from_valid_snapshot(tmp_path, monkeypatch):
    rollback_dir = tmp_path / "state" / "rollback"
    rollback_dir.mkdir(parents=True)

    latest = rollback_dir / "rollback.latest.json"
    latest.write_text(
        json.dumps(
            {
                "deploy_artifact": {
                    "json_path": "/tmp/deploy.json",
                    "markdown_path": "/tmp/deploy.md",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))

    result = {
        "next_action": "deploy",
        "executed_action": None,
        "deploy_artifact": None,
        "rollback_info": None,
        "execution_log": "blocked: deploy rate limit used=1 limit=1",
    }

    healed = mod._auto_heal_result(result)

    assert healed["executed_action"] == "deploy"
    assert isinstance(healed["deploy_artifact"], dict)
    assert isinstance(healed["rollback_info"], dict)
    assert healed["auto_heal"]["ok"] is True
    assert healed["auto_heal"]["mode"] == "partial"
    assert "deploy_artifact" in healed["auto_heal"]["healed_keys"]
    assert "executed_action" in healed["auto_heal"]["healed_keys"]
    assert "rollback_info" in healed["auto_heal"]["healed_keys"]

def test_detect_snapshot_anomalies_when_snapshot_missing(tmp_path, monkeypatch):
    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))

    anomalies = mod._detect_snapshot_anomalies()
    assert "snapshot_unavailable" in anomalies

def test_detect_snapshot_anomalies_when_latest_missing_artifact(tmp_path, monkeypatch):
    rollback_dir = tmp_path / "state" / "rollback"
    rollback_dir.mkdir(parents=True)

    latest = rollback_dir / "rollback.latest.json"
    latest.write_text(
        json.dumps({"deploy_artifact": None}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))

    anomalies = mod._detect_snapshot_anomalies()
    assert "snapshot_missing_deploy_artifact" in anomalies

def test_audit_e2e_partial_heal_writes_auto_heal_summary(tmp_path, monkeypatch):
    rollback_dir = tmp_path / "state" / "rollback"
    rollback_dir.mkdir(parents=True)

    (rollback_dir / "rollback.latest.json").write_text(
        json.dumps(
            {
                "deploy_artifact": {
                    "json_path": "/tmp/healed.json",
                    "markdown_path": "/tmp/healed.md",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    result = {
        "task_id": "task-partial-heal-audit",
        "query": "audit partial heal e2e",
        "selected_skill": "decision",
        "selected_skills": ["execution", "critique"],
        "next_action": "deploy",
        "executed_action": None,
        "deploy_artifact": None,
        "rollback_info": None,
        "execution_log": "blocked: deploy rate limit used=1 limit=1",
    }

    normalized = mod._normalize_execution_state(result)
    log_path = Path(mod._append_audit_log(normalized))

    last = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])

    assert isinstance(last.get("auto_heal"), dict)
    assert last["auto_heal"]["ok"] is True
    assert isinstance(last.get("auto_heal_summary"), dict)
    assert last["auto_heal_summary"]["ok"] is True
    assert last["auto_heal_summary"]["mode"] == "partial"
    assert "deploy_artifact" in (last["auto_heal_summary"]["healed_keys"] or [])
    assert isinstance(last.get("diagnostics"), dict)

def test_audit_e2e_snapshot_repair_writes_snapshot_repair_summary(tmp_path, monkeypatch):
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
                    "json_path": "/tmp/repaired.json",
                    "markdown_path": "/tmp/repaired.md",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    result = {
        "task_id": "task-snapshot-repair-audit",
        "query": "audit snapshot repair e2e",
        "selected_skill": "decision",
        "selected_skills": ["execution", "critique"],
        "next_action": "deploy",
        "executed_action": "deploy",
        "deploy_artifact": {
            "json_path": "/tmp/current.json",
            "markdown_path": "/tmp/current.md",
        },
        "rollback_info": {
            "restored_from": "/tmp/original",
            "snapshot_kind": "latest",
        },
        "execution_log": "deploy executed: /tmp/current.json",
    }

    normalized = mod._normalize_execution_state(result)
    log_path = Path(mod._append_audit_log(normalized))

    last = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])

    assert isinstance(last.get("snapshot_repair"), dict)
    assert last["snapshot_repair"]["ok"] is True
    assert last["snapshot_repair"]["repaired"] is True
    assert isinstance(last.get("snapshot_repair_summary"), dict)
    assert last["snapshot_repair_summary"]["ok"] is True
    assert last["snapshot_repair_summary"]["repaired"] is True
    assert last["snapshot_repair_summary"]["selected_kind"] == "versioned"
    assert isinstance(last.get("diagnostics"), dict)
    assert last["diagnostics"]["snapshot_repair_attempted"] is True
    assert last["diagnostics"]["snapshot_repaired"] is True

def test_visual_summary_e2e_partial_heal_marks_recovered(tmp_path, monkeypatch):
    rollback_dir = tmp_path / "state" / "rollback"
    rollback_dir.mkdir(parents=True)

    (rollback_dir / "rollback.latest.json").write_text(
        json.dumps(
            {
                "deploy_artifact": {
                    "json_path": "/tmp/healed.json",
                    "markdown_path": "/tmp/healed.md",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    result = {
        "task_id": "task-visual-partial-heal",
        "query": "visual summary partial heal e2e",
        "selected_skill": "decision",
        "selected_skills": ["execution", "critique"],
        "next_action": "deploy",
        "executed_action": None,
        "deploy_artifact": None,
        "rollback_info": None,
        "execution_log": "blocked: deploy rate limit used=1 limit=1",
    }

    normalized = mod._normalize_execution_state(result)
    log_path = Path(mod._append_audit_log(normalized))
    last = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])

    visual = last.get("visual_summary") or {}
    assert visual.get("status") == "recovered"
    assert "auto-heal:partial" in (visual.get("flags") or [])
    assert "executed:deploy" in (visual.get("flags") or [])
    assert isinstance(visual.get("headline"), str)
    assert "auto-heal:partial" in visual.get("headline", "")


def test_visual_summary_e2e_snapshot_repair_marks_recovered(tmp_path, monkeypatch):
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
                    "json_path": "/tmp/repaired.json",
                    "markdown_path": "/tmp/repaired.md",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    result = {
        "task_id": "task-visual-snapshot-repair",
        "query": "visual summary snapshot repair e2e",
        "selected_skill": "decision",
        "selected_skills": ["execution", "critique"],
        "next_action": "deploy",
        "executed_action": "deploy",
        "deploy_artifact": {
            "json_path": "/tmp/current.json",
            "markdown_path": "/tmp/current.md",
        },
        "rollback_info": {
            "restored_from": "/tmp/original",
            "snapshot_kind": "latest",
        },
        "execution_log": "deploy executed: /tmp/current.json",
    }

    normalized = mod._normalize_execution_state(result)
    log_path = Path(mod._append_audit_log(normalized))
    last = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])

    visual = last.get("visual_summary") or {}
    assert visual.get("status") == "recovered"
    assert "snapshot-repair:versioned" in (visual.get("flags") or [])
    assert "executed:deploy" in (visual.get("flags") or [])
    assert isinstance(visual.get("headline"), str)
    assert "snapshot-repair:versioned" in visual.get("headline", "")

def test_compact_summary_e2e_partial_heal_marks_recovered(tmp_path, monkeypatch):
    rollback_dir = tmp_path / "state" / "rollback"
    rollback_dir.mkdir(parents=True)

    (rollback_dir / "rollback.latest.json").write_text(
        json.dumps(
            {
                "deploy_artifact": {
                    "json_path": "/tmp/healed.json",
                    "markdown_path": "/tmp/healed.md",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    result = {
        "task_id": "task-compact-partial-heal",
        "query": "compact summary partial heal e2e",
        "selected_skill": "decision",
        "selected_skills": ["execution", "critique"],
        "next_action": "deploy",
        "executed_action": None,
        "deploy_artifact": None,
        "rollback_info": None,
        "execution_log": "blocked: deploy rate limit used=1 limit=1",
    }

    normalized = mod._normalize_execution_state(result)
    log_path = Path(mod._append_audit_log(normalized))
    last = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])

    compact = last.get("compact_summary") or {}
    assert compact.get("status") == "recovered"
    assert compact.get("healed") is True
    assert compact.get("heal_mode") == "partial"
    assert compact.get("executed_action") == "deploy"
    assert compact.get("state_anomaly_count") == 0


def test_compact_summary_e2e_snapshot_repair_marks_recovered(tmp_path, monkeypatch):
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
                    "json_path": "/tmp/repaired.json",
                    "markdown_path": "/tmp/repaired.md",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    result = {
        "task_id": "task-compact-snapshot-repair",
        "query": "compact summary snapshot repair e2e",
        "selected_skill": "decision",
        "selected_skills": ["execution", "critique"],
        "next_action": "deploy",
        "executed_action": "deploy",
        "deploy_artifact": {
            "json_path": "/tmp/current.json",
            "markdown_path": "/tmp/current.md",
        },
        "rollback_info": {
            "restored_from": "/tmp/original",
            "snapshot_kind": "latest",
        },
        "execution_log": "deploy executed: /tmp/current.json",
    }

    normalized = mod._normalize_execution_state(result)
    log_path = Path(mod._append_audit_log(normalized))
    last = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])

    compact = last.get("compact_summary") or {}
    assert compact.get("status") == "recovered"
    assert compact.get("snapshot_repaired") is True
    assert compact.get("snapshot_repair_kind") == "versioned"
    assert compact.get("executed_action") == "deploy"
    assert compact.get("snapshot_anomaly_count") == 0

def test_audit_compact_truncates_long_query_and_keeps_compact_artifact(tmp_path, monkeypatch):
    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    long_query = "x" * 400

    result = {
        "task_id": "task-compact-audit",
        "query": long_query,
        "selected_skill": "decision",
        "selected_skills": ["execution", "critique"],
        "next_action": "deploy",
        "executed_action": "deploy",
        "deploy_artifact": {
            "json_path": "/tmp/deploy.json",
            "markdown_path": "/tmp/deploy.md",
            "extra": "should_not_be_saved",
        },
        "rollback_info": {
            "latest": "/tmp/latest.json",
            "snapshot_kind": "latest",
        },
        "execution_log": "deploy executed: /tmp/deploy.json",
        "diagnostics": {
            "state_checked": True,
            "snapshot_checked": True,
            "state_anomaly_count": 0,
            "snapshot_anomaly_count": 0,
        },
        "state_anomalies": [],
        "snapshot_anomalies": [],
    }

    log_path = Path(mod._append_audit_log(result))
    last = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])

    assert isinstance(last.get("query"), str)
    assert len(last["query"]) < len(long_query)
    assert last["query"].endswith("...<truncated>")

    assert last.get("deploy_artifact") == {
        "json_path": "/tmp/deploy.json",
        "markdown_path": "/tmp/deploy.md",
    }


def test_audit_compact_limits_long_lists(tmp_path, monkeypatch):
    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    result = {
        "task_id": "task-compact-lists",
        "query": "list compaction test",
        "selected_skill": "decision",
        "selected_skills": ["a", "b", "c", "d", "e", "f", "g"],
        "next_action": "deploy",
        "executed_action": "deploy",
        "deploy_artifact": {
            "json_path": "/tmp/deploy.json",
            "markdown_path": "/tmp/deploy.md",
        },
        "rollback_info": {
            "latest": "/tmp/latest.json",
            "snapshot_kind": "latest",
        },
        "execution_log": ["l1", "l2", "l3", "l4", "l5", "l6", "l7"],
        "diagnostics": {
            "state_checked": True,
            "snapshot_checked": True,
            "state_anomaly_count": 6,
            "snapshot_anomaly_count": 6,
        },
        "state_anomalies": ["s1", "s2", "s3", "s4", "s5", "s6"],
        "snapshot_anomalies": ["p1", "p2", "p3", "p4", "p5", "p6"],
    }

    log_path = Path(mod._append_audit_log(result))
    last = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])

    assert last["selected_skills"][-1] == "...<2 more>"
    assert last["execution_log"][-1] == "l7"
    assert len(last["execution_log"]) == 5
    assert last["state_anomalies"][-1] == "...<1 more>"
    assert last["snapshot_anomalies"][-1] == "...<1 more>"

def test_rotate_audit_log_if_needed_rotates_when_size_exceeded(tmp_path, monkeypatch):
    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    entry_path = logs_dir / "execution_history.jsonl"
    entry_path.write_text("x" * 200, encoding="utf-8")

    rotation = mod._rotate_audit_log_if_needed(entry_path, max_bytes=100, backup_count=3)

    assert rotation["rotated"] is True
    assert rotation["reason"] == "size_limit"
    assert not entry_path.exists()
    assert (logs_dir / "execution_history.jsonl.1").exists()


def test_append_audit_log_writes_rotation_metadata_when_rotated(tmp_path, monkeypatch):
    target_file = tmp_path / "tools" / "run_agent_os_request.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# dummy", encoding="utf-8")

    monkeypatch.setattr(mod, "__file__", str(target_file))
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "AUDIT_LOG_MAX_BYTES", 100)

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    entry_path = logs_dir / "execution_history.jsonl"
    entry_path.write_text("y" * 200, encoding="utf-8")

    result = {
        "task_id": "task-audit-rotation",
        "query": "rotation test",
        "selected_skill": "decision",
        "selected_skills": ["execution", "critique"],
        "next_action": "deploy",
        "executed_action": "deploy",
        "deploy_artifact": {
            "json_path": "/tmp/deploy.json",
            "markdown_path": "/tmp/deploy.md",
        },
        "rollback_info": {
            "latest": "/tmp/latest.json",
            "snapshot_kind": "latest",
        },
        "execution_log": "deploy executed: /tmp/deploy.json",
        "diagnostics": {
            "state_checked": True,
            "snapshot_checked": True,
            "state_anomaly_count": 0,
            "snapshot_anomaly_count": 0,
        },
        "state_anomalies": [],
        "snapshot_anomalies": [],
    }

    log_path = Path(mod._append_audit_log(result))
    last = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])

    assert isinstance(last.get("audit_rotation"), dict)
    assert last["audit_rotation"]["rotated"] is True
    assert (logs_dir / "execution_history.jsonl.1").exists()
