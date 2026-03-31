"""Tests for goal management system."""
import unittest
import tempfile
from pathlib import Path

from ops.goal_store import create_goal, load_goals, update_progress, GOALS_FILE
from ops.goal_decomposer import suggest_decomposition
from ops.progress_tracker import generate_progress_report


class TestGoalStore(unittest.TestCase):
    def test_suggest_decomposition_agi(self):
        goal = {"title": "AGI開発", "description": "自律システム"}
        suggestions = suggest_decomposition(goal)
        
        self.assertEqual(len(suggestions), 4)
        self.assertIn("Phase 1", suggestions[0]["title"])


class TestProgressTracker(unittest.TestCase):
    def test_generate_report(self):
        report = generate_progress_report()
        
        self.assertIn("summary", report)
        self.assertIn("total_goals", report["summary"])


if __name__ == "__main__":
    unittest.main()
