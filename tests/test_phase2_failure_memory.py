from pathlib import Path

from tools.lib.failure_memory import build_failure_episodes, append_failure_episodes


def test_build_failure_episodes_basic():
    result = {
        "failure_control": {
            "failures": [
                {
                    "type": "state_failure",
                    "severity": "high",
                    "recoverable": True,
                    "confidence": 0.95,
                    "risk": "mid",
                    "anomalies": ["deploy_not_executed"],
                    "strategy": "auto_heal",
                }
            ],
            "heal_actions": [
                {
                    "failure_type": "state_failure",
                    "strategy": "auto_heal",
                    "decision": None,
                    "reason": None,
                }
            ],
        },
        "healed_keys": ["deploy_artifact", "executed_action"],
        "snapshot_repair_attempted": False,
        "snapshot_repaired": False,
        "auto_heal_attempted": True,
        "auto_heal_applied": True,
    }

    episodes = build_failure_episodes(result)
    assert len(episodes) == 1

    ep = episodes[0]
    assert ep["failure_type"] == "state_failure"
    assert ep["chosen_strategy"] == "auto_heal"
    assert ep["healed_keys"] == ["deploy_artifact", "executed_action"]
    assert ep["outcome"]["auto_heal_applied"] is True


def test_append_failure_episodes_writes_jsonl(tmp_path):
    result = {
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
    }

    out = append_failure_episodes(result, base_dir=tmp_path)
    assert out["ok"] is True
    assert out["count"] == 1

    p = Path(out["path"])
    assert p.exists() is True
    text = p.read_text(encoding="utf-8")
    assert "rate_limit_failure" in text
    assert "retry_or_skip" in text
