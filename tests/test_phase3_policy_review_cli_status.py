import json
import subprocess
import sys

from tools.lib.failure_memory import append_failure_episodes
from tools.lib.failure_insights import write_failure_insights
from tools.lib.policy_suggestions import append_policy_suggestions
from tools.lib.policy_review_queue import mark_policy_suggestion_status
from tools.lib.policy_overrides import write_policy_overrides
from tools.lib.policy_review_audit import append_policy_review_audit


def test_policy_review_cli_status_shows_summary(tmp_path):
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
    mark_policy_suggestion_status(
        index=0,
        status="approved",
        reviewer_note="apply conservative bias",
        base_dir=tmp_path,
    )
    write_policy_overrides(base_dir=tmp_path)
    append_policy_review_audit(
        action="review",
        updated={
            "failure_type": "execution_failure",
            "suggested_action": "manual_review_bias",
            "status": "approved",
            "reason": "high_risk_execution_failures_accumulated",
            "reviewer_note": "apply conservative bias",
            "reviewed_at": "2026-03-29T00:00:00+00:00",
        },
        reviewer="boss",
        base_dir=tmp_path,
    )

    cmd = [
        sys.executable,
        "tools/policy_review_cli.py",
        "--base-dir", str(tmp_path),
        "status",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)

    assert data["ok"] is True
    assert "pending_policy_suggestion_count" in data
    assert "active_policy_override_count" in data
    assert "active_policy_override_types" in data
    assert "latest_policy_review_audit" in data
    assert "insight_summary" in data
    assert "learning_control_preview" in data
    assert data["active_policy_override_count"] >= 1
