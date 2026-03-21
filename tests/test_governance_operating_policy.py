#!/usr/bin/env python3
"""Tests for Governance / Operating Policy Layer.

These tests verify:
- manual approval required for risky actions
- expired apply plan becomes ineligible
- incomplete verification blocks advancement
- PROMOTE_ELIGIBLE does not cause automatic promotion execution
- REVERT_CANDIDATE_RECOMMENDED does not cause automatic revert execution
- ambiguous state is handled conservatively
- append-only governance decision recording is preserved
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "governance"))
sys.path.insert(0, str(PROJECT_ROOT / "policy"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
sys.path.insert(0, str(PROJECT_ROOT / "verification"))

from governance.operating_policy import (
    evaluate_action_eligibility,
    record_governance_decision,
    get_action_eligibility_status,
    load_governance_decisions,
    check_manual_approval_granted,
    is_action_allowed,
    ACTION_APPLY,
    ACTION_PROMOTE,
    ACTION_REVERT,
    ACTION_COMMIT,
    DECISION_ALLOWED,
    DECISION_DENIED,
    DECISION_MANUAL_APPROVAL_REQUIRED,
    DECISION_INELIGIBLE_EXPIRED,
    DECISION_INELIGIBLE_INCOMPLETE,
)
from tools.apply_lifecycle import (
    create_apply_plan,
    create_post_apply_verification,
    complete_post_apply_verification,
    record_apply_state_transition,
)
from policy.improvement_policy import evaluate_apply_outcome


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


def test_manual_approval_required_for_risky_actions():
    """Test manual approval required for risky actions."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_governance_001",
        approved_by="manual_test",
    )
    
    # Evaluate APPLY action
    result = evaluate_action_eligibility(ACTION_APPLY, plan["apply_plan_id"])
    
    # Should require manual approval
    assert result["manual_approval_required"] == True
    assert result["decision"] == DECISION_MANUAL_APPROVAL_REQUIRED
    
    # Evaluate PROMOTE action
    result2 = evaluate_action_eligibility(ACTION_PROMOTE, plan["apply_plan_id"])
    assert result2["manual_approval_required"] == True
    
    # Evaluate REVERT action
    result3 = evaluate_action_eligibility(ACTION_REVERT, plan["apply_plan_id"])
    assert result3["manual_approval_required"] == True
    
    print("✅ test_manual_approval_required_for_risky_actions passed")


def test_expired_apply_plan_becomes_ineligible():
    """Test expired apply plan becomes ineligible."""
    from datetime import timezone
    
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_governance_002",
        approved_by="manual_test",
    )
    
    # Manually append an updated plan with past expiry (using UTC)
    plans_path = PROJECT_ROOT / "state" / "apply_plans.jsonl"
    expired_plan = plan.copy()
    expired_plan["eligibility_expires_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    with open(plans_path, "a") as f:
        f.write(json.dumps(expired_plan) + "\n")
    
    # Evaluate action - should find the expired plan
    result = evaluate_action_eligibility(ACTION_APPLY, plan["apply_plan_id"])
    
    # Should be ineligible due to expiry
    assert result["decision"] == DECISION_INELIGIBLE_EXPIRED
    
    print("✅ test_expired_apply_plan_becomes_ineligible passed")


def test_incomplete_verification_blocks_advancement():
    """Test incomplete verification blocks advancement."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_governance_003",
        approved_by="manual_test",
    )
    
    # Create verification without completing
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_003",
    )
    
    # Evaluate PROMOTE action (verification still pending)
    result = evaluate_action_eligibility(ACTION_PROMOTE, plan["apply_plan_id"])
    
    # Should be ineligible due to incomplete verification
    assert result["decision"] == DECISION_INELIGIBLE_INCOMPLETE
    
    print("✅ test_incomplete_verification_blocks_advancement passed")


def test_promote_eligible_does_not_auto_promote():
    """Test PROMOTE_ELIGIBLE does not cause automatic promotion execution."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_governance_004",
        approved_by="manual_test",
    )
    
    # Create and complete verification (passed)
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_004",
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
    
    # Evaluate policy outcome (should get PROMOTE_ELIGIBLE)
    policy_result = evaluate_apply_outcome(plan["apply_plan_id"])
    assert policy_result["decision"] == "PROMOTE_ELIGIBLE"
    
    # Now evaluate PROMOTE action through governance
    result = evaluate_action_eligibility(ACTION_PROMOTE, plan["apply_plan_id"])
    
    # Should STILL require manual approval (not auto-allowed)
    assert result["manual_approval_required"] == True
    assert result["decision"] == DECISION_MANUAL_APPROVAL_REQUIRED
    
    # is_action_allowed should return False without approval
    allowed = is_action_allowed(ACTION_PROMOTE, plan["apply_plan_id"])
    assert allowed["allowed"] == False
    assert "manual_approval_not_granted" in allowed["reason"]
    
    print("✅ test_promote_eligible_does_not_auto_promote passed")


