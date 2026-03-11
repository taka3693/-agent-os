#!/usr/bin/env python3
"""Step92: Task Scheduler Tests

Tests for the scheduler implementation that manages:
- Finding executable tasks (queued, retry-able)
- Respecting run_at / next_retry_at timing
- Preventing double execution
- Lock mechanism
- Retry policies
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.task_scheduler import (
    _now_iso,
    _parse_iso,
    _is_future,
    _init_schedule,
    _ensure_schedule,
    _is_task_locked,
    _acquire_lock,
    _release_lock,
    _can_retry,
    _increment_retry,
    find_executable_tasks,
    run_scheduler_cycle,
    create_scheduled_task,
)


class TestStep92ScheduleSchema(unittest.TestCase):
    """Test schedule section schema."""

    def test_init_schedule_has_all_fields(self):
        schedule = _init_schedule()

        self.assertIn("run_at", schedule)
        self.assertIn("retry_count", schedule)
        self.assertIn("max_retries", schedule)
        self.assertIn("last_attempt_at", schedule)
        self.assertIn("next_retry_at", schedule)
        self.assertIn("locked_by", schedule)
        self.assertIn("locked_at", schedule)

    def test_ensure_schedule_adds_missing_fields(self):
        task = {"task_id": "test", "status": "queued"}
        task = _ensure_schedule(task)

        self.assertIn("schedule", task)
        self.assertEqual(task["schedule"]["retry_count"], 0)
        self.assertEqual(task["schedule"]["max_retries"], 3)

    def test_ensure_schedule_preserves_existing(self):
        task = {
            "task_id": "test",
            "status": "queued",
            "schedule": {
                "retry_count": 2,
                "max_retries": 5,
            },
        }
        task = _ensure_schedule(task)

        self.assertEqual(task["schedule"]["retry_count"], 2)
        self.assertEqual(task["schedule"]["max_retries"], 5)


class TestStep92Locking(unittest.TestCase):
    """Test task locking mechanism."""

    def test_task_not_locked_initially(self):
        task = _ensure_schedule({"task_id": "test"})
        self.assertFalse(_is_task_locked(task))

    def test_acquire_lock(self):
        task = _ensure_schedule({"task_id": "test"})
        task = _acquire_lock(task, "scheduler-1")

        self.assertEqual(task["schedule"]["locked_by"], "scheduler-1")
        self.assertIsNotNone(task["schedule"]["locked_at"])
        self.assertTrue(_is_task_locked(task))

    def test_release_lock(self):
        task = _ensure_schedule({"task_id": "test"})
        task = _acquire_lock(task, "scheduler-1")
        task = _release_lock(task)

        self.assertIsNone(task["schedule"]["locked_by"])
        self.assertIsNone(task["schedule"]["locked_at"])
        self.assertFalse(_is_task_locked(task))

    def test_lock_expires_after_5_minutes(self):
        task = _ensure_schedule({"task_id": "test"})

        # Set locked_at to 6 minutes ago
        past = (datetime.now(timezone.utc) - timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task["schedule"]["locked_by"] = "scheduler-1"
        task["schedule"]["locked_at"] = past

        # Lock should be expired
        self.assertFalse(_is_task_locked(task))


class TestStep92RetryPolicy(unittest.TestCase):
    """Test retry policy handling."""

    def test_can_retry_under_limit(self):
        task = _ensure_schedule({"task_id": "test", "status": "failed"})
        task["schedule"]["retry_count"] = 2
        task["schedule"]["max_retries"] = 3

        self.assertTrue(_can_retry(task))

    def test_cannot_retry_over_limit(self):
        task = _ensure_schedule({"task_id": "test", "status": "failed"})
        task["schedule"]["retry_count"] = 3
        task["schedule"]["max_retries"] = 3

        self.assertFalse(_can_retry(task))

    def test_increment_retry_increments_count(self):
        task = _ensure_schedule({"task_id": "test", "status": "failed"})
        task["schedule"]["retry_count"] = 0

        task = _increment_retry(task)

        self.assertEqual(task["schedule"]["retry_count"], 1)
        self.assertIsNotNone(task["schedule"]["last_attempt_at"])
        self.assertIsNotNone(task["schedule"]["next_retry_at"])


class TestStep92FindExecutableTasks(unittest.TestCase):
    """Test finding executable tasks."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.tasks_dir = Path(self.temp_dir) / "tasks"
        self.tasks_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_queued_task(self):
        """queued task を拾う"""
        task = create_scheduled_task(
            task_id="task-test-queued",
            query="test query",
            skill_chain=["research"],
        )
        task_path = self.tasks_dir / "task-test-queued.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        tasks = find_executable_tasks(self.tasks_dir)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], "task-test-queued")

    def test_skip_future_run_at(self):
        """future run_at task は拾わない"""
        # Set run_at to 1 hour in the future
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task = create_scheduled_task(
            task_id="task-test-future",
            query="test query",
            skill_chain=["research"],
            run_at=future,
        )
        task_path = self.tasks_dir / "task-test-future.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        tasks = find_executable_tasks(self.tasks_dir)

        self.assertEqual(len(tasks), 0)

    def test_skip_running_task(self):
        """running task は拾わない"""
        task = create_scheduled_task(
            task_id="task-test-running",
            query="test query",
            skill_chain=["research"],
        )
        task["status"] = "running"
        task_path = self.tasks_dir / "task-test-running.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        tasks = find_executable_tasks(self.tasks_dir)

        self.assertEqual(len(tasks), 0)

    def test_skip_retry_limit_exceeded(self):
        """retry 上限超過 task は再実行しない"""
        task = create_scheduled_task(
            task_id="task-test-retry-exceeded",
            query="test query",
            skill_chain=["research"],
            max_retries=3,
        )
        task["status"] = "failed"
        task["schedule"]["retry_count"] = 3
        task_path = self.tasks_dir / "task-test-retry-exceeded.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        tasks = find_executable_tasks(self.tasks_dir)

        self.assertEqual(len(tasks), 0)

    def test_skip_locked_task(self):
        """lock 済み task はスキップ"""
        task = create_scheduled_task(
            task_id="task-test-locked",
            query="test query",
            skill_chain=["research"],
        )
        task = _acquire_lock(task, "other-scheduler")
        task_path = self.tasks_dir / "task-test-locked.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        tasks = find_executable_tasks(self.tasks_dir)

        self.assertEqual(len(tasks), 0)

    def test_find_failed_task_with_retries_remaining(self):
        """failed task with retries remaining is found"""
        task = create_scheduled_task(
            task_id="task-test-retry",
            query="test query",
            skill_chain=["research"],
            max_retries=3,
        )
        task["status"] = "failed"
        task["schedule"]["retry_count"] = 1
        task_path = self.tasks_dir / "task-test-retry.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        tasks = find_executable_tasks(self.tasks_dir)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], "task-test-retry")

    def test_skip_future_next_retry_at(self):
        """future next_retry_at is skipped"""
        task = create_scheduled_task(
            task_id="task-test-future-retry",
            query="test query",
            skill_chain=["research"],
        )
        task["status"] = "failed"
        task["schedule"]["retry_count"] = 1
        # Set next_retry_at to 1 hour in the future
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task["schedule"]["next_retry_at"] = future
        task_path = self.tasks_dir / "task-test-future-retry.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        tasks = find_executable_tasks(self.tasks_dir)

        self.assertEqual(len(tasks), 0)


