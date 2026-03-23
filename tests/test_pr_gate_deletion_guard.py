import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.pr_gate import assess_risk, decide_merge_recommendation, build_checklist


def test_assess_risk_medium_without_blocked_deletions():
    policy = {
        "max_files_changed": 20,
        "max_additions": 500,
        "max_deletions": 200,
        "warn_files_changed": 8,
        "warn_additions": 150,
        "warn_deletions": 50,
    }

    changed_files = [f"file{i}.py" for i in range(10)]
    diff_summary = {"changed_files": 10, "additions": 20, "deletions": 10}
    blocked_deletions = []

    risk = assess_risk(changed_files, diff_summary, policy, blocked_deletions)

    assert risk == "medium"


def test_assess_risk_high_with_blocked_deletions():
    policy = {
        "max_files_changed": 20,
        "max_additions": 500,
        "max_deletions": 200,
        "warn_files_changed": 8,
        "warn_additions": 150,
        "warn_deletions": 50,
    }

    changed_files = ["tools/approve_pr.py"]
    diff_summary = {"changed_files": 1, "additions": 1, "deletions": 1}
    blocked_deletions = ["tools/approve_pr.py"]

    risk = assess_risk(changed_files, diff_summary, policy, blocked_deletions)

    assert risk == "high"


def test_decide_merge_recommendation_hard_block_with_blocked_deletions():
    merge = decide_merge_recommendation(
        risk_level="high",
        blocked_deletions=["tools/approve_pr.py"],
    )

    assert merge == "hard_block"


def test_decide_merge_recommendation_manual_for_medium_without_blocked_deletions():
    merge = decide_merge_recommendation(
        risk_level="medium",
        blocked_deletions=[],
    )

    assert merge == "manual_approval_required"


def test_build_checklist_includes_hard_block_reason():
    checklist = build_checklist(
        risk_level="high",
        merge_recommendation="hard_block",
        blocked_deletions=["tools/approve_pr.py"],
    )

    assert any("Hard Block: protected paths deleted:" in item for item in checklist)
    assert any("tools/approve_pr.py" in item for item in checklist)


def test_build_checklist_manual_review_message_for_medium():
    checklist = build_checklist(
        risk_level="medium",
        merge_recommendation="manual_approval_required",
        blocked_deletions=[],
    )

    assert "Merge requires manual approval" in checklist
