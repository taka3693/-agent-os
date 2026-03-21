#!/usr/bin/env python3
"""Tests for Improvement Policy Engine.

These tests verify:
- passed verification records a conservative positive decision
- failed verification records a conservative negative decision
- failed verification can create a revert candidate record
- incomplete evidence results in HOLD_REVIEW
- append-only decision records are preserved
- no automatic rollback or promotion execution occurs
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "policy"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
sys.path.insert(0, str(PROJECT_ROOT / "verification"))

from policy.improvement_policy import (
    evaluate_apply_outcome,
    get_policy_decision_status,
    load_policy_decisions,
    load_revert_candidates,
    get_pending_revert_candidates,
    DECISION_PROMOTE_ELIGIBLE,
    DECISION_HOLD_REVIEW,
    DECISION_REJECT,
    DECISION_REVERT_CANDIDATE_RECOMMENDED,
)
from tools.apply_lifecycle import (
    create_apply_plan,
    create_post_apply_verification,
    complete_post_apply_verification,
    record_apply_state_transition,
)
from verification.post_apply_verifier import run_post_apply_verification


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
    ]
    for f in files_to_clean:
        path = state_dir / f
        if path.exists():
            os.remove(path)


def test_passed_verification_records_promote_eligible():
    """Test passed verification records a conservative positive decision."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_policy_001",
        approved_by="manual_test",
    )
    
    # Create and complete verification (passed)
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_001",
    )
    
    # Complete verification with evidence
    complete_post_apply_verification(
        verification_id=verification["verification_id"],
        result="passed",
        summary="All checks passed",
        evidence_refs=["syntax_check:passed", "pytest:passed"],
    )
    
    # Record state transition
    record_apply_state_transition(
        apply_plan_id=plan["apply_plan_id"],
        event="post_apply_verification_passed",
    )
    
    # Evaluate outcome
    decision = evaluate_apply_outcome(plan["apply_plan_id"])
    
    assert decision["decision"] == DECISION_PROMOTE_ELIGIBLE
    assert decision["executed"] == False  # No auto-execution
    assert len(decision["evidence_refs"]) >= 1
    
    print("✅ test_passed_verification_records_promote_eligible passed")


def test_failed_verification_records_reject():
    """Test failed verification records a conservative negative decision."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_policy_002",
        approved_by="manual_test",
    )
    
    # Create and complete verification (failed)
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_002",
    )
    
    complete_post_apply_verification(
        verification_id=verification["verification_id"],
        result="failed",
        summary="Syntax check failed",
        failure_codes=["SYNTAX_ERROR"],
    )
    
    # Evaluate outcome
    decision = evaluate_apply_outcome(plan["apply_plan_id"])
    
    assert decision["decision"] in (DECISION_REJECT, DECISION_REVERT_CANDIDATE_RECOMMENDED)
    assert decision["executed"] == False
    
    print("✅ test_failed_verification_records_reject passed")


def test_failed_verification_creates_revert_candidate():
    """Test failed verification can create a revert candidate record."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_policy_003",
        approved_by="manual_test",
    )
    
    # Simulate patch applied successfully
    record_apply_state_transition(
        apply_plan_id=plan["apply_plan_id"],
        event="patch_attempt_succeeded",
    )
    
    # Create and complete verification (failed)
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_003",
    )
    
    complete_post_apply_verification(
        verification_id=verification["verification_id"],
        result="failed",
        summary="Verification failed after patch",
        failure_codes=["PYTEST_FAILED"],
    )
    
    # Evaluate outcome
    decision = evaluate_apply_outcome(plan["apply_plan_id"])
    
    # Should recommend revert
    assert decision["decision"] == DECISION_REVERT_CANDIDATE_RECOMMENDED
    
    # Check revert candidate was created
    candidates = get_pending_revert_candidates()
    matching = [c for c in candidates if c.get("apply_plan_id") == plan["apply_plan_id"]]
    
    assert len(matching) >= 1
    assert matching[0]["status"] == "pending"  # Not auto-executed
    
    print("✅ test_failed_verification_creates_revert_candidate passed")


