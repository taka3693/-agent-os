from tools.lib.failure_policy import resolve_heal_strategy, apply_heal_policy


def test_resolve_heal_strategy_defaults():
    assert resolve_heal_strategy({
        "type": "snapshot_failure",
        "severity": "high",
        "recoverable": True,
        "confidence": 0.95,
        "risk": "high",
    }) == "repair_snapshot"

    assert resolve_heal_strategy({
        "type": "state_failure",
        "severity": "high",
        "recoverable": True,
        "confidence": 0.95,
        "risk": "mid",
    }) == "auto_heal"

    assert resolve_heal_strategy({
        "type": "rate_limit_failure",
        "severity": "mid",
        "recoverable": True,
        "confidence": 0.90,
        "risk": "low",
    }) == "retry_or_skip"


def test_resolve_heal_strategy_honors_policy_override():
    strategy = resolve_heal_strategy(
        {
            "type": "state_failure",
            "severity": "high",
            "recoverable": True,
            "confidence": 0.95,
            "risk": "mid",
        },
        policy={"state_failure": "manual_review"},
    )
    assert strategy == "manual_review"


def test_apply_heal_policy_uses_resolver():
    out = apply_heal_policy([
        {
            "type": "snapshot_failure",
            "severity": "high",
            "recoverable": True,
            "confidence": 0.95,
            "risk": "high",
        },
        {
            "type": "state_failure",
            "severity": "high",
            "recoverable": True,
            "confidence": 0.95,
            "risk": "mid",
        },
    ])

    assert out[0]["strategy"] == "repair_snapshot"
    assert out[1]["strategy"] == "auto_heal"
