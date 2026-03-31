import json

from skills.execution import run_execution


def test_fix_result_evidence_flows_into_state():
    query = {
        "type": "execution",
        "goal": "fix_finding の evidence 流入確認",
        "findings": [
            {
                "finding_key": "dummy-finding-1",
                "type": "test",
                "severity": "low",
                "target_step": "apply_fixes",
                "message": "dummy finding for execution evidence flow test",
            }
        ],
    }

    out = run_execution(query)
    state = out.get("state", {}) or {}
    exec_result = out.get("execution_result", {}) or {}

    state_execution_evidence = state.get("execution_evidence", [])
    result_execution_evidence = exec_result.get("execution_evidence", [])
    state_evidence = state.get("evidence", [])

    assert state_execution_evidence, "state.execution_evidence should not be empty"
    assert result_execution_evidence, "execution_result.execution_evidence should not be empty"

    assert any(
        isinstance(item, dict)
        and item.get("action_type") == "fix_finding"
        and "dummy finding for execution evidence flow test" in str(item.get("finding_key", ""))
        for item in state_execution_evidence
    ), state_execution_evidence

    matched = [
        item for item in state_evidence
        if isinstance(item, dict)
        and item.get("source_type") == "external"
        and item.get("finding_key") == "test|dummy finding for execution evidence flow test__evidence__"
    ]
    assert matched, state_evidence

    item = matched[0]
    assert item.get("confidence") in ("medium", "high"), item
    assert isinstance(item.get("validated"), bool), item
