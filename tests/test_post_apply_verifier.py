#!/usr/bin/env python3
"""Tests for Post-Apply Verification Policy Layer.

These tests verify:
- verification starts for a valid pending verification entry
- verification records passed result on successful checks
- verification records failed result on failed checks
- verification records structured failure codes/evidence
- verification does not alter patch_attempt_results responsibilities
- apply_state_transition events are recorded correctly
- apply_closed is only recorded on successful verification
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "verification"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from verification.post_apply_verifier import (
    run_post_apply_verification,
    get_verification_status,
    _run_verification_checks,
)
from tools.apply_lifecycle import (
    create_apply_plan,
    create_post_apply_verification,
    load_post_apply_verification_results,
    load_apply_state_transitions,
    get_latest_apply_state,
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


def test_verification_starts_for_pending_entry():
    """Test verification starts for a valid pending verification entry."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_verifier_001",
        approved_by="manual_test",
    )
    
    # Create verification entry
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_001",
        verification_steps=["syntax_check"],
    )
    
    # Run verification
    result = run_post_apply_verification(
        verification_id=verification["verification_id"],
    )
    
    assert result["status"] == "completed"
    assert "passed" in result
    
    print("✅ test_verification_starts_for_pending_entry passed")


def test_verification_records_passed_result():
    """Test verification records passed result on successful checks."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_verifier_002",
        approved_by="manual_test",
    )
    
    # Create verification entry
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_002",
    )
    
    # Run verification with no files (should pass)
    result = run_post_apply_verification(
        verification_id=verification["verification_id"],
        changed_files=[],
    )
    
    assert result["status"] == "completed"
    assert result["passed"] == True
    assert len(result["failure_codes"]) == 0
    
    # Verify state in file
    verifications = load_post_apply_verification_results()
    matching = [v for v in verifications if v.get("verification_id") == verification["verification_id"]]
    
    # Find the latest (completed) record
    completed = [v for v in matching if v.get("result") == "passed"]
    assert len(completed) >= 1
    
    print("✅ test_verification_records_passed_result passed")


def test_verification_records_failed_result():
    """Test verification records failed result on failed checks."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_verifier_003",
        approved_by="manual_test",
    )
    
    # Create verification entry
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_003",
    )
    
    # Create a temp Python file with syntax error
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def broken(:\n")  # Invalid syntax
        temp_path = f.name
    
    try:
        # Run verification with broken file
        result = run_post_apply_verification(
            verification_id=verification["verification_id"],
            changed_files=[temp_path],
        )
        
        assert result["status"] == "completed"
        assert result["passed"] == False
        assert "SYNTAX_ERROR" in result["failure_codes"]
        
    finally:
        os.unlink(temp_path)
    
    print("✅ test_verification_records_failed_result passed")


def test_verification_records_structured_failure_codes():
    """Test verification records structured failure codes/evidence."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_verifier_004",
        approved_by="manual_test",
    )
    
    # Create verification entry
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_004",
    )
    
    # Run verification with non-existent file (should still work)
    result = run_post_apply_verification(
        verification_id=verification["verification_id"],
        changed_files=["/nonexistent/file.py"],
    )
    
    assert result["status"] == "completed"
    assert len(result["evidence_refs"]) > 0
    
    # Evidence should contain syntax check result
    assert any("syntax_check" in ref for ref in result["evidence_refs"])
    
    print("✅ test_verification_records_structured_failure_codes passed")


def test_verification_preserves_patch_attempt_separation():
    """Test verification does not alter patch_attempt_results responsibilities."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_verifier_005",
        approved_by="manual_test",
    )
    
    # Create verification entry
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_005",
    )
    
    # Run verification
    result = run_post_apply_verification(
        verification_id=verification["verification_id"],
    )
    
    # Verify patch_attempt_results was not modified
    patch_attempts_path = PROJECT_ROOT / "state" / "patch_attempt_results.jsonl"
    if patch_attempts_path.exists():
        with open(patch_attempts_path, "r") as f:
            content = f.read()
        assert verification["verification_id"] not in content
    
    print("✅ test_verification_preserves_patch_attempt_separation passed")


