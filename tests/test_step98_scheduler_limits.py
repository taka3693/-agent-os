#!/usr/bin/env python3
"""Step98: Scheduler Limits / Fairness Tests

Tests for:
- Global max_concurrent_tasks enforcement
- Composed limit (scheduler + parallel executor)
- Priority ordering: queued > partial > failed(retry)
- Starvation prevention for long-waiting tasks
- Fairness across skill chains
- No regression on existing behaviour
"""
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.task_scheduler import (
    _now_iso,
    _atomic_write_json,
    _ensure_schedule,
    _task_sort_key,
    _count_running_tasks,
    find_executable_tasks,
    run_scheduler_cycle,
    create_scheduled_task,
    DEFAULT_MAX_CONCURRENT_TASKS,
    _STARVATION_THRESHOLD_SECONDS,
)
from runner.parallel_executor import (
    effective_max_workers,
    DEFAULT_MAX_PARALLEL_WORKERS,
)


def _make_task(task_id, status="queued", skill="research", created_at=None,
               retry_count=0, max_retries=3):
    """Helper to build a task dict quickly."""
    task = create_scheduled_task(
        task_id=task_id,
        query=f"query for {task_id}",
        skill_chain=[skill],
        max_retries=max_retries,
    )
    task["status"] = status
    if created_at:
        task["created_at"] = created_at
    task["schedule"]["retry_count"] = retry_count
    return task


