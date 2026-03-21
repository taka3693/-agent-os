#!/usr/bin/env python3
"""Tests for Recovery and Failure Behavior.

These tests verify conservative behavior under partial failures or ambiguous state:
- partial state records are handled conservatively
- missing state files are handled gracefully
- corrupted/incomplete records are detected
- recovery from partial failures is safe
- no automatic recovery actions are executed
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
sys.path.insert(0, str(PROJECT_ROOT / "governance"))
sys.path.insert(0, str(PROJECT_ROOT / "policy"))
sys.path.insert(0, str(PROJECT_ROOT / "audit"))

from tools.apply_lifecycle import (
    create_apply_plan,
    load_apply_plans,
    get_latest_apply_state,
    load_post_apply_verification_results,
    create_post_apply_verification,
)
from governance.operating_policy import (
    evaluate_action_eligibility,
    is_action_allowed,
    ACTION_APPLY,
    ACTION_PROMOTE,
)
from policy.improvement_policy import (
    evaluate_apply_outcome,
    load_policy_decisions,
)
from audit.operational_report import (
    get_apply_plan_operational_status,
    build_operational_summary,
)


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


# =============================================================================
# Recovery Test 1: Partial State Records
# =============================================================================

def test_recovery_partial_state_records():
    """Test partial state records are handled conservatively.
    
    Scenario:
    - Apply plan exists but verification is incomplete
    - Policy evaluation should be conservative
    - Governance should require manual review
    """
    print("\n=== Recovery: Partial State Records ===")
    
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="recovery_partial_001",
        approved_by="manual_test",
    )
    apply_plan_id = plan["apply_plan_id"]
    
    # Create verification but don't complete (partial state)
    verification = create_post_apply_verification(
        apply_plan_id=apply_plan_id,
        patch_attempt_id="patch_partial",
    )
    
    # Evaluate policy - should be conservative
    print("Evaluating policy with incomplete verification...")
    policy = evaluate_apply_outcome(apply_plan_id)
    print(f"  Policy decision: {policy['decision']}")
    assert policy["decision"] in ("HOLD_REVIEW", "REJECT")
    
    # Evaluate governance - should require manual
    print("Evaluating governance with incomplete state...")
    gov = evaluate_action_eligibility(ACTION_PROMOTE, apply_plan_id)
    print(f"  Governance decision: {gov['decision']}")
    assert gov["decision"] in ("MANUAL_APPROVAL_REQUIRED", "INELIGIBLE_INCOMPLETE", "DENIED")
    
    print("✅ Recovery: Partial State Records passed")


# =============================================================================
# Recovery Test 2: Missing State Files
# =============================================================================

def test_recovery_missing_state_files():
    """Test missing state files are handled gracefully.
    
    Scenario:
    - Some state files don't exist
    - Operations should still work
    - Should return empty results, not crash
    """
    print("\n=== Recovery: Missing State Files ===")
    
    # Ensure state directory exists but files may be missing
    state_dir = PROJECT_ROOT / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    
    # Temporarily remove policy decisions file
    policy_path = state_dir / "policy_decisions.jsonl"
    policy_backup = None
    if policy_path.exists():
        with open(policy_path, "r") as f:
            policy_backup = f.read()
        os.remove(policy_path)
    
    try:
        # Load policy decisions - should return empty list
        decisions = load_policy_decisions()
        print(f"  Loaded {len(decisions)} decisions from missing file")
        assert decisions == []
        
        # Operational summary should still work
        summary = build_operational_summary()
        print(f"  Summary counts: {summary['counts']}")
        assert summary["status"] == "ok"
        
    finally:
        # Restore backup
        if policy_backup:
            with open(policy_path, "w") as f:
                f.write(policy_backup)
    
    print("✅ Recovery: Missing State Files passed")


# =============================================================================
# Recovery Test 3: Corrupted/Incomplete Records
# =============================================================================

def test_recovery_corrupted_records():
    """Test corrupted/incomplete records are detected.
    
    Scenario:
    - JSONL file has corrupted line
    - Loading should skip corrupted lines
    - Should not crash
    """
    print("\n=== Recovery: Corrupted Records ===")
    
    # Create valid apply plan
    plan = create_apply_plan(
        proposal_id="recovery_corrupted_001",
        approved_by="manual_test",
    )
    
    # Add corrupted line to apply plans file
    plans_path = PROJECT_ROOT / "state" / "apply_plans.jsonl"
    with open(plans_path, "a") as f:
        f.write("{corrupted json line\n")  # Invalid JSON
        f.write("\n")  # Empty line
    
    # Loading should still work (skip corrupted)
    plans = load_apply_plans()
    print(f"  Loaded {len(plans)} plans (some may be corrupted)")
    assert len(plans) >= 1  # At least the valid one
    
    # Find our plan
    our_plans = [p for p in plans if p.get("proposal_id") == "recovery_corrupted_001"]
    assert len(our_plans) >= 1
    print(f"  Found {len(our_plans)} valid plans for our test")
    
    print("✅ Recovery: Corrupted Records passed")


# =============================================================================
# Recovery Test 4: Recovery from Partial Failures
# =============================================================================

def test_recovery_from_partial_failure():
    """Test recovery from partial failures is safe.
    
    Scenario:
    - Apply plan has inconsistent state
    - Operational status should detect inconsistency
    - Governance should deny action
    """
    print("\n=== Recovery: From Partial Failure ===")
    
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="recovery_failure_001",
        approved_by="manual_test",
    )
    apply_plan_id = plan["apply_plan_id"]
    
    # Manually create inconsistent state:
    # - Apply state shows verification passed
    # - But verification results don't exist
    
    from tools.apply_lifecycle import record_apply_state_transition
    record_apply_state_transition(
        apply_plan_id=apply_plan_id,
        event="post_apply_verification_passed",
    )
    
    # Check operational status - should detect inconsistency
    status = get_apply_plan_operational_status(apply_plan_id)
    print(f"  Latest apply state: {status['latest_apply_state']}")
    print(f"  Latest verification: {status['latest_verification_status']}")
    
    # State and verification should be inconsistent
    # Operational status should handle this gracefully
    assert status["apply_plan_exists"] == True
    
    # Governance should be conservative
    gov = evaluate_action_eligibility(ACTION_PROMOTE, apply_plan_id)
    print(f"  Governance decision: {gov['decision']}")
    # Should still require manual approval at minimum
    assert gov["manual_approval_required"] == True
    
    print("✅ Recovery: From Partial Failure passed")


# =============================================================================
# Recovery Test 5: No Automatic Recovery Execution
# =============================================================================

def test_recovery_no_automatic_execution():
    """Test no automatic recovery actions are executed.
    
    Scenario:
    - Multiple items in various states
    - Running operational summary/scheduler
    - Verify no actions are automatically executed
    """
    print("\n=== Recovery: No Automatic Execution ===")
    
    # Create several apply plans in different states
    plans = []
    for i in range(3):
        plan = create_apply_plan(
            proposal_id=f"recovery_auto_{i:03d}",
            approved_by="manual_test",
        )
        plans.append(plan)
    
    # Run operational summary multiple times
    for i in range(3):
        summary = build_operational_summary()
        print(f"  Run {i+1}: {summary['counts']}")
    
    # Verify no automatic actions were executed
    for plan in plans:
        state = get_latest_apply_state(plan["apply_plan_id"])
        if state:
            event = state.get("event")
            print(f"  {plan['proposal_id']}: {event}")
            # Should only have apply_plan_created
            assert event not in ("patch_attempt_succeeded", "patch_attempt_failed", "apply_closed")
    
    # Verify governance still requires manual approval
    for plan in plans:
        allowed = is_action_allowed(ACTION_APPLY, plan["apply_plan_id"])
        print(f"  {plan['proposal_id']} allowed: {allowed['allowed']}")
        assert allowed["allowed"] == False
    
    print("✅ Recovery: No Automatic Execution passed")


# =============================================================================
# Recovery Test 6: Stale State Recovery
# =============================================================================

def test_recovery_stale_state():
    """Test stale state is detected and handled conservatively.
    
    Scenario:
    - Apply plan is old (stale)
    - Operational status detects staleness
    - Governance denies action
    """
    print("\n=== Recovery: Stale State ===")
    
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="recovery_stale_001",
        approved_by="manual_test",
    )
    apply_plan_id = plan["apply_plan_id"]
    
    # Make it stale
    plans_path = PROJECT_ROOT / "state" / "apply_plans.jsonl"
    stale_plan = plan.copy()
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale_plan["created_at"] = stale_time
    
    with open(plans_path, "a") as f:
        f.write(json.dumps(stale_plan) + "\n")
    
    # Check operational status
    status = get_apply_plan_operational_status(apply_plan_id)
    print(f"  Is stale: {status['is_stale']}")
    print(f"  Blocked reason: {status['stale_or_blocked_reason']}")
    assert status["is_stale"] == True
    
    # Verify governance denies
    gov = evaluate_action_eligibility(ACTION_APPLY, apply_plan_id)
    print(f"  Governance decision: {gov['decision']}")
    assert gov["decision"] == "INELIGIBLE_EXPIRED"
    
    # Verify action is not allowed
    allowed = is_action_allowed(ACTION_APPLY, apply_plan_id)
    print(f"  Action allowed: {allowed['allowed']}")
    assert allowed["allowed"] == False
    
    print("✅ Recovery: Stale State passed")


# =============================================================================
# Recovery Test 7: Empty State Recovery
# =============================================================================

def test_recovery_empty_state():
    """Test empty state is handled gracefully.
    
    Scenario:
    - No apply plans exist
    - Operational summary should still work
    - Should return empty results
    """
    print("\n=== Recovery: Empty State ===")
    
    # Clean all state
    setup_module()
    
    # Operational summary should work
    summary = build_operational_summary()
    print(f"  Summary counts: {summary['counts']}")
    assert summary["counts"]["apply_plans"] == 0
    assert summary["status"] == "ok"
    
    # Get status for non-existent plan
    status = get_apply_plan_operational_status("nonexistent_plan")
    print(f"  Non-existent plan status: {status['apply_plan_exists']}")
    assert status["apply_plan_exists"] == False
    assert status["stale_or_blocked_reason"] == "apply_plan_not_found"
    
    # Governance should deny
    gov = evaluate_action_eligibility(ACTION_APPLY, "nonexistent_plan")
    print(f"  Governance decision: {gov['decision']}")
    assert gov["decision"] == "DENIED"
    
    print("✅ Recovery: Empty State passed")


def run_all_tests():
    """Run all recovery tests."""
    setup_module()
    
    test_recovery_partial_state_records()
    test_recovery_missing_state_files()
    test_recovery_corrupted_records()
    test_recovery_from_partial_failure()
    test_recovery_no_automatic_execution()
    test_recovery_stale_state()
    test_recovery_empty_state()
    
    print("\n" + "=" * 60)
    print("=== All 7 recovery behavior tests passed ===")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
