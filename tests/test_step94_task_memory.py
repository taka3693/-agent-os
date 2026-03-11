#!/usr/bin/env python3
"""Step94: Task Memory Tests

Tests for the memory implementation that manages:
- Structured working memory (summary, decisions, questions, actions)
- Memory size limits
- Memory preservation during recovery/resume
"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.task_memory import (
    _now_iso,
    _init_memory,
    _ensure_memory,
    _truncate_summary,
    _dedupe_and_limit,
    update_memory,
    extract_memory_from_step_result,
    update_memory_from_step,
    preserve_memory_on_recovery,
    get_memory_summary,
    MAX_SUMMARY_LENGTH,
    MAX_DECISIONS,
    MAX_OPEN_QUESTIONS,
    MAX_NEXT_ACTIONS,
)


class TestStep94MemorySchema(unittest.TestCase):
    """Test memory section schema."""

    def test_init_memory_has_all_fields(self):
        memory = _init_memory()

        self.assertIn("summary", memory)
        self.assertIn("decisions", memory)
        self.assertIn("open_questions", memory)
        self.assertIn("next_actions", memory)
        self.assertIn("updated_at", memory)
        self.assertIn("version", memory)

    def test_ensure_memory_adds_missing_fields(self):
        task = {"task_id": "test", "status": "queued"}
        task = _ensure_memory(task)

        self.assertIn("memory", task)
        self.assertEqual(task["memory"]["summary"], "")
        self.assertGreaterEqual(task["memory"]["version"], 1)  # Allow version upgrades

    def test_ensure_memory_preserves_existing(self):
        task = {
            "task_id": "test",
            "memory": {
                "summary": "existing summary",
                "decisions": ["decision 1"],
            },
        }
        task = _ensure_memory(task)

        self.assertEqual(task["memory"]["summary"], "existing summary")
        self.assertEqual(task["memory"]["decisions"], ["decision 1"])


class TestStep94MemoryLimits(unittest.TestCase):
    """Test memory size limits."""

    def test_truncate_summary(self):
        long_summary = "x" * 1000
        truncated = _truncate_summary(long_summary, max_length=100)

        self.assertLessEqual(len(truncated), 100)
        self.assertTrue(truncated.endswith("..."))

    def test_dedupe_and_limit(self):
        items = ["a", "b", "a", "c", "b", "d", "e", "f", "g", "h", "i", "j", "k"]
        result = _dedupe_and_limit(items, max_items=5)

        self.assertEqual(len(result), 5)
        self.assertEqual(result, ["a", "b", "c", "d", "e"])

    def test_empty_items(self):
        result = _dedupe_and_limit([], max_items=5)
        self.assertEqual(result, [])


class TestStep94UpdateMemory(unittest.TestCase):
    """Test memory update functionality."""

    def test_update_summary(self):
        """skill 実行で summary が更新される"""
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(task, summary="Test summary")

        self.assertEqual(task["memory"]["summary"], "Test summary")

    def test_append_summary(self):
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(task, summary="First")
        task = update_memory(task, summary="Second", append=True)

        self.assertIn("First", task["memory"]["summary"])
        self.assertIn("Second", task["memory"]["summary"])

    def test_update_decisions(self):
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(task, decisions=["Decision 1", "Decision 2"])

        self.assertEqual(len(task["memory"]["decisions"]), 2)

    def test_append_decisions(self):
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(task, decisions=["D1"])
        task = update_memory(task, decisions=["D2"], append=True)

        self.assertEqual(task["memory"]["decisions"], ["D1", "D2"])

    def test_decisions_deduped(self):
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(task, decisions=["D1", "D2", "D1", "D3"])

        self.assertEqual(task["memory"]["decisions"], ["D1", "D2", "D3"])

    def test_decisions_limited(self):
        """decisions / open_questions / next_actions が上限内に保たれる"""
        task = _ensure_memory({"task_id": "test"})
        many_decisions = [f"Decision {i}" for i in range(20)]
        task = update_memory(task, decisions=many_decisions)

        self.assertLessEqual(len(task["memory"]["decisions"]), MAX_DECISIONS)

    def test_open_questions_limited(self):
        task = _ensure_memory({"task_id": "test"})
        many_questions = [f"Question {i}" for i in range(20)]
        task = update_memory(task, open_questions=many_questions)

        self.assertLessEqual(len(task["memory"]["open_questions"]), MAX_OPEN_QUESTIONS)

    def test_next_actions_limited(self):
        task = _ensure_memory({"task_id": "test"})
        many_actions = [f"Action {i}" for i in range(20)]
        task = update_memory(task, next_actions=many_actions)

        self.assertLessEqual(len(task["memory"]["next_actions"]), MAX_NEXT_ACTIONS)


class TestStep94ExtractFromStepResult(unittest.TestCase):
    """Test memory extraction from step results."""

    def test_extract_summary(self):
        step_result = {
            "output": {
                "summary": "Task completed successfully",
            },
        }
        memory_update = extract_memory_from_step_result(step_result)

        self.assertEqual(memory_update["summary"], "Task completed successfully")

    def test_extract_decisions(self):
        step_result = {
            "output": {
                "decisions": ["Use approach A", "Skip step 3"],
            },
        }
        memory_update = extract_memory_from_step_result(step_result)

        self.assertEqual(len(memory_update["decisions"]), 2)

    def test_extract_from_nested_result(self):
        step_result = {
            "output": {
                "result": {
                    "summary": "Nested summary",
                    "decisions": ["D1"],
                    "next_actions": ["A1"],
                },
            },
        }
        memory_update = extract_memory_from_step_result(step_result)

        self.assertEqual(memory_update["summary"], "Nested summary")
        self.assertEqual(memory_update["decisions"], ["D1"])
        self.assertEqual(memory_update["next_actions"], ["A1"])

    def test_extract_empty_output(self):
        step_result = {"output": {}}
        memory_update = extract_memory_from_step_result(step_result)

        self.assertEqual(memory_update, {})


class TestStep94UpdateFromStep(unittest.TestCase):
    """Test memory update from step execution."""

    def test_update_from_step(self):
        """task 実行後に memory が生成される"""
        task = _ensure_memory({"task_id": "test"})
        step_result = {
            "output": {
                "summary": "Step completed",
                "decisions": ["Decision made"],
            },
        }
        task = update_memory_from_step(task, step_result)

        self.assertEqual(task["memory"]["summary"], "Step completed")
        self.assertEqual(task["memory"]["decisions"], ["Decision made"])

    def test_update_from_step_appends(self):
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(task, decisions=["D1"])

        step_result = {"output": {"decisions": ["D2"]}}
        task = update_memory_from_step(task, step_result)

        self.assertEqual(task["memory"]["decisions"], ["D1", "D2"])


class TestStep94PreserveOnRecovery(unittest.TestCase):
    """Test memory preservation during recovery."""

    def test_memory_preserved_on_recovery(self):
        """recovery / resume で memory が保持される"""
        task = _ensure_memory({
            "task_id": "test",
            "status": "running",
        })
        task = update_memory(task, summary="Work in progress", decisions=["D1"])

        # Simulate recovery
        task = preserve_memory_on_recovery(task)

        # Memory should be preserved
        self.assertIn("Work in progress", task["memory"]["summary"])
        self.assertEqual(task["memory"]["decisions"], ["D1"])
        self.assertIn("Recovered", task["memory"]["summary"])


class TestStep94MemorySummary(unittest.TestCase):
    """Test memory summary formatting."""

    def test_empty_memory_summary(self):
        task = {"task_id": "test"}
        summary = get_memory_summary(task)

        self.assertEqual(summary, "メモリなし")

    def test_full_memory_summary(self):
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(
            task,
            summary="Task summary",
            decisions=["Decision 1", "Decision 2"],
            open_questions=["Question 1"],
            next_actions=["Action 1", "Action 2", "Action 3"],
        )
        summary = get_memory_summary(task)

        self.assertIn("要約:", summary)
        self.assertIn("決定事項", summary)
        self.assertIn("未解決", summary)
        self.assertIn("次のアクション", summary)


if __name__ == "__main__":
    unittest.main()
