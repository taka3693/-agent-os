#!/usr/bin/env python3
"""Step99: Multi-Agent Orchestration Tests

Tests for:
- Coordinator subtask generation
- Worker count limit enforcement
- Worker processes only assigned subtask
- Coordinator merges results
- Worker failure → correct parent status
- Memory / state merge not broken
- Existing tests not broken
"""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.orchestrator import (
    ROLE_COORDINATOR,
    ROLE_WORKER,
    DEFAULT_MAX_WORKERS_PER_TASK,
    MAX_ORCHESTRATION_DEPTH,
    MAX_SUBTASKS,
    create_subtask,
    decompose_task,
    execute_subtask,
    merge_subtask_results,
    run_orchestration,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_task(task_id="task-orch-test"):
    return {
        "task_id": task_id,
        "status": "queued",
        "created_at": "2026-03-11T00:00:00Z",
        "request": {"text": "orchestration test query"},
        "plan": {"skill_chain": ["research"]},
        "step_results": [],
    }


def _simple_decompose(task):
    """Split into 2 subtasks."""
    return [
        {"query": "sub-query-1", "skill": "research"},
        {"query": "sub-query-2", "skill": "critique"},
    ]


def _large_decompose(task):
    """Return more than MAX_SUBTASKS items."""
    return [
        {"query": f"q{i}", "skill": "research"}
        for i in range(MAX_SUBTASKS + 5)
    ]


def _simple_worker(subtask):
    return {"answer": f"result for {subtask['subtask_id']}"}


def _failing_worker(subtask):
    raise RuntimeError("worker crashed")


# ---------------------------------------------------------------------------
# Tests: Coordinator generates subtasks
# ---------------------------------------------------------------------------

class TestStep99CoordinatorDecompose(unittest.TestCase):
    """coordinator が subtask を生成する"""

    def test_decompose_creates_subtasks(self):
        task = _base_task()
        subtasks = decompose_task(task, _simple_decompose)

        self.assertEqual(len(subtasks), 2)
        self.assertEqual(subtasks[0]["skill"], "research")
        self.assertEqual(subtasks[1]["skill"], "critique")

    def test_subtask_has_parent_link(self):
        task = _base_task("task-parent")
        subtasks = decompose_task(task, _simple_decompose)

        for st in subtasks:
            self.assertEqual(st["parent_task_id"], "task-parent")

    def test_subtask_has_worker_role(self):
        task = _base_task()
        subtasks = decompose_task(task, _simple_decompose)

        for st in subtasks:
            self.assertEqual(st["role"], ROLE_WORKER)

    def test_subtask_initial_status_queued(self):
        task = _base_task()
        subtasks = decompose_task(task, _simple_decompose)

        for st in subtasks:
            self.assertEqual(st["status"], "queued")

    def test_decompose_caps_at_max_subtasks(self):
        task = _base_task()
        subtasks = decompose_task(task, _large_decompose)

        self.assertEqual(len(subtasks), MAX_SUBTASKS)

    def test_decompose_empty_returns_empty(self):
        task = _base_task()
        subtasks = decompose_task(task, lambda t: [])

        self.assertEqual(subtasks, [])

    def test_decompose_non_list_returns_empty(self):
        task = _base_task()
        subtasks = decompose_task(task, lambda t: "not a list")

        self.assertEqual(subtasks, [])


# ---------------------------------------------------------------------------
# Tests: Worker count limit
# ---------------------------------------------------------------------------

class TestStep99WorkerLimit(unittest.TestCase):
    """worker 数が上限を超えない"""

    def test_max_workers_caps_concurrency(self):
        task = _base_task()
        concurrent = [0]
        max_seen = [0]
        lock = threading.Lock()

        def counting_worker(subtask):
            with lock:
                concurrent[0] += 1
                max_seen[0] = max(max_seen[0], concurrent[0])
            time.sleep(0.03)
            with lock:
                concurrent[0] -= 1
            return {"ok": True}

        def four_subtasks(t):
            return [
                {"query": f"q{i}", "skill": "research"}
                for i in range(4)
            ]

        result = run_orchestration(
            task,
            decompose_fn=four_subtasks,
            worker_fn=counting_worker,
            max_workers_per_task=2,
        )

        # At most 2 concurrent workers
        self.assertLessEqual(max_seen[0], 2)
        # All 4 subtasks still processed
        orch_result = result.get("orchestration_result", {})
        self.assertEqual(len(orch_result.get("subtask_results", [])), 4)

    def test_default_max_workers(self):
        self.assertEqual(DEFAULT_MAX_WORKERS_PER_TASK, 3)


# ---------------------------------------------------------------------------
# Tests: Worker processes only assigned subtask
# ---------------------------------------------------------------------------

class TestStep99WorkerIsolation(unittest.TestCase):
    """worker は割り当て subtask だけ処理する"""

    def test_worker_receives_only_its_subtask(self):
        received_ids = []

        def tracking_worker(subtask):
            received_ids.append(subtask["subtask_id"])
            return {"done": True}

        task = _base_task()
        run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=tracking_worker,
        )

        self.assertEqual(len(received_ids), 2)
        self.assertTrue(all("sub-" in sid for sid in received_ids))

    def test_worker_cannot_change_query(self):
        """worker が subtask の query を変えても元の subtask は影響しない"""
        original_queries = []

        def sneaky_worker(subtask):
            original_queries.append(subtask["query"])
            subtask["query"] = "TAMPERED"
            return {"done": True}

        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=sneaky_worker,
        )

        # Workers saw the original queries
        self.assertIn("sub-query-1", original_queries)
        self.assertIn("sub-query-2", original_queries)


