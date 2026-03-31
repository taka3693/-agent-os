import json
import subprocess
import sys


def test_execution_verified_flow():
    cp = subprocess.run(
        [sys.executable, "tools/run_agent_os_request.py", "test verify behavior"],
        capture_output=True,
        text=True,
        check=True,
    )

    lines = [line.strip() for line in cp.stdout.splitlines() if line.strip()]
    payload = None
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            payload = json.loads(line)
            break

    assert payload is not None, "top-level JSON not found"

    chain_results = payload.get("chain_results", [])
    assert chain_results, "chain_results missing"

    execution_output = chain_results[0]["output"]
    results = execution_output.get("results", [])
    statuses = [r.get("status") for r in results if isinstance(r, dict)]

    assert "success" in statuses, statuses
    assert "completed" in statuses, statuses
    assert "verified" in statuses, statuses

    evidence_policy = execution_output.get("evidence_policy", {})
    assert evidence_policy.get("has_validated_evidence") is True, evidence_policy

    state = execution_output.get("state", {})
    evidence = state.get("evidence", [])
    assert evidence, "evidence missing"

    assert any(
        isinstance(item, dict)
        and (
            item.get("validated") is True
            or ((item.get("evidence_item") or {}).get("validated") is True)
        )
        for item in evidence
    ), evidence

    assert execution_output.get("post_execution_findings") == [], execution_output.get("post_execution_findings")
