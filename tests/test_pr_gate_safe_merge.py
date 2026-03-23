from tools.pr_gate import decide_merge_recommendation


def test_decide_merge_recommendation_safe_for_low_risk_without_blocked_deletions():
    merge = decide_merge_recommendation(
        risk_level="low",
        blocked_deletions=[],
        checks={
            "syntax": "pass",
            "tests": "pass",
            "freshness": "unknown",
        },
    )
    assert merge == "safe_merge"


def test_decide_merge_recommendation_manual_approval_for_medium_risk():
    merge = decide_merge_recommendation(
        risk_level="medium",
        blocked_deletions=[],
        checks={
            "syntax": "pass",
            "tests": "pass",
            "freshness": "unknown",
        },
    )
    assert merge == "manual_approval_required"


def test_decide_merge_recommendation_hard_block_when_tests_fail():
    merge = decide_merge_recommendation(
        risk_level="low",
        blocked_deletions=[],
        checks={
            "syntax": "pass",
            "tests": "fail",
            "freshness": "unknown",
        },
    )
    assert merge == "hard_block"


def test_decide_merge_recommendation_hard_block_when_syntax_fail():
    merge = decide_merge_recommendation(
        risk_level="low",
        blocked_deletions=[],
        checks={
            "syntax": "fail",
            "tests": "pass",
            "freshness": "unknown",
        },
    )
    assert merge == "hard_block"