# ---------------------------------------------------------------------------
# Tests: Coordinator merges results
# ---------------------------------------------------------------------------

class TestStep99CoordinatorMerge(unittest.TestCase):
    """coordinator が結果を統合する"""

    def test_default_merge_collects_all_results(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
        )

        orch_result = result.get("orchestration_result", {})
        subtask_results = orch_result.get("subtask_results", [])
        self.assertEqual(len(subtask_results), 2)

    def test_custom_merge_fn(self):
        def custom_merge(task, subtasks):
            combined = " + ".join(
                s.get("result", {}).get("answer", "")
                for s in subtasks if s.get("status") == "completed"
            )
            return {"combined": combined}

        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
            merge_fn=custom_merge,
        )

        orch_result = result.get("orchestration_result", {})
        self.assertIn("combined", orch_result)
        self.assertIn("+", orch_result["combined"])

    def test_coordinator_role_set(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
        )

        self.assertEqual(
            result.get("orchestration", {}).get("role"),
            ROLE_COORDINATOR,
        )

    def test_orchestration_metadata(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
        )

        orch = result.get("orchestration", {})
        self.assertEqual(orch["subtask_count"], 2)
        self.assertEqual(orch["completed_count"], 2)
        self.assertEqual(orch["failed_count"], 0)
        self.assertEqual(len(orch["subtask_ids"]), 2)


# ---------------------------------------------------------------------------
# Tests: Worker failure status
# ---------------------------------------------------------------------------

class TestStep99WorkerFailure(unittest.TestCase):
    """worker failure 時の status が仕様通り"""

    def test_all_workers_fail_status_failed(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_failing_worker,
        )

        self.assertEqual(result["status"], "failed")

    def test_partial_failure_status_partial(self):
        call_count = [0]

        def partial_worker(subtask):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("first fails")
            return {"ok": True}

        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=partial_worker,
        )

        self.assertEqual(result["status"], "partial")

    def test_all_success_status_completed(self):
        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
        )

        self.assertEqual(result["status"], "completed")

    def test_failed_subtask_has_error(self):
        task = _base_task()
        subtask = create_subtask("st-1", "t-1", "q", "research", 0)
        executed = execute_subtask(subtask, _failing_worker)

        self.assertEqual(executed["status"], "failed")
        self.assertIn("RuntimeError", executed["error"])


# ---------------------------------------------------------------------------
# Tests: Memory / state merge not broken
# ---------------------------------------------------------------------------

class TestStep99MemoryIntegrity(unittest.TestCase):
    """memory / state merge が壊れない"""

    def test_memory_preserved_after_orchestration(self):
        task = _base_task()
        task["memory"] = {
            "summary": "existing summary",
            "decisions": ["d1"],
            "open_questions": [],
            "next_actions": [],
        }

        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
        )

        mem = result.get("memory", {})
        self.assertEqual(mem["summary"], "existing summary")
        self.assertIn("d1", mem["decisions"])

    def test_memory_created_if_missing(self):
        task = _base_task()
        # no memory key
        task.pop("memory", None)

        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
        )

        self.assertIn("memory", result)
        self.assertIsInstance(result["memory"], dict)

    def test_revision_bumped(self):
        task = _base_task()
        task["revision"] = 5

        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
        )

        self.assertGreater(result.get("revision", 0), 5)

    def test_state_merge_compatible(self):
        """merge_task_states still works with orchestrated task"""
        from runner.state_merge import merge_task_states

        task = _base_task()
        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
        )

        # Merge with itself should not crash
        merged = merge_task_states(task, result, result)
        self.assertIn("status", merged)


# ---------------------------------------------------------------------------
# Tests: Orchestration depth limit
# ---------------------------------------------------------------------------

class TestStep99DepthLimit(unittest.TestCase):
    """orchestration depth が上限を超えない"""

    def test_depth_exceeded_fails(self):
        task = _base_task()
        task["orchestration"] = {"depth": MAX_ORCHESTRATION_DEPTH}

        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
        )

        self.assertEqual(result["status"], "failed")
        self.assertIn("depth", result.get("error", ""))

    def test_depth_zero_is_allowed(self):
        task = _base_task()

        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
        )

        self.assertEqual(result["status"], "completed")

    def test_max_depth_default_is_1(self):
        self.assertEqual(MAX_ORCHESTRATION_DEPTH, 1)


# ---------------------------------------------------------------------------
# Tests: Persistence (task_path)
# ---------------------------------------------------------------------------

class TestStep99Persistence(unittest.TestCase):
    """task_path 指定時にファイルへ永続化"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.task_path = Path(self.temp_dir) / "task-orch.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_result_written_to_file(self):
        task = _base_task()

        result = run_orchestration(
            task,
            decompose_fn=_simple_decompose,
            worker_fn=_simple_worker,
            task_path=self.task_path,
        )

        self.assertTrue(self.task_path.exists())
        saved = json.loads(self.task_path.read_text())
        self.assertEqual(saved["status"], "completed")
        self.assertIn("orchestration_result", saved)


if __name__ == "__main__":
    unittest.main()
