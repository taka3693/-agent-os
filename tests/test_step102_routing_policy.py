#!/usr/bin/env python3
"""Step102: Policy-Driven Routing Refinement Tests

Tests for:
- Low budget → short chain
- High failure history → avoid failed chains
- Partial history → critique/decision reinforcement
- Simple task → no orchestration
- Complex task → orchestration eligible
- Existing tests not broken
"""
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from router.routing_policy import (
    estimate_complexity,
    filter_failed_chains,
    reinforce_for_partials,
    should_orchestrate,
    trim_chain_for_budget,
    apply_routing_policy,
)
from router.result import build_route_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _route(text):
    """Build a standard route result for testing."""
    return build_route_result(text)


# ---------------------------------------------------------------------------
# Tests: Complexity estimation
# ---------------------------------------------------------------------------

class TestStep102Complexity(unittest.TestCase):

    def test_short_text_single_skill_is_simple(self):
        self.assertEqual(estimate_complexity("hello", ["research"]), "simple")

    def test_long_text_is_complex(self):
        long_text = "a" * 301
        self.assertEqual(estimate_complexity(long_text, ["research"]), "complex")

    def test_multi_skill_with_complex_is_complex(self):
        self.assertEqual(
            estimate_complexity("medium text here", ["critique", "decision"]),
            "complex",
        )

    def test_moderate_text(self):
        medium = "a" * 100
        self.assertEqual(estimate_complexity(medium, ["research"]), "moderate")

    def test_three_skills_is_complex(self):
        self.assertEqual(
            estimate_complexity("text", ["research", "critique", "decision"]),
            "complex",
        )


# ---------------------------------------------------------------------------
# Tests: Low budget → short chain
# ---------------------------------------------------------------------------

class TestStep102LowBudgetTrim(unittest.TestCase):
    """低予算 task で短い chain が選ばれる"""

    def test_trim_chain_when_budget_low(self):
        chain = ["research", "critique", "decision"]
        budget = {"max_worker_runs": 5, "spent_worker_runs": 4}
        result = trim_chain_for_budget(chain, budget)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "research")

    def test_keep_chain_when_budget_ok(self):
        chain = ["research", "critique"]
        budget = {"max_worker_runs": 10, "spent_worker_runs": 0}
        result = trim_chain_for_budget(chain, budget)
        self.assertEqual(result, chain)

    def test_apply_policy_trims_for_budget(self):
        route = _route("比較して選定して実行して")
        adjusted = apply_routing_policy(
            route, "比較して選定して実行して",
            task_context={
                "budget": {"max_worker_runs": 3, "spent_worker_runs": 2},
            },
        )
        self.assertLessEqual(len(adjusted["selected_skills"]), 1)


# ---------------------------------------------------------------------------
# Tests: Failed chains avoided
# ---------------------------------------------------------------------------

class TestStep102FailureAvoidance(unittest.TestCase):
    """failed 履歴が多い chain を避ける"""

    def test_filter_removes_high_failure_skill(self):
        chain = ["research", "critique", "decision"]
        failures = {"critique": 5, "decision": 1}
        result = filter_failed_chains(chain, failures, threshold=3)
        self.assertNotIn("critique", result)
        self.assertIn("research", result)
        self.assertIn("decision", result)

    def test_filter_keeps_below_threshold(self):
        chain = ["research", "critique"]
        failures = {"critique": 2}
        result = filter_failed_chains(chain, failures, threshold=3)
        self.assertEqual(result, chain)

    def test_filter_all_failed_falls_back_to_research(self):
        chain = ["critique", "decision"]
        failures = {"critique": 10, "decision": 10}
        result = filter_failed_chains(chain, failures, threshold=3)
        self.assertEqual(result, ["research"])

    def test_apply_policy_with_failure_history(self):
        route = _route("批評してレビューして")
        adjusted = apply_routing_policy(
            route, "批評してレビューして",
            task_context={
                "failure_history": {"critique": 5},
            },
        )
        self.assertNotIn("critique", adjusted["selected_skills"])
        self.assertIn(
            "failure_avoidance",
            adjusted["routing_policy"]["adjustments_applied"],
        )


# ---------------------------------------------------------------------------
# Tests: Partial reinforcement
# ---------------------------------------------------------------------------

