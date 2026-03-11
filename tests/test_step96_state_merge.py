#!/usr/bin/env python3
"""Step96: Parallel-Safe State Merge Tests

Tests for merge capabilities:
- Revision-based conflict detection
- Append-safe step_results merging
- Memory merging with union semantics
- Status transition priority
"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.state_merge import (
    get_status_priority,
    resolve_status_conflict,
    _ensure_revision,
    bump_revision,
    check_revision_conflict,
    merge_step_results,
    merge_memory,
    merge_schedule,
    merge_recovery,
    merge_task_states,
    safe_update_task,
)


class TestStep96StatusPriority(unittest.TestCase):
    """Test status transition priority."""

    def test_failed_highest(self):
        """status 遷移の優先順位が固定される"""
        self.assertEqual(
            resolve_status_conflict(["queued", "running", "failed"]),
            "failed"
        )

    def test_partial_over_completed(self):
        self.assertEqual(
            resolve_status_conflict(["completed", "partial"]),
            "partial"
        )

    def test_completed_over_running(self):
        self.assertEqual(
            resolve_status_conflict(["running", "completed"]),
            "completed"
        )

    def test_running_over_queued(self):
        self.assertEqual(
            resolve_status_conflict(["queued", "running"]),
            "running"
        )

    def test_single_status_unchanged(self):
        self.assertEqual(resolve_status_conflict(["completed"]), "completed")


class TestStep96Revision(unittest.TestCase):
    """Test revision handling."""

    def test_ensure_revision(self):
        task = {"task_id": "test"}
        task = _ensure_revision(task)

        self.assertIn("revision", task)
        self.assertEqual(task["revision"], 1)

    def test_bump_revision(self):
        task = {"task_id": "test", "revision": 5}
        task = bump_revision(task)

        self.assertEqual(task["revision"], 6)

    def test_check_no_conflict(self):
        base = {"revision": 5}
        current = {"revision": 5}

        self.assertFalse(check_revision_conflict(base, current))

    def test_check_conflict(self):
        base = {"revision": 5}
        current = {"revision": 7}

        self.assertTrue(check_revision_conflict(base, current))


class TestStep96StepResultsMerge(unittest.TestCase):
    """Test step_results merging."""

    def test_merge_step_results_no_conflict(self):
        """step_results の競合更新が欠落しない"""
        base = [
            {"step_index": 0, "status": "ok"},
        ]
        ours = [
            {"step_index": 0, "status": "ok"},
            {"step_index": 1, "status": "ok"},
        ]
        theirs = [
            {"step_index": 0, "status": "ok"},
            {"step_index": 2, "status": "ok"},
        ]

        merged = merge_step_results(base, ours, theirs)

        # All steps should be present
        indices = [s["step_index"] for s in merged]
        self.assertIn(0, indices)
        self.assertIn(1, indices)
        self.assertIn(2, indices)

    def test_merge_step_results_newer_wins(self):
        base = [
            {"step_index": 0, "status": "ok", "finished_at": "2026-03-10T10:00:00Z"},
        ]
        ours = [
            {"step_index": 0, "status": "error", "finished_at": "2026-03-10T11:00:00Z"},
        ]
        theirs = [
            {"step_index": 0, "status": "ok", "finished_at": "2026-03-10T12:00:00Z"},
        ]

        merged = merge_step_results(base, ours, theirs)

        # Theirs is newer, should win
        self.assertEqual(merged[0]["status"], "ok")


class TestStep96MemoryMerge(unittest.TestCase):
    """Test memory merging."""

    def test_merge_memory_decisions_union(self):
        """memory 競合更新で decisions / questions / actions が壊れない"""
        base = {
            "decisions": ["D1"],
            "open_questions": ["Q1"],
            "next_actions": ["A1"],
        }
        ours = {
            "decisions": ["D1", "D2"],
            "open_questions": ["Q1", "Q2"],
            "next_actions": ["A1", "A2"],
        }
        theirs = {
            "decisions": ["D1", "D3"],
            "open_questions": ["Q1", "Q3"],
            "next_actions": ["A1", "A3"],
        }

        merged = merge_memory(base, ours, theirs)

        # Union of all decisions
        self.assertIn("D1", merged["decisions"])
        self.assertIn("D2", merged["decisions"])
        self.assertIn("D3", merged["decisions"])

        # Union of all questions
        self.assertIn("Q2", merged["open_questions"])
        self.assertIn("Q3", merged["open_questions"])

        # Union of all actions
        self.assertIn("A2", merged["next_actions"])
        self.assertIn("A3", merged["next_actions"])

    def test_merge_memory_dedupes(self):
        base = {"decisions": ["D1", "D2"]}
        ours = {"decisions": ["D1", "D2", "D3"]}
        theirs = {"decisions": ["D1", "D2", "D3"]}

        merged = merge_memory(base, ours, theirs)

        # Should dedupe
        self.assertEqual(merged["decisions"].count("D1"), 1)
        self.assertEqual(merged["decisions"].count("D2"), 1)
        self.assertEqual(merged["decisions"].count("D3"), 1)


class TestStep96ScheduleMerge(unittest.TestCase):
    """Test schedule merging."""

    def test_merge_schedule_retry_count(self):
        base = {"retry_count": 0}
        ours = {"retry_count": 1}
        theirs = {"retry_count": 2}

        merged = merge_schedule(base, ours, theirs)

        # Use highest
        self.assertEqual(merged["retry_count"], 2)

    def test_merge_schedule_clears_lock(self):
        base = {"locked_by": "scheduler-1", "locked_at": "2026-03-10T10:00:00Z"}
        ours = {"locked_by": None, "locked_at": None}
        theirs = {"locked_by": "scheduler-2", "locked_at": "2026-03-10T11:00:00Z"}

        merged = merge_schedule(base, ours, theirs)

        # Lock should be cleared if either side cleared it
        self.assertIsNone(merged["locked_by"])


class TestStep96RecoveryMerge(unittest.TestCase):
    """Test recovery merging."""

    def test_merge_recovery_count(self):
        base = {"recovery_count": 0}
        ours = {"recovery_count": 1}
        theirs = {"recovery_count": 2}

        merged = merge_recovery(base, ours, theirs)

        # Use highest
        self.assertEqual(merged["recovery_count"], 2)


class TestStep96FullTaskMerge(unittest.TestCase):
    """Test full task state merging."""

    def test_merge_full_task(self):
        """recovery と scheduler 更新が競合しても state が壊れない"""
        base = {
            "task_id": "test",
            "status": "running",
            "revision": 5,
            "step_results": [
                {"step_index": 0, "status": "ok", "finished_at": "2026-03-10T10:00:00Z"},
            ],
            "memory": {
                "summary": "Working",
                "decisions": ["D1"],
            },
            "schedule": {
                "retry_count": 0,
                "locked_by": "scheduler-1",
            },
            "recovery": {
                "recovery_count": 0,
            },
            "execution": {
                "current_step_index": 1,
            },
        }

        # Scheduler adds a step
        ours = {
            "status": "running",
            "revision": 6,
            "step_results": [
                {"step_index": 0, "status": "ok", "finished_at": "2026-03-10T10:00:00Z"},
                {"step_index": 1, "status": "ok", "finished_at": "2026-03-10T11:00:00Z"},
            ],
            "schedule": {
                "retry_count": 0,
                "locked_by": None,  # Unlocked after completion
            },
        }

        # Recovery detects stale and recovers
        theirs = {
            "status": "partial",
            "revision": 6,
            "memory": {
                "summary": "Recovered",
                "decisions": ["D1", "D2"],
            },
            "recovery": {
                "recovery_count": 1,
                "recovered_at": "2026-03-10T12:00:00Z",
            },
        }

        merged = merge_task_states(base, ours, theirs)

        # Status should be partial (higher priority than running)
        self.assertEqual(merged["status"], "partial")

        # Both steps should be present
        self.assertEqual(len(merged["step_results"]), 2)

        # Memory should be merged
        self.assertIn("D2", merged["memory"]["decisions"])

        # Lock should be cleared (ours cleared it)
        self.assertIsNone(merged["schedule"]["locked_by"])

        # Revision should be bumped
        self.assertEqual(merged["revision"], 7)

        # Recovery count should be 1
        self.assertEqual(merged["recovery"]["recovery_count"], 1)


class TestStep96SafeUpdate(unittest.TestCase):
    """Test safe update functionality."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.task_path = Path(self.temp_dir) / "task-test.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_safe_update_success(self):
        task = {
            "task_id": "test",
            "revision": 1,
            "status": "queued",
        }
        self.task_path.write_text(json.dumps(task))

        def update_status(t):
            t = dict(t)
            t["status"] = "running"
            return t

        updated, success = safe_update_task(self.task_path, update_status)

        self.assertTrue(success)
        self.assertEqual(updated["status"], "running")
        self.assertEqual(updated["revision"], 2)


if __name__ == "__main__":
    unittest.main()
