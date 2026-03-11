#!/usr/bin/env python3
"""Step103: Cost-Aware Execution Policy Tests"""
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.execution_policy import (
    POLICY_CHEAP, POLICY_BALANCED, POLICY_THOROUGH,
    get_policy_defaults,
    select_policy_tier,
    build_execution_policy,
    apply_execution_policy,
)
from router.result import build_route_result


def _route(text):
    return build_route_result(text)


def _healthy_budget():
    return {"max_subtasks": 5, "spent_subtasks": 0,
            "max_worker_runs": 10, "spent_worker_runs": 0}


def _low_budget():
    return {"max_subtasks": 5, "spent_subtasks": 0,
            "max_worker_runs": 4, "spent_worker_runs": 3}


# ---------------------------------------------------------------------------
# Policy defaults
# ---------------------------------------------------------------------------

class TestStep103PolicyDefaults(unittest.TestCase):

    def test_cheap_disallows_orchestration(self):
        p = get_policy_defaults(POLICY_CHEAP)
        self.assertFalse(p["allow_orchestration"])

    def test_cheap_disallows_parallel(self):
        p = get_policy_defaults(POLICY_CHEAP)
        self.assertFalse(p["allow_parallel"])

    def test_cheap_max_chain_1(self):
        p = get_policy_defaults(POLICY_CHEAP)
        self.assertEqual(p["max_chain_override"], 1)

    def test_cheap_fail_fast(self):
        p = get_policy_defaults(POLICY_CHEAP)
        self.assertTrue(p["fail_fast"])

    def test_balanced_allows_parallel(self):
        p = get_policy_defaults(POLICY_BALANCED)
        self.assertTrue(p["allow_parallel"])

    def test_balanced_no_orchestration(self):
        p = get_policy_defaults(POLICY_BALANCED)
        self.assertFalse(p["allow_orchestration"])

    def test_thorough_allows_orchestration(self):
        p = get_policy_defaults(POLICY_THOROUGH)
        self.assertTrue(p["allow_orchestration"])

    def test_thorough_continue_on_error(self):
        p = get_policy_defaults(POLICY_THOROUGH)
        self.assertTrue(p["continue_on_error"])

    def test_unknown_tier_falls_back_to_balanced(self):
        p = get_policy_defaults("nonexistent")
        self.assertEqual(p["max_chain_override"], 2)


# ---------------------------------------------------------------------------
# Tier selection
# ---------------------------------------------------------------------------

class TestStep103TierSelection(unittest.TestCase):

    def test_low_budget_selects_cheap(self):
        tier = select_policy_tier("moderate", budget=_low_budget())
        self.assertEqual(tier, POLICY_CHEAP)

    def test_budget_limit_hits_selects_cheap(self):
        tier = select_policy_tier(
            "moderate",
            budget=_healthy_budget(),
            metrics={"budget_limit_hits": 2},
        )
        self.assertEqual(tier, POLICY_CHEAP)

    def test_high_failure_history_selects_cheap(self):
        tier = select_policy_tier(
            "moderate",
            budget=_healthy_budget(),
            failure_history={"critique": 3, "decision": 2},
        )
        self.assertEqual(tier, POLICY_CHEAP)

    def test_high_failed_steps_selects_cheap(self):
        tier = select_policy_tier(
            "moderate",
            budget=_healthy_budget(),
            metrics={"failed_steps": 6},
        )
        self.assertEqual(tier, POLICY_CHEAP)

    def test_complex_healthy_selects_thorough(self):
        tier = select_policy_tier("complex", budget=_healthy_budget())
        self.assertEqual(tier, POLICY_THOROUGH)

    def test_complex_insufficient_budget_not_thorough(self):
        tier = select_policy_tier(
            "complex",
            budget={"max_subtasks": 5, "spent_subtasks": 3,
                    "max_worker_runs": 10, "spent_worker_runs": 8},
        )
        self.assertNotEqual(tier, POLICY_THOROUGH)

    def test_simple_healthy_selects_balanced(self):
        tier = select_policy_tier("simple", budget=_healthy_budget())
        self.assertEqual(tier, POLICY_BALANCED)

    def test_moderate_healthy_selects_balanced(self):
        tier = select_policy_tier("moderate", budget=_healthy_budget())
        self.assertEqual(tier, POLICY_BALANCED)


# ---------------------------------------------------------------------------
# Policy building
# ---------------------------------------------------------------------------

