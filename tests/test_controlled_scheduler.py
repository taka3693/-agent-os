#!/usr/bin/env python3
"""Tests for Controlled Scheduler Layer.

These tests verify:
- scheduler detects pending verifications
- scheduler detects stale items
- scheduler detects pending revert candidates
- scheduler does not execute risky actions
- scheduler reuses existing reporting/governance layers
- scheduler records append-only run state
- scheduler output is conservative when state is ambiguous
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scheduler"))
sys.path.insert(0, str(PROJECT_ROOT / "governance"))
sys.path.insert(0, str(PROJECT_ROOT / "policy"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
sys.path.insert(0, str(PROJECT_ROOT / "verification"))

from scheduler.controlled_scheduler import (
    build_scheduler_actions,
    run_controlled_scheduler_once,
    get_scheduler_status,
    load_scheduler_runs,
    get_recent_scheduler_runs,
    format_scheduler_report,
    verify_scheduler_safety,
    SCHEDULER_ACTION_DETECT,
    SCHEDULER_ACTION_REPORT,
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
        "scheduler_runs.jsonl",
    ]
    for f in files_to_clean:
        path = state_dir / f
        if path.exists():
            os.remove(path)


def test_scheduler_detects_pending_verifications():
    """Test scheduler detects pending verifications."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_scheduler_001",
        approved_by="manual_test",
    )
    
    # Create verification without completing
    verification = create_post_apply_verification(
        apply_plan_id=plan["apply_plan_id"],
        patch_attempt_id="patch_001",
    )
    
    # Run scheduler
    result = run_controlled_scheduler_once()
    
    # Should detect pending verification
    assert result["status"] == "completed"
    assert result["actions_executed"] == 0
    
    pending_ids = [v.get("apply_plan_id") for v in result["actions"]["pending_verifications"]]
    assert plan["apply_plan_id"] in pending_ids
    
    print("✅ test_scheduler_detects_pending_verifications passed")


def test_scheduler_detects_stale_items():
    """Test scheduler detects stale items."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_scheduler_002",
        approved_by="manual_test",
    )
    
    # Manually append a stale plan
    plans_path = PROJECT_ROOT / "state" / "apply_plans.jsonl"
    stale_plan = plan.copy()
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale_plan["created_at"] = stale_time
    
    with open(plans_path, "a") as f:
        f.write(json.dumps(stale_plan) + "\n")
    
    # Run scheduler
    result = run_controlled_scheduler_once()
    
    # Should detect stale item
    stale_ids = [s.get("apply_plan_id") for s in result["actions"]["stale_apply_plans"]]
    assert plan["apply_plan_id"] in stale_ids
    
    print("✅ test_scheduler_detects_stale_items passed")


def test_scheduler_detects_revert_candidates():
    """Test scheduler detects pending revert candidates."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_scheduler_003",
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
        patch_attempt_id="patch_003",
    )
    
    complete_post_apply_verification(
        verification_id=verification["verification_id"],
        result="failed",
        failure_codes=["SYNTAX_ERROR"],
    )
    
    # Evaluate policy (should create revert candidate)
    evaluate_apply_outcome(plan["apply_plan_id"])
    
    # Run scheduler
    result = run_controlled_scheduler_once()
    
    # Should detect revert candidate
    revert_ids = [c.get("apply_plan_id") for c in result["actions"]["revert_candidates_pending"]]
    assert plan["apply_plan_id"] in revert_ids
    
    print("✅ test_scheduler_detects_revert_candidates passed")


def test_scheduler_does_not_execute_risky_actions():
    """Test scheduler does not execute risky actions."""
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_scheduler_004",
        approved_by="manual_test",
    )
    
    # Run scheduler multiple times
    for i in range(3):
        result = run_controlled_scheduler_once()
        assert result["actions_executed"] == 0
        assert "No risky actions were executed" in result.get("note", "")
    
    # Verify no apply was executed
    from tools.apply_lifecycle import get_latest_apply_state
    state = get_latest_apply_state(plan["apply_plan_id"])
    
    # Should only have apply_plan_created, not patch_attempt_*
    if state:
        assert state.get("event") == "apply_plan_created"
    
    print("✅ test_scheduler_does_not_execute_risky_actions passed")


