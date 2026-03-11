#!/usr/bin/env python3
"""Step95: Memory Compaction and Retrieval Policy Tests

Tests for memory compaction and retrieval policies:
- Compaction removes solved questions and completed actions
- Conflicting decisions are merged
- Retrieval policies are fixed per skill
- Memory is preserved during recovery/resume
"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.task_memory import (
    _ensure_memory,
    update_memory,
    compact_memory,
    compact_memory_on_resume,
    get_retrieval_policy,
    retrieve_memory_for_skill,
    mark_question_solved,
    mark_action_completed,
    solve_question,
    complete_action,
    preserve_memory_on_recovery,
    RETRIEVAL_POLICY,
)


class TestStep95RetrievalPolicy(unittest.TestCase):
    """Test retrieval policy for each skill."""

    def test_decision_policy(self):
        """skill ごとの retrieval policy が固定される"""
        policy = get_retrieval_policy("decision")
        self.assertEqual(policy, ["summary", "decisions", "open_questions"])

    def test_critique_policy(self):
        policy = get_retrieval_policy("critique")
        self.assertEqual(policy, ["summary", "open_questions", "next_actions"])

    def test_execution_policy(self):
        policy = get_retrieval_policy("execution")
        self.assertEqual(policy, ["summary", "decisions", "next_actions"])

    def test_retrospective_policy(self):
        policy = get_retrieval_policy("retrospective")
        self.assertEqual(policy, ["summary", "decisions", "open_questions", "next_actions"])

    def test_unknown_skill_defaults_to_summary(self):
        policy = get_retrieval_policy("unknown_skill")
        self.assertEqual(policy, ["summary"])

    def test_retrieve_for_decision(self):
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(
            task,
            summary="Test summary",
            decisions=["D1", "D2"],
            open_questions=["Q1"],
            next_actions=["A1"],
        )

        memory = retrieve_memory_for_skill(task, "decision")

        self.assertIn("summary", memory)
        self.assertIn("decisions", memory)
        self.assertIn("open_questions", memory)
        self.assertNotIn("next_actions", memory)


class TestStep95MarkSolvedCompleted(unittest.TestCase):
    """Test marking questions and actions."""

    def test_mark_question_solved(self):
        question = "How to implement X?"
        solved = mark_question_solved(question)

        self.assertTrue(solved.startswith("[SOLVED]"))
        self.assertIn(question, solved)

    def test_already_solved_unchanged(self):
        question = "[SOLVED] Already done"
        solved = mark_question_solved(question)

        self.assertEqual(solved, question)

    def test_mark_action_completed(self):
        action = "Implement feature Y"
        completed = mark_action_completed(action)

        self.assertTrue(completed.startswith("[DONE]"))
        self.assertIn(action, completed)

    def test_already_completed_unchanged(self):
        action = "[DONE] Already done"
        completed = mark_action_completed(action)

        self.assertEqual(completed, action)


class TestStep95Compaction(unittest.TestCase):
    """Test memory compaction."""

    def test_solved_questions_removed(self):
        """solved open_questions が compaction で消える"""
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(
            task,
            open_questions=["Q1", "[SOLVED] Q2", "Q3"],
        )

        task = compact_memory(task)

        questions = task["memory"]["open_questions"]
        self.assertEqual(len(questions), 2)
        self.assertIn("Q1", questions)
        self.assertIn("Q3", questions)
        self.assertNotIn("[SOLVED] Q2", questions)

    def test_completed_actions_removed(self):
        """completed next_actions が compaction で消える"""
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(
            task,
            next_actions=["A1", "[DONE] A2", "A3"],
        )

        task = compact_memory(task)

        actions = task["memory"]["next_actions"]
        self.assertEqual(len(actions), 2)
        self.assertIn("A1", actions)
        self.assertIn("A3", actions)
        self.assertNotIn("[DONE] A2", actions)

    def test_duplicate_decisions_merged(self):
        """conflicting / duplicate decisions が統合される"""
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(
            task,
            decisions=["Use approach A", "Use approach A", "Use approach B"],
        )

        task = compact_memory(task)

        decisions = task["memory"]["decisions"]
        # Duplicates removed
        self.assertEqual(len(decisions), 2)

    def test_compaction_updates_metadata(self):
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(task, summary="Test")

        task = compact_memory(task)

        self.assertIsNotNone(task["memory"]["compacted_at"])
        self.assertEqual(task["memory"]["compaction_count"], 1)

    def test_compaction_on_resume(self):
        """recovery / resume 時に stale memory が整理される"""
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(
            task,
            summary="Test",
            open_questions=["Q1", "[SOLVED] Q2"],
            next_actions=["A1", "[DONE] A2"],
        )

        task = compact_memory_on_resume(task)

        # Stale items removed
        self.assertEqual(len(task["memory"]["open_questions"]), 1)
        self.assertEqual(len(task["memory"]["next_actions"]), 1)
        self.assertIsNotNone(task["memory"]["compacted_at"])


class TestStep95SolveQuestion(unittest.TestCase):
    """Test solving specific questions."""

    def test_solve_question_by_index(self):
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(
            task,
            open_questions=["Q1", "Q2", "Q3"],
        )

        task = solve_question(task, 1)  # Mark Q2 as solved

        questions = task["memory"]["open_questions"]
        self.assertTrue(questions[1].startswith("[SOLVED]"))

    def test_invalid_index_unchanged(self):
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(
            task,
            open_questions=["Q1"],
        )

        original = list(task["memory"]["open_questions"])
        task = solve_question(task, 99)  # Invalid index

        self.assertEqual(task["memory"]["open_questions"], original)


class TestStep95CompleteAction(unittest.TestCase):
    """Test completing specific actions."""

    def test_complete_action_by_index(self):
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(
            task,
            next_actions=["A1", "A2", "A3"],
        )

        task = complete_action(task, 0)  # Mark A1 as completed

        actions = task["memory"]["next_actions"]
        self.assertTrue(actions[0].startswith("[DONE]"))


class TestStep95PreserveOnRecovery(unittest.TestCase):
    """Test memory preservation during recovery."""

    def test_memory_preserved_and_compacted(self):
        """recovery / resume で memory が保持される"""
        task = _ensure_memory({"task_id": "test"})
        task = update_memory(
            task,
            summary="Work in progress",
            decisions=["D1"],
            open_questions=["Q1", "[SOLVED] Q2"],
            next_actions=["A1"],
        )

        task = preserve_memory_on_recovery(task)

        # Memory preserved
        self.assertIn("D1", task["memory"]["decisions"])
        self.assertIn("Q1", task["memory"]["open_questions"])
        self.assertIn("A1", task["memory"]["next_actions"])

        # Stale items removed by compaction
        self.assertNotIn("[SOLVED] Q2", task["memory"]["open_questions"])

        # Recovery note added
        self.assertIn("Recovered", task["memory"]["summary"])


if __name__ == "__main__":
    unittest.main()
