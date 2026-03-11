#!/usr/bin/env python3
"""Step104: Evaluation Harness Tests"""
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.cases import load_cases, EVAL_CASES, make_case
from eval.harness import run_case, run_harness, _collect_result, _check_expectations


# ---------------------------------------------------------------------------
# Cases loading
# ---------------------------------------------------------------------------

class TestStep104CasesLoad(unittest.TestCase):

    def test_load_all_cases(self):
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 8)

    def test_load_by_kind(self):
        cases = load_cases(kinds=["simple"])
        self.assertGreater(len(cases), 0)
        for c in cases:
            self.assertEqual(c["kind"], "simple")

    def test_load_multiple_kinds(self):
        cases = load_cases(kinds=["simple", "decision"])
        kinds = {c["kind"] for c in cases}
        self.assertIn("simple", kinds)
        self.assertIn("decision", kinds)

    def test_all_required_kinds_present(self):
        required = {
            "simple", "decision", "research", "execution",
            "complex", "failure_history", "low_budget", "orchestration",
        }
        actual = {c["kind"] for c in EVAL_CASES}
        self.assertTrue(required.issubset(actual), f"missing: {required - actual}")

    def test_case_has_required_fields(self):
        for c in EVAL_CASES:
            self.assertIn("case_id", c)
            self.assertIn("label", c)
            self.assertIn("kind", c)
            self.assertIn("text", c)
            self.assertIn("task_context", c)
            self.assertIn("expected", c)


# ---------------------------------------------------------------------------
# Result fields
# ---------------------------------------------------------------------------

class TestStep104ResultFields(unittest.TestCase):

    def test_result_has_required_fields(self):
        case = load_cases(kinds=["simple"])[0]
        outcome = run_case(case)
        result = outcome["result"]
        for key in [
            "case_id", "label", "kind",
            "selected_skill", "skill_chain", "planning_mode",
            "execution_policy_tier", "allow_orchestration", "allow_parallel",
            "final_status", "budget_limit_hit",
        ]:
            self.assertIn(key, result, f"missing key: {key}")

    def test_final_status_is_eval_only(self):
        case = load_cases(kinds=["simple"])[0]
        outcome = run_case(case)
        self.assertEqual(outcome["result"]["final_status"], "eval_only")

    def test_check_field_present(self):
        case = load_cases(kinds=["simple"])[0]
        outcome = run_case(case)
        self.assertIn("check", outcome)
        self.assertIn("ok", outcome["check"])
        self.assertIn("passed", outcome["check"])
        self.assertIn("failed", outcome["check"])


# ---------------------------------------------------------------------------
# Policy tier differences
# ---------------------------------------------------------------------------

class TestStep104PolicyTierDiff(unittest.TestCase):
    """policy tier 差が出力される"""

    def test_cheap_tier_for_low_budget(self):
        cases = load_cases(kinds=["low_budget"])
        self.assertGreater(len(cases), 0)
        outcome = run_case(cases[0])
        self.assertEqual(outcome["result"]["execution_policy_tier"], "cheap")

    def test_thorough_tier_for_complex(self):
        cases = load_cases(kinds=["complex"])
        self.assertGreater(len(cases), 0)
        outcome = run_case(cases[0])
        self.assertEqual(outcome["result"]["execution_policy_tier"], "thorough")

    def test_cheap_no_orchestration(self):
        cases = load_cases(kinds=["low_budget"])
        outcome = run_case(cases[0])
        self.assertFalse(outcome["result"]["allow_orchestration"])

    def test_thorough_allows_orchestration(self):
        cases = load_cases(kinds=["orchestration"])
        outcome = run_case(cases[0])
        self.assertTrue(outcome["result"]["allow_orchestration"])

    def test_all_tiers_represented(self):
        cases = load_cases()
        summary = run_harness(cases)
        tiers = {cr["result"]["execution_policy_tier"] for cr in summary["cases"]}
        # We should see at least cheap and thorough
        self.assertIn("cheap", tiers)
        self.assertIn("thorough", tiers)


# ---------------------------------------------------------------------------
# Failure case recording
# ---------------------------------------------------------------------------

class TestStep104FailureCase(unittest.TestCase):
    """failure case を正しく記録する"""

    def test_failure_history_case_is_cheap(self):
        cases = load_cases(kinds=["failure_history"])
        outcome = run_case(cases[0])
        self.assertEqual(outcome["result"]["execution_policy_tier"], "cheap")

    def test_failure_history_case_no_orchestration(self):
        cases = load_cases(kinds=["failure_history"])
        outcome = run_case(cases[0])
        self.assertFalse(outcome["result"]["allow_orchestration"])

    def test_expectation_check_fails_correctly(self):
        fake_result = {
            "execution_policy_tier": "cheap",
            "selected_skill": "research",
            "skill_chain_length": 3,
        }
        expected = {
            "execution_policy.tier": "thorough",  # wrong
            "selected_skill_in": ["critique", "decision"],  # wrong
        }
        check = _check_expectations(fake_result, expected)
        self.assertFalse(check["ok"])
        self.assertEqual(len(check["failed"]), 2)

    def test_expectation_check_passes_correctly(self):
        fake_result = {
            "execution_policy_tier": "cheap",
            "allow_orchestration": False,
        }
        expected = {
            "execution_policy.tier": "cheap",
            "allow_orchestration": False,
        }
        check = _check_expectations(fake_result, expected)
        self.assertTrue(check["ok"])
        self.assertEqual(len(check["failed"]), 0)


# ---------------------------------------------------------------------------
# Harness output
# ---------------------------------------------------------------------------

class TestStep104HarnessOutput(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_harness_returns_summary(self):
        cases = load_cases()
        summary = run_harness(cases)
        self.assertIn("total", summary)
        self.assertIn("passed", summary)
        self.assertIn("failed", summary)
        self.assertIn("cases", summary)
        self.assertEqual(summary["total"], len(cases))

    def test_harness_json_output(self):
        cases = load_cases()
        path = Path(self.temp_dir) / "eval_results.json"
        summary = run_harness(cases, output_path=path, output_format="json")
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text())
        self.assertEqual(loaded["total"], summary["total"])

    def test_harness_markdown_output(self):
        cases = load_cases()
        path = Path(self.temp_dir) / "eval_results.md"
        run_harness(cases, output_path=path, output_format="markdown")
        self.assertTrue(path.exists())
        content = path.read_text()
        self.assertIn("# Evaluation Harness Results", content)
        self.assertIn("case-001", content)

    def test_all_expected_assertions_pass(self):
        """全 case の expected アサーションが通る"""
        cases = load_cases()
        summary = run_harness(cases)
        failures = [
            f"{cr['case_id']}: {cr['check']['failed']}"
            for cr in summary["cases"]
            if not cr["check"]["ok"]
        ]
        self.assertEqual(failures, [], f"Expectation failures:\n" + "\n".join(failures))


# ---------------------------------------------------------------------------
# make_case helper
# ---------------------------------------------------------------------------

class TestStep104MakeCase(unittest.TestCase):

    def test_make_case_defaults(self):
        c = make_case("x", "label", "simple", "text")
        self.assertEqual(c["case_id"], "x")
        self.assertEqual(c["task_context"], {})
        self.assertEqual(c["expected"], {})

    def test_load_empty_kinds_returns_all(self):
        self.assertEqual(load_cases([]), EVAL_CASES)


if __name__ == "__main__":
    unittest.main()