def test_revert_candidate_does_not_auto_revert():
    """Test REVERT_CANDIDATE_RECOMMENDED does not cause automatic revert execution."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_governance_005",
        approved_by="manual_test",
    )
    
    # Simulate patch applied
    record_apply_state_transition(
        apply_plan_id=plan["apply_plan_id"],
        event="patch_attempt_succeeded",
    )
    
    # Create and complete verification (failed)
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_005",
    )
    
    complete_post_apply_verification(
        verification_id=verification["verification_id"],
        result="failed",
        failure_codes=["SYNTAX_ERROR"],
    )
    
    # Evaluate policy outcome (should get REVERT_CANDIDATE_RECOMMENDED)
    policy_result = evaluate_apply_outcome(plan["apply_plan_id"])
    assert policy_result["decision"] == "REVERT_CANDIDATE_RECOMMENDED"
    
    # Now evaluate REVERT action through governance
    result = evaluate_action_eligibility(ACTION_REVERT, plan["apply_plan_id"])
    
    # Should STILL require manual approval (not auto-allowed)
    assert result["manual_approval_required"] == True
    
    # is_action_allowed should return False without approval
    allowed = is_action_allowed(ACTION_REVERT, plan["apply_plan_id"])
    assert allowed["allowed"] == False
    
    print("✅ test_revert_candidate_does_not_auto_revert passed")


def test_ambiguous_state_handled_conservatively():
    """Test ambiguous state is handled conservatively."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_governance_006",
        approved_by="manual_test",
    )
    
    # Create verification with ambiguous result
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_006",
    )
    
    # Manually set verification to ambiguous state
    verifications_path = PROJECT_ROOT / "state" / "post_apply_verification_results.jsonl"
    verifications = []
    with open(verifications_path, "r") as f:
        for line in f:
            if line.strip():
                v = json.loads(line)
                if v.get("verification_id") == verification["verification_id"]:
                    v["result"] = "ambiguous"  # Not passed or failed
                verifications.append(v)
    
    with open(verifications_path, "w") as f:
        for v in verifications:
            f.write(json.dumps(v) + "\n")
    
    # Evaluate PROMOTE action
    result = evaluate_action_eligibility(ACTION_PROMOTE, plan["apply_plan_id"])
    
    # Should be denied or require manual approval
    assert result["decision"] in (DECISION_DENIED, DECISION_INELIGIBLE_INCOMPLETE)
    
    print("✅ test_ambiguous_state_handled_conservatively passed")


def test_append_only_governance_decisions_preserved():
    """Test append-only governance decision recording is preserved."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_governance_007",
        approved_by="manual_test",
    )
    
    # Evaluate action twice
    result1 = evaluate_action_eligibility(ACTION_APPLY, plan["apply_plan_id"])
    result2 = evaluate_action_eligibility(ACTION_APPLY, plan["apply_plan_id"])
    
    # Both decisions should be recorded (append-only)
    decisions = load_governance_decisions()
    matching = [d for d in decisions if d.get("entity_id") == plan["apply_plan_id"]]
    
    assert len(matching) >= 2
    assert result1["decision_id"] != result2["decision_id"]
    
    print("✅ test_append_only_governance_decisions_preserved passed")


def test_manual_approval_grant_enables_action():
    """Test that granting manual approval enables the action."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_governance_008",
        approved_by="manual_test",
    )
    
    # First check - no approval yet
    allowed1 = is_action_allowed(ACTION_APPLY, plan["apply_plan_id"])
    assert allowed1["allowed"] == False
    
    # Grant approval
    record_governance_decision(
        action_type=ACTION_APPLY,
        entity_id=plan["apply_plan_id"],
        decision=DECISION_ALLOWED,
        reason="operator approved",
        approver="manual_test",
    )
    
    # Check again - should now be allowed
    allowed2 = is_action_allowed(ACTION_APPLY, plan["apply_plan_id"])
    assert allowed2["allowed"] == True
    
    print("✅ test_manual_approval_grant_enables_action passed")


def test_invalid_action_type_denied():
    """Test invalid action type is denied."""
    result = evaluate_action_eligibility("INVALID_ACTION", "some_entity_id")
    
    assert result["decision"] == DECISION_DENIED
    assert "invalid_action_type" in result["reason"]
    
    print("✅ test_invalid_action_type_denied passed")


def test_nonexistent_apply_plan_denied():
    """Test nonexistent apply plan is denied."""
    result = evaluate_action_eligibility(ACTION_APPLY, "nonexistent_plan_id")
    
    assert result["decision"] == DECISION_DENIED
    assert "apply_plan_not_found" in result["reason"]
    
    print("✅ test_nonexistent_apply_plan_denied passed")


def run_all_tests():
    """Run all tests in this module."""
    setup_module()
    
    test_manual_approval_required_for_risky_actions()
    test_expired_apply_plan_becomes_ineligible()
    test_incomplete_verification_blocks_advancement()
    test_promote_eligible_does_not_auto_promote()
    test_revert_candidate_does_not_auto_revert()
    test_ambiguous_state_handled_conservatively()
    test_append_only_governance_decisions_preserved()
    test_manual_approval_grant_enables_action()
    test_invalid_action_type_denied()
    test_nonexistent_apply_plan_denied()
    
    print("\n=== All 10 governance operating policy tests passed ===")


if __name__ == "__main__":
    run_all_tests()
