#!/usr/bin/env python3
"""Tests for Apply Lifecycle Separation Layer.

These tests verify:
- apply plan append-only creation
- apply state transition append-only recording
- execution lease duplicate/conflict handling
- post-apply verification result recording
- patch_attempt_results schema separation
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.apply_lifecycle import (
    create_apply_plan,
    load_apply_plans,
    record_apply_state_transition,
    load_apply_state_transitions,
    get_latest_apply_state,
    acquire_execution_lease,
    find_active_lease_for_plan,
    load_execution_leases,
    create_post_apply_verification,
    complete_post_apply_verification,
    load_post_apply_verification_results,
    create_extended_patch_attempt,
    complete_extended_patch_attempt,
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
    ]
    for f in files_to_clean:
        path = state_dir / f
        if path.exists():
            os.remove(path)


def test_apply_plan_creation():
    """Test apply plan append-only creation."""
    plan = create_apply_plan(
        proposal_id="test_proposal_001",
        approved_by="manual_test",
        patch_artifact_ref="patches/test_001.diff",
        expected_verifications=["syntax_check", "pytest"],
    )
    
    assert "apply_plan_id" in plan
    assert plan["proposal_id"] == "test_proposal_001"
    assert plan["approved_by"] == "manual_test"
    assert plan["patch_artifact_ref"] == "patches/test_001.diff"
    assert "syntax_check" in plan["expected_verifications"]
    assert "apply_plan_id" in plan
    
    # Verify it was persisted
    plans = load_apply_plans()
    assert len(plans) >= 1
    assert any(p["apply_plan_id"] == plan["apply_plan_id"] for p in plans)
    
    print("✅ test_apply_plan_creation passed")


def test_apply_state_transition_recording():
    """Test apply state transition append-only recording."""
    plan = create_apply_plan(
        proposal_id="test_proposal_002",
        approved_by="manual_test",
    )
    
    apply_plan_id = plan["apply_plan_id"]
    
    # Record additional transitions
    record_apply_state_transition(apply_plan_id, "apply_plan_approved", actor="reviewer")
    record_apply_state_transition(apply_plan_id, "patch_attempt_started", actor="executor")
    record_apply_state_transition(apply_plan_id, "patch_attempt_succeeded", reason="all_checks_passed")
    
    # Verify transitions
    transitions = load_apply_state_transitions()
    matching = [t for t in transitions if t["apply_plan_id"] == apply_plan_id]
    
    assert len(matching) >= 4  # created + 3 additional
    events = [t["event"] for t in matching]
    assert "apply_plan_created" in events
    assert "apply_plan_approved" in events
    assert "patch_attempt_started" in events
    assert "patch_attempt_succeeded" in events
    
    # Verify latest state
    latest = get_latest_apply_state(apply_plan_id)
    assert latest["event"] == "patch_attempt_succeeded"
    
    print("✅ test_apply_state_transition_recording passed")


def test_execution_lease_duplicate_handling():
    """Test execution lease duplicate/conflict handling (conservative)."""
    plan = create_apply_plan(
        proposal_id="test_proposal_003",
        approved_by="manual_test",
    )
    
    apply_plan_id = plan["apply_plan_id"]
    
    # First lease should succeed
    lease1 = acquire_execution_lease(
        apply_plan_id=apply_plan_id,
        acquired_by="worker_1",
        expires_in_seconds=3600,
    )
    
    assert lease1["status"] == "active"
    assert lease1["lease_id"] != ""
    
    # Second lease for same plan should be blocked
    lease2 = acquire_execution_lease(
        apply_plan_id=apply_plan_id,
        acquired_by="worker_2",
        expires_in_seconds=3600,
    )
    
    assert lease2["status"] == "blocked"
    assert "existing_lease" in lease2["reason"]
    
    # Verify find_active_lease_for_plan
    active = find_active_lease_for_plan(apply_plan_id)
    assert active is not None
    assert active["lease_id"] == lease1["lease_id"]
    
    print("✅ test_execution_lease_duplicate_handling passed")


def test_post_apply_verification_recording():
    """Test post-apply verification result recording."""
    plan = create_apply_plan(
        proposal_id="test_proposal_004",
        approved_by="manual_test",
    )
    
    apply_plan_id = plan["apply_plan_id"]
    
    # Create verification (started)
    verification = create_post_apply_verification(
        apply_plan_id=apply_plan_id,
        patch_attempt_id="patch_004_001",
        verification_steps=["syntax_check", "pytest", "diff_review"],
    )
    
    assert verification["result"] == "pending"
    assert verification["verification_id"] != ""
    assert len(verification["verification_steps"]) == 3
    
    # Complete verification (passed)
    completed = complete_post_apply_verification(
        verification_id=verification["verification_id"],
        result="passed",
        summary="All verification steps passed",
        evidence_refs=["logs/syntax_check.log", "logs/pytest.log"],
    )
    
    assert completed["result"] == "passed"
    assert completed["summary"] == "All verification steps passed"
    assert len(completed["evidence_refs"]) == 2
    
    # Verify state transition
    latest = get_latest_apply_state(apply_plan_id)
    assert latest["event"] == "post_apply_verification_passed"
    
    print("✅ test_post_apply_verification_recording passed")


def test_extended_patch_attempt():
    """Test extended patch attempt with full execution facts."""
    plan = create_apply_plan(
        proposal_id="test_proposal_005",
        approved_by="manual_test",
    )
    
    apply_plan_id = plan["apply_plan_id"]
    
    # Acquire lease
    lease = acquire_execution_lease(apply_plan_id, acquired_by="executor")
    assert lease["status"] == "active"
    
    # Create extended patch attempt
    attempt = create_extended_patch_attempt(
        apply_plan_id=apply_plan_id,
        execution_lease_id=lease["lease_id"],
        executor_identity="manual_executor",
        patch_artifact_ref="patches/test_005.diff",
    )
    
    assert attempt["patch_attempt_id"] != ""
    assert attempt["apply_plan_id"] == apply_plan_id
    assert attempt["execution_lease_id"] == lease["lease_id"]
    assert attempt["executor_identity"] == "manual_executor"
    assert attempt["execution_result"] == "pending"
    
    # Complete patch attempt (succeeded)
    completed = complete_extended_patch_attempt(
        patch_attempt_id=attempt["patch_attempt_id"],
        execution_result="succeeded",
        precondition_check_result="passed",
        diff_summary="+10 -5 lines in 2 files",
        produced_artifact_refs=["artifacts/patch_005_applied.diff"],
    )
    
    assert completed["execution_result"] == "succeeded"
    assert completed["diff_summary"] == "+10 -5 lines in 2 files"
    assert len(completed["produced_artifact_refs"]) == 1
    
    # Verify state transition
    latest = get_latest_apply_state(apply_plan_id)
    assert latest["event"] == "patch_attempt_succeeded"
    
    print("✅ test_extended_patch_attempt passed")


def test_verification_failure():
    """Test post-apply verification failure recording."""
    plan = create_apply_plan(
        proposal_id="test_proposal_006",
        approved_by="manual_test",
    )
    
    apply_plan_id = plan["apply_plan_id"]
    
    verification = create_post_apply_verification(
        apply_plan_id=apply_plan_id,
        patch_attempt_id="patch_006_001",
    )
    
    # Complete verification (failed)
    completed = complete_post_apply_verification(
        verification_id=verification["verification_id"],
        result="failed",
        summary="Syntax check failed",
        failure_codes=["SYNTAX_ERROR"],
    )
    
    assert completed["result"] == "failed"
    assert "SYNTAX_ERROR" in completed["failure_codes"]
    
    # Verify state transition
    latest = get_latest_apply_state(apply_plan_id)
    assert latest["event"] == "post_apply_verification_failed"
    
    print("✅ test_verification_failure passed")


def test_patch_attempt_failure():
    """Test extended patch attempt failure recording."""
    plan = create_apply_plan(
        proposal_id="test_proposal_007",
        approved_by="manual_test",
    )
    
    apply_plan_id = plan["apply_plan_id"]
    lease = acquire_execution_lease(apply_plan_id, acquired_by="executor")
    
    attempt = create_extended_patch_attempt(
        apply_plan_id=apply_plan_id,
        execution_lease_id=lease["lease_id"],
        executor_identity="manual_executor",
    )
    
    # Complete with failure
    completed = complete_extended_patch_attempt(
        patch_attempt_id=attempt["patch_attempt_id"],
        execution_result="failed",
        failure_code="PRECONDITION_FAILED",
        failure_detail="Target file has been modified since plan creation",
    )
    
    assert completed["execution_result"] == "failed"
    assert completed["failure_code"] == "PRECONDITION_FAILED"
    
    # Verify state transition
    latest = get_latest_apply_state(apply_plan_id)
    assert latest["event"] == "patch_attempt_failed"
    
    print("✅ test_patch_attempt_failure passed")


def run_all_tests():
    """Run all tests in this module."""
    setup_module()
    
    test_apply_plan_creation()
    test_apply_state_transition_recording()
    test_execution_lease_duplicate_handling()
    test_post_apply_verification_recording()
    test_extended_patch_attempt()
    test_verification_failure()
    test_patch_attempt_failure()
    
    print("\n=== All 7 apply lifecycle tests passed ===")


if __name__ == "__main__":
    run_all_tests()
