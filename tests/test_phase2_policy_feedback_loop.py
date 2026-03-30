import json
from pathlib import Path

from tools.lib.failure_policy import resolve_heal_strategy


def test_resolver_uses_default_without_insights(tmp_path):
    strategy = resolve_heal_strategy(
        {
            "type": "state_failure",
            "severity": "high",
            "recoverable": True,
            "confidence": 0.95,
            "risk": "mid",
        },
        base_dir=tmp_path,
    )
    assert strategy == "auto_heal"


def test_resolver_can_use_insight_file_without_breaking_default(tmp_path):
    p = tmp_path / "state" / "learning_memory"
    p.mkdir(parents=True, exist_ok=True)
    (p / "failure_insights.json").write_text(
        json.dumps(
            {
                "episode_count": 5,
                "risk_summary": {
                    "execution_failure": {"high": 4},
                    "rate_limit_failure": {"low": 5},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    strategy1 = resolve_heal_strategy(
        {
            "type": "execution_failure",
            "severity": "high",
            "recoverable": True,
            "confidence": 0.95,
            "risk": "high",
        },
        base_dir=tmp_path,
    )
    assert strategy1 == "retry_or_skip"

    strategy2 = resolve_heal_strategy(
        {
            "type": "rate_limit_failure",
            "severity": "mid",
            "recoverable": True,
            "confidence": 0.90,
            "risk": "low",
        },
        base_dir=tmp_path,
    )
    assert strategy2 == "retry_or_skip"
