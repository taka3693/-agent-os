#!/usr/bin/env python3
"""Step101: Observability / Metrics Tests

Tests for:
- task status change → event recorded
- step error → failed_steps metric incremented
- recovery → recovery event / count
- orchestration → worker_runs / orchestration_runs
- budget limit → budget_limit_hits
- Existing tests not broken
"""
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.task_events import (
    init_metrics,
    ensure_observability,
    record_event,
    increment_metric,
    set_metric,
    get_metric,
    get_events,
    compute_metrics_from_task,
    MAX_EVENTS,
)
from runner.orchestrator import run_orchestration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_task(task_id="task-obs-test"):
    return {
        "task_id": task_id,
        "status": "queued",
        "created_at": "2026-03-11T00:00:00Z",
        "request": {"text": "obs test"},
        "plan": {"skill_chain": ["research"]},
        "step_results": [],
    }


def _decompose_n(n):
    def fn(task):
        return [{"query": f"q{i}", "skill": "research"} for i in range(n)]
    return fn


def _ok_worker(subtask):
    return {"answer": "ok"}


def _failing_worker(subtask):
    raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Tests: Event recording
# ---------------------------------------------------------------------------

class TestStep101EventRecording(unittest.TestCase):

    def test_record_event_appends(self):
        task = _base_task()
        task = ensure_observability(task)
        task = record_event(task, "test_event", reason="hello")

        self.assertEqual(len(task["events"]), 1)
        self.assertEqual(task["events"][0]["event_type"], "test_event")
        self.assertEqual(task["events"][0]["reason"], "hello")
        self.assertIn("timestamp", task["events"][0])
        self.assertEqual(task["events"][0]["task_id"], "task-obs-test")

    def test_events_capped_at_max(self):
        task = _base_task()
        task = ensure_observability(task)
        for i in range(MAX_EVENTS + 20):
            task = record_event(task, f"evt_{i}")
        self.assertLessEqual(len(task["events"]), MAX_EVENTS)

    def test_event_includes_optional_fields(self):
        task = _base_task()
        task = ensure_observability(task)
        task = record_event(
            task, "status_change",
            step_id="s1", subtask_id="sub-0",
            status_before="queued", status_after="running",
            reason="started", source="scheduler",
        )
        evt = task["events"][0]
        self.assertEqual(evt["step_id"], "s1")
        self.assertEqual(evt["subtask_id"], "sub-0")
        self.assertEqual(evt["status_before"], "queued")
        self.assertEqual(evt["status_after"], "running")
        self.assertEqual(evt["source"], "scheduler")

    def test_get_events_filters_by_type(self):
        task = _base_task()
        task = ensure_observability(task)
        task = record_event(task, "a")
        task = record_event(task, "b")
        task = record_event(task, "a")

        self.assertEqual(len(get_events(task, "a")), 2)
        self.assertEqual(len(get_events(task, "b")), 1)
        self.assertEqual(len(get_events(task)), 3)


# ---------------------------------------------------------------------------
# Tests: Metrics
# ---------------------------------------------------------------------------

class TestStep101Metrics(unittest.TestCase):

    def test_init_metrics_all_zero(self):
        m = init_metrics()
        for v in m.values():
            self.assertEqual(v, 0)

    def test_increment_metric(self):
        task = _base_task()
        task = ensure_observability(task)
        task = increment_metric(task, "failed_steps")
        task = increment_metric(task, "failed_steps", 2)
        self.assertEqual(get_metric(task, "failed_steps"), 3)

    def test_set_metric(self):
        task = _base_task()
        task = ensure_observability(task)
        task = set_metric(task, "total_steps", 42)
        self.assertEqual(get_metric(task, "total_steps"), 42)

    def test_get_metric_default_zero(self):
        task = _base_task()
        self.assertEqual(get_metric(task, "nonexistent"), 0)

    def test_ensure_observability_idempotent(self):
        task = _base_task()
        task = ensure_observability(task)
        task = increment_metric(task, "retry_count", 5)
        task = ensure_observability(task)
        self.assertEqual(get_metric(task, "retry_count"), 5)


# ---------------------------------------------------------------------------
# Tests: Status change events via orchestration
# ---------------------------------------------------------------------------

class TestStep101StatusChangeEvents(unittest.TestCase):
    """task status 変化で event が残る"""

    def test_orchestration_records_start_event(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(1),
            worker_fn=_ok_worker,
        )

        start_events = get_events(result, "orchestration_start")
        self.assertGreaterEqual(len(start_events), 1)
        self.assertEqual(start_events[0]["status_after"], "running")

    def test_orchestration_records_status_change(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(1),
            worker_fn=_ok_worker,
        )

        change_events = get_events(result, "status_change")
        # running → completed
        self.assertGreaterEqual(len(change_events), 1)


# ---------------------------------------------------------------------------
# Tests: Step error → failed_steps
# ---------------------------------------------------------------------------

