#!/usr/bin/env python3
"""Step91: Pipeline Executor Contract Tests

Tests for the executor implementation that manages:
- Task state schema (task_id, status, created_at, request, plan, execution, step_results)
- Step result schema (step_index, skill, status, continue_on_error, started_at, finished_at, duration_ms, output, error_type, error_message)
- Execution contract (running status, error handling, atomic writes)
"""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

# Import executor functions
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "lib"))

from router_cli import (
    _now_iso,
    _atomic_write_json,
    _init_task_state,
    _execute_single_step,
    run_pipeline_executor,
)


class TestStep91TaskStateSchema(unittest.TestCase):
    """Test task state schema has all required fields."""

    def test_task_state_schema_minimum(self):
        task = _init_task_state(
            task_id="task-20260310-001",
            query="test query",
            selected_skill="decision",
            skill_chain=["decision", "execution"],
            source="cli",
        )

        # Required top-level fields
        self.assertIn("task_id", task)
        self.assertIn("status", task)
        self.assertIn("created_at", task)
        self.assertIn("started_at", task)
        self.assertIn("finished_at", task)
        self.assertIn("request", task)
        self.assertIn("plan", task)
        self.assertIn("execution", task)
        self.assertIn("step_results", task)

        # Request schema
        self.assertIn("source", task["request"])
        self.assertIn("text", task["request"])

        # Plan schema
        self.assertIn("selected_skill", task["plan"])
        self.assertIn("skill_chain", task["plan"])

        # Execution schema
        self.assertIn("current_step_index", task["execution"])
        self.assertIn("completed_steps", task["execution"])
        self.assertIn("resume_count", task["execution"])

    def test_task_initial_status_is_pending(self):
        task = _init_task_state(
            task_id="task-test",
            query="test",
            selected_skill="research",
            skill_chain=["research"],
        )
        self.assertEqual(task["status"], "pending")


class TestStep91StepResultSchema(unittest.TestCase):
    """Test step result schema has all required fields."""

    def test_step_result_schema_minimum(self):
        task = _init_task_state(
            task_id="task-test",
            query="test",
            selected_skill="decision",
            skill_chain=["decision"],
        )

        task = _execute_single_step(
            task=task,
            step_index=0,
            skill="decision",
            step_fn=lambda t: {"result": "ok"},
            continue_on_error=False,
        )

        step = task["step_results"][0]

        required = [
            "step_index",
            "skill",
            "status",
            "continue_on_error",
            "started_at",
            "finished_at",
            "duration_ms",
            "output",
            "error_type",
            "error_message",
        ]
        for key in required:
            self.assertIn(key, step, f"Missing required field: {key}")

    def test_step_result_has_timestamps(self):
        task = _init_task_state(
            task_id="task-test",
            query="test",
            selected_skill="research",
            skill_chain=["research"],
        )

        task = _execute_single_step(
            task=task,
            step_index=0,
            skill="research",
            step_fn=lambda t: {},
            continue_on_error=False,
        )

        step = task["step_results"][0]
        self.assertIsNotNone(step["started_at"])
        self.assertIsNotNone(step["finished_at"])
        self.assertIsNotNone(step["duration_ms"])
        self.assertGreaterEqual(step["duration_ms"], 0)

    def test_step_result_output_captured(self):
        task = _init_task_state(
            task_id="task-test",
            query="test",
            selected_skill="research",
            skill_chain=["research"],
        )

        task = _execute_single_step(
            task=task,
            step_index=0,
            skill="research",
            step_fn=lambda t: {"answer": 42, "items": [1, 2, 3]},
            continue_on_error=False,
        )

        step = task["step_results"][0]
        self.assertEqual(step["output"]["answer"], 42)
        self.assertEqual(step["output"]["items"], [1, 2, 3])


class TestStep91ErrorHandling(unittest.TestCase):
    """Test error handling in step execution."""

    def test_step_error_captured(self):
        def failing_step(task):
            raise ValueError("test error")

        task = _init_task_state(
            task_id="task-test",
            query="test",
            selected_skill="execution",
            skill_chain=["execution"],
        )

        task = _execute_single_step(
            task=task,
            step_index=0,
            skill="execution",
            step_fn=failing_step,
            continue_on_error=False,
        )

        step = task["step_results"][0]
        self.assertEqual(step["status"], "error")
        self.assertEqual(step["error_type"], "ValueError")
        self.assertEqual(step["error_message"], "test error")

    def test_continue_on_error_contract(self):
        """When continue_on_error=True, step error doesn't stop execution."""
        def failing_step(task):
            raise RuntimeError("intentional failure")

        task = _init_task_state(
            task_id="task-test",
            query="test",
            selected_skill="decision",
            skill_chain=["decision", "execution"],
        )

        # First step fails with continue_on_error=True
        task = _execute_single_step(
            task=task,
            step_index=0,
            skill="decision",
            step_fn=failing_step,
            continue_on_error=True,
        )

        # Second step should still run
        task = _execute_single_step(
            task=task,
            step_index=1,
            skill="execution",
            step_fn=lambda t: {"ok": True},
            continue_on_error=False,
        )

        self.assertEqual(len(task["step_results"]), 2)
        self.assertEqual(task["step_results"][0]["status"], "error")
        self.assertEqual(task["step_results"][1]["status"], "ok")


