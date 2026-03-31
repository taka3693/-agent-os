"""Tests for meta-cognition system."""
import unittest

from ops.capability_model import get_capabilities, can_handle, assess_task_complexity
from ops.self_assessor import assess_task, infer_task_type, should_ask_for_help
from ops.limitation_detector import detect_limitation, handle_limitation


class TestCapabilityModel(unittest.TestCase):
    def test_get_capabilities(self):
        caps = get_capabilities()
        self.assertIn("research", caps)
        self.assertIn("coding", caps)
    
    def test_can_handle_known(self):
        result = can_handle("research")
        self.assertTrue(result["can_handle"])
        self.assertGreater(result["confidence"], 0.5)
    
    def test_can_handle_unknown(self):
        result = can_handle("teleportation")
        self.assertFalse(result["can_handle"])


class TestSelfAssessor(unittest.TestCase):
    def test_infer_task_type(self):
        self.assertEqual(infer_task_type({"query": "調べてください"}), "research")
        self.assertEqual(infer_task_type({"query": "コードを修正"}), "coding")
    
    def test_assess_task(self):
        result = assess_task({"query": "簡単な調査"})
        self.assertTrue(result["can_proceed"])
        self.assertIn("task_type", result)


class TestLimitationDetector(unittest.TestCase):
    def test_detect_timeout(self):
        result = detect_limitation("Operation timed out")
        self.assertIsNotNone(result)
        self.assertEqual(result["pattern"], "timeout")
    
    def test_detect_auth(self):
        result = detect_limitation("401 Unauthorized")
        self.assertIsNotNone(result)
        self.assertEqual(result["pattern"], "auth_failure")
    
    def test_handle_limitation(self):
        result = handle_limitation("timeout occurred")
        self.assertTrue(result["limitation_detected"])
        self.assertEqual(result["response"]["action"], "retry")


if __name__ == "__main__":
    unittest.main()
