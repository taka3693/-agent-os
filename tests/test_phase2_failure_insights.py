import json
from pathlib import Path

from tools.lib.failure_memory import append_failure_episodes
from tools.lib.failure_insights import build_failure_insights, write_failure_insights


def test_build_failure_insights_basic(tmp_path):
    result1 = {
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
        "healed_keys": ["deploy_artifact"],
        "snapshot_repair_attempted": False,
        "snapshot_repaired": False,
        "auto_heal_attempted": True,
        "auto_heal_applied": True,
    }

    result2 = {
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

    append_failure_episodes(result1, base_dir=tmp_path)
    append_failure_episodes(result2, base_dir=tmp_path)

    insights = build_failure_insights(base_dir=tmp_path)
    assert insights["episode_count"] == 2
    assert insights["top_failure_types"][0]["count"] >= 1
    assert "outcomes" in insights
    assert "risk_summary" in insights


def test_write_failure_insights_writes_json(tmp_path):
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
        "healed_keys": ["deploy_artifact"],
        "snapshot_repair_attempted": False,
        "snapshot_repaired": False,
        "auto_heal_attempted": True,
        "auto_heal_applied": True,
    }

    append_failure_episodes(result, base_dir=tmp_path)
    out = write_failure_insights(base_dir=tmp_path)

    assert out["ok"] is True
    p = Path(out["path"])
    assert p.exists() is True

    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["episode_count"] == 1
    assert "top_failure_types" in data
    assert "top_strategies" in data
