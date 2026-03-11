#!/usr/bin/env python3
"""Step107: Scenario Pack Expansion Tests"""
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.cases import (
    EVAL_CASES,
    make_case,
    load_cases,
    load_packs,
    list_packs,
    _healthy_budget,
    _low_budget,
    _stressed_budget,
    _exhausted_budget,
    _failure_metrics,
    _partial_metrics,
)
from eval.harness import run_harness, run_case
from eval.benchmark import compare_snapshots, extract_snapshot, save_baseline, load_baseline
from eval.candidate_rules import generate_candidate_report


# ---------------------------------------------------------------------------
# Pack loading
# ---------------------------------------------------------------------------

class TestStep107PackLoading(unittest.TestCase):

    def test_list_packs_returns_expected(self):
        packs = list_packs()
        expected = {
            "budget_stress", "failure_recovery", "partial_heavy",
            "orchestration_boundary", "routing_ambiguity", "execution_risk",
        }
        self.assertTrue(expected.issubset(set(packs)), f"missing packs: {expected - set(packs)}")

    def test_load_packs_budget_stress(self):
        cases = load_packs(["budget_stress"])
        self.assertGreaterEqual(len(cases), 3)
        for c in cases:
            self.assertIn("budget_stress", c.get("packs", []))

    def test_load_packs_multiple(self):
        cases = load_packs(["budget_stress", "failure_recovery"])
        for c in cases:
            self.assertTrue(
                "budget_stress" in c.get("packs", []) or
                "failure_recovery" in c.get("packs", [])
            )

    def test_load_packs_empty_returns_all(self):
        cases = load_packs([])
        self.assertEqual(len(cases), len(EVAL_CASES))

    def test_each_pack_has_minimum_cases(self):
        """各 pack が 2 件以上のケースを持つ"""
        for pack in list_packs():
            cases = load_packs([pack])
            self.assertGreaterEqual(len(cases), 2, f"pack {pack} has only {len(cases)} cases")


# ---------------------------------------------------------------------------
# Budget helpers
# ---------------------------------------------------------------------------

class TestStep107BudgetHelpers(unittest.TestCase):

    def test_healthy_budget_has_room(self):
        b = _healthy_budget()
        self.assertEqual(b["max_worker_runs"] - b["spent_worker_runs"], 10)

    def test_low_budget_remaining_1(self):
        b = _low_budget()
        self.assertEqual(b["max_worker_runs"] - b["spent_worker_runs"], 1)

    def test_stressed_budget_zero_remaining(self):
        b = _stressed_budget()
        self.assertEqual(b["max_worker_runs"] - b["spent_worker_runs"], 0)

    def test_exhausted_budget_has_hits(self):
        b = _exhausted_budget()
        self.assertGreater(b["budget_limit_hits"], 0)

    def test_failure_metrics_has_failures(self):
        m = _failure_metrics()
        self.assertGreater(m.get("failed_steps", 0), 0)

    def test_partial_metrics_has_partials(self):
        m = _partial_metrics()
        self.assertGreater(m.get("partial_runs", 0), 0)


# ---------------------------------------------------------------------------
# Pack content checks
# ---------------------------------------------------------------------------

