from tools.lib.failure_policy import (
    detect_failures_from_anomalies,
    apply_heal_policy,
    build_failure_control_output,
)
from tools.lib.failure_integration import run_phase2_failure_control


def test_detect_failures_from_anomalies_basic():
    failures = detect_failures_from_anomalies([
        "snapshot_unavailable",
        "deploy_not_executed",
        "rate_limit",
        "some_other_error",
    ])

    types = [x["type"] for x in failures]
    assert "snapshot_failure" in types
    assert "state_failure" in types
    assert "rate_limit_failure" in types
    assert "execution_failure" in types
    assert len(failures) == 4


def test_detect_failures_groups_same_type():
    failures = detect_failures_from_anomalies([
        "deploy_not_executed",
        "missing_deploy_artifact",
        "missing_executed_action",
    ])

    assert len(failures) == 1
    assert failures[0]["type"] == "state_failure"
    assert failures[0]["severity"] == "high"
    assert failures[0]["recoverable"] is True
    assert failures[0]["anomalies"] == [
        "deploy_not_executed",
        "missing_deploy_artifact",
        "missing_executed_action",
    ]


def test_apply_heal_policy_sets_strategy():
    failures = [
        {"type": "snapshot_failure"},
        {"type": "state_failure"},
        {"type": "execution_failure"},
        {"type": "rate_limit_failure"},
    ]

    out = apply_heal_policy(failures)

    mapping = {x["type"]: x["strategy"] for x in out}
    assert mapping["snapshot_failure"] == "repair_snapshot"
    assert mapping["state_failure"] == "auto_heal"
    assert mapping["execution_failure"] == "retry_or_skip"
    assert mapping["rate_limit_failure"] == "retry_or_skip"


def test_build_failure_control_output_contains_expected_keys():
    out = build_failure_control_output(
        result={"ok": True},
        anomalies=["snapshot_unavailable", "deploy_not_executed"],
    )

    assert "result" in out
    assert "failure_control" in out

    fc = out["failure_control"]
    assert fc["failure_count"] == 2
    assert len(fc["failures"]) == 2
    assert "policy" in fc
    assert "heal_actions" in fc
    assert "snapshot_repair" in fc
    assert "auto_heal" in fc


def test_run_phase2_failure_control_attaches_failure_fields():
    result = {
        "ok": True,
        "state_anomalies": ["deploy_not_executed"],
        "snapshot_anomalies": ["snapshot_unavailable"],
    }

    out = run_phase2_failure_control(
        result,
        state_anomalies=result["state_anomalies"],
        snapshot_anomalies=result["snapshot_anomalies"],
    )

    assert "failure_control" in out
    assert "failures" in out
    assert out["failure_count"] == 2
    assert out["snapshot_repair_attempted"] is False
    assert out["snapshot_repaired"] is False
    assert out["auto_heal_attempted"] is False
    assert out["auto_heal_applied"] is False
    assert out["healed_keys"] == []