class TestStep92RunSchedulerCycle(unittest.TestCase):
    """Test scheduler cycle execution."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.tasks_dir = Path(self.temp_dir) / "tasks"
        self.tasks_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scheduler_executes_queued_task(self):
        """scheduler executes queued task"""
        task = create_scheduled_task(
            task_id="task-test-cycle",
            query="test query",
            skill_chain=["research"],
        )
        task_path = self.tasks_dir / "task-test-cycle.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        def executor(t):
            t = dict(t)
            t["status"] = "completed"
            return t

        summary = run_scheduler_cycle(self.tasks_dir, executor)

        self.assertEqual(summary["executed"], 1)
        self.assertEqual(summary["errors"], 0)

        # Verify task was updated
        updated = json.loads(task_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["status"], "completed")

    def test_scheduler_handles_executor_error(self):
        """scheduler handles executor errors gracefully"""
        task = create_scheduled_task(
            task_id="task-test-error",
            query="test query",
            skill_chain=["research"],
        )
        task_path = self.tasks_dir / "task-test-error.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))

        def failing_executor(t):
            raise RuntimeError("executor failed")

        summary = run_scheduler_cycle(self.tasks_dir, failing_executor)

        self.assertEqual(summary["executed"], 0)
        self.assertEqual(summary["errors"], 1)

        # Verify task was marked as failed
        updated = json.loads(task_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["status"], "failed")


class TestStep92CreateScheduledTask(unittest.TestCase):
    """Test scheduled task creation."""

    def test_create_scheduled_task_has_all_fields(self):
        task = create_scheduled_task(
            task_id="task-test-create",
            query="test query",
            skill_chain=["decision", "execution"],
            run_at="2026-03-10T12:00:00Z",
            max_retries=5,
        )

        self.assertEqual(task["task_id"], "task-test-create")
        self.assertEqual(task["status"], "queued")
        self.assertEqual(task["plan"]["skill_chain"], ["decision", "execution"])
        self.assertEqual(task["schedule"]["run_at"], "2026-03-10T12:00:00Z")
        self.assertEqual(task["schedule"]["max_retries"], 5)
        self.assertEqual(task["schedule"]["retry_count"], 0)


if __name__ == "__main__":
    unittest.main()
