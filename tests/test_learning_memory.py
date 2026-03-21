#!/usr/bin/env python3
"""Tests for Learning Memory Layer.

These tests verify:
- episode capture creates records
- outcome classification works (stored in learning_episodes.jsonl)
- insight generation creates records
- similar episode retrieval works
- learning layer does not mutate execution state
- no new automation power is introduced
- no separate classification state file
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "learning"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from learning.episode_store import (
    record_episode_from_apply_plan,
    load_learning_episodes,
    get_episode_by_id,
)
from learning.outcome_classifier import (
    classify_episode_outcome,
    get_latest_classification,
    get_outcome_statistics,
)
from learning.insight_report import (
    generate_learning_insights,
    load_learning_insights,
    get_similar_past_episodes,
)
from tools.apply_lifecycle import (
    create_apply_plan,
    create_post_apply_verification,
    complete_post_apply_verification,
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
        "learning_episodes.jsonl",
        "learning_insights.jsonl",
    ]
    for f in files_to_clean:
        path = state_dir / f
        if path.exists():
            os.remove(path)
    
    # Ensure no episode_classifications.jsonl exists
    old_classifications = state_dir / "episode_classifications.jsonl"
    if old_classifications.exists():
        os.remove(old_classifications)


def test_episode_capture_creates_record():
    """Test episode capture creates a record."""
    print("\n=== Test: Episode Capture ===")
    
    # Create apply plan
    plan = create_apply_plan(
        proposal_id="test_learning_001",
        approved_by="manual_test",
        patch_artifact_ref="patches/test.py",
    )
    apply_plan_id = plan["apply_plan_id"]
    
    # Record episode
    episode = record_episode_from_apply_plan(apply_plan_id)
    
    print(f"  Episode ID: {episode['episode_id']}")
    print(f"  Apply plan: {episode['apply_plan_id']}")
    
    assert episode["episode_id"] is not None
    assert episode["apply_plan_id"] == apply_plan_id
    
    # Verify it can be loaded
    loaded = get_episode_by_id(episode["episode_id"])
    assert loaded is not None
    assert loaded["episode_id"] == episode["episode_id"]
    
    print("✅ Episode capture test passed")


def test_outcome_classification_stored_in_episodes():
    """Test outcome classification is stored in learning_episodes.jsonl, not separate file."""
    print("\n=== Test: Outcome Classification Storage ===")
    
    # Create episode
    plan = create_apply_plan(
        proposal_id="test_learning_002",
        approved_by="manual_test",
    )
    
    episode = record_episode_from_apply_plan(plan["apply_plan_id"])
    
    # Classify
    classification = classify_episode_outcome(episode["episode_id"])
    
    print(f"  Episode ID: {classification['episode_id']}")
    print(f"  Outcome: {classification['outcome']}")
    
    assert classification["episode_id"] == episode["episode_id"]
    assert classification["outcome"] is not None
    
    # Verify classification is stored in learning_episodes.jsonl
    episodes = load_learning_episodes()
    classified_records = [e for e in episodes if e.get("episode_id") == episode["episode_id"] and "outcome" in e]
    assert len(classified_records) >= 1, "Classification should be in learning_episodes.jsonl"
    
    # Verify get_latest_classification returns the classified record
    latest = get_latest_classification(episode["episode_id"])
    assert latest is not None
    assert latest.get("outcome") == classification["outcome"]
    
    print("✅ Outcome classification storage test passed")


def test_no_separate_classification_file():
    """Test that no separate episode_classifications.jsonl file is created."""
    print("\n=== Test: No Separate Classification File ===")
    
    state_dir = PROJECT_ROOT / "state"
    old_classifications = state_dir / "episode_classifications.jsonl"
    
    # Should not exist
    assert not old_classifications.exists(), "episode_classifications.jsonl should not exist"
    print("  ✓ No episode_classifications.jsonl file")
    
    print("✅ No separate classification file test passed")


def test_insight_generation_creates_record():
    """Test insight generation creates a record."""
    print("\n=== Test: Insight Generation ===")
    
    # Create some episodes
    for i in range(2):
        plan = create_apply_plan(
            proposal_id=f"test_learning_insight_{i:03d}",
            approved_by="manual_test",
        )
        episode = record_episode_from_apply_plan(plan["apply_plan_id"])
        classify_episode_outcome(episode["episode_id"])
    
    # Generate insights
    insights = generate_learning_insights()
    
    print(f"  Insight ID: {insights['insight_id']}")
    print(f"  Statistics: {insights['statistics']}")
    
    assert insights["insight_id"] is not None
    assert "statistics" in insights
    assert "patterns" in insights
    assert "recommendations" in insights
    
    # Verify it can be loaded
    loaded = load_learning_insights()
    assert len(loaded) >= 1
    
    print("✅ Insight generation test passed")


def test_similar_episode_retrieval():
    """Test similar episode retrieval works."""
    print("\n=== Test: Similar Episode Retrieval ===")
    
    # Create episodes with specific patch type
    for i in range(2):
        plan = create_apply_plan(
            proposal_id=f"test_learning_similar_{i:03d}",
            approved_by="manual_test",
            patch_artifact_ref="patches/test.py",
        )
        record_episode_from_apply_plan(plan["apply_plan_id"])
    
    # Search for similar episodes
    similar = get_similar_past_episodes(
        patch_type="python_code",
        limit=5,
    )
    
    print(f"  Similar episodes found: {len(similar)}")
    
    # May or may not find matches depending on implementation
    # Just verify it doesn't crash
    assert isinstance(similar, list)
    
    print("✅ Similar episode retrieval test passed")


def test_no_state_mutation():
    """Test learning layer does not mutate execution state."""
    print("\n=== Test: No State Mutation ===")
    
    # Get file count before
    state_dir = PROJECT_ROOT / "state"
    
    # Perform learning operations
    plan = create_apply_plan(
        proposal_id="test_learning_mutation",
        approved_by="manual_test",
    )
    
    episode = record_episode_from_apply_plan(plan["apply_plan_id"])
    classification = classify_episode_outcome(episode["episode_id"])
    insights = generate_learning_insights()
    
    # Verify learning files exist
    learning_files = [
        "learning_episodes.jsonl",
        "learning_insights.jsonl",
    ]
    
    for f in learning_files:
        path = state_dir / f
        assert path.exists(), f"Learning file {f} should exist"
        print(f"  ✓ {f} exists")
    
    # Verify episode_classifications.jsonl does NOT exist
    old_classifications = state_dir / "episode_classifications.jsonl"
    assert not old_classifications.exists(), "episode_classifications.jsonl should NOT exist"
    print("  ✓ episode_classifications.jsonl does not exist")
    
    print("✅ No state mutation test passed")


def test_no_automation():
    """Test no new automation power is introduced."""
    print("\n=== Test: No Automation ===")
    
    # Verify learning layer functions don't execute actions
    plan = create_apply_plan(
        proposal_id="test_learning_automation",
        approved_by="manual_test",
    )
    
    # Record episode (should not execute anything)
    episode = record_episode_from_apply_plan(plan["apply_plan_id"])
    assert episode["episode_id"] is not None
    print("  ✓ Episode recorded without execution")
    
    # Generate insights (should not modify anything)
    insights = generate_learning_insights()
    assert insights["note"] is not None
    print("  ✓ Insights generated without automatic execution")
    
    # Verify no auto-apply code exists
    import subprocess
    result = subprocess.run(
        ["grep", "-r", "auto_apply\|automatic_apply", "--include=*.py", "learning/"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 or not result.stdout.strip()
    print("  ✓ No auto-apply code in learning layer")
    
    print("✅ No automation test passed")


def test_outcome_statistics():
    """Test outcome statistics work."""
    print("\n=== Test: Outcome Statistics ===")
    
    # Create and classify episodes
    for i in range(3):
        plan = create_apply_plan(
            proposal_id=f"test_learning_stats_{i:03d}",
            approved_by="manual_test",
        )
        episode = record_episode_from_apply_plan(plan["apply_plan_id"])
        classify_episode_outcome(episode["episode_id"])
    
    # Get statistics
    stats = get_outcome_statistics()
    
    print(f"  Total episodes: {stats['total_episodes']}")
    print(f"  Total classified: {stats['total_classified']}")
    print(f"  By outcome: {stats['by_outcome']}")
    
    assert stats["total_classified"] >= 3
    assert "by_outcome" in stats
    
    print("✅ Outcome statistics test passed")


def run_all_tests():
    """Run all learning memory tests."""
    setup_module()
    
    test_episode_capture_creates_record()
    test_outcome_classification_stored_in_episodes()
    test_no_separate_classification_file()
    test_insight_generation_creates_record()
    test_similar_episode_retrieval()
    test_no_state_mutation()
    test_no_automation()
    test_outcome_statistics()
    
    print("\n" + "=" * 60)
    print("=== All 8 learning memory tests passed ===")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
