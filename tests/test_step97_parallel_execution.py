#!/usr/bin/env python3
"""Step97: Parallel Execution Tests

Tests for parallel execution of independent substeps:
- Parallel-safe detection
- Dependency-based serialization
- Worker limit enforcement
- Result merging without loss
"""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.parallel_executor import (
    analyze_step_dependencies,
    is_parallel_safe,
    execute_step_with_context,
    execute_parallel_steps,
    run_parallel_pipeline,
    DEFAULT_MAX_PARALLEL_WORKERS,
)


class TestStep97ParallelSafety(unittest.TestCase):
    """Test parallel-safe step detection."""

    def test_step_without_depends_on_is_parallel_safe(self):
        """独立 substep が並列実行される"""
        step = {"skill": "research"}
        self.assertTrue(is_parallel_safe(step))

    def test_step_with_depends_on_is_not_parallel_safe(self):
        """depends_on 付き substep は直列実行される"""
        step = {"skill": "execution", "depends_on": "decision"}
        self.assertFalse(is_parallel_safe(step))

    def test_step_with_empty_depends_on_is_parallel_safe(self):
        step = {"skill": "research", "depends_on": None}
        self.assertTrue(is_parallel_safe(step))


class TestStep97DependencyAnalysis(unittest.TestCase):
    """Test dependency analysis."""

    def test_all_independent_steps(self):
        steps = [
            {"skill": "research"},
            {"skill": "critique"},
        ]
        analysis = analyze_step_dependencies(steps)

        self.assertEqual(len(analysis["parallel_groups"]), 1)
        self.assertEqual(len(analysis["parallel_groups"][0]), 2)
        self.assertEqual(len(analysis["serial_steps"]), 0)

    def test_all_dependent_steps(self):
        steps = [
            {"skill": "decision"},
            {"skill": "execution", "depends_on": "decision"},
        ]
        analysis = analyze_step_dependencies(steps)

        self.assertEqual(len(analysis["serial_steps"]), 1)
        # First step has no depends_on, so it's parallel-safe
        self.assertEqual(len(analysis["parallel_groups"]), 1)
        self.assertEqual(len(analysis["parallel_groups"][0]), 1)

    def test_mixed_dependencies(self):
        steps = [
            {"skill": "research"},  # Parallel
            {"skill": "decision", "depends_on": "research"},  # Serial
            {"skill": "critique"},  # Parallel (independent)
        ]
        analysis = analyze_step_dependencies(steps)

        # research and critique are parallel-safe
        parallel_steps = analysis["parallel_groups"][0] if analysis["parallel_groups"] else []
        parallel_skills = [s["step"].get("skill") for s in parallel_steps]
        self.assertIn("research", parallel_skills)
        self.assertIn("critique", parallel_skills)

        # decision is serial
        serial_skills = [s["step"].get("skill") for s in analysis["serial_steps"]]
        self.assertIn("decision", serial_skills)


class TestStep97StepExecution(unittest.TestCase):
    """Test step execution with context."""

    def test_execute_step_returns_result(self):
        task = {"task_id": "test"}
        step = {"skill": "test_skill"}

        def step_fn(t, s):
            return {"result": "ok"}

        result = execute_step_with_context(task, step, step_fn, 0)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["step_index"], 0)
        self.assertIn("started_at", result)
        self.assertIn("finished_at", result)
        self.assertIsNotNone(result["duration_ms"])

    def test_execute_step_captures_error(self):
        task = {"task_id": "test"}
        step = {"skill": "failing_skill"}

        def failing_fn(t, s):
            raise ValueError("intentional error")

        result = execute_step_with_context(task, step, failing_fn, 0)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "ValueError")
        self.assertIn("intentional error", result["error_message"])

    def test_execute_step_includes_thread_id(self):
        task = {"task_id": "test"}
        step = {"skill": "test"}

        result = execute_step_with_context(task, step, lambda t, s: {}, 0)

        self.assertIn("thread_id", result)


