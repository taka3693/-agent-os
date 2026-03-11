#!/usr/bin/env python3
"""Step93: Task Recovery Tests

Tests for the recovery implementation that manages:
- Detecting stale running tasks (heartbeat timeout)
- Detecting expired locked tasks
- Resume-able vs non-resume-able recovery
- Recovery limits
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.task_recovery import (
    _now_iso,
    _parse_iso,
    _seconds_since,
    _init_recovery,
    _ensure_recovery,
    _ensure_execution_heartbeat,
    _is_stale_running,
    _is_expired_lock,
    _can_recover,
    _is_resume_able,
    _recover_task,
    _fail_task,
    find_stale_tasks,
    run_recovery_cycle,
    update_heartbeat,
)


class TestStep93RecoverySchema(unittest.TestCase):
    """Test recovery section schema."""

    def test_init_recovery_has_all_fields(self):
        recovery = _init_recovery()

        self.assertIn("stale_after_seconds", recovery)
        self.assertIn("detected_at", recovery)
        self.assertIn("recovered_at", recovery)
        self.assertIn("recovery_count", recovery)
        self.assertIn("last_recovery_reason", recovery)
        self.assertIn("max_recoveries", recovery)

    def test_ensure_recovery_adds_missing_fields(self):
        task = {"task_id": "test", "status": "running"}
        task = _ensure_recovery(task)

        self.assertIn("recovery", task)
        self.assertEqual(task["recovery"]["stale_after_seconds"], 300)
        self.assertEqual(task["recovery"]["max_recoveries"], 3)

    def test_ensure_execution_heartbeat(self):
        task = {"task_id": "test", "status": "running"}
        task = _ensure_execution_heartbeat(task)

        self.assertIn("last_heartbeat_at", task["execution"])


class TestStep93StaleDetection(unittest.TestCase):
    """Test stale task detection."""

    def test_stale_running_task_detected(self):
        """stale running task を検出"""
        # Set heartbeat to 10 minutes ago
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task = {
            "task_id": "test",
            "status": "running",
            "started_at": past,
            "execution": {
                "last_heartbeat_at": past,
            },
            "recovery": {
                "stale_after_seconds": 300,
            },
        }

        self.assertTrue(_is_stale_running(task))

    def test_recent_heartbeat_not_stale(self):
        """新しい heartbeat の running task は回収しない"""
        # Set heartbeat to 1 minute ago
        recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task = {
            "task_id": "test",
            "status": "running",
            "execution": {
                "last_heartbeat_at": recent,
            },
            "recovery": {
                "stale_after_seconds": 300,
            },
        }

        self.assertFalse(_is_stale_running(task))

    def test_non_running_not_stale(self):
        """non-running tasks are not stale"""
        task = {
            "task_id": "test",
            "status": "completed",
        }

        self.assertFalse(_is_stale_running(task))


class TestStep93ExpiredLock(unittest.TestCase):
    """Test expired lock detection."""

    def test_expired_lock_detected(self):
        """expired lock task を回収"""
        # Set locked_at to 10 minutes ago
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task = {
            "task_id": "test",
            "status": "queued",
            "schedule": {
                "locked_by": "scheduler-1",
                "locked_at": past,
            },
        }

        self.assertTrue(_is_expired_lock(task))

    def test_recent_lock_not_expired(self):
        """recent locks are not expired"""
        recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task = {
            "task_id": "test",
            "status": "queued",
            "schedule": {
                "locked_by": "scheduler-1",
                "locked_at": recent,
            },
        }

        self.assertFalse(_is_expired_lock(task))

    def test_no_lock_not_expired(self):
        """tasks without lock are not expired"""
        task = {
            "task_id": "test",
            "status": "queued",
            "schedule": {},
        }

        self.assertFalse(_is_expired_lock(task))


class TestStep93RecoveryActions(unittest.TestCase):
    """Test recovery actions."""

    def test_resume_able_task_goes_to_partial(self):
        """resume可能 task を partial に戻す"""
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task = {
            "task_id": "test",
            "status": "running",
            "started_at": past,
            "execution": {
                "last_heartbeat_at": past,
                "current_step_index": 2,
                "completed_steps": 2,
            },
            "step_results": [
                {"step_index": 0, "status": "ok"},
                {"step_index": 1, "status": "ok"},
            ],
            "recovery": {
                "stale_after_seconds": 300,
                "recovery_count": 0,
                "max_recoveries": 3,
            },
        }

        task = _recover_task(task, "stale_heartbeat")

        self.assertEqual(task["status"], "partial")
        self.assertEqual(task["recovery"]["recovery_count"], 1)
        self.assertEqual(task["recovery"]["last_recovery_reason"], "stale_heartbeat")

    def test_non_resume_able_task_goes_to_queued(self):
        """resume不可 task を queued に戻す"""
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task = {
            "task_id": "test",
            "status": "running",
            "started_at": past,
            "execution": {
                "last_heartbeat_at": past,
                "current_step_index": 0,
                "completed_steps": 0,
            },
            "step_results": [],  # No successful steps
            "recovery": {
                "stale_after_seconds": 300,
                "recovery_count": 0,
                "max_recoveries": 3,
            },
        }

        task = _recover_task(task, "stale_heartbeat")

        self.assertEqual(task["status"], "queued")

    def test_fail_task_marks_failed(self):
        """resume不可 task を failed にする"""
        task = {
            "task_id": "test",
            "status": "running",
            "step_results": [],
            "recovery": {
                "recovery_count": 3,
                "max_recoveries": 3,
            },
        }

        task = _fail_task(task, "recovery_limit_exceeded")

        self.assertEqual(task["status"], "failed")
        self.assertIsNotNone(task["finished_at"])


class TestStep93RecoveryLimits(unittest.TestCase):
    """Test recovery limits."""

    def test_can_recover_under_limit(self):
        task = {
            "recovery": {
                "recovery_count": 2,
                "max_recoveries": 3,
            },
        }

        self.assertTrue(_can_recover(task))

    def test_cannot_recover_over_limit(self):
        """recovery 上限超過で自動回復しない"""
        task = {
            "recovery": {
                "recovery_count": 3,
                "max_recoveries": 3,
            },
        }

        self.assertFalse(_can_recover(task))


class TestStep93RecoveryCycle(unittest.TestCase):
    """Test recovery cycle execution."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.tasks_dir = Path(self.temp_dir) / "tasks"
        self.tasks_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_recovery_cycle_detects_stale_task(self):
        """stale running task を検出"""
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task = {
            "task_id": "task-stale",
            "status": "running",
            "started_at": past,
            "execution": {
                "last_heartbeat_at": past,
            },
            "step_results": [
                {"step_index": 0, "status": "ok"},
            ],
            "recovery": {
                "stale_after_seconds": 300,
                "recovery_count": 0,
                "max_recoveries": 3,
            },
        }
        task_path = self.tasks_dir / "task-stale.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        summary = run_recovery_cycle(self.tasks_dir)

        self.assertEqual(summary["found"], 1)
        self.assertEqual(summary["recovered"], 1)

        # Verify task was recovered
        updated = json.loads(task_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["status"], "partial")

    def test_recovery_cycle_handles_expired_lock(self):
        """expired lock task を回収"""
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task = {
            "task_id": "task-locked",
            "status": "queued",
            "schedule": {
                "locked_by": "scheduler-1",
                "locked_at": past,
            },
            "step_results": [],
            "recovery": {
                "recovery_count": 0,
                "max_recoveries": 3,
            },
        }
        task_path = self.tasks_dir / "task-locked.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        summary = run_recovery_cycle(self.tasks_dir)

        self.assertEqual(summary["found"], 1)
        self.assertEqual(summary["recovered"], 1)

        # Verify lock was cleared
        updated = json.loads(task_path.read_text(encoding="utf-8"))
        self.assertIsNone(updated["schedule"]["locked_by"])

    def test_recovery_cycle_fails_over_limit(self):
        """recovery 上限超過で自動回復しない"""
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task = {
            "task_id": "task-limit",
            "status": "running",
            "started_at": past,
            "execution": {
                "last_heartbeat_at": past,
            },
            "step_results": [],
            "recovery": {
                "stale_after_seconds": 300,
                "recovery_count": 3,
                "max_recoveries": 3,
            },
        }
        task_path = self.tasks_dir / "task-limit.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        summary = run_recovery_cycle(self.tasks_dir)

        self.assertEqual(summary["found"], 1)
        self.assertEqual(summary["failed"], 1)

        # Verify task was failed
        updated = json.loads(task_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["status"], "failed")


class TestStep93Heartbeat(unittest.TestCase):
    """Test heartbeat update."""

    def test_update_heartbeat(self):
        task = {
            "task_id": "test",
            "status": "running",
            "execution": {
                "last_heartbeat_at": None,
            },
        }

        task = update_heartbeat(task)

        self.assertIsNotNone(task["execution"]["last_heartbeat_at"])


if __name__ == "__main__":
    unittest.main()
