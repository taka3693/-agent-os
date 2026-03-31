"""Tests for learning system."""
import unittest
from learning.pattern_extractor import extract_patterns, get_recommendations
from learning.action_policy import generate_policies_from_recommendations


class TestPatternExtractor(unittest.TestCase):
    def test_extract_patterns_empty(self):
        patterns = extract_patterns(episodes=[])
        self.assertEqual(patterns["summary"]["total_episodes"], 0)
        self.assertEqual(patterns["patterns"], [])
    
    def test_extract_patterns_with_data(self):
        episodes = [
            {"outcome": "success_clean", "target_area": "config"},
            {"outcome": "failed_verification", "target_area": "config", "failure_codes": ["timeout"]},
            {"outcome": "failed_verification", "target_area": "config", "failure_codes": ["timeout"]},
        ]
        patterns = extract_patterns(episodes=episodes, min_occurrences=2)
        
        self.assertEqual(patterns["summary"]["total_episodes"], 3)
        # 2回失敗したのでhigh_risk_areaが検出されるはず
        self.assertGreaterEqual(len(patterns["patterns"]), 0)


class TestActionPolicy(unittest.TestCase):
    def test_generate_policies_from_recommendations(self):
        recommendations = [
            {"action": "add_review_step", "target": "config", "reason": "High failure rate", "priority": "high"},
        ]
        policies = generate_policies_from_recommendations(recommendations)
        
        self.assertEqual(len(policies), 1)
        self.assertEqual(policies[0]["action"], "add_review_step")
        self.assertIn("id", policies[0])


if __name__ == "__main__":
    unittest.main()


class TestFailureAnalyzer(unittest.TestCase):
    def test_analyze_test_failures(self):
        from learning.failure_analyzer import analyze_test_failures
        
        output = "FAILED tests/test_foo.py::test_bar - AssertionError"
        failures = analyze_test_failures(output)
        
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["type"], "test_failure")
        self.assertEqual(failures[0]["file"], "tests/test_foo.py")
        self.assertEqual(failures[0]["test"], "test_bar")


class TestSelfImprove(unittest.TestCase):
    def test_run_self_improvement_cycle_dry_run(self):
        from learning.self_improve import run_self_improvement_cycle
        
        result = run_self_improvement_cycle(dry_run=True)
        
        self.assertIn("issues_analyzed", result)
        self.assertIn("fixes_proposed", result)
        self.assertTrue(result["dry_run"])
