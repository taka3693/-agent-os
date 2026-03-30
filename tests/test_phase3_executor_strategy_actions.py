from tools.lib.failure_policy import build_failure_control_output


def test_executor_records_manual_review_action():
    out = build_failure_control_output(
        result={"ok": True},
        anomalies=["process_exit_nonzero"],
        policy={"execution_failure": "manual_review"},
    )

    fc = out["failure_control"]
    assert fc["failure_count"] == 1
    assert len(fc["heal_actions"]) == 1
    action = fc["heal_actions"][0]
    assert action["strategy"] == "manual_review"
    assert action["decision"] == "manual_review"
    assert action["reason"] == "requires_human_review"


def test_executor_records_backoff_retry_action():
    out = build_failure_control_output(
        result={"ok": True},
        anomalies=["rate_limit"],
        policy={"rate_limit_failure": "backoff_retry"},
    )

    fc = out["failure_control"]
    assert fc["failure_count"] == 1
    assert len(fc["heal_actions"]) == 1
    action = fc["heal_actions"][0]
    assert action["strategy"] == "backoff_retry"
    assert action["decision"] == "backoff_retry"
    assert action["reason"] == "policy_override_backoff_retry"