def test_scheduler_reuses_existing_layers():
    """Test scheduler reuses existing reporting/governance layers."""
    # Build scheduler actions
    actions = build_scheduler_actions()
    
    # Should have operational summary snapshot
    assert "operational_summary_snapshot" in actions
    assert "counts" in actions["operational_summary_snapshot"]
    
    # Should reuse audit layer counts
    assert "pending_verifications" in actions
    assert "stale_apply_plans" in actions
    assert "revert_candidates_pending" in actions
    
    print("✅ test_scheduler_reuses_existing_layers passed")


def test_scheduler_records_append_only_runs():
    """Test scheduler records append-only run state."""
    # Run scheduler
    result1 = run_controlled_scheduler_once()
    result2 = run_controlled_scheduler_once()
    
    # Load scheduler runs
    runs = load_scheduler_runs()
    
    # Should have at least 2 runs
    assert len(runs) >= 2
    
    # Each run should have unique ID
    run_ids = [r.get("run_id") for r in runs]
    assert result1["run_id"] in run_ids
    assert result2["run_id"] in run_ids
    assert result1["run_id"] != result2["run_id"]
    
    # All runs should have actions_executed = 0
    for run in runs:
        assert run.get("actions_executed") == 0
    
    print("✅ test_scheduler_records_append_only_runs passed")


def test_scheduler_output_conservative_when_ambiguous():
    """Test scheduler output is conservative when state is ambiguous."""
    # Create apply plan with ambiguous state (no verification)
    plan = create_apply_plan(
        proposal_id="test_scheduler_006",
        approved_by="manual_test",
    )
    
    # Run scheduler
    result = run_controlled_scheduler_once()
    
    # Should still complete successfully
    assert result["status"] == "completed"
    
    # Should have note about no automatic execution
    assert "No risky actions" in result.get("note", "")
    
    # Actions should have note
    assert "No automatic execution" in result["actions"].get("note", "")
    
    print("✅ test_scheduler_output_conservative_when_ambiguous passed")


def test_get_scheduler_status():
    """Test get scheduler status."""
    # Run scheduler first
    run_controlled_scheduler_once()
    
    # Get status
    status = get_scheduler_status()
    
    assert status["scheduler_type"] == "controlled"
    assert status["mode"] == "detect_and_report_only"
    assert status["automatic_execution"] == False
    assert status["total_runs"] >= 1
    assert status["last_run"] is not None
    
    print("✅ test_get_scheduler_status passed")


def test_format_scheduler_report():
    """Test format scheduler report."""
    # Run scheduler
    result = run_controlled_scheduler_once()
    
    # Format report
    report = format_scheduler_report(result)
    
    assert "SCHEDULER REPORT" in report
    assert "DETECTED ITEMS" in report
    assert "No risky actions were executed" in report
    assert result["run_id"] in report
    
    print("✅ test_format_scheduler_report passed")


def test_verify_scheduler_safety():
    """Test verify scheduler safety."""
    # Verify safety
    result = verify_scheduler_safety()
    
    assert result["verified"] == True
    assert len(result["checks"]) > 0
    assert len(result["warnings"]) == 0
    assert "no automatic execution" in result["note"].lower()
    
    print("✅ test_verify_scheduler_safety passed")


def test_get_recent_scheduler_runs():
    """Test get recent scheduler runs."""
    # Run scheduler multiple times
    for i in range(5):
        run_controlled_scheduler_once()
    
    # Get recent runs
    recent = get_recent_scheduler_runs(limit=3)
    
    assert len(recent) <= 3
    
    print("✅ test_get_recent_scheduler_runs passed")


def run_all_tests():
    """Run all tests in this module."""
    setup_module()
    
    test_scheduler_detects_pending_verifications()
    test_scheduler_detects_stale_items()
    test_scheduler_detects_revert_candidates()
    test_scheduler_does_not_execute_risky_actions()
    test_scheduler_reuses_existing_layers()
    test_scheduler_records_append_only_runs()
    test_scheduler_output_conservative_when_ambiguous()
    test_get_scheduler_status()
    test_format_scheduler_report()
    test_verify_scheduler_safety()
    test_get_recent_scheduler_runs()
    
    print("\n=== All 11 controlled scheduler tests passed ===")


if __name__ == "__main__":
    run_all_tests()
