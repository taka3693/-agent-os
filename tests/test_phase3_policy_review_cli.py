import json
import subprocess
import sys
from pathlib import Path

from tools.lib.failure_memory import append_failure_episodes
from tools.lib.failure_insights import write_failure_insights
from tools.lib.policy_suggestions import append_policy_suggestions


def test_policy_review_cli_list(tmp_path):
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

    cmd = [
        sys.executable,
        "tools/policy_review_cli.py",
        "--base-dir", str(tmp_path),
        "list",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)

    assert data["ok"] is True
    assert data["count"] >= 1
    assert data["items"][0]["status"] == "pending_review"


def test_policy_review_cli_review_updates_override(tmp_path):
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

    cmd = [
        sys.executable,
        "tools/policy_review_cli.py",
        "--base-dir", str(tmp_path),
        "review",
        "--index", "0",
        "--status", "approved",
        "--note", "apply conservative bias",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)

    assert data["ok"] is True
    assert data["review"]["updated"]["status"] == "approved"
    assert data["policy_overrides"]["ok"] is True

    override_path = Path(data["policy_overrides"]["path"])
    assert override_path.exists() is True
