#!/usr/bin/env python3
"""End-to-End Scenario Tests.

These tests verify complete flows across major layers:
- successful apply flow through verification/policy/governance/reporting
- failed verification leading to revert candidate recommendation
- expired/stale apply plan handled conservatively
- ambiguous/incomplete state handled conservatively
- scheduler reporting without risky action execution
- manual ops surface respecting governance requirements

IMPORTANT: These tests do NOT introduce new automation.
They only verify that existing layers work together correctly.
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
sys.path.insert(0, str(PROJECT_ROOT / "verification"))
sys.path.insert(0, str(PROJECT_ROOT / "policy"))
sys.path.insert(0, str(PROJECT_ROOT / "governance"))
sys.path.insert(0, str(PROJECT_ROOT / "audit"))
sys.path.insert(0, str(PROJECT_ROOT / "scheduler"))

from tools.apply_lifecycle import (
    create_apply_plan,
    load_apply_plans,
    create_post_apply_verification,
    complete_post_apply_verification,
    record_apply_state_transition,
    get_latest_apply_state,
    load_post_apply_verification_results,
)
from verification.post_apply_verifier import run_post_apply_verification
from policy.improvement_policy import evaluate_apply_outcome, load_revert_candidates
from governance.operating_policy import evaluate_action_eligibility, is_action_allowed, ACTION_APPLY, ACTION_PROMOTE
from audit.operational_report import (
    get_apply_plan_operational_status,
    build_operational_summary,
)
from scheduler.controlled_scheduler import (
    run_controlled_scheduler_once,
    verify_scheduler_safety,
)
from tools.manual_ops import (
    run_manual_apply,
    grant_manual_approval,
    show_operational_summary,
    show_apply_plan_status,
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
        "scheduler_runs.jsonl",
    ]
    for f in files_to_clean:
        path = state_dir / f
        if path.exists():
            os.remove(path)


# =============================================================================
# E2E Test 1: Successful Apply Flow
# =============================================================================

def test_e2e_successful_apply_flow():
    """Test complete successful apply flow through all layers."""
    print("\n=== E2E: Successful Apply Flow ===")
    
    # Step 1: Create apply plan
    print("Step 1: Create apply plan...")
    plan = create_apply_plan(
        proposal_id="e2e_success_001",
        approved_by="manual_test",
    )
    apply_plan_id = plan["apply_plan_id"]
    print(f"  Created: {apply_plan_id}")
    
    # Step 2: Run verification
    print("Step 2: Run verification...")
    verification = create_post_apply_verification(
        apply_plan_id=apply_plan_id,
        patch_attempt_id="patch_e2e_001",
    )
    
    verification_result = run_post_apply_verification(
        verification_id=verification["verification_id"],
        changed_files=[],
    )
    print(f"  Verification: {verification_result['result']}")
    assert verification_result["passed"] == True
    
    # Step 3: Evaluate policy
    print("Step 3: Evaluate policy...")
    policy_result = evaluate_apply_outcome(apply_plan_id)
    print(f"  Policy decision: {policy_result['decision']}")
    assert policy_result["decision"] == "PROMOTE_ELIGIBLE"
    
    # Step 4: Evaluate governance
    print("Step 4: Evaluate governance...")
    gov_result = evaluate_action_eligibility(ACTION_PROMOTE, apply_plan_id)
    print(f"  Governance decision: {gov_result['decision']}")
    assert gov_result["manual_approval_required"] == True
    
    # Step 5: Check operational status
    print("Step 5: Check operational status...")
    status = get_apply_plan_operational_status(apply_plan_id)
    print(f"  Latest state: {status['latest_apply_state']}")
    print(f"  Verification: {status['latest_verification_status']}")
    print(f"  Policy: {status['latest_policy_decision']}")
    assert status["latest_verification_status"] == "passed"
    assert status["latest_policy_decision"] == "PROMOTE_ELIGIBLE"
    
    # Step 6: Verify scheduler reports correctly
    print("Step 6: Run scheduler...")
    scheduler_result = run_controlled_scheduler_once()
    assert scheduler_result["actions_executed"] == 0
    print(f"  Scheduler actions detected: {scheduler_result['actions_detected']}")
    
    print("✅ E2E: Successful Apply Flow passed")


# =============================================================================
# E2E Test 2: Failed Verification → Revert Candidate
# =============================================================================

def test_e2e_failed_verification_revert_candidate():
    """Test failed verification leading to revert candidate recommendation."""
    print("\n=== E2E: Failed Verification → Revert Candidate ===")
    
    # Step 1: Create apply plan
    print("Step 1: Create apply plan...")
    plan = create_apply_plan(
        proposal_id="e2e_failed_001",
        approved_by="manual_test",
    )
    apply_plan_id = plan["apply_plan_id"]
    
    # Step 2: Record patch succeeded
    print("Step 2: Record patch succeeded...")
    record_apply_state_transition(
        apply_plan_id=apply_plan_id,
        event="patch_attempt_succeeded",
    )
    
    # Step 3: Run verification (failed)
    print("Step 3: Run verification (will fail)...")
    verification = create_post_apply_verification(
        apply_plan_id=apply_plan_id,
        patch_attempt_id="patch_e2e_failed",
    )
    
    # Create temp file with syntax error
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def broken(:\n")
        temp_path = f.name
    
    try:
        verification_result = run_post_apply_verification(
            verification_id=verification["verification_id"],
            changed_files=[temp_path],
        )
        print(f"  Verification: {verification_result['result']}")
        assert verification_result["passed"] == False
    finally:
        os.unlink(temp_path)
    
    # Step 4: Evaluate policy
    print("Step 4: Evaluate policy...")
    policy_result = evaluate_apply_outcome(apply_plan_id)
    print(f"  Policy decision: {policy_result['decision']}")
    assert policy_result["decision"] == "REVERT_CANDIDATE_RECOMMENDED"
    
    # Step 5: Verify revert candidate created
    print("Step 5: Verify revert candidate...")
    candidates = load_revert_candidates()
    matching = [c for c in candidates if c.get("apply_plan_id") == apply_plan_id]
    assert len(matching) >= 1
    print(f"  Revert candidate created: {matching[0]['candidate_id']}")
    
    # Step 6: Verify operational summary
    print("Step 6: Check operational summary...")
    summary = build_operational_summary()
    revert_ids = [c.get("apply_plan_id") for c in summary.get("revert_candidates_pending", [])]
    assert apply_plan_id in revert_ids
    print(f"  Summary shows {summary['counts']['revert_candidates_pending']} revert candidates")
    
    print("✅ E2E: Failed Verification → Revert Candidate passed")


# =============================================================================
# E2E Test 3: Expired/Stale Apply Plan
# =============================================================================

def test_e2e_expired_apply_plan_conservative():
    """Test expired/stale apply plan handled conservatively."""
    print("\n=== E2E: Expired/Stale Apply Plan ===")
    
    # Step 1: Create apply plan
    print("Step 1: Create apply plan...")
    plan = create_apply_plan(
        proposal_id="e2e_expired_001",
        approved_by="manual_test",
    )
    apply_plan_id = plan["apply_plan_id"]
    
    # Step 2: Make it stale
    print("Step 2: Make plan stale...")
    plans_path = PROJECT_ROOT / "state" / "apply_plans.jsonl"
    stale_plan = plan.copy()
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale_plan["created_at"] = stale_time
    
    with open(plans_path, "a") as f:
        f.write(json.dumps(stale_plan) + "\n")
    
    # Step 3: Verify governance denies
    print("Step 3: Verify governance denies action...")
    gov_result = evaluate_action_eligibility(ACTION_APPLY, apply_plan_id)
    print(f"  Governance decision: {gov_result['decision']}")
    assert gov_result["decision"] == "INELIGIBLE_EXPIRED"
    
    # Step 4: Verify operational status
    print("Step 4: Check operational status...")
    status = get_apply_plan_operational_status(apply_plan_id)
    print(f"  Is stale: {status['is_stale']}")
    print(f"  Blocked reason: {status['stale_or_blocked_reason']}")
    assert status["is_stale"] == True
    
    # Step 5: Verify scheduler detects
    print("Step 5: Run scheduler...")
    scheduler_result = run_controlled_scheduler_once()
    stale_ids = [s.get("apply_plan_id") for s in scheduler_result["actions"]["stale_apply_plans"]]
    assert apply_plan_id in stale_ids
    print(f"  Scheduler detected {scheduler_result['actions']['counts']['stale_apply_plans']} stale items")
    
    print("✅ E2E: Expired/Stale Apply Plan passed")


# =============================================================================
# E2E Test 4: Ambiguous/Incomplete State
# =============================================================================

def test_e2e_ambiguous_state_conservative():
    """Test ambiguous/incomplete state handled conservatively."""
    print("\n=== E2E: Ambiguous/Incomplete State ===")
    
    # Step 1: Create apply plan
    print("Step 1: Create apply plan...")
    plan = create_apply_plan(
        proposal_id="e2e_ambiguous_001",
        approved_by="manual_test",
    )
    apply_plan_id = plan["apply_plan_id"]
    
    # Step 2: Create incomplete verification
    print("Step 2: Create incomplete verification...")
    verification = create_post_apply_verification(
        apply_plan_id=apply_plan_id,
        patch_attempt_id="patch_e2e_ambiguous",
    )
    # Don't complete verification
    
    # Step 3: Verify policy evaluates conservatively
    print("Step 3: Evaluate policy...")
    policy_result = evaluate_apply_outcome(apply_plan_id)
    print(f"  Policy decision: {policy_result['decision']}")
    assert policy_result["decision"] in ("HOLD_REVIEW", "REJECT")
    
    # Step 4: Verify governance requires manual review
    print("Step 4: Evaluate governance...")
    gov_result = evaluate_action_eligibility(ACTION_PROMOTE, apply_plan_id)
    print(f"  Governance decision: {gov_result['decision']}")
    assert gov_result["decision"] in (
        "MANUAL_APPROVAL_REQUIRED",
        "INELIGIBLE_INCOMPLETE",
        "DENIED",
    )
    
    # Step 5: Verify operational status
    print("Step 5: Check operational status...")
    status = get_apply_plan_operational_status(apply_plan_id)
    print(f"  Verification status: {status['latest_verification_status']}")
    print(f"  Next manual action: {status['next_manual_action']}")
    assert status["latest_verification_status"] in ("pending", None)
    
    print("✅ E2E: Ambiguous/Incomplete State passed")


# =============================================================================
# E2E Test 5: Scheduler No Risky Actions
# =============================================================================

def test_e2e_scheduler_no_risky_actions():
    """Test scheduler reporting without risky action execution."""
    print("\n=== E2E: Scheduler No Risky Actions ===")
    
    # Step 1: Create apply plans
    print("Step 1: Create apply plans...")
    plans = []
    for i in range(3):
        plan = create_apply_plan(
            proposal_id=f"e2e_scheduler_{i:03d}",
            approved_by="manual_test",
        )
        plans.append(plan)
        print(f"  Created: {plan['apply_plan_id']}")
    
    # Step 2: Run scheduler multiple times
    print("Step 2: Run scheduler multiple times...")
    for i in range(3):
        result = run_controlled_scheduler_once()
        print(f"  Run {i+1}: detected={result['actions_detected']}, executed={result['actions_executed']}")
        assert result["actions_executed"] == 0
    
    # Step 3: Verify no risky actions
    print("Step 3: Verify no apply was executed...")
    for plan in plans:
        state = get_latest_apply_state(plan["apply_plan_id"])
        if state:
            event = state.get("event")
            print(f"  {plan['apply_plan_id']}: {event}")
            assert event not in ("patch_attempt_succeeded", "patch_attempt_failed")
    
    # Step 4: Verify scheduler safety
    print("Step 4: Verify scheduler safety...")
    safety = verify_scheduler_safety()
    print(f"  Safety verified: {safety['verified']}")
    assert safety["verified"] == True
    
    print("✅ E2E: Scheduler No Risky Actions passed")


# =============================================================================
# E2E Test 6: Manual Ops Respects Governance
# =============================================================================

def test_e2e_manual_ops_respects_governance():
    """Test manual ops surface respecting governance requirements."""
    print("\n=== E2E: Manual Ops Respects Governance ===")
    
    # Step 1: Create apply plan
    print("Step 1: Create apply plan...")
    plan = create_apply_plan(
        proposal_id="e2e_manual_ops_001",
        approved_by="manual_test",
    )
    apply_plan_id = plan["apply_plan_id"]
    
    # Step 2: Try manual apply without approval
    print("Step 2: Try manual apply without approval...")
    result = run_manual_apply(apply_plan_id)
    print(f"  Result: {result['status']}")
    print(f"  Reason: {result.get('reason', 'N/A')}")
    assert result["status"] == "blocked"
    
    # Step 3: Grant manual approval
    print("Step 3: Grant manual approval...")
    approval = grant_manual_approval(
        action_type=ACTION_APPLY,
        entity_id=apply_plan_id,
        approver="test_operator",
        reason="test approval for e2e",
    )
    print(f"  Approval status: {approval['status']}")
    assert approval["status"] == "approved"
    
    # Step 4: Try manual apply again
    print("Step 4: Try manual apply with approval...")
    result = run_manual_apply(apply_plan_id)
    print(f"  Result: {result['status']}")
    assert result["status"] != "blocked"
    
    # Step 5: Verify audit trail
    print("Step 5: Verify audit trail...")
    status = show_apply_plan_status(apply_plan_id)
    print(f"  Plan exists: {status['apply_plan_exists']}")
    assert status["apply_plan_exists"] == True
    
    print("✅ E2E: Manual Ops Respects Governance passed")


# =============================================================================
# E2E Test 7: Complete Flow Summary
# =============================================================================

def test_e2e_complete_flow_summary():
    """Test complete operational summary across all states."""
    print("\n=== E2E: Complete Flow Summary ===")
    
    # Step 1: Create apply plans in different states
    print("Step 1: Create apply plans in different states...")
    
    # Plan 1: Fresh, no verification
    plan1 = create_apply_plan(
        proposal_id="e2e_summary_fresh",
        approved_by="manual_test",
    )
    print(f"  Created fresh plan: {plan1['apply_plan_id']}")
    
    # Plan 2: Verification passed
    plan2 = create_apply_plan(
        proposal_id="e2e_summary_passed",
        approved_by="manual_test",
    )
    verification2 = create_post_apply_verification(
        apply_plan_id=plan2["apply_plan_id"],
        patch_attempt_id="patch_summary_passed",
    )
    complete_post_apply_verification(
        verification_id=verification2["verification_id"],
        result="passed",
        evidence_refs=["test:passed"],
    )
    print(f"  Created passed plan: {plan2['apply_plan_id']}")
    
    # Plan 3: Verification failed
    plan3 = create_apply_plan(
        proposal_id="e2e_summary_failed",
        approved_by="manual_test",
    )
    record_apply_state_transition(
        apply_plan_id=plan3["apply_plan_id"],
        event="patch_attempt_succeeded",
    )
    verification3 = create_post_apply_verification(
        apply_plan_id=plan3["apply_plan_id"],
        patch_attempt_id="patch_summary_failed",
    )
    complete_post_apply_verification(
        verification_id=verification3["verification_id"],
        result="failed",
        failure_codes=["TEST_ERROR"],
    )
    print(f"  Created failed plan: {plan3['apply_plan_id']}")
    
    # Step 2: Run operational summary
    print("Step 2: Run operational summary...")
    summary = show_operational_summary()
    
    # Step 3: Verify all states captured
    print("Step 3: Verify summary...")
    print(f"  Total apply plans: {summary['counts']['apply_plans']}")
    print(f"  Pending verifications: {summary['counts']['pending_verifications']}")
    print(f"  Failed verifications: {summary['counts']['failed_verifications']}")
    
    assert summary["counts"]["apply_plans"] >= 3
    assert summary["status"] == "ok"
    
    print("✅ E2E: Complete Flow Summary passed")


def run_all_tests():
    """Run all E2E tests."""
    setup_module()
    
    test_e2e_successful_apply_flow()
    test_e2e_failed_verification_revert_candidate()
    test_e2e_expired_apply_plan_conservative()
    test_e2e_ambiguous_state_conservative()
    test_e2e_scheduler_no_risky_actions()
    test_e2e_manual_ops_respects_governance()
    test_e2e_complete_flow_summary()
    
    print("\n" + "=" * 60)
    print("=== All 7 E2E scenario tests passed ===")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