class TestStep103BuildPolicy(unittest.TestCase):

    def test_policy_has_tier(self):
        p = build_execution_policy(POLICY_CHEAP, "simple")
        self.assertEqual(p["tier"], POLICY_CHEAP)

    def test_policy_has_complexity(self):
        p = build_execution_policy(POLICY_BALANCED, "moderate")
        self.assertEqual(p["complexity"], "moderate")

    def test_thorough_with_partials_enables_critique_boost(self):
        p = build_execution_policy(POLICY_THOROUGH, "complex", partial_runs=3)
        self.assertTrue(p["critique_boost"])
        self.assertTrue(p["decision_boost"])

    def test_thorough_without_partials_no_boost(self):
        p = build_execution_policy(POLICY_THOROUGH, "complex", partial_runs=0)
        self.assertFalse(p["critique_boost"])

    def test_cheap_no_boost_even_with_partials(self):
        p = build_execution_policy(POLICY_CHEAP, "complex", partial_runs=5)
        self.assertFalse(p["critique_boost"])

    def test_simple_complexity_suppresses_orchestration(self):
        p = build_execution_policy(POLICY_THOROUGH, "simple")
        self.assertFalse(p["allow_orchestration"])
        self.assertFalse(p["allow_parallel"])


# ---------------------------------------------------------------------------
# apply_execution_policy
# ---------------------------------------------------------------------------

class TestStep103ApplyPolicy(unittest.TestCase):

    def test_execution_policy_key_present(self):
        route = _route("調べて")
        result = apply_execution_policy(route, "調べて")
        self.assertIn("execution_policy", result)

    def test_cheap_trims_chain_to_1(self):
        route = _route("批評してレビューして実行して")
        result = apply_execution_policy(
            route, "批評してレビューして実行して",
            task_context={"budget": _low_budget(), "complexity": "moderate"},
        )
        self.assertEqual(len(result["selected_skills"]), 1)
        self.assertEqual(result["execution_policy"]["tier"], POLICY_CHEAP)

    def test_balanced_keeps_chain_up_to_2(self):
        route = _route("比較して整理して")
        # Inject a chain of length >=2 to test balanced cap
        route = dict(route)
        route["selected_skills"] = ["decision", "critique", "research"]
        result = apply_execution_policy(
            route, "比較して整理して",
            task_context={"budget": _healthy_budget(), "complexity": "moderate"},
        )
        self.assertLessEqual(len(result["selected_skills"]), 2)
        self.assertEqual(result["execution_policy"]["tier"], POLICY_BALANCED)

    def test_thorough_no_chain_trim(self):
        route = _route("比較して選定して実装して " * 50)
        long_text = "比較して選定して実装して " * 50
        result = apply_execution_policy(
            route, long_text,
            task_context={"budget": _healthy_budget(), "complexity": "complex"},
        )
        self.assertEqual(result["execution_policy"]["tier"], POLICY_THOROUGH)
        # max_chain_override is None → no trim
        self.assertIsNone(result["execution_policy"]["max_chain_override"])

    def test_cheap_no_orchestration(self):
        route = _route("調べて")
        result = apply_execution_policy(
            route, "調べて",
            task_context={"budget": _low_budget()},
        )
        self.assertFalse(result["execution_policy"]["allow_orchestration"])

    def test_thorough_allows_orchestration(self):
        long_text = "複雑な比較と選定と批評と実行と " * 30
        route = _route(long_text)
        result = apply_execution_policy(
            route, long_text,
            task_context={"budget": _healthy_budget(), "complexity": "complex"},
        )
        self.assertTrue(result["execution_policy"]["allow_orchestration"])

    def test_high_failure_suppresses_thorough(self):
        long_text = "複雑な比較と選定と " * 30
        route = _route(long_text)
        result = apply_execution_policy(
            route, long_text,
            task_context={
                "budget": _healthy_budget(),
                "complexity": "complex",
                "failure_history": {"critique": 3, "decision": 3},
            },
        )
        self.assertEqual(result["execution_policy"]["tier"], POLICY_CHEAP)

    def test_complexity_from_routing_policy(self):
        route = _route("調べて")
        route["routing_policy"] = {"complexity": "complex"}
        result = apply_execution_policy(
            route, "調べて",
            task_context={"budget": _healthy_budget()},
        )
        self.assertEqual(result["execution_policy"]["complexity"], "complex")

    def test_original_not_mutated(self):
        route = _route("調べて")
        original_skills = list(route["selected_skills"])
        apply_execution_policy(
            route, "調べて",
            task_context={"budget": _low_budget()},
        )
        self.assertEqual(route["selected_skills"], original_skills)

    def test_pipeline_updated_on_trim(self):
        route = _route("比較して選定して")
        route = dict(route)
        route["selected_skills"] = ["decision", "critique"]
        result = apply_execution_policy(
            route, "比較して選定して",
            task_context={"budget": _low_budget(), "complexity": "moderate"},
        )
        pipeline_chain = result["pipeline"]["skill_chain"]
        self.assertEqual(len(pipeline_chain), 1)

    def test_thorough_critique_boost_with_partials(self):
        long_text = "複雑な比較と選定と " * 30
        route = _route(long_text)
        result = apply_execution_policy(
            route, long_text,
            task_context={
                "budget": _healthy_budget(),
                "complexity": "complex",
                "metrics": {"partial_runs": 3},
            },
        )
        self.assertTrue(result["execution_policy"].get("critique_boost"))


if __name__ == "__main__":
    unittest.main()
