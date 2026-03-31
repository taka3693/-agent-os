"""Tests for proactive task generation system."""
import json
import tempfile
import unittest
from pathlib import Path

from ops.proactive_observer import ProactiveObserver, observe_system
from ops.proactive_generator import ProactiveTaskGenerator, generate_proactive_tasks
from ops.proactive_runner import run_proactive_cycle


class TestProactiveObserver(unittest.TestCase):
    def test_observe_empty_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_root = Path(tmpdir) / "state"
            tasks_root = Path(tmpdir) / "tasks"
            state_root.mkdir()
            tasks_root.mkdir()
            
            result = observe_system(state_root, tasks_root)
            
            self.assertIn("observed_at", result)
            self.assertIn("health", result)
            self.assertIn("failures", result)
            self.assertIn("idle", result)
    
    def test_observe_detects_idle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_root = Path(tmpdir) / "state"
            tasks_root = Path(tmpdir) / "tasks"
            state_root.mkdir()
            tasks_root.mkdir()
            (tasks_root / "pending").mkdir()
            (tasks_root / "running").mkdir()
            
            result = observe_system(state_root, tasks_root)
            
            self.assertTrue(result["idle"]["is_idle"])


class TestProactiveGenerator(unittest.TestCase):
    def test_generate_from_idle(self):
        observations = {
            "health": {"status": "healthy", "issues": []},
            "failures": {"patterns": [], "count": 0},
            "learning": {"insights": []},
            "idle": {"is_idle": True},
        }
        
        tasks = generate_proactive_tasks(observations)
        
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["type"], "exploration")
        self.assertEqual(tasks[0]["skill"], "research")
    
    def test_generate_from_health_issues(self):
        observations = {
            "health": {
                "status": "degraded",
                "issues": [{"type": "high_failure_rate", "detail": "5 failed"}],
            },
            "failures": {"patterns": []},
            "learning": {"insights": []},
            "idle": {"is_idle": False},
        }
        
        tasks = generate_proactive_tasks(observations)
        
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["type"], "maintenance")
        self.assertEqual(tasks[0]["priority"], "high")


class TestProactiveRunner(unittest.TestCase):
    def test_dry_run_cycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_root = Path(tmpdir) / "state"
            tasks_root = Path(tmpdir) / "tasks"
            state_root.mkdir()
            tasks_root.mkdir()
            (tasks_root / "pending").mkdir()
            (tasks_root / "running").mkdir()
            
            result = run_proactive_cycle(state_root, tasks_root, dry_run=True)
            
            self.assertIn("cycle_id", result)
            self.assertTrue(result["dry_run"])
            self.assertGreaterEqual(result["generated_tasks"], 0)


if __name__ == "__main__":
    unittest.main()
