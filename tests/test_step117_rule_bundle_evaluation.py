#!/usr/bin/env python3
"""Step117 Phase 1-A: Rule Bundle Evaluation Tests

Tests for evaluating bundles of rules together.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.candidate_rules import (
    AdoptionRegistry,
    make_candidate,
    review_candidate,
    make_provenance,
    evaluate_rule_bundle,
    REVIEW_STATUS_ACCEPTED,
)


def _make_accepted_candidate(rule_id: str, rule_type: str = "tier_threshold") -> dict:
    """Helper to create an accepted candidate."""
    c = make_candidate(
        candidate_rule_id=rule_id,
        description="Test rule",
        expected_effect="Test effect",
        affected_cases=["case-1"],
        risk_level="low",
        recommendation="adopt",
        rule_type=rule_type,
        suggested_change={"test": 1},
    )
    return review_candidate(c, decision="accepted", reviewer="tester")


def _adopt_with_provenance(
    registry: AdoptionRegistry,
    rule_id: str,
    risk_level: str = "low",
) -> dict:
    """Helper to adopt a rule with provenance."""
    candidate = _make_accepted_candidate(rule_id)
    provenance = make_provenance(
        rule_id=rule_id,
        source_candidate_rule_id=rule_id,
        source_regression_case_ids=["case-1"],
        created_by="test",
    )
    candidate["risk_level"] = risk_level
    return registry.adopt(candidate, adopted_by="tester", provenance=provenance)


class TestEvaluateRuleBundle(unittest.TestCase):
    """Tests for evaluate_rule_bundle()."""

    def test_empty_bundle(self):
        """Empty bundle should return neutral result."""
        registry = AdoptionRegistry()
        result = evaluate_rule_bundle([], registry)

        self.assertEqual(result["bundle_rule_ids"], [])
        self.assertEqual(result["bundle_result"], 0.0)
        self.assertTrue(result["no_added_value"])

    def test_single_rule_bundle(self):
        """Single rule bundle should work."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        result = evaluate_rule_bundle(["rule-001"], registry)

        self.assertEqual(result["bundle_rule_ids"], ["rule-001"])
        self.assertIn("rule-001", result["per_rule_results"])
        self.assertIn("bundle_result", result)

    def test_multi_rule_bundle(self):
        """Multiple rule bundle should be evaluated."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", risk_level="low")
        _adopt_with_provenance(registry, "rule-002", risk_level="medium")

        result = evaluate_rule_bundle(["rule-001", "rule-002"], registry)

        self.assertEqual(len(result["bundle_rule_ids"]), 2)
        self.assertIn("rule-001", result["per_rule_results"])
        self.assertIn("rule-002", result["per_rule_results"])
        self.assertIn("bundle_result", result)

    def test_bundle_with_provided_individual_results(self):
        """Bundle should use provided individual results."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        _adopt_with_provenance(registry, "rule-002")

        individual_results = {"rule-001": 0.8, "rule-002": 0.6}
        result = evaluate_rule_bundle(
            ["rule-001", "rule-002"],
            registry,
            individual_results=individual_results
        )

        self.assertEqual(result["per_rule_results"]["rule-001"], 0.8)
        self.assertEqual(result["per_rule_results"]["rule-002"], 0.6)