class TestStep91PipelineExecutor(unittest.TestCase):
    """Test full pipeline execution."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.tasks_dir = Path(self.temp_dir) / "tasks"
        self.tasks_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pipeline_all_steps_ok(self):
        """All steps succeed -> status=completed."""
        task = run_pipeline_executor(
            task_id="task-test-ok",
            query="test query",
            skill_chain=["decision", "execution"],
            step_fns=[
                lambda t: {"decision": "proceed"},
                lambda t: {"executed": True},
            ],
            tasks_dir=self.tasks_dir,
            source="cli",
        )

        self.assertEqual(task["status"], "completed")
        self.assertEqual(len(task["step_results"]), 2)
        self.assertEqual(task["execution"]["completed_steps"], 2)

    def test_pipeline_step_fails_no_continue(self):
        """Step fails without continue_on_error -> status=failed, stops early."""
        task = run_pipeline_executor(
            task_id="task-test-fail",
            query="test query",
            skill_chain=["decision", "execution", "retrospective"],
            step_fns=[
                lambda t: {"ok": True},
                lambda t: (_ for _ in ()).throw(RuntimeError("step failed")),
                lambda t: {"never": "reached"},
            ],
            tasks_dir=self.tasks_dir,
            source="cli",
            continue_on_error_chain=[False, False, False],
        )

        self.assertEqual(task["status"], "failed")
        self.assertEqual(len(task["step_results"]), 2)  # Third step not reached
        self.assertEqual(task["step_results"][1]["status"], "error")

    def test_pipeline_step_fails_with_continue(self):
        """Step fails with continue_on_error=True -> status=partial, continues."""
        task = run_pipeline_executor(
            task_id="task-test-partial",
            query="test query",
            skill_chain=["decision", "execution", "retrospective"],
            step_fns=[
                lambda t: {"ok": True},
                lambda t: (_ for _ in ()).throw(RuntimeError("step failed")),
                lambda t: {"ok": True},
            ],
            tasks_dir=self.tasks_dir,
            source="cli",
            continue_on_error_chain=[False, True, False],
        )

        self.assertEqual(task["status"], "partial")
        self.assertEqual(len(task["step_results"]), 3)
        self.assertEqual(task["step_results"][1]["status"], "error")
        self.assertEqual(task["step_results"][2]["status"], "ok")

    def test_pipeline_updates_current_step_index(self):
        """current_step_index is updated after each step."""
        task = run_pipeline_executor(
            task_id="task-test-index",
            query="test query",
            skill_chain=["decision", "execution"],
            step_fns=[
                lambda t: {"step": 1},
                lambda t: {"step": 2},
            ],
            tasks_dir=self.tasks_dir,
        )

        # After 2 steps, current_step_index should be 2 (next step would be index 2)
        self.assertEqual(task["execution"]["current_step_index"], 2)

    def test_pipeline_atomic_write(self):
        """Task state is written atomically."""
        task = run_pipeline_executor(
            task_id="task-test-atomic",
            query="test query",
            skill_chain=["research"],
            step_fns=[lambda t: {"found": True}],
            tasks_dir=self.tasks_dir,
        )

        task_path = self.tasks_dir / "task-test-atomic.json"
        self.assertTrue(task_path.exists())

        loaded = json.loads(task_path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["task_id"], "task-test-atomic")
        self.assertEqual(loaded["status"], "completed")


class TestStep91Timestamps(unittest.TestCase):
    """Test timestamp handling."""

    def test_now_iso_format(self):
        ts = _now_iso()
        # Should be parseable as ISO 8601
        parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        self.assertIsNotNone(parsed)

    def test_task_has_valid_timestamps(self):
        task = _init_task_state(
            task_id="task-test",
            query="test",
            selected_skill="research",
            skill_chain=["research"],
        )

        # created_at should be valid ISO
        parsed = datetime.strptime(task["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        self.assertIsNotNone(parsed)


if __name__ == "__main__":
    unittest.main()
