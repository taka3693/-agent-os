from tools.lib.failure_policy import build_failure_control_output


def test_heal_actions_include_timing_metadata():
    out = build_failure_control_output(
        result={"ok": True},
        anomalies=["snapshot_unavailable", "deploy_not_executed", "rate_limit"],
        repair_snapshot_fn=lambda *, base_dir=None: {
            "attempted": True,
            "repaired": True,
            "selected_kind": "versioned",
        },
        auto_heal_fn=lambda result, *, base_dir=None: {
            "result": dict(result),
            "healed_keys": ["deploy_artifact"],
        },
        retry_or_skip_fn=lambda result, *, failure, base_dir=None: {
            "attempted": True,
            "decision": "retry",
            "reason": "rate_limit_recoverable",
        },
    )

    actions = out["failure_control"]["heal_actions"]
    assert len(actions) == 3

    for action in actions:
        assert "started_at" in action
        assert "finished_at" in action
        assert "duration_ms" in action
        assert isinstance(action["started_at"], str)
        assert isinstance(action["finished_at"], str)
        assert isinstance(action["duration_ms"], int)
