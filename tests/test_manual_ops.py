#!/usr/bin/env python3
"""Tests for Manual Ops Surface.

These tests verify:
- operational summary is exposed through manual ops surface
- apply plan status is exposed through manual ops surface
- manual apply is blocked when governance denies it
- manual apply is allowed only when governance/manual approval conditions are satisfied
- manual verification routes through verifier correctly
- manual policy evaluation routes through policy layer correctly
- manual ops surface does not bypass existing safety checks
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
sys.path.insert(0, str(PROJECT_ROOT / "governance"))
sys.path.insert(0, str(PROJECT_ROOT / "policy"))
sys.path.insert(0, str(PROJECT_ROOT / "verification"))

from tools.manual_ops import (
    show_operational_summary,
    show_apply_plan_status,
    show_apply_plan_audit_report,
    list_all_apply_plans,
    run_manual_verification,
    evaluate_manual_policy,
    evaluate_manual_governance,
    run_manual_apply,
    grant_manual_approval,
    list_pending_revert_candidates,
    list_pending_verifications,
    format_summary_for_display,
    format_status_for_display,
    ACTION_APPLY,
    ACTION_PROMOTE,
)
from tools.apply_lifecycle import (
    create_apply_plan,
    create_post_apply_verification,
    complete_post_apply_verification,
    record_apply_state_transition,
)
from governance.operating_policy import DECISION_MANUAL_APPROVAL_REQUIRED


def setup_module():
    """Clean state files before tests."""
    state_dir = PROJECT_ROOT / "state"
    files_to_clean = [
        "apply_plans.jsonl",
        "apply_state_transitions.jsonl",
        "execution_leases.jsonl",
        "post_apply_verification_results.jsonl",
        "patch_attempt_results.jsonl",
        "policy_decisions.jsonl",
        "revert_candidates.jsonl",
        "governance_decisions.jsonl",
    ]
    for f in files_to_clean:
        path = state_dir / f
        if path.exists():
            os.remove(path)


def test_operational_summary_exposed():
    """Test operational summary is exposed through manual ops surface."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_manual_ops_001",
        approved_by="manual_test",
    )
    
    # Get operational summary
    summary = show_operational_summary()
    
    assert summary["command"] == "show_operational_summary"
    assert summary["status"] == "ok"
    assert "counts" in summary
    assert summary["counts"]["apply_plans"] >= 1
    
    print("✅ test_operational_summary_exposed passed")


def test_apply_plan_status_exposed():
    """Test apply plan status is exposed through manual ops surface."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_manual_ops_002",
        approved_by="manual_test",
    )
    
    # Get apply plan status
    status = show_apply_plan_status(plan["apply_plan_id"])
    
    assert status["command"] == "show_apply_plan_status"
    assert status["apply_plan_id"] == plan["apply_plan_id"]
    assert status["apply_plan_exists"] == True
    assert status["status"] == "ok"
    
    print("✅ test_apply_plan_status_exposed passed")


def test_manual_apply_blocked_when_governance_denies():
    """Test manual apply is blocked when governance denies it."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_manual_ops_003",
        approved_by="manual_test",
    )
    
    # Try to run manual apply without approval
    result = run_manual_apply(plan["apply_plan_id"])
    
    # Should be blocked
    assert result["status"] == "blocked"
    assert "Governance denied" in result["reason"]
    # patch_applied should be False or not set when blocked
    assert result.get("patch_applied", False) == False
    
    print("✅ test_manual_apply_blocked_when_governance_denies passed")


def test_manual_apply_allowed_with_approval():
    """Test manual apply is allowed only when governance/manual approval conditions are satisfied."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_manual_ops_004",
        approved_by="manual_test",
    )
    
    # Grant manual approval
    approval = grant_manual_approval(
        action_type=ACTION_APPLY,
        entity_id=plan["apply_plan_id"],
        approver="test_operator",
        reason="test approval",
    )
    
    assert approval["status"] == "approved"
    
    # Now try to run manual apply
    result = run_manual_apply(
        apply_plan_id=plan["apply_plan_id"],
        patch_path=None,
        executor_identity="test_operator",
    )
    
    # Should not be blocked (but may fail for other reasons like missing patch)
    assert result["status"] != "blocked"
    
    print("✅ test_manual_apply_allowed_with_approval passed")


def test_manual_verification_routes_correctly():
    """Test manual verification routes through verifier correctly."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_manual_ops_005",
        approved_by="manual_test",
    )
    
    # Create verification
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_005",
    )
    
    # Run manual verification
    result = run_manual_verification(
        verification_id=verification["verification_id"],
        changed_files=[],
    )
    
    assert result["command"] == "run_manual_verification"
    assert result["status"] == "completed"
    assert result["passed"] == True
    
    print("✅ test_manual_verification_routes_correctly passed")