class TestStep101FailedStepsMetric(unittest.TestCase):
    """step error で failed_steps が増える"""

    def test_failed_worker_increments_metric(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(2),
            worker_fn=_failing_worker,
        )

        self.assertEqual(get_metric(result, "failed_steps"), 2)

    def test_partial_failure_counts(self):
        call_count = [0]

        def half_fail(subtask):
            call_count[0] += 1
            if call_count[0] <= 1:
                raise RuntimeError("fail")
            return {"ok": True}

        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(2),
            worker_fn=half_fail,
        )

        self.assertEqual(get_metric(result, "failed_steps"), 1)


# ---------------------------------------------------------------------------
# Tests: Recovery events
# ---------------------------------------------------------------------------

class TestStep101RecoveryMetrics(unittest.TestCase):
    """recovery 時に recovery event / count が増える"""

    def test_compute_metrics_includes_recovery(self):
        task = _base_task()
        task["recovery"] = {"recovery_count": 3}
        m = compute_metrics_from_task(task)
        self.assertEqual(m["recovery_count"], 3)

    def test_compute_metrics_includes_retry(self):
        task = _base_task()
        task["schedule"] = {"retry_count": 2}
        m = compute_metrics_from_task(task)
        self.assertEqual(m["retry_count"], 2)


# ---------------------------------------------------------------------------
# Tests: Orchestration runs / worker runs
# ---------------------------------------------------------------------------

class TestStep101OrchestrationMetrics(unittest.TestCase):
    """orchestration 実行で worker_runs / orchestration_runs が増える"""

    def test_orchestration_runs_incremented(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(2),
            worker_fn=_ok_worker,
        )

        self.assertEqual(get_metric(result, "orchestration_runs"), 1)

    def test_worker_runs_incremented(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(3),
            worker_fn=_ok_worker,
        )

        self.assertEqual(get_metric(result, "worker_runs"), 3)

    def test_worker_complete_events(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(2),
            worker_fn=_ok_worker,
        )

        wc = get_events(result, "worker_complete")
        self.assertEqual(len(wc), 2)


# ---------------------------------------------------------------------------
# Tests: Budget limit hits
# ---------------------------------------------------------------------------

class TestStep101BudgetLimitMetric(unittest.TestCase):
    """budget 超過で budget_limit_hits が増える"""

    def test_budget_limit_increments_metric(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(5),
            worker_fn=_ok_worker,
            budget={"max_subtasks": 0},
        )

        self.assertEqual(get_metric(result, "budget_limit_hits"), 1)

    def test_budget_limit_records_event(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(5),
            worker_fn=_ok_worker,
            budget={"max_worker_runs": 1},
        )

        bl = get_events(result, "budget_limit")
        self.assertGreaterEqual(len(bl), 1)
        self.assertIn("max_worker_runs", bl[0].get("reason", ""))

    def test_no_budget_hit_when_within(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(1),
            worker_fn=_ok_worker,
        )

        self.assertEqual(get_metric(result, "budget_limit_hits"), 0)


# ---------------------------------------------------------------------------
# Tests: compute_metrics_from_task
# ---------------------------------------------------------------------------

class TestStep101ComputeMetrics(unittest.TestCase):

    def test_compute_from_completed_task(self):
        task = _base_task()
        task["status"] = "completed"
        task["started_at"] = "2026-03-11T00:00:00Z"
        task["finished_at"] = "2026-03-11T00:00:02Z"
        task["step_results"] = [
            {"status": "ok"},
            {"status": "error"},
        ]
        task["orchestration"] = {"role": "coordinator", "subtask_count": 2}
        task["budget"] = {"limit_reached_reason": None}

        m = compute_metrics_from_task(task)
        self.assertEqual(m["total_steps"], 2)
        self.assertEqual(m["failed_steps"], 1)
        self.assertEqual(m["orchestration_runs"], 1)
        self.assertEqual(m["worker_runs"], 2)
        self.assertEqual(m["total_duration_ms"], 2000)
        self.assertEqual(m["budget_limit_hits"], 0)

    def test_compute_partial_status(self):
        task = _base_task()
        task["status"] = "partial"
        m = compute_metrics_from_task(task)
        self.assertEqual(m["partial_runs"], 1)

    def test_compute_budget_hit(self):
        task = _base_task()
        task["budget"] = {"limit_reached_reason": "something"}
        m = compute_metrics_from_task(task)
        self.assertEqual(m["budget_limit_hits"], 1)


# ---------------------------------------------------------------------------
# Tests: total_steps metric
# ---------------------------------------------------------------------------

class TestStep101TotalSteps(unittest.TestCase):

    def test_total_steps_set_after_orchestration(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_decompose_n(3),
            worker_fn=_ok_worker,
        )

        self.assertEqual(get_metric(result, "total_steps"), 3)


if __name__ == "__main__":
    unittest.main()
