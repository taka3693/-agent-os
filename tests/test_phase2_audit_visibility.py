from tools.run_agent_os_request import process_request


def test_process_request_exposes_phase2_visibility_fields():
    out = process_request("hello")

    assert "failure_count" in out
    assert "failure_types" in out
    assert "heal_action_count" in out
    assert "snapshot_repair_attempted" in out
    assert "snapshot_repaired" in out
    assert "auto_heal_attempted" in out
    assert "auto_heal_applied" in out
    assert "healed_keys" in out

    assert isinstance(out["failure_types"], list)
    assert isinstance(out["heal_action_count"], int)
    assert isinstance(out["healed_keys"], list)