class TestBundleComparisons(unittest.TestCase):
    """Tests for bundle vs individual comparisons."""

    def test_beneficial_bundle(self):
        """Bundle better than best individual should not be harmful."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", risk_level="low")
        _adopt_with_provenance(registry, "rule-002", risk_level="low")

        # Low risk = 0.7 score each, bundle average = 0.7
        result = evaluate_rule_bundle(["rule-001", "rule-002"], registry)

        # Both rules have same score, so bundle = individual
        self.assertFalse(result["harmful_interaction"])

    def test_no_added_value(self):
        """Bundle with no improvement should be marked."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", risk_level="medium")

        result = evaluate_rule_bundle(["rule-001"], registry)

        # Single rule, bundle = individual
        self.assertTrue(result["no_added_value"])

    def test_harmful_interaction_high_risk(self):
        """High risk rules should result in harmful interaction."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", risk_level="low")
        _adopt_with_provenance(registry, "rule-002", risk_level="high")

        result = evaluate_rule_bundle(["rule-001", "rule-002"], registry)

        # High risk = 0.3, low risk = 0.7
        # Bundle average = 0.5, best individual = 0.7
        # Delta = -0.2, which is harmful
        self.assertTrue(result["harmful_interaction"])

    def test_delta_calculation(self):
        """Delta should be calculated correctly."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", risk_level="low")
        _adopt_with_provenance(registry, "rule-002", risk_level="medium")

        result = evaluate_rule_bundle(["rule-001", "rule-002"], registry)

        # Low risk = 0.7, medium risk = 0.5
        # Bundle average = 0.6, best individual = 0.7
        # Delta = -0.1
        self.assertIn("delta_vs_best_individual", result)
        self.assertLess(result["delta_vs_best_individual"], 0)


class TestBundleOutputFormat(unittest.TestCase):
    """Tests for bundle evaluation output format."""

    def test_required_fields_present(self):
        """All required fields should be present."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        result = evaluate_rule_bundle(["rule-001"], registry)

        required_fields = [
            "bundle_rule_ids",
            "per_rule_results",
            "bundle_result",
            "delta_vs_best_individual",
            "harmful_interaction",
            "no_added_value",
        ]
        for field in required_fields:
            self.assertIn(field, result)

    def test_detected_conflicts_field(self):
        """detected_conflicts field should be present."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        result = evaluate_rule_bundle(["rule-001"], registry)

        self.assertIn("detected_conflicts", result)


class TestBundleEvaluationInExport(unittest.TestCase):
    """Tests for bundle evaluation in export()."""

    def test_export_with_bundle_evaluation_json(self):
        """Export with include_bundle_eval should include bundle evaluation in JSON."""
        import json
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        _adopt_with_provenance(registry, "rule-002")

        exported = registry.export(
            fmt="json",
            include_bundle_eval=True,
            bundle_rule_ids=["rule-001", "rule-002"]
        )
        data = json.loads(exported)

        self.assertIn("bundle_evaluation", data)
        self.assertEqual(data["bundle_evaluation"]["bundle_rule_ids"], ["rule-001", "rule-002"])

    def test_export_without_bundle_evaluation_json(self):
        """Export without include_bundle_eval should not include bundle evaluation."""
        import json
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        exported = registry.export(fmt="json", include_bundle_eval=False)
        data = json.loads(exported)

        self.assertNotIn("bundle_evaluation", data)

    def test_export_bundle_without_rule_ids(self):
        """Export with include_bundle_eval but no bundle_rule_ids should not include bundle."""
        import json
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        exported = registry.export(fmt="json", include_bundle_eval=True, bundle_rule_ids=None)
        data = json.loads(exported)

        self.assertNotIn("bundle_evaluation", data)


class TestRegistryGetBundleEvaluation(unittest.TestCase):
    """Tests for AdoptionRegistry.get_bundle_evaluation()."""

    def test_get_bundle_evaluation_method(self):
        """Registry should have get_bundle_evaluation method."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        _adopt_with_provenance(registry, "rule-002")

        result = registry.get_bundle_evaluation(["rule-001", "rule-002"])

        self.assertEqual(result["bundle_rule_ids"], ["rule-001", "rule-002"])
        self.assertIn("bundle_result", result)
        self.assertIn("harmful_interaction", result)
        self.assertIn("no_added_value", result)

    def test_bundle_with_detected_conflicts(self):
        """Bundle evaluation should include detected conflicts."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Bad")
        _adopt_with_provenance(registry, "rule-002")

        result = registry.get_bundle_evaluation(["rule-001", "rule-002"])

        self.assertIn("detected_conflicts", result)

    def test_bundle_harmful_interaction_in_result(self):
        """Bundle result should reflect harmful_interaction status."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", risk_level="low")
        _adopt_with_provenance(registry, "rule-002", risk_level="high")

        result = registry.get_bundle_evaluation(["rule-001", "rule-002"])

        self.assertTrue(result["harmful_interaction"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