class TestStep98GlobalConcurrencyLimit(unittest.TestCase):
    """max_concurrent_tasks を超えない"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.tasks_dir = Path(self.temp_dir) / "tasks"
        self.tasks_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_respects_global_limit(self):
        """queued task が limit を超えて返されない"""
        for i in range(6):
            task = _make_task(f"task-q{i}")
            _atomic_write_json(self.tasks_dir / f"task-q{i}.json", task)

        tasks = find_executable_tasks(
            self.tasks_dir, max_concurrent_tasks=3,
        )
        self.assertEqual(len(tasks), 3)

    def test_running_tasks_reduce_available_slots(self):
        """running task があると利用可能スロットが減る"""
        # 2 running
        for i in range(2):
            task = _make_task(f"task-r{i}", status="running")
            _atomic_write_json(self.tasks_dir / f"task-r{i}.json", task)
        # 4 queued
        for i in range(4):
            task = _make_task(f"task-q{i}")
            _atomic_write_json(self.tasks_dir / f"task-q{i}.json", task)

        tasks = find_executable_tasks(
            self.tasks_dir, max_concurrent_tasks=3,
        )
        # only 1 slot available (3 - 2 running)
        self.assertEqual(len(tasks), 1)

    def test_zero_slots_returns_empty(self):
        """全スロットが running なら空リスト"""
        for i in range(3):
            task = _make_task(f"task-r{i}", status="running")
            _atomic_write_json(self.tasks_dir / f"task-r{i}.json", task)
        task = _make_task("task-q0")
        _atomic_write_json(self.tasks_dir / "task-q0.json", task)

        tasks = find_executable_tasks(
            self.tasks_dir, max_concurrent_tasks=3,
        )
        self.assertEqual(len(tasks), 0)

    def test_default_limit_is_4(self):
        self.assertEqual(DEFAULT_MAX_CONCURRENT_TASKS, 4)


class TestStep98ComposedLimit(unittest.TestCase):
    """parallel executor と scheduler の合成上限"""

    def test_effective_workers_capped_by_scheduler(self):
        """scheduler limit が parallel workers より小さい場合"""
        result = effective_max_workers(
            scheduler_max_concurrent=3,
            current_running=2,
            max_parallel_workers=4,
        )
        # remaining = 3-2 = 1, min(4, 1) = 1
        self.assertEqual(result, 1)

    def test_effective_workers_capped_by_parallel(self):
        """parallel workers が scheduler limit より小さい場合"""
        result = effective_max_workers(
            scheduler_max_concurrent=10,
            current_running=0,
            max_parallel_workers=2,
        )
        self.assertEqual(result, 2)

    def test_effective_workers_zero_when_exhausted(self):
        """スロット使い切りで 0"""
        result = effective_max_workers(
            scheduler_max_concurrent=3,
            current_running=5,
            max_parallel_workers=2,
        )
        self.assertEqual(result, 0)

    def test_effective_workers_exact_match(self):
        result = effective_max_workers(
            scheduler_max_concurrent=4,
            current_running=2,
            max_parallel_workers=2,
        )
        self.assertEqual(result, 2)


class TestStep98PriorityOrdering(unittest.TestCase):
    """優先順位が仕様通り: queued > partial > failed(retry)"""

    def test_queued_before_partial(self):
        queued = _make_task("t1", status="queued")
        partial = _make_task("t2", status="partial")
        # same created_at so starvation doesn't interfere
        now = _now_iso()
        queued["created_at"] = now
        partial["created_at"] = now
        self.assertLess(
            _task_sort_key(queued),
            _task_sort_key(partial),
        )

    def test_partial_before_failed(self):
        partial = _make_task("t1", status="partial")
        failed = _make_task("t2", status="failed")
        now = _now_iso()
        partial["created_at"] = now
        failed["created_at"] = now
        # same skill for deterministic comparison
        partial["plan"]["skill_chain"] = ["same"]
        failed["plan"]["skill_chain"] = ["same"]
        self.assertLess(
            _task_sort_key(partial),
            _task_sort_key(failed),
        )

    def test_priority_in_find_executable(self):
        """find_executable_tasks の結果が優先順位順"""
        temp_dir = tempfile.mkdtemp()
        tasks_dir = Path(temp_dir) / "tasks"
        tasks_dir.mkdir(parents=True)

        now = _now_iso()
        # failed with retry
        t_failed = _make_task("task-aaa-failed", status="failed",
                              skill="same", retry_count=0)
        t_failed["created_at"] = now
        _atomic_write_json(tasks_dir / "task-aaa-failed.json", t_failed)

        # queued
        t_queued = _make_task("task-bbb-queued", status="queued",
                              skill="same")
        t_queued["created_at"] = now
        _atomic_write_json(tasks_dir / "task-bbb-queued.json", t_queued)

        # partial
        t_partial = _make_task("task-ccc-partial", status="partial",
                               skill="same", retry_count=0)
        t_partial["created_at"] = now
        _atomic_write_json(tasks_dir / "task-ccc-partial.json", t_partial)

        tasks = find_executable_tasks(tasks_dir, max_concurrent_tasks=10)
        statuses = [t["status"] for t in tasks]

        # queued first, then partial, then failed
        self.assertEqual(statuses, ["queued", "partial", "failed"])

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestStep98StarvationPrevention(unittest.TestCase):
    """古い待機 task が starvation しない"""

    def test_old_task_boosted(self):
        """長時間待機 task はステータスに関係なく優先される"""
        # old failed task (10 minutes ago)
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        old_failed = _make_task("t-old", status="failed", skill="same",
                                retry_count=0)
        old_failed["created_at"] = old_ts

        # new queued task (just now)
        new_queued = _make_task("t-new", status="queued", skill="same")
        new_queued["created_at"] = _now_iso()

        # old task should sort first despite lower status priority
        self.assertLess(
            _task_sort_key(old_failed),
            _task_sort_key(new_queued),
        )

    def test_starvation_threshold_boundary(self):
        """ちょうど threshold 以上で boost される"""
        boundary_ts = (
            datetime.now(timezone.utc)
            - timedelta(seconds=_STARVATION_THRESHOLD_SECONDS)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        task = _make_task("t-boundary", status="failed", retry_count=0)
        task["created_at"] = boundary_ts

        key = _task_sort_key(task)
        self.assertEqual(key[0], 0, "task at threshold should be boosted")

    def test_young_task_not_boosted(self):
        """新しい task は boost されない"""
        task = _make_task("t-young")
        task["created_at"] = _now_iso()

        key = _task_sort_key(task)
        self.assertEqual(key[0], 1, "young task should NOT be boosted")


class TestStep98Fairness(unittest.TestCase):
    """同一系列 task の偏りが抑えられる"""

    def test_different_skills_interleaved(self):
        """異なるスキルチェーンの task が混合される"""
        temp_dir = tempfile.mkdtemp()
        tasks_dir = Path(temp_dir) / "tasks"
        tasks_dir.mkdir(parents=True)

        now = _now_iso()
        skills = ["research", "critique", "decision"]
        for i, skill in enumerate(skills):
            for j in range(3):
                tid = f"task-{skill}-{j}"
                task = _make_task(tid, skill=skill)
                task["created_at"] = now
                _atomic_write_json(tasks_dir / f"{tid}.json", task)

        tasks = find_executable_tasks(tasks_dir, max_concurrent_tasks=9)

        # All 9 tasks returned
        self.assertEqual(len(tasks), 9)

        # Check that it's not all one skill first
        first_three_skills = [
            (t.get("plan") or {}).get("skill_chain", [""])[0]
            for t in tasks[:3]
        ]
        # With fairness hashing, skills should be distributed
        # (not all 3 from the same skill)
        unique_first = set(first_three_skills)
        # At least 2 different skills in first 3 slots
        self.assertGreaterEqual(
            len(unique_first), 2,
            f"First 3 tasks should have >= 2 distinct skills, got {first_three_skills}",
        )

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestStep98SchedulerCycleWithLimit(unittest.TestCase):
    """run_scheduler_cycle が max_concurrent_tasks を受け取れる"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.tasks_dir = Path(self.temp_dir) / "tasks"
        self.tasks_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cycle_respects_global_limit(self):
        for i in range(5):
            task = _make_task(f"task-c{i}")
            _atomic_write_json(self.tasks_dir / f"task-c{i}.json", task)

        def executor(t):
            t = dict(t)
            t["status"] = "completed"
            return t

        summary = run_scheduler_cycle(
            self.tasks_dir,
            executor,
            max_concurrent_tasks=2,
        )
        self.assertLessEqual(summary["executed"], 2)

    def test_cycle_backward_compatible(self):
        """max_concurrent_tasks 未指定でも動く"""
        task = _make_task("task-compat")
        _atomic_write_json(self.tasks_dir / "task-compat.json", task)

        def executor(t):
            t = dict(t)
            t["status"] = "completed"
            return t

        summary = run_scheduler_cycle(self.tasks_dir, executor)
        self.assertEqual(summary["executed"], 1)


class TestStep98CountRunning(unittest.TestCase):
    """_count_running_tasks のユニットテスト"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.tasks_dir = Path(self.temp_dir) / "tasks"
        self.tasks_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_counts_running_only(self):
        _atomic_write_json(
            self.tasks_dir / "task-r1.json",
            _make_task("task-r1", status="running"),
        )
        _atomic_write_json(
            self.tasks_dir / "task-q1.json",
            _make_task("task-q1", status="queued"),
        )
        _atomic_write_json(
            self.tasks_dir / "task-c1.json",
            _make_task("task-c1", status="completed"),
        )
        self.assertEqual(_count_running_tasks(self.tasks_dir), 1)

    def test_empty_dir(self):
        self.assertEqual(_count_running_tasks(self.tasks_dir), 0)

    def test_nonexistent_dir(self):
        self.assertEqual(
            _count_running_tasks(Path("/nonexistent")), 0,
        )


if __name__ == "__main__":
    unittest.main()
