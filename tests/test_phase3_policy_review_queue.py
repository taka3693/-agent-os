from tools.lib.failure_memory import append_failure_episodes
from tools.lib.failure_insights import write_failure_insights
from tools.lib.policy_suggestions import append_policy_suggestions
from tools.lib.policy_review_queue import (
    list_pending_policy_suggestions,
    mark_policy_suggestion_status,
)


def test_policy_review_queue_lists_pending(tmp_path):
    for _ in range(5):
        append_failure_episodes(
            {
                "failure_control": {
                    "failures": [
                        {
                            "type": "rate_limit_failure",
                            "severity": "mid",
                            "recoverable": True,
                            "confidence": 0.90,
                            "risk": "low",
                            "anomalies": ["rate_limit"],
                            "strategy": "retry_or_skip",
                        }
                    ],
                    "heal_actions": [
                        {
                            "failure_type": "rate_limit_failure",
                            "strategy": "retry_or_skip",
                            "decision": "retry",
                            "reason": "rate_limit_recoverable",
                        }
                    ],
                },
                "healed_keys": [],
                "snapshot_repair_attempted": False,
                "snapshot_repaired": False,
                "auto_heal_attempted": False,
                "auto_heal_applied": False,
            },
            base_dir=tmp_path,
        )

    write_failure_insights(base_dir=tmp_path)
    append_policy_suggestions(base_dir=tmp_path)

    rows = list_pending_policy_suggestions(base_dir=tmp_path)
    assert len(rows) >= 1
    assert rows[0]["status"] == "pending_review"


def test_policy_review_queue_can_approve(tmp_path):
    for _ in range(5):
        append_failure_episodes(
            {
                "failure_control": {
                    "failures": [
                        {
                            "type": "execution_failure",
                            "severity": "high",
                            "recoverable": True,
                            "confidence": 0.95,
                            "risk": "high",
                            "anomalies": ["process_exit_nonzero"],
                            "strategy": "retry_or_skip",
                        }
                    ],
                    "heal_actions": [
                        {
                            "failure_type": "execution_failure",
                            "strategy": "retry_or_skip",
                            "decision": "retry",
                            "reason": "execution_recoverable",
                        }
                    ],
                },
                "healed_keys": [],
                "snapshot_repair_attempted": False,
                "snapshot_repaired": False,
                "auto_heal_attempted": False,
                "auto_heal_applied": False,
            },
            base_dir=tmp_path,
        )

    write_failure_insights(base_dir=tmp_path)
    append_policy_suggestions(base_dir=tmp_path)

    out = mark_policy_suggestion_status(
        index=0,
        status="approved",
        reviewer_note="apply conservative bias",
        base_dir=tmp_path,
    )

    assert out["ok"] is True
    assert out["updated"]["status"] == "approved"
    assert out["updated"]["reviewer_note"] == "apply conservative bias"
