from tools.run_agent_os_request import process_request


def test_process_request_keeps_phase2_failure_control():
    out = process_request("hello")

    assert isinstance(out, dict)
    assert "failure_control" in out
    assert "failures" in out
    assert "failure_count" in out

    fc = out["failure_control"]
    assert isinstance(fc, dict)
    assert "anomalies" in fc
    assert "failures" in fc
    assert "failure_count" in fc
    assert "policy" in fc
    assert "heal_actions" in fc
    assert "snapshot_repair" in fc
    assert "auto_heal" in fc
