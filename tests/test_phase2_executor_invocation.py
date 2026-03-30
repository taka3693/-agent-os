from tools.lib.failure_policy import build_failure_control_output


def test_executor_invokes_snapshot_repair_and_auto_heal():
    calls = {
        "repair_snapshot": 0,
        "auto_heal": 0,
    }

    def fake_repair_snapshot_fn(*, base_dir=None):
        calls["repair_snapshot"] += 1
        return {
            "attempted": True,
            "repaired": True,
            "selected_kind": "versioned",
        }

    def fake_auto_heal_fn(result, *, base_dir=None):
        calls["auto_heal"] += 1
        out = dict(result)
        out["healed_marker"] = True
        return {
            "result": out,
            "healed_keys": ["deploy_artifact", "executed_action"],
        }

    out = build_failure_control_output(
        result={"ok": True},
        anomalies=["snapshot_unavailable", "deploy_not_executed"],
        repair_snapshot_fn=fake_repair_snapshot_fn,
        auto_heal_fn=fake_auto_heal_fn,
    )

    assert calls["repair_snapshot"] == 1
    assert calls["auto_heal"] == 1

    fc = out["failure_control"]
    assert fc["snapshot_repair"]["attempted"] is True
    assert fc["snapshot_repair"]["repaired"] is True
    assert fc["snapshot_repair"]["selected_kind"] == "versioned"

    assert fc["auto_heal"]["attempted"] is True
    assert fc["auto_heal"]["healed"] is True
    assert fc["auto_heal"]["healed_keys"] == ["deploy_artifact", "executed_action"]

    assert out["result"]["healed_marker"] is True
    assert len(fc["heal_actions"]) == 2