def test_manual_policy_evaluation_routes_correctly():
    """Test manual policy evaluation routes through policy layer correctly."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_manual_ops_006",
        approved_by="manual_test",
    )
    
    # Create and complete verification (passed)
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_006",
    )
    
    complete_post_apply_verification(
        verification_id=verification["verification_id"],
        result="passed",
        evidence_refs=["check:passed"],
    )
    
    record_apply_state_transition(
        apply_plan_id=plan["apply_plan_id"],
        event="post_apply_verification_passed",
    )
    
    # Run manual policy evaluation
    result = evaluate_manual_policy(plan["apply_plan_id"])
    
    assert result["command"] == "evaluate_manual_policy"
    assert result["policy_decision"] == "PROMOTE_ELIGIBLE"
    assert result["status"] == "ok"
    assert result["executed"] == False  # No automatic execution
    
    print("✅ test_manual_policy_evaluation_routes_correctly passed")


def test_manual_ops_does_not_bypass_safety():
    """Test manual ops surface does not bypass existing safety checks."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_manual_ops_007",
        approved_by="manual_test",
    )
    
    # Try to run apply without any approval
    result = run_manual_apply(plan["apply_plan_id"])
    
    # Should be blocked
    assert result["status"] == "blocked"
    
    # Try to grant approval for invalid action
    # (this should work but won't enable the action if ineligible)
    
    # Try to run verification for nonexistent ID
    result = run_manual_verification("nonexistent_verification_id")
    assert result["status"] in ("error", "unknown")
    
    print("✅ test_manual_ops_does_not_bypass_safety passed")


def test_list_pending_revert_candidates():
    """Test list pending revert candidates."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_manual_ops_008",
        approved_by="manual_test",
    )
    
    # Simulate patch applied
    record_apply_state_transition(
        apply_plan_id=plan["apply_plan_id"],
        event="patch_attempt_succeeded",
    )
    
    # Create failed verification
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_008",
    )
    
    complete_post_apply_verification(
        verification_id=verification["verification_id"],
        result="failed",
        failure_codes=["SYNTAX_ERROR"],
    )
    
    # Evaluate policy (should create revert candidate)
    evaluate_manual_policy(plan["apply_plan_id"])
    
    # List pending revert candidates
    result = list_pending_revert_candidates()
    
    assert result["command"] == "list_pending_revert_candidates"
    assert result["count"] >= 1
    
    # Find our plan in the list
    plan_ids = [c.get("apply_plan_id") for c in result["candidates"]]
    assert plan["apply_plan_id"] in plan_ids
    
    print("✅ test_list_pending_revert_candidates passed")


def test_list_pending_verifications():
    """Test list pending verifications."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_manual_ops_009",
        approved_by="manual_test",
    )
    
    # Create verification without completing
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_009",
    )
    
    # List pending verifications
    result = list_pending_verifications()
    
    assert result["command"] == "list_pending_verifications"
    assert result["count"] >= 1
    
    # Find our verification in the list
    verification_ids = [v.get("verification_id") for v in result["verifications"]]
    assert verification["verification_id"] in verification_ids
    
    print("✅ test_list_pending_verifications passed")


def test_format_functions():
    """Test format functions for display."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_manual_ops_010",
        approved_by="manual_test",
    )
    
    # Get summary and format
    summary = show_operational_summary()
    formatted_summary = format_summary_for_display(summary)
    
    assert "OPERATIONAL SUMMARY" in formatted_summary
    assert "COUNTS:" in formatted_summary
    
    # Get status and format
    status = show_apply_plan_status(plan["apply_plan_id"])
    formatted_status = format_status_for_display(status)
    
    assert "APPLY PLAN STATUS" in formatted_status
    assert plan["apply_plan_id"] in formatted_status
    
    print("✅ test_format_functions passed")


def test_list_all_apply_plans():
    """Test list all apply plans."""
    # Create apply plans
    plan1 = create_apply_plan(
        proposal_id="test_manual_ops_011a",
        approved_by="manual_test",
    )
    plan2 = create_apply_plan(
        proposal_id="test_manual_ops_011b",
        approved_by="manual_test",
    )
    
    # List all apply plans
    result = list_all_apply_plans()
    
    assert result["command"] == "list_all_apply_plans"
    assert result["count"] >= 2
    
    plan_ids = [p.get("apply_plan_id") for p in result["apply_plans"]]
    assert plan1["apply_plan_id"] in plan_ids
    assert plan2["apply_plan_id"] in plan_ids
    
    print("✅ test_list_all_apply_plans passed")


def test_evaluate_manual_governance():
    """Test evaluate manual governance."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_manual_ops_012",
        approved_by="manual_test",
    )
    
    # Evaluate governance for APPLY
    result = evaluate_manual_governance(ACTION_APPLY, plan["apply_plan_id"])
    
    assert result["command"] == "evaluate_manual_governance"
    assert result["action_type"] == ACTION_APPLY
    assert result["entity_id"] == plan["apply_plan_id"]
    assert result["manual_approval_required"] == True
    assert result["is_allowed"] == False  # No approval yet
    
    print("✅ test_evaluate_manual_governance passed")


def run_all_tests():
    """Run all tests in this module."""
    setup_module()
    
    test_operational_summary_exposed()
    test_apply_plan_status_exposed()
    test_manual_apply_blocked_when_governance_denies()
    test_manual_apply_allowed_with_approval()
    test_manual_verification_routes_correctly()
    test_manual_policy_evaluation_routes_correctly()
    test_manual_ops_does_not_bypass_safety()
    test_list_pending_revert_candidates()
    test_list_pending_verifications()
    test_format_functions()
    test_list_all_apply_plans()
    test_evaluate_manual_governance()
    
    print("\n=== All 12 manual ops tests passed ===")


if __name__ == "__main__":
    run_all_tests()
