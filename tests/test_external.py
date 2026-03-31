"""Tests for external environment system."""
import unittest

from ops.github_observer import run_gh_command
from ops.environment_monitor import get_system_resources, analyze_environment
from ops.event_reactor import prioritize_events, get_reaction


class TestEnvironmentMonitor(unittest.TestCase):
    def test_get_system_resources(self):
        res = get_system_resources()
        self.assertIn("cpu", res)
        self.assertIn("memory", res)
        self.assertIn("disk", res)
    
    def test_analyze_environment(self):
        env = analyze_environment()
        self.assertIn("resources", env)
        self.assertIn("healthy", env)


class TestEventReactor(unittest.TestCase):
    def test_prioritize_events(self):
        events = [
            {"type": "stale_pr"},
            {"type": "ci_failure"},
            {"type": "high_memory"},
        ]
        sorted_events = prioritize_events(events)
        # ci_failure should be first (high priority)
        self.assertEqual(sorted_events[0]["type"], "ci_failure")
    
    def test_get_reaction(self):
        event = {"type": "ci_failure"}
        reaction = get_reaction(event)
        self.assertEqual(reaction["action"], "investigate")


if __name__ == "__main__":
    unittest.main()
