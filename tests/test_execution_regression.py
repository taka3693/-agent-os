from pathlib import Path
import json
import glob

from skills.execution.execution_impl import run_execution


def _base_query():
    return {
        "findings": [
            {
                "kind": "missing_evidence",
                "issue": "evidence_missing",
                "message": "根拠が不足している",
                "field": "evidence",
            }
        ],
        "state": {
            "constraints": [],
            "evidence": [],
            "next_actions": [],
        },
    }


def test_fresh_input_converges():
    out = run_execution(_base_query())
    assert out["ok"] is True
    assert out["status"] == "completed"
    assert out["post_execution_findings"] == []


def test_already_in_state_is_skipped_but_verified():
    query = _base_query()
    query["state"]["evidence"] = [
        {
            "type": "missing_evidence",
            "message": "根拠が不足している",
            "finding_key": "missing_evidence|根拠が不足している",
        }
    ]

    out = run_execution(query)
    assert out["ok"] is True
    assert out["status"] == "completed"

    all_results = []
    for it in out["execution_result"]["iterations"]:
        all_results.extend(it["results"])

    assert any(
        r["result"].get("status") == "skipped"
        and r["result"].get("reason") == "already_in_state"
        for r in all_results
    )
    assert any(
        r["result"].get("status") == "verified"
        for r in all_results
    )


def test_duplicate_findings_are_not_double_applied():
    query = _base_query()
    query["findings"] = [
        query["findings"][0],
        dict(query["findings"][0]),
    ]

    out = run_execution(query)
    applied = out["execution_result"]["applied_fixes"]

    evidence_keys = [
        x.get("finding_key")
        for x in applied
        if isinstance(x, dict)
    ]

    assert evidence_keys.count("missing_evidence|根拠が不足している") == 1


def test_audit_log_contains_stats():
    before = set(glob.glob("runtime_logs/execution/execution_*.json"))
    out = run_execution(_base_query())
    assert out["ok"] is True

    after = set(glob.glob("runtime_logs/execution/execution_*.json"))
    created = sorted(after - before)
    assert created, "no audit log created"

    latest = created[-1]
    data = json.loads(Path(latest).read_text(encoding="utf-8"))

    assert "stats" in data
    assert data["stats"]["converged"] is True
    assert data["stats"]["initial_findings_count"] >= 1
    assert data["stats"]["final_findings_count"] == 0


def test_structured_fix_entries_are_written():
    out = run_execution(_base_query())
    assert out["ok"] is True

    state = out["state"]

    assert state["evidence"], "evidence should not be empty"
    assert state["constraints"], "constraints should not be empty"
    assert state["next_actions"], "next_actions should not be empty"

    ev = state["evidence"][0]
    cs = state["constraints"][0]
    na = state["next_actions"][0]

    assert ev["field"] == "evidence"
    assert ev["evidence_type"] == "generated"
    assert "finding_key" in ev

    assert cs["field"] == "constraints"
    assert cs["constraint_type"] == "guardrail"
    assert "constraint" in cs

    assert na["field"] == "next_actions"
    assert na["action_type"] == "followup"
    assert "action" in na


def test_applied_fix_carries_entry():
    out = run_execution(_base_query())
    assert out["ok"] is True

    found = []
    for it in out["execution_result"]["iterations"]:
        for r in it["results"]:
            result = r.get("result", {})
            if result.get("action_type") == "fix_finding" and result.get("status") == "completed":
                applied_fix = result.get("applied_fix", {})
                if isinstance(applied_fix, dict):
                    found.append(applied_fix)

    assert found, "no applied fixes found"
    assert any(isinstance(x.get("entry"), dict) and x["entry"].get("field") for x in found)


def test_evidence_entry_has_template():
    out = run_execution(_base_query())
    assert out["ok"] is True

    ev = out["state"]["evidence"][0]
    assert ev["field"] == "evidence"
    assert ev["evidence_type"] == "generated"
    assert isinstance(ev.get("evidence_item"), dict)
    assert ev["evidence_item"]["source_type"] == "generated"
    assert ev["evidence_item"]["confidence"] == "low"
    assert ev["evidence_item"]["needs_review"] is True


def test_evidence_confidence_is_inferred():
    out = run_execution(_base_query())
    assert out["ok"] is True

    ev = out["state"]["evidence"][0]
    item = ev["evidence_item"]

    assert item["confidence"] in {"low", "medium", "high"}
    assert item["needs_review"] in {True, False}


def test_high_confidence_evidence_updates_policy():
    query = {
        "findings": [
            {
                "kind": "missing_evidence",
                "message": "pytestで検証成功した結果がある",
                "field": "evidence",
            }
        ],
        "state": {
            "constraints": [],
            "evidence": [],
            "next_actions": [],
        },
    }

    out = run_execution(query)
    assert out["ok"] is True
    assert out["evidence_policy"]["has_high_confidence_evidence"] is True
    assert out["evidence_policy"]["review_required"] is False
