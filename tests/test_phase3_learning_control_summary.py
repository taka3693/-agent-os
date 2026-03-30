import json
from pathlib import Path

from tools.run_agent_os_request import process_request


def test_process_request_exposes_learning_control_summary_with_overrides_and_audit(tmp_path):
    state_dir = tmp_path / "state"
    (state_dir / "policy_suggestions").mkdir(parents=True, exist_ok=True)
    (state_dir / "audit").mkdir(parents=True, exist_ok=True)

    (state_dir / "policy_overrides.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-29T00:00:00+00:00",
                "overrides": {
                    "execution_failure": "manual_review",
                    "rate_limit_failure": "backoff_retry",
                },
                "sources": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    (state_dir / "policy_suggestions" / "policy_suggestions.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-03-29T00:00:00+00:00",
                "kind": "policy_suggestion",
                "failure_type": "state_failure",
                "suggested_action": "tighten_auto_heal_scope",
                "reason": "repeated_high_risk_state_failures",
                "status": "pending_review",
            },
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    (state_dir / "audit" / "policy_review_audit.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-03-29T00:00:00+00:00",
                "kind": "policy_review_audit",
                "action": "review",
                "reviewer": "boss",
                "failure_type": "execution_failure",
                "suggested_action": "manual_review_bias",
                "status": "approved",
                "reason": "high_risk_execution_failures_accumulated",
            },
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    out = process_request("hello", base_dir=tmp_path)

    assert out["policy_override_count"] == 2
    assert out["pending_policy_suggestion_count"] == 1
    assert out["latest_policy_review_audit"]["status"] == "approved"

    summary = out["learning_control_summary"]
    assert summary["policy_override_count"] == 2
    assert summary["pending_policy_suggestion_count"] == 1
    assert summary["latest_policy_review_audit"]["failure_type"] == "execution_failure"


def test_process_request_reply_text_contains_learning_control_block(tmp_path):
    out = process_request("hello", base_dir=tmp_path)

    assert "[learning-control]" in out["reply_text"]
    assert "failure_count:" in out["reply_text"]
    assert "active_overrides:" in out["reply_text"]
    assert "pending_suggestions:" in out["reply_text"]
