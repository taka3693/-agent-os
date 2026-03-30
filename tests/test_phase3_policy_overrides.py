import json
from pathlib import Path

from tools.lib.failure_memory import append_failure_episodes
from tools.lib.failure_insights import write_failure_insights
from tools.lib.policy_suggestions import append_policy_suggestions
from tools.lib.policy_review_queue import mark_policy_suggestion_status
from tools.lib.policy_overrides import (
    build_policy_overrides,
    write_policy_overrides,
    load_policy_overrides,
)
from tools.lib.failure_policy import resolve_heal_strategy


def test_build_policy_overrides_from_approved_suggestion(tmp_path):
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
        reviewer_note="be conservative",
        base_dir=tmp_path,
    )

    data = build_policy_overrides(base_dir=tmp_path)
    assert data["overrides"]["execution_failure"] == "manual_review"


def test_write_and_load_policy_overrides(tmp_path):
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
    mark_policy_suggestion_status(
        index=0,
        status="approved",
        reviewer_note="prefer backoff",
        base_dir=tmp_path,
    )

    out = write_policy_overrides(base_dir=tmp_path)
    assert out["ok"] is True

    data = load_policy_overrides(base_dir=tmp_path)
    assert data["overrides"]["rate_limit_failure"] == "backoff_retry"


def test_resolver_reads_policy_overrides(tmp_path):
    p = tmp_path / "state"
    p.mkdir(parents=True, exist_ok=True)
    (p / "policy_overrides.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-29T00:00:00+00:00",
                "overrides": {
                    "execution_failure": "manual_review",
                },
                "sources": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    strategy = resolve_heal_strategy(
        {
            "type": "execution_failure",
            "severity": "high",
            "recoverable": True,
            "confidence": 0.95,
            "risk": "high",
        },
        base_dir=tmp_path,
    )
    assert strategy == "manual_review"