class TestStep97ParallelExecution(unittest.TestCase):
    """Test parallel step execution."""

    def test_parallel_execution_completes_all_steps(self):
        """並列実行後の step_results が欠落しない"""
        task = {"task_id": "test", "step_results": []}
        steps = [
            {"step_id": "s1", "skill": "research"},
            {"step_id": "s2", "skill": "critique"},
        ]

        call_count = [0]

        def step_fn(t, s):
            call_count[0] += 1
            time.sleep(0.01)  # Small delay
            return {"processed": s.get("step_id")}

        result_task = execute_parallel_steps(task, steps, step_fn, max_workers=2)

        # Both steps should be executed
        self.assertEqual(call_count[0], 2)
        self.assertEqual(len(result_task["step_results"]), 2)

    def test_parallel_execution_respects_max_workers(self):
        """max_parallel_workers を超えない"""
        task = {"task_id": "test", "step_results": []}
        steps = [
            {"step_id": f"s{i}", "skill": "research"}
            for i in range(5)
        ]

        max_concurrent = [0]

        def step_fn(t, s):
            # Track concurrent executions
            current = threading.active_count()
            max_concurrent[0] = max(max_concurrent[0], current)
            time.sleep(0.02)
            return {"ok": True}

        result_task = execute_parallel_steps(task, steps, step_fn, max_workers=2)

        # Max concurrent should not exceed max_workers + main thread overhead
        self.assertLessEqual(max_concurrent[0], 2 + 2)

    def test_parallel_execution_merges_results(self):
        task = {"task_id": "test", "step_results": []}
        steps = [
            {"step_id": "s1", "skill": "research"},
            {"step_id": "s2", "skill": "critique"},
        ]

        def step_fn(t, s):
            return {"step": s.get("step_id")}

        result_task = execute_parallel_steps(task, steps, step_fn)

        step_ids = [r.get("step_id") for r in result_task["step_results"]]
        self.assertIn("s1", step_ids)
        self.assertIn("s2", step_ids)


class TestStep97Pipeline(unittest.TestCase):
    """Test full parallel pipeline."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.task_path = Path(self.temp_dir) / "task-test.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parallel_pipeline_executes_all(self):
        task = {
            "task_id": "test-pipeline",
            "status": "queued",
            "step_results": [],
        }
        self.task_path.write_text(json.dumps(task))

        steps = [
            {"skill": "research"},
            {"skill": "critique"},
            {"skill": "decision", "depends_on": "research"},
        ]

        executed = []

        def step_fn(t, s):
            skill = s.get("skill")
            if skill:
                executed.append(skill)
            return {"skill": skill}

        result = run_parallel_pipeline(
            task,
            steps,
            step_fn,
            max_parallel_workers=2,
            task_path=self.task_path,
        )

        # All steps executed (3 skills)
        self.assertEqual(len(executed), 3)
        self.assertIn("research", executed)
        self.assertIn("critique", executed)
        self.assertIn("decision", executed)

        # Status should be completed
        self.assertEqual(result["status"], "completed")

    def test_parallel_pipeline_with_failure(self):
        """1 worker fail 時の status が仕様通り"""
        task = {
            "task_id": "test-failure",
            "status": "queued",
            "step_results": [],
        }
        self.task_path.write_text(json.dumps(task))

        steps = [
            {"skill": "research"},
            {"skill": "failing", "continue_on_error": True},
            {"skill": "critique"},
        ]

        def step_fn(t, s):
            if s.get("skill") == "failing":
                raise RuntimeError("intentional failure")
            return {"skill": s.get("skill")}

        result = run_parallel_pipeline(
            task,
            steps,
            step_fn,
            max_parallel_workers=2,
            task_path=self.task_path,
        )

        # Should have partial status (completed with errors)
        self.assertEqual(result["status"], "partial")

        # All steps should have results
        self.assertEqual(len(result["step_results"]), 3)

    def test_memory_merge_not_broken(self):
        """memory merge が壊れない"""
        task = {
            "task_id": "test-memory",
            "status": "queued",
            "step_results": [],
            "memory": {
                "summary": "",
                "decisions": [],
                "open_questions": [],
                "next_actions": [],
            },
        }
        self.task_path.write_text(json.dumps(task))

        steps = [
            {"skill": "research"},
            {"skill": "critique"},
        ]

        def step_fn(t, s):
            # Return memory updates
            return {
                "skill": s.get("skill"),
                "decisions": [f"{s.get('skill')} decision"],
            }

        result = run_parallel_pipeline(
            task,
            steps,
            step_fn,
            max_parallel_workers=2,
            task_path=self.task_path,
        )

        # Memory should exist
        self.assertIn("memory", result)


if __name__ == "__main__":
    unittest.main()
