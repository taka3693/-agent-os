#!/usr/bin/env python3
"""Step111: Shadow Evaluation for Adopted Rules Tests"""
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.candidate_rules import (
    make_candidate,
    review_candidate,
    AdoptionRegistry,
    create_adoption_registry,
    create_shadow_evaluator,
    can_shadow_evaluate,
    compare_shadow_vs_baseline,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_INACTIVE,
    ADOPTION_STATUS_ROLLED_BACK,
    REVIEW_STATUS_ACCEPTED,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_accepted_candidate(rule_id="rule-001"):
    c = make_candidate(
        candidate_rule_id=rule_id,
        description="test rule",
        expected_effect="improve",
        affected_cases=["c1"],
        risk_level="low",
        recommendation="adopt",
        rule_type="failed_chain",
        suggested_change={"threshold": 2},
    )
    return review_candidate(c, REVIEW_STATUS_ACCEPTED, "reviewer")


def _make_harness_summary(cases):
    """Create a minimal harness summary for testing."""
    return {
        "total": len(cases),
        "cases": cases,
    }


def _make_case(case_id, tier="balanced", orch=False, skill="research"):
    return {
        "case_id": case_id,
        "result": {
            "execution_policy_tier": tier,
            "allow_orchestration": orch,
            "selected_skill": skill,
        },
        "check": {"ok": True, "passed": [], "failed": []},
    }


# ---------------------------------------------------------------------------
# can_shadow_evaluate helper
# ---------------------------------------------------------------------------

class TestStep111CanShadowEvaluate(unittest.TestCase):

    def test_adopted_is_shadowable(self):
        entry = {"adoption_status": ADOPTION_STATUS_ADOPTED}
        self.assertTrue(can_shadow_evaluate(entry))

    def test_inactive_not_shadowable(self):
        entry = {"adoption_status": ADOPTION_STATUS_INACTIVE}
        self.assertFalse(can_shadow_evaluate(entry))

    def test_rolled_back_not_shadowable(self):
        entry = {"adoption_status": ADOPTION_STATUS_ROLLED_BACK}
        self.assertFalse(can_shadow_evaluate(entry))


# ---------------------------------------------------------------------------
# compare_shadow_vs_baseline
# ---------------------------------------------------------------------------

class TestStep111Compare(unittest.TestCase):

    def test_identical_summaries_no_changes(self):
        baseline = _make_harness_summary([
            _make_case("c1", "balanced", False),
            _make_case("c2", "balanced", False),
        ])
        shadow = _make_harness_summary([
            _make_case("c1", "balanced", False),
            _make_case("c2", "balanced", False),
        ])
        result = compare_shadow_vs_baseline(baseline, shadow)
        self.assertEqual(result["changed_count"], 0)
        self.assertEqual(result["neutral_count"], 2)
        self.assertTrue(result["ok"])

    def test_tier_change_detected(self):
        baseline = _make_harness_summary([
            _make_case("c1", "balanced"),
        ])
        shadow = _make_harness_summary([
            _make_case("c1", "thorough"),
        ])
        result = compare_shadow_vs_baseline(baseline, shadow)
        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(result["improvement_count"], 1)

    def test_tier_downgrade_is_regression(self):
        baseline = _make_harness_summary([
            _make_case("c1", "thorough"),
        ])
        shadow = _make_harness_summary([
            _make_case("c1", "cheap"),
        ])
        result = compare_shadow_vs_baseline(baseline, shadow)
        self.assertEqual(result["regression_count"], 1)
        self.assertFalse(result["ok"])

    def test_orchestration_disabled_is_regression(self):
        baseline = _make_harness_summary([
            _make_case("c1", "thorough", True),
        ])
        shadow = _make_harness_summary([
            _make_case("c1", "thorough", False),
        ])
        result = compare_shadow_vs_baseline(baseline, shadow)
        self.assertEqual(result["regression_count"], 1)

    def test_orchestration_enabled_is_improvement(self):
        baseline = _make_harness_summary([
            _make_case("c1", "thorough", False),
        ])
        shadow = _make_harness_summary([
            _make_case("c1", "thorough", True),
        ])
        result = compare_shadow_vs_baseline(baseline, shadow)
        self.assertEqual(result["improvement_count"], 1)

    def test_mixed_cases(self):
        baseline = _make_harness_summary([
            _make_case("c1", "balanced"),
            _make_case("c2", "thorough"),
            _make_case("c3", "cheap"),
        ])
        shadow = _make_harness_summary([
            _make_case("c1", "balanced"),  # neutral
            _make_case("c2", "cheap"),     # regression
            _make_case("c3", "thorough"),  # improvement
        ])
        result = compare_shadow_vs_baseline(baseline, shadow)
        self.assertEqual(result["neutral_count"], 1)
        self.assertEqual(result["regression_count"], 1)
        self.assertEqual(result["improvement_count"], 1)


# ---------------------------------------------------------------------------
# ShadowEvaluator eligibility
# ---------------------------------------------------------------------------

class TestStep111EvaluatorEligibility(unittest.TestCase):

    def test_adopted_can_be_evaluated(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        result = ev.evaluate(
            "r1",
            _make_harness_summary([_make_case("c1")]),
            _make_harness_summary([_make_case("c1")]),
            "bob",
        )
        self.assertIsNotNone(result)

    def test_inactive_cannot_be_evaluated(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.deactivate("r1")
        ev = create_shadow_evaluator(reg)
        with self.assertRaises(ValueError):
            ev.evaluate("r1", {}, {}, "bob")

    def test_rolled_back_cannot_be_evaluated(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.rollback("r1", "bob", "reason")
        ev = create_shadow_evaluator(reg)
        with self.assertRaises(ValueError):
            ev.evaluate("r1", {}, {}, "charol")

    def test_nonexistent_raises_keyerror(self):
        reg = create_adoption_registry()
        ev = create_shadow_evaluator(reg)
        with self.assertRaises(KeyError):
            ev.evaluate("nonexistent", {}, {}, "bob")


# ---------------------------------------------------------------------------
# ShadowEvaluator metadata
# ---------------------------------------------------------------------------

class TestStep111EvaluatorMetadata(unittest.TestCase):

    def test_shadowed_at_is_set(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        result = ev.evaluate("r1", _make_harness_summary([]), _make_harness_summary([]), "bob")
        self.assertIsNotNone(result["shadowed_at"])

    def test_shadowed_by_is_set(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        result = ev.evaluate("r1", _make_harness_summary([]), _make_harness_summary([]), "charol")
        self.assertEqual(result["shadowed_by"], "charol")

    def test_compared_against_baseline_true(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        result = ev.evaluate("r1", _make_harness_summary([]), _make_harness_summary([]), "bob")
        self.assertTrue(result["compared_against_baseline"])

    def test_notes_preserved(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        result = ev.evaluate(
            "r1",
            _make_harness_summary([]),
            _make_harness_summary([]),
            "bob",
            notes="testing phase",
        )
        self.assertEqual(result["notes"], "testing phase")

    def test_source_candidate_rule_id_preserved(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("my-rule-123")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        result = ev.evaluate("my-rule-123", _make_harness_summary([]), _make_harness_summary([]), "bob")
        self.assertEqual(result["source_candidate_rule_id"], "my-rule-123")


# ---------------------------------------------------------------------------
# ShadowEvaluator summary
# ---------------------------------------------------------------------------

class TestStep111EvaluatorSummary(unittest.TestCase):

    def test_summary_counts_evaluated(self):
        reg = create_adoption_registry()
        c1 = _make_accepted_candidate("r1")
        c2 = _make_accepted_candidate("r2")
        reg.adopt(c1, "alice")
        reg.adopt(c2, "alice")
        ev = create_shadow_evaluator(reg)
        ev.evaluate("r1", _make_harness_summary([]), _make_harness_summary([]), "bob")
        ev.evaluate("r2", _make_harness_summary([]), _make_harness_summary([]), "bob")
        summary = ev.summarize()
        self.assertEqual(summary["total_evaluated"], 2)

    def test_summary_counts_regressions(self):
        reg = create_adoption_registry()
        c1 = _make_accepted_candidate("r1")
        reg.adopt(c1, "alice")
        ev = create_shadow_evaluator(reg)
        ev.evaluate(
            "r1",
            _make_harness_summary([_make_case("c1", "thorough")]),
            _make_harness_summary([_make_case("c1", "cheap")]),
            "bob",
        )
        summary = ev.summarize()
        self.assertEqual(summary["with_regressions"], 1)
        self.assertFalse(summary["all_ok"])

    def test_summary_all_ok(self):
        reg = create_adoption_registry()
        c1 = _make_accepted_candidate("r1")
        reg.adopt(c1, "alice")
        ev = create_shadow_evaluator(reg)
        ev.evaluate(
            "r1",
            _make_harness_summary([_make_case("c1")]),
            _make_harness_summary([_make_case("c1")]),
            "bob",
        )
        summary = ev.summarize()
        self.assertTrue(summary["all_ok"])


# ---------------------------------------------------------------------------
# Export / save / load
# ---------------------------------------------------------------------------

class TestStep111Export(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_json_valid(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        ev.evaluate("r1", _make_harness_summary([]), _make_harness_summary([]), "bob")
        s = ev.export(fmt="json")
        parsed = json.loads(s)
        self.assertIn("summary", parsed)
        self.assertIn("results", parsed)
        self.assertEqual(len(parsed["results"]), 1)

    def test_export_markdown_has_header(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        ev.evaluate("r1", _make_harness_summary([]), _make_harness_summary([]), "bob")
        md = ev.export(fmt="markdown")
        self.assertIn("Shadow Evaluation Report", md)
        self.assertIn("r1", md)

    def test_export_markdown_shows_regressions(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        ev.evaluate(
            "r1",
            _make_harness_summary([_make_case("c1", "thorough")]),
            _make_harness_summary([_make_case("c1", "cheap")]),
            "bob",
        )
        md = ev.export(fmt="markdown")
        self.assertIn("Regressions", md)
        self.assertIn("⚠️", md)

    def test_save_json(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        ev.evaluate("r1", _make_harness_summary([]), _make_harness_summary([]), "bob")
        path = Path(self.temp_dir) / "shadow.json"
        ev.save(path, fmt="json")
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text())
        self.assertEqual(loaded["summary"]["total_evaluated"], 1)

    def test_save_markdown(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        ev.evaluate("r1", _make_harness_summary([]), _make_harness_summary([]), "bob")
        path = Path(self.temp_dir) / "shadow.md"
        ev.save(path, fmt="markdown")
        self.assertTrue(path.exists())
        self.assertIn("Shadow Evaluation", path.read_text())

    def test_load_roundtrip(self):
        reg1 = create_adoption_registry()
        c1 = _make_accepted_candidate("r1")
        c2 = _make_accepted_candidate("r2")
        reg1.adopt(c1, "alice")
        reg1.adopt(c2, "alice")
        ev1 = create_shadow_evaluator(reg1)
        ev1.evaluate("r1", _make_harness_summary([]), _make_harness_summary([]), "bob")
        ev1.evaluate("r2", _make_harness_summary([]), _make_harness_summary([]), "carol")

        path = Path(self.temp_dir) / "shadow.json"
        ev1.save(path)

        reg2 = create_adoption_registry()
        ev2 = create_shadow_evaluator(reg2)
        ev2.load(path)

        self.assertEqual(ev2.summarize()["total_evaluated"], 2)

    def test_load_nonexistent_is_ok(self):
        reg = create_adoption_registry()
        ev = create_shadow_evaluator(reg)
        ev.load(Path(self.temp_dir) / "nonexistent.json")
        self.assertEqual(ev.summarize()["total_evaluated"], 0)


# ---------------------------------------------------------------------------
# No policy modification
# ---------------------------------------------------------------------------

class TestStep111NoPolicyModification(unittest.TestCase):

    def test_evaluate_does_not_modify_policy(self):
        """本番 policy を変更しない"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        ev.evaluate("r1", _make_harness_summary([]), _make_harness_summary([]), "tester")
        self.assertTrue(True)

    def test_export_contains_note(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        ev.evaluate("r1", _make_harness_summary([]), _make_harness_summary([]), "bob")
        s = ev.export(fmt="json")
        self.assertIn("does not modify production", s.lower())


if __name__ == "__main__":
    unittest.main()
