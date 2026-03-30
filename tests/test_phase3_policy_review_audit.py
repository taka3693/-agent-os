import json
import subprocess
import sys
from pathlib import Path

from tools.lib.failure_memory import append_failure_episodes
from tools.lib.failure_insights import write_failure_insights
from tools.lib.policy_suggestions import append_policy_suggestions


def test_policy_review_cli_writes_audit_log(tmp_path):
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
        "--reviewer", "boss",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)

    assert data["ok"] is True
    assert data["audit"]["ok"] is True
    assert data["audit"]["event"]["reviewer"] == "boss"
    assert data["audit"]["event"]["status"] == "approved"

    audit_path = Path(data["audit"]["path"])
    assert audit_path.exists() is True

    lines = [x for x in audit_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) >= 1
    row = json.loads(lines[0])
    assert row["kind"] == "policy_review_audit"
    assert row["reviewer"] == "boss"