def test_apply_state_transition_events_recorded():
    """Test apply_state_transition events are recorded correctly."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_verifier_006",
        approved_by="manual_test",
    )
    
    # Create verification entry
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_006",
    )
    
    # Run verification
    result = run_post_apply_verification(
        verification_id=verification["verification_id"],
        changed_files=[],
    )
    
    # Verify state transitions
    transitions = load_apply_state_transitions()
    matching = [t for t in transitions if t.get("apply_plan_id") == plan["apply_plan_id"]]
    events = [t.get("event") for t in matching]
    
    # Should have: apply_plan_created, post_apply_verification_started, 
    # post_apply_verification_passed, apply_closed
    assert "apply_plan_created" in events
    assert "post_apply_verification_started" in events
    
    if result["passed"]:
        assert "post_apply_verification_passed" in events
        assert "apply_closed" in events
    
    print("✅ test_apply_state_transition_events_recorded passed")


def test_apply_closed_only_on_successful_verification():
    """Test apply_closed is only recorded on successful verification."""
    # Test passed case
    plan_passed = create_apply_plan(
        proposal_id="test_verifier_007a",
        approved_by="manual_test",
    )
    
    verification_passed = create_post_apply_verification(
        apply_plan_id=plan_passed["apply_plan_id"],
        patch_attempt_id="patch_007a",
    )
    
    result_passed = run_post_apply_verification(
        verification_id=verification_passed["verification_id"],
        changed_files=[],
    )
    
    # Check apply_closed was recorded
    latest_passed = get_latest_apply_state(plan_passed["apply_plan_id"])
    if result_passed["passed"]:
        assert latest_passed["event"] == "apply_closed"
    
    # Test failed case
    plan_failed = create_apply_plan(
        proposal_id="test_verifier_007b",
        approved_by="manual_test",
    )
    
    verification_failed = create_post_apply_verification(
        apply_plan_id=plan_failed["apply_plan_id"],
        patch_attempt_id="patch_007b",
    )
    
    # Create broken file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def broken(:\n")
        temp_path = f.name
    
    try:
        result_failed = run_post_apply_verification(
            verification_id=verification_failed["verification_id"],
            changed_files=[temp_path],
        )
        
        # Check apply_closed was NOT recorded
        latest_failed = get_latest_apply_state(plan_failed["apply_plan_id"])
        if not result_failed["passed"]:
            assert latest_failed["event"] != "apply_closed"
            assert latest_failed["event"] == "post_apply_verification_failed"
    finally:
        os.unlink(temp_path)
    
    print("✅ test_apply_closed_only_on_successful_verification passed")


def test_verification_already_completed():
    """Test that already completed verification returns appropriate status."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_verifier_008",
        approved_by="manual_test",
    )
    
    # Create and complete verification
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_008",
    )
    
    # First run
    result1 = run_post_apply_verification(
        verification_id=verification["verification_id"],
        changed_files=[],
    )
    
    # Second run (already completed)
    result2 = run_post_apply_verification(
        verification_id=verification["verification_id"],
        changed_files=[],
    )
    
    assert result2["status"] == "already_completed"
    
    print("✅ test_verification_already_completed passed")


def run_all_tests():
    """Run all tests in this module."""
    setup_module()
    
    test_verification_starts_for_pending_entry()
    test_verification_records_passed_result()
    test_verification_records_failed_result()
    test_verification_records_structured_failure_codes()
    test_verification_preserves_patch_attempt_separation()
    test_apply_state_transition_events_recorded()
    test_apply_closed_only_on_successful_verification()
    test_verification_already_completed()
    
    print("\n=== All 8 post-apply verifier tests passed ===")


if __name__ == "__main__":
    run_all_tests()
