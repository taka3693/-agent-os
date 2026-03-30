import json
from pathlib import Path

from tools.lib.failure_memory import append_failure_episodes
from tools.lib.failure_insights import write_failure_insights
from tools.lib.policy_suggestions import build_policy_suggestions, append_policy_suggestions


def test_build_policy_suggestions_basic(tmp_path):
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
    suggestions = build_policy_suggestions(base_dir=tmp_path)

    assert len(suggestions) >= 1
    assert suggestions[0]["kind"] == "policy_suggestion"
    assert suggestions[0]["status"] == "pending_review"


def test_append_policy_suggestions_writes_jsonl(tmp_path):
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
    out = append_policy_suggestions(base_dir=tmp_path)

    assert out["ok"] is True
    p = Path(out["path"])
    assert p.exists() is True

    lines = [x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) >= 1
    row = json.loads(lines[0])
    assert row["kind"] == "policy_suggestion"
    assert row["status"] == "pending_review"