class TestStep102PartialReinforcement(unittest.TestCase):
    """partial 履歴で critique / decision が補強される"""

    def test_reinforce_adds_critique(self):
        chain = ["research"]
        result = reinforce_for_partials(chain, partial_runs=3)
        self.assertIn("critique", result)

    def test_reinforce_adds_decision(self):
        chain = ["research"]
        result = reinforce_for_partials(chain, partial_runs=3)
        self.assertIn("decision", result)

    def test_no_reinforce_below_threshold(self):
        chain = ["research"]
        result = reinforce_for_partials(chain, partial_runs=1)
        self.assertEqual(result, ["research"])

    def test_reinforce_respects_max_chain(self):
        chain = ["research", "execution", "experiment"]
        result = reinforce_for_partials(chain, partial_runs=5)
        self.assertLessEqual(len(result), 3)

    def test_reinforce_does_not_duplicate(self):
        chain = ["critique", "decision"]
        result = reinforce_for_partials(chain, partial_runs=5)
        self.assertEqual(result.count("critique"), 1)
        self.assertEqual(result.count("decision"), 1)

    def test_apply_policy_with_partials(self):
        route = _route("調べて")  # research
        adjusted = apply_routing_policy(
            route, "調べて",
            task_context={
                "metrics": {"partial_runs": 3},
            },
        )
        skills = adjusted["selected_skills"]
        self.assertIn("critique", skills)


# ---------------------------------------------------------------------------
# Tests: Simple task → no orchestration
# ---------------------------------------------------------------------------

class TestStep102SimpleNoOrchestration(unittest.TestCase):
    """単純 task で orchestration しない"""

    def test_simple_task_not_orchestrated(self):
        result = should_orchestrate(
            complexity="simple",
            budget={"max_subtasks": 5, "spent_subtasks": 0,
                    "max_worker_runs": 10, "spent_worker_runs": 0},
            metrics={},
        )
        self.assertFalse(result)

    def test_apply_policy_simple_not_eligible(self):
        route = _route("hello")
        adjusted = apply_routing_policy(
            route, "hello",
            task_context={
                "budget": {"max_subtasks": 5, "spent_subtasks": 0,
                           "max_worker_runs": 10, "spent_worker_runs": 0},
                "metrics": {},
            },
        )
        self.assertFalse(adjusted["routing_policy"]["orchestration_eligible"])


# ---------------------------------------------------------------------------
# Tests: Complex task → orchestration eligible
# ---------------------------------------------------------------------------

class TestStep102ComplexOrchestration(unittest.TestCase):
    """高複雑度 task で orchestration 候補になる"""

    def test_complex_with_budget_is_eligible(self):
        result = should_orchestrate(
            complexity="complex",
            budget={"max_subtasks": 5, "spent_subtasks": 0,
                    "max_worker_runs": 10, "spent_worker_runs": 0},
            metrics={},
        )
        self.assertTrue(result)

    def test_complex_no_budget_not_eligible(self):
        result = should_orchestrate(
            complexity="complex",
            budget={"max_subtasks": 2, "spent_subtasks": 2,
                    "max_worker_runs": 10, "spent_worker_runs": 0},
            metrics={},
        )
        self.assertFalse(result)

    def test_complex_high_failures_suppressed(self):
        result = should_orchestrate(
            complexity="complex",
            budget={"max_subtasks": 5, "spent_subtasks": 0,
                    "max_worker_runs": 10, "spent_worker_runs": 0},
            metrics={"failed_steps": 6},
        )
        self.assertFalse(result)

    def test_apply_policy_complex_eligible(self):
        long_text = "比較して選定して " * 50  # > 300 chars
        route = _route(long_text)
        adjusted = apply_routing_policy(
            route, long_text,
            task_context={
                "budget": {"max_subtasks": 5, "spent_subtasks": 0,
                           "max_worker_runs": 10, "spent_worker_runs": 0},
                "metrics": {},
            },
        )
        self.assertTrue(adjusted["routing_policy"]["orchestration_eligible"])


# ---------------------------------------------------------------------------
# Tests: Moderate → no orchestration by default
# ---------------------------------------------------------------------------

class TestStep102ModerateOrchestration(unittest.TestCase):

    def test_moderate_not_orchestrated(self):
        result = should_orchestrate(
            complexity="moderate",
            budget={"max_subtasks": 5, "spent_subtasks": 0,
                    "max_worker_runs": 10, "spent_worker_runs": 0},
            metrics={},
        )
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# Tests: Policy metadata
# ---------------------------------------------------------------------------

class TestStep102PolicyMetadata(unittest.TestCase):

    def test_routing_policy_key_present(self):
        route = _route("調べて")
        adjusted = apply_routing_policy(route, "調べて")
        self.assertIn("routing_policy", adjusted)
        self.assertIn("complexity", adjusted["routing_policy"])
        self.assertIn("orchestration_eligible", adjusted["routing_policy"])

    def test_no_mutation_of_original(self):
        route = _route("調べて")
        original_skills = list(route["selected_skills"])
        _ = apply_routing_policy(
            route, "調べて",
            task_context={"failure_history": {"research": 999}},
        )
        # Original should be unchanged
        self.assertEqual(route["selected_skills"], original_skills)


if __name__ == "__main__":
    unittest.main()
