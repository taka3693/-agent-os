from tools.lib.failure_policy import build_failure_control_output


def test_retry_or_skip_for_rate_limit_failure():
    out = build_failure_control_output(
        result={"ok": True},
        anomalies=["rate_limit"],
        retry_or_skip_fn=lambda result, *, failure, base_dir=None: {
            "attempted": True,
            "decision": "retry",
            "reason": "rate_limit_recoverable",
        },
    )

    fc = out["failure_control"]
    assert fc["failure_count"] == 1
    assert len(fc["heal_actions"]) == 1
    assert fc["heal_actions"][0]["strategy"] == "retry_or_skip"
    assert fc["heal_actions"][0]["decision"] == "retry"
    assert fc["heal_actions"][0]["reason"] == "rate_limit_recoverable"


def test_retry_or_skip_default_skip_when_not_implemented():
    out = build_failure_control_output(
        result={"ok": True},
        anomalies=["some_other_error"],
    )

    fc = out["failure_control"]
    assert fc["failure_count"] == 1
    assert len(fc["heal_actions"]) == 1
    assert fc["heal_actions"][0]["strategy"] == "retry_or_skip"
    assert fc["heal_actions"][0]["decision"] == "skip"
    assert fc["heal_actions"][0]["reason"] == "retry_or_skip_not_implemented"
