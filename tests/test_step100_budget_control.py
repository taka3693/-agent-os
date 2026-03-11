#!/usr/bin/env python3
"""Step100: Orchestration Guardrails / Budget Control Tests

Tests for:
- max_subtasks budget enforcement
- max_worker_runs budget enforcement
- duration budget enforcement
- retries total budget tracking
- limit_reached_reason is saved
- Existing tests not broken
"""
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.orchestrator import (
    init_budget,
    _ensure_budget,
    _budget_start_clock,
    _check_budget_subtasks,
    _check_budget_worker_runs,
    _check_budget_retries,
    _check_budget_duration,
    _set_limit_reached,
    run_orchestration,
    DEFAULT_BUDGET_MAX_SUBTASKS,
    DEFAULT_BUDGET_MAX_WORKER_RUNS,
    DEFAULT_BUDGET_MAX_RETRIES_TOTAL,
    DEFAULT_BUDGET_MAX_DURATION_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_task(task_id="task-budget-test"):
    return {
        "task_id": task_id,
        "status": "queued",
        "created_at": "2026-03-11T00:00:00Z",
        "request": {"text": "budget test"},
        "plan": {"skill_chain": ["research"]},
        "step_results": [],
    }


def _decompose_n(n):
    """Return a decompose_fn that produces n subtasks."""
    def fn(task):
        return [{"query": f"q{i}", "skill": "research"} for i in range(n)]
    return fn


def _ok_worker(subtask):
    return {"answer": "ok"}


def _failing_worker(subtask):
    raise RuntimeError("boom")


def _slow_worker(delay):
    def fn(subtask):
        time.sleep(delay)
        return {"answer": "slow"}
    return fn


# ---------------------------------------------------------------------------
# Tests: init / ensure budget
# ---------------------------------------------------------------------------

class TestStep100BudgetInit(unittest.TestCase):

    def test_init_budget_defaults(self):
        b = init_budget()
        self.assertEqual(b["max_subtasks"], DEFAULT_BUDGET_MAX_SUBTASKS)
        self.assertEqual(b["max_worker_runs"], DEFAULT_BUDGET_MAX_WORKER_RUNS)
        self.assertEqual(b["max_retries_total"], DEFAULT_BUDGET_MAX_RETRIES_TOTAL)
        self.assertEqual(b["max_duration_seconds"], DEFAULT_BUDGET_MAX_DURATION_SECONDS)
        self.assertEqual(b["spent_subtasks"], 0)
        self.assertEqual(b["spent_worker_runs"], 0)
        self.assertEqual(b["spent_retries_total"], 0)
        self.assertIsNone(b["started_budget_at"])
        self.assertIsNone(b["limit_reached_reason"])

    def test_ensure_budget_adds_missing(self):
        task = _base_task()
        task = _ensure_budget(task)
        self.assertIn("budget", task)
        self.assertEqual(task["budget"]["spent_subtasks"], 0)

    def test_ensure_budget_preserves_existing(self):
        task = _base_task()
        task["budget"] = {"max_subtasks": 2, "spent_subtasks": 1}
        task = _ensure_budget(task)
        self.assertEqual(task["budget"]["max_subtasks"], 2)
        self.assertEqual(task["budget"]["spent_subtasks"], 1)
        # Missing keys filled
        self.assertIn("max_worker_runs", task["budget"])


# ---------------------------------------------------------------------------
# Tests: max_subtasks budget
# ---------------------------------------------------------------------------

class TestStep100MaxSubtasks(unittest.TestCase):
    """max_subtasks を超えて分解しない"""

    def test_decompose_capped_by_budget(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(10),
            worker_fn=_ok_worker,
            budget={"max_subtasks": 3},
        )

        orch = result.get("orchestration", {})
        self.assertLessEqual(orch.get("subtask_count", 99), 3)

    def test_budget_spent_subtasks_exhausted(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(5),
            worker_fn=_ok_worker,
            budget={"max_subtasks": 2, "spent_subtasks": 2},
        )

        self.assertEqual(result["status"], "failed")
        reason = result.get("budget", {}).get("limit_reached_reason", "")
        self.assertIn("max_subtasks", reason)

    def test_zero_remaining_budget_blocks(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(1),
            worker_fn=_ok_worker,
            budget={"max_subtasks": 3, "spent_subtasks": 3},
        )

        self.assertEqual(result["status"], "failed")


# ---------------------------------------------------------------------------
# Tests: max_worker_runs budget
# ---------------------------------------------------------------------------

class TestStep100MaxWorkerRuns(unittest.TestCase):
    """max_worker_runs を超えて実行しない"""

    def test_worker_runs_budget_blocks(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(3),
            worker_fn=_ok_worker,
            budget={"max_worker_runs": 2},
        )

        self.assertEqual(result["status"], "failed")
        reason = result.get("budget", {}).get("limit_reached_reason", "")
        self.assertIn("max_worker_runs", reason)

    def test_worker_runs_within_budget(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(2),
            worker_fn=_ok_worker,
            budget={"max_worker_runs": 5},
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["budget"]["spent_worker_runs"], 2)

    def test_worker_runs_accumulate(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(2),
            worker_fn=_ok_worker,
            budget={"max_worker_runs": 10, "spent_worker_runs": 3},
        )

        self.assertEqual(result["budget"]["spent_worker_runs"], 5)  # 3 + 2


# ---------------------------------------------------------------------------
# Tests: duration budget
# ---------------------------------------------------------------------------

class TestStep100DurationBudget(unittest.TestCase):
    """duration budget 超過で停止する"""

    def test_expired_budget_blocks_start(self):
        task = _base_task()
        # started 10 minutes ago, limit 1 second
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(1),
            worker_fn=_ok_worker,
            budget={
                "max_duration_seconds": 1,
                "started_budget_at": past,
            },
        )

        self.assertEqual(result["status"], "failed")
        reason = result.get("budget", {}).get("limit_reached_reason", "")
        self.assertIn("max_duration_seconds", reason)

    def test_within_duration_succeeds(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(1),
            worker_fn=_ok_worker,
            budget={"max_duration_seconds": 300},
        )

        self.assertEqual(result["status"], "completed")

    def test_check_budget_duration_none_when_ok(self):
        budget = init_budget()
        budget["started_budget_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        budget["max_duration_seconds"] = 300
        self.assertIsNone(_check_budget_duration(budget))

    def test_check_budget_duration_returns_reason(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        budget = init_budget()
        budget["started_budget_at"] = past
        budget["max_duration_seconds"] = 10
        reason = _check_budget_duration(budget)
        self.assertIsNotNone(reason)
        self.assertIn("max_duration_seconds", reason)


# ---------------------------------------------------------------------------
# Tests: retries total
# ---------------------------------------------------------------------------

class TestStep100RetriesTotalBudget(unittest.TestCase):
    """retry/recovery/orchestration の合算上限が効く"""

    def test_retries_tracked(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(2),
            worker_fn=_failing_worker,
            budget={"max_retries_total": 10},
        )

        self.assertEqual(result["budget"]["spent_retries_total"], 2)

    def test_check_budget_retries_none_when_ok(self):
        budget = init_budget()
        self.assertIsNone(_check_budget_retries(budget))

    def test_check_budget_retries_exceeded(self):
        budget = init_budget()
        budget["spent_retries_total"] = 6
        budget["max_retries_total"] = 6
        reason = _check_budget_retries(budget, 1)
        self.assertIsNotNone(reason)
        self.assertIn("max_retries_total", reason)


# ---------------------------------------------------------------------------
# Tests: limit_reached_reason saved
# ---------------------------------------------------------------------------

class TestStep100LimitReasonSaved(unittest.TestCase):
    """limit_reached_reason が保存される"""

    def test_subtask_limit_reason(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(5),
            worker_fn=_ok_worker,
            budget={"max_subtasks": 0},
        )
        reason = result.get("budget", {}).get("limit_reached_reason")
        self.assertIsNotNone(reason)
        self.assertIn("max_subtasks", reason)

    def test_worker_runs_limit_reason(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(3),
            worker_fn=_ok_worker,
            budget={"max_worker_runs": 1},
        )
        reason = result.get("budget", {}).get("limit_reached_reason")
        self.assertIsNotNone(reason)
        self.assertIn("max_worker_runs", reason)

    def test_duration_limit_reason(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(1),
            worker_fn=_ok_worker,
            budget={"max_duration_seconds": 1, "started_budget_at": past},
        )
        reason = result.get("budget", {}).get("limit_reached_reason")
        self.assertIsNotNone(reason)
        self.assertIn("max_duration_seconds", reason)

    def test_no_reason_when_within_budget(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(1),
            worker_fn=_ok_worker,
        )
        reason = result.get("budget", {}).get("limit_reached_reason")
        self.assertIsNone(reason)


# ---------------------------------------------------------------------------
# Tests: backward compatibility
# ---------------------------------------------------------------------------

class TestStep100BackwardCompat(unittest.TestCase):
    """budget 未指定でも既存動作が壊れない"""

    def test_no_budget_param_works(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(2),
            worker_fn=_ok_worker,
        )
        self.assertEqual(result["status"], "completed")
        self.assertIn("budget", result)

    def test_budget_clock_auto_started(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(1),
            worker_fn=_ok_worker,
        )
        self.assertIsNotNone(result["budget"]["started_budget_at"])


if __name__ == "__main__":
    unittest.main()
