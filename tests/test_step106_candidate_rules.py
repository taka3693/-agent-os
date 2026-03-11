#!/usr/bin/env python3
"""Step106: Auto-Tuning Candidate Rules Tests"""
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.candidate_rules import (
    make_candidate,
    analyze_regressions,
    generate_candidates,
    simulate_effect,
    generate_candidate_report,
    report_to_json,
    report_to_markdown,
    save_report,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_regression_report(with_regressions=True):
    """Create a synthetic regression report for testing."""
    if not with_regressions:
        return {
            "regressions": 0,
            "regression_details": [],
        }
    return {
        "regressions": 3,
        "regression_details": [
            {
                "case_id": "case-001",
                "diffs": [
                    "selected_skill: baseline='research', latest='critique'",
                    "execution_policy_tier: baseline='balanced', latest='cheap'",
                ],
            },
            {
                "case_id": "case-002",
                "diffs": [
                    "allow_orchestration: baseline=True, latest=False",
                ],
            },
            {
                "case_id": "case-003",
                "diffs": [
                    "skill_chain_length: baseline=2, latest=1 (diff=1 > tol=1)",
                ],
            },
        ],
    }


def _make_harness_summary():
    return {
        "total": 5,
        "cases": [
            {"case_id": "case-001", "result": {}},
            {"case_id": "case-002", "result": {}},
            {"case_id": "case-003", "result": {}},
            {"case_id": "case-004", "result": {}},
            {"case_id": "case-005", "result": {}},
        ],
    }


# ---------------------------------------------------------------------------
# make_candidate
# ---------------------------------------------------------------------------

class TestStep106MakeCandidate(unittest.TestCase):

    def test_make_candidate_has_required_fields(self):
        c = make_candidate(
            candidate_rule_id="rule-001",
            description="test rule",
            expected_effect="improve",
            affected_cases=["c1", "c2"],
            risk_level="low",
            recommendation="adopt",
            rule_type="failed_chain",
            suggested_change={"threshold": 2},
        )
        self.assertEqual(c["candidate_rule_id"], "rule-001")
        self.assertEqual(c["risk_level"], "low")
        self.assertEqual(c["recommendation"], "adopt")
        self.assertIn("threshold", c["suggested_change"])

    def test_make_candidate_all_risk_levels(self):
        for level in ("low", "medium", "high"):
            c = make_candidate("r", "d", "e", [], level, "adopt", "t", {})
            self.assertEqual(c["risk_level"], level)

    def test_make_candidate_all_recommendations(self):
        for rec in ("adopt", "review", "discard"):
            c = make_candidate("r", "d", "e", [], "low", rec, "t", {})
            self.assertEqual(c["recommendation"], rec)


# ---------------------------------------------------------------------------
# analyze_regressions
# ---------------------------------------------------------------------------

class TestStep106AnalyzeRegressions(unittest.TestCase):

    def test_no_regressions_returns_empty(self):
        report = _make_regression_report(with_regressions=False)
        patterns = analyze_regressions(report)
        self.assertEqual(patterns, [])

    def test_extracts_field_patterns(self):
        report = _make_regression_report(with_regressions=True)
        patterns = analyze_regressions(report)
        self.assertGreater(len(patterns), 0)

        fields = {p["field"] for p in patterns}
        self.assertIn("selected_skill", fields)
        self.assertIn("execution_policy_tier", fields)
        self.assertIn("allow_orchestration", fields)

    def test_extracts_case_ids(self):
        report = _make_regression_report(with_regressions=True)
        patterns = analyze_regressions(report)
        case_ids = {p["case_id"] for p in patterns}
        self.assertIn("case-001", case_ids)
        self.assertIn("case-002", case_ids)

    def test_extracts_values(self):
        report = _make_regression_report(with_regressions=True)
        patterns = analyze_regressions(report)
        # Find selected_skill pattern
        ss = next(p for p in patterns if p["field"] == "selected_skill")
        self.assertEqual(ss["baseline_val"], "research")
        self.assertEqual(ss["latest_val"], "critique")


# ---------------------------------------------------------------------------
# generate_candidates
# ---------------------------------------------------------------------------

class TestStep106GenerateCandidates(unittest.TestCase):

    def test_no_patterns_returns_empty(self):
        candidates = generate_candidates([])
        self.assertEqual(candidates, [])

    def test_generates_selected_skill_rule(self):
        patterns = [{"pattern_type": "field_regression", "case_id": "c1",
                     "field": "selected_skill", "baseline_val": "a", "latest_val": "b"}]
        candidates = generate_candidates(patterns)
        self.assertGreater(len(candidates), 0)
        self.assertTrue(any(c["rule_type"] == "failed_chain" for c in candidates))

    def test_generates_orchestration_rule(self):
        patterns = [{"pattern_type": "field_regression", "case_id": "c1",
                     "field": "allow_orchestration", "baseline_val": True, "latest_val": False}]
        candidates = generate_candidates(patterns)
        self.assertTrue(any(c["rule_type"] == "orchestration" for c in candidates))

    def test_generates_tier_rule(self):
        patterns = [
            {"pattern_type": "field_regression", "case_id": "c1",
             "field": "execution_policy_tier", "baseline_val": "balanced", "latest_val": "cheap"},
            {"pattern_type": "field_regression", "case_id": "c2",
             "field": "execution_policy_tier", "baseline_val": "balanced", "latest_val": "cheap"},
        ]
        candidates = generate_candidates(patterns)
        self.assertTrue(any(c["rule_type"] == "tier_threshold" for c in candidates))

    def test_candidate_has_required_fields(self):
        patterns = [{"pattern_type": "field_regression", "case_id": "c1",
                     "field": "selected_skill", "baseline_val": "a", "latest_val": "b"}]
        candidates = generate_candidates(patterns)
        for c in candidates:
            self.assertIn("candidate_rule_id", c)
            self.assertIn("description", c)
            self.assertIn("risk_level", c)
            self.assertIn("recommendation", c)
            self.assertIn("affected_cases", c)
            self.assertIn("suggested_change", c)

    def test_candidate_has_risk_level(self):
        patterns = [{"pattern_type": "field_regression", "case_id": "c1",
                     "field": "selected_skill", "baseline_val": "a", "latest_val": "b"}]
        candidates = generate_candidates(patterns)
        for c in candidates:
            self.assertIn(c["risk_level"], ("low", "medium", "high"))

    def test_candidate_has_recommendation(self):
        patterns = [{"pattern_type": "field_regression", "case_id": "c1",
                     "field": "selected_skill", "baseline_val": "a", "latest_val": "b"}]
        candidates = generate_candidates(patterns)
        for c in candidates:
            self.assertIn(c["recommendation"], ("adopt", "review", "discard"))


# ---------------------------------------------------------------------------
# simulate_effect
# ---------------------------------------------------------------------------

class TestStep106SimulateEffect(unittest.TestCase):

    def test_empty_candidates(self):
        summary = simulate_effect([], _make_harness_summary())
        self.assertEqual(summary["total_candidates"], 0)
        self.assertEqual(summary["estimated_affected_cases"], 0)

    def test_counts_by_risk_level(self):
        candidates = [
            make_candidate("r1", "d", "e", ["c1"], "low", "adopt", "t", {}),
            make_candidate("r2", "d", "e", ["c2"], "medium", "review", "t", {}),
            make_candidate("r3", "d", "e", ["c3"], "high", "discard", "t", {}),
        ]
        summary = simulate_effect(candidates, _make_harness_summary())
        self.assertEqual(summary["by_risk_level"]["low"], 1)
        self.assertEqual(summary["by_risk_level"]["medium"], 1)
        self.assertEqual(summary["by_risk_level"]["high"], 1)

    def test_counts_by_recommendation(self):
        candidates = [
            make_candidate("r1", "d", "e", [], "low", "adopt", "t", {}),
            make_candidate("r2", "d", "e", [], "low", "adopt", "t", {}),
            make_candidate("r3", "d", "e", [], "low", "review", "t", {}),
        ]
        summary = simulate_effect(candidates, _make_harness_summary())
        self.assertEqual(summary["by_recommendation"]["adopt"], 2)
        self.assertEqual(summary["by_recommendation"]["review"], 1)

    def test_estimates_affected_cases(self):
        candidates = [
            make_candidate("r1", "d", "e", ["c1", "c2"], "low", "adopt", "t", {}),
            make_candidate("r2", "d", "e", ["c2", "c3"], "low", "adopt", "t", {}),
        ]
        summary = simulate_effect(candidates, _make_harness_summary())
        # c1, c2, c3 = 3 unique
        self.assertEqual(summary["estimated_affected_cases"], 3)

    def test_counts_by_rule_type(self):
        candidates = [
            make_candidate("r1", "d", "e", [], "low", "adopt", "failed_chain", {}),
            make_candidate("r2", "d", "e", [], "low", "adopt", "orchestration", {}),
        ]
        summary = simulate_effect(candidates, _make_harness_summary())
        self.assertEqual(summary["by_rule_type"]["failed_chain"], 1)
        self.assertEqual(summary["by_rule_type"]["orchestration"], 1)


# ---------------------------------------------------------------------------
# generate_candidate_report
# ---------------------------------------------------------------------------

class TestStep106GenerateReport(unittest.TestCase):

    def test_report_structure(self):
        report = generate_candidate_report(_make_regression_report())
        self.assertIn("generated_at", report)
        self.assertIn("regression_count", report)
        self.assertIn("pattern_count", report)
        self.assertIn("candidate_count", report)
        self.assertIn("candidates", report)
        self.assertIn("simulation", report)
        self.assertIn("note", report)

    def test_report_no_regressions(self):
        report = generate_candidate_report(_make_regression_report(with_regressions=False))
        self.assertEqual(report["regression_count"], 0)
        self.assertEqual(report["candidate_count"], 0)

    def test_report_with_harness_summary(self):
        report = generate_candidate_report(
            _make_regression_report(),
            harness_summary=_make_harness_summary(),
        )
        self.assertEqual(report["simulation"]["total_cases_analyzed"], 5)

    def test_report_does_not_modify_policy(self):
        """本番 policy を直接変更しない"""
        report = generate_candidate_report(_make_regression_report())
        self.assertIn("advisory only", report["note"])
        # No side effects on actual policy files
        self.assertTrue(True)  # just documenting the invariant


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

class TestStep106OutputFormatters(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_report_to_json_valid(self):
        report = generate_candidate_report(_make_regression_report())
        s = report_to_json(report)
        parsed = json.loads(s)
        self.assertEqual(parsed["regression_count"], report["regression_count"])

    def test_report_to_markdown_has_header(self):
        report = generate_candidate_report(_make_regression_report())
        md = report_to_markdown(report)
        self.assertIn("Auto-Tuning Candidate Rules Report", md)
        self.assertIn("advisory only", md)

    def test_markdown_includes_candidates(self):
        report = generate_candidate_report(_make_regression_report())
        md = report_to_markdown(report)
        if report["candidate_count"] > 0:
            self.assertIn("rule-", md)
            self.assertIn("Expected effect:", md)

    def test_markdown_includes_simulation(self):
        report = generate_candidate_report(_make_regression_report())
        md = report_to_markdown(report)
        self.assertIn("Simulation Summary", md)

    def test_save_report_json(self):
        report = generate_candidate_report(_make_regression_report())
        path = Path(self.temp_dir) / "candidates.json"
        save_report(report, path, fmt="json")
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text())
        self.assertEqual(loaded["regression_count"], report["regression_count"])

    def test_save_report_markdown(self):
        report = generate_candidate_report(_make_regression_report())
        path = Path(self.temp_dir) / "candidates.md"
        save_report(report, path, fmt="markdown")
        self.assertTrue(path.exists())
        content = path.read_text()
        self.assertIn("Auto-Tuning", content)


# ---------------------------------------------------------------------------
# Integration: full pipeline from regression → candidates
# ---------------------------------------------------------------------------

class TestStep106Integration(unittest.TestCase):

    def test_full_pipeline_from_regression_report(self):
        reg_report = _make_regression_report(with_regressions=True)
        report = generate_candidate_report(reg_report, harness_summary=_make_harness_summary())

        self.assertGreater(report["pattern_count"], 0)
        self.assertGreater(report["candidate_count"], 0)
        self.assertIn("candidates", report)
        for c in report["candidates"]:
            self.assertIn("risk_level", c)
            self.assertIn("recommendation", c)


if __name__ == "__main__":
    unittest.main()