def test_incomplete_evidence_results_in_hold_review():
    """Test incomplete evidence results in HOLD_REVIEW."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_policy_004",
        approved_by="manual_test",
    )
    
    # Create verification without completing
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_004",
    )
    
    # Evaluate outcome (verification still pending)
    decision = evaluate_apply_outcome(plan["apply_plan_id"])
    
    assert decision["decision"] == DECISION_HOLD_REVIEW
    assert decision["executed"] == False
    
    print("✅ test_incomplete_evidence_results_in_hold_review passed")


def test_append_only_decision_records_preserved():
    """Test append-only decision records are preserved."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_policy_005",
        approved_by="manual_test",
    )
    
    # Create and complete verification
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_005",
    )
    
    complete_post_apply_verification(
        verification_id=verification["verification_id"],
        result="passed",
        evidence_refs=["test:evidence"],
    )
    
    # Evaluate outcome twice
    decision1 = evaluate_apply_outcome(plan["apply_plan_id"])
    decision2 = evaluate_apply_outcome(plan["apply_plan_id"])
    
    # Both decisions should be recorded (append-only)
    decisions = load_policy_decisions()
    matching = [d for d in decisions if d.get("apply_plan_id") == plan["apply_plan_id"]]
    
    assert len(matching) >= 2
    assert decision1["decision_id"] != decision2["decision_id"]
    
    print("✅ test_append_only_decision_records_preserved passed")


def test_no_automatic_rollback_or_promotion():
    """Test no automatic rollback or promotion execution occurs."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_policy_006",
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
    
    # Evaluate outcome
    decision = evaluate_apply_outcome(plan["apply_plan_id"])
    
    # Verify no automatic execution
    assert decision["executed"] == False
    
    # Check that apply_closed was NOT automatically recorded by policy
    # (it should only be recorded by verification layer)
    from tools.apply_lifecycle import load_apply_state_transitions
    transitions = load_apply_state_transitions()
    policy_closed = [t for t in transitions 
                     if t.get("apply_plan_id") == plan["apply_plan_id"]
                     and t.get("event") == "apply_closed"
                     and t.get("actor") == "policy_engine"]
    
    # Policy engine should NOT record apply_closed automatically
    assert len(policy_closed) == 0
    
    print("✅ test_no_automatic_rollback_or_promotion passed")


def test_get_policy_decision_status():
    """Test get_policy_decision_status returns correct status."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_policy_007",
        approved_by="manual_test",
    )
    
    # Create and complete verification
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_007",
    )
    
    complete_post_apply_verification(
        verification_id=verification["verification_id"],
        result="passed",
        evidence_refs=["check:passed"],
    )
    
    # Evaluate outcome
    decision = evaluate_apply_outcome(plan["apply_plan_id"])
    
    # Get status
    status = get_policy_decision_status(decision["decision_id"])
    
    assert status is not None
    assert status["decision_id"] == decision["decision_id"]
    assert status["decision"] == decision["decision"]
    
    print("✅ test_get_policy_decision_status passed")


def test_missing_verification_uses_hold_review():
    """Test missing verification uses HOLD_REVIEW."""
    # Create apply plan without verification
    plan = create_apply_plan(
        proposal_id="test_policy_008",
        approved_by="manual_test",
    )
    
    # Evaluate outcome (no verification)
    decision = evaluate_apply_outcome(plan["apply_plan_id"])
    
    assert decision["decision"] == DECISION_HOLD_REVIEW
    assert decision["verification_result"] is None
    
    print("✅ test_missing_verification_uses_hold_review passed")


def run_all_tests():
    """Run all tests in this module."""
    setup_module()
    
    test_passed_verification_records_promote_eligible()
    test_failed_verification_records_reject()
    test_failed_verification_creates_revert_candidate()
    test_incomplete_evidence_results_in_hold_review()
    test_append_only_decision_records_preserved()
    test_no_automatic_rollback_or_promotion()
    test_get_policy_decision_status()
    test_missing_verification_uses_hold_review()
    
    print("\n=== All 8 improvement policy tests passed ===")


if __name__ == "__main__":
    run_all_tests()