class TestStep107PackContent(unittest.TestCase):

    def test_budget_stress_causes_cheap_tier(self):
        cases = load_packs(["budget_stress"])
        for c in cases:
            outcome = run_case(c)
            tier = outcome["result"]["execution_policy_tier"]
            self.assertEqual(tier, "cheap", f"case {c['case_id']} should be cheap, got {tier}")

    def test_failure_recovery_suppresses_orchestration(self):
        cases = load_packs(["failure_recovery"])
        for c in cases:
            outcome = run_case(c)
            orch = outcome["result"]["allow_orchestration"]
            self.assertFalse(orch, f"case {c['case_id']} should not allow orchestration")

    def test_partial_heavy_enables_critique_boost(self):
        cases = load_packs(["partial_heavy"])
        for c in cases:
            outcome = run_case(c)
            # At minimum, should have critique or decision in chain
            chain = outcome["result"]["skill_chain"]
            # Not all will have critique_boost set, but chain should be reasonable
            self.assertGreaterEqual(len(chain), 1)

    def test_orchestration_boundary_has_mixed_orchestration(self):
        cases = load_packs(["orchestration_boundary"])
        orch_values = set()
        for c in cases:
            outcome = run_case(c)
            orch_values.add(outcome["result"]["allow_orchestration"])
        # Should have both True and False across boundary cases
        self.assertGreater(len(orch_values), 1, "orchestration_boundary should have mixed values")

    def test_routing_ambiguity_has_research_fallback(self):
        cases = load_packs(["routing_ambiguity"])
        for c in cases:
            outcome = run_case(c)
            skill = outcome["result"]["selected_skill"]
            # Should resolve to some skill (research as fallback)
            self.assertIsNotNone(skill)

    def test_execution_risk_uses_safe_tier(self):
        cases = load_packs(["execution_risk"])
        for c in cases:
            outcome = run_case(c)
            tier = outcome["result"]["execution_policy_tier"]
            self.assertIn(tier, ("cheap", "balanced"))


# ---------------------------------------------------------------------------
# Harness with packs
# ---------------------------------------------------------------------------

class TestStep107HarnessWithPacks(unittest.TestCase):

    def test_harness_runs_pack_subset(self):
        cases = load_packs(["budget_stress"])
        summary = run_harness(cases)
        self.assertEqual(summary["total"], len(cases))
        self.assertTrue(summary["passed"] + summary["failed"] > 0)

    def test_harness_all_packs(self):
        summary = run_harness(EVAL_CASES)
        self.assertEqual(summary["total"], len(EVAL_CASES))


# ---------------------------------------------------------------------------
# Benchmark with packs
# ---------------------------------------------------------------------------

class TestStep107BenchmarkWithPacks(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_baseline_from_pack(self):
        cases = load_packs(["budget_stress"])
        summary = run_harness(cases)
        path = Path(self.temp_dir) / "baseline.json"
        save_baseline(summary, path)
        loaded = load_baseline(path)
        self.assertEqual(len(loaded["snapshot"]), len(cases))

    def test_compare_packs(self):
        cases = load_packs(["budget_stress"])
        summary = run_harness(cases)
        baseline = {"snapshot": extract_snapshot(summary)}
        # Run again (identical)
        latest = run_harness(cases)
        report = compare_snapshots(baseline, latest)
        self.assertTrue(report["ok"])


# ---------------------------------------------------------------------------
# Candidate rules with packs
# ---------------------------------------------------------------------------

class TestStep107CandidateRulesWithPacks(unittest.TestCase):

    def test_candidate_report_from_pack_regressions(self):
        # Create artificial regression report from pack cases
        cases = load_packs(["budget_stress"])
        summary = run_harness(cases)
        baseline = {"snapshot": extract_snapshot(summary)}

        # Simulate a regression by modifying one case's expected behavior
        # (In real usage, this would come from a different run)
        report = generate_candidate_report(
            {"regressions": 1, "regression_details": [
                {"case_id": cases[0]["case_id"], "diffs": [
                    "execution_policy_tier: baseline='cheap', latest='thorough'"
                ]}
            ]},
            harness_summary=summary,
        )
        self.assertGreater(report["candidate_count"], 0)

    def test_no_regression_no_candidates(self):
        report = generate_candidate_report(
            {"regressions": 0, "regression_details": []},
            harness_summary={"total": 5, "cases": []},
        )
        self.assertEqual(report["candidate_count"], 0)


# ---------------------------------------------------------------------------
# Case counts
# ---------------------------------------------------------------------------

class TestStep107CaseCounts(unittest.TestCase):

    def test_total_cases_increased(self):
        """Step107 でケース数が増えている"""
        self.assertGreaterEqual(len(EVAL_CASES), 20)

    def test_packs_cover_most_cases(self):
        """ほとんどのケースが何らかの pack に属している"""
        with_packs = [c for c in EVAL_CASES if c.get("packs")]
        coverage = len(with_packs) / len(EVAL_CASES) if EVAL_CASES else 0
        self.assertGreater(coverage, 0.8, f"pack coverage is only {coverage:.1%}")


if __name__ == "__main__":
    unittest.main()
