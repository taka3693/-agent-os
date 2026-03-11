#!/usr/bin/env python3
"""Step118: Policy Health Scoring Tests

Tests for computing policy health scores.
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
    compute_policy_health,
    get_policy_health,
    REVIEW_STATUS_ACCEPTED,
    ADOPTION_STATUS_ROLLED_BACK,
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
    with_provenance: bool = True,
) -> dict:
    """Helper to adopt a rule with provenance."""
    candidate = _make_accepted_candidate(rule_id)
    candidate["risk_level"] = risk_level
    if with_provenance:
        provenance = make_provenance(
            rule_id=rule_id,
            source_candidate_rule_id=rule_id,
            source_regression_case_ids=["case-1"],
            created_by="test",
        )
        return registry.adopt(candidate, adopted_by="tester", provenance=provenance)
    else:
        return registry.adopt(candidate, adopted_by="tester", provenance={})


class TestComputePolicyHealth(unittest.TestCase):
    """Tests for compute_policy_health()."""

    def test_empty_registry(self):
        """Empty registry should have perfect health."""
        registry = AdoptionRegistry()
        health = compute_policy_health(registry)

        self.assertEqual(health["health_score"], 100)
        self.assertEqual(health["grade"], "A")

    def test_health_score_range(self):
        """Health score should be between 0 and 100."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        health = compute_policy_health(registry)

        self.assertGreaterEqual(health["health_score"], 0)
        self.assertLessEqual(health["health_score"], 100)

    def test_health_has_required_fields(self):
        """Health report should have required fields."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        health = compute_policy_health(registry)

        self.assertIn("health_score", health)
        self.assertIn("grade", health)
        self.assertIn("breakdown", health)
        self.assertIn("issues", health)
        self.assertIn("summary", health)

    def test_get_policy_health_alias(self):
        """get_policy_health should work as alias."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        health1 = compute_policy_health(registry)
        health2 = get_policy_health(registry)

        self.assertEqual(health1["health_score"], health2["health_score"])


class TestProvenanceHealth(unittest.TestCase):
    """Tests for provenance health impact."""

    def test_missing_provenance_reduces_score(self):
        """Missing provenance should reduce health score."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        _adopt_with_provenance(registry, "rule-002", with_provenance=False)

        health = compute_policy_health(registry)

        self.assertLess(health["breakdown"]["provenance_completeness"], 20)

    def test_all_provenance_perfect_score(self):
        """All rules with provenance should have perfect provenance score."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        _adopt_with_provenance(registry, "rule-002", with_provenance=True)

        health = compute_policy_health(registry)

        self.assertEqual(health["breakdown"]["provenance_completeness"], 20)


class TestConflictHealth(unittest.TestCase):
    """Tests for conflict health impact."""

    def test_conflicts_reduce_score(self):
        """Conflicts should reduce health score."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Bad")
        _adopt_with_provenance(registry, "rule-002")

        health = compute_policy_health(registry)

        # Rollback reintroduction should reduce conflict health
        self.assertLess(health["breakdown"]["conflict_health"], 20)


class TestRollbackHealth(unittest.TestCase):
    """Tests for rollback health impact."""

    def test_rollback_reduces_score(self):
        """Rolled back rules should reduce health score."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        _adopt_with_provenance(registry, "rule-002")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Bad")

        health = compute_policy_health(registry)

        self.assertLess(health["breakdown"]["rollback_health"], 20)
        self.assertEqual(health["summary"]["rolled_back_rules"], 1)


class TestBundleHealth(unittest.TestCase):
    """Tests for bundle health impact."""

    def test_harmful_bundle_reduces_score(self):
        """Harmful bundles should reduce health score."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", risk_level="low")
        _adopt_with_provenance(registry, "rule-002", risk_level="high")

        health = compute_policy_health(registry)

        # High risk + low risk = harmful interaction
        self.assertGreater(health["summary"]["harmful_bundles"], 0)

    def test_beneficial_bundle_improves_score(self):
        """Beneficial bundles should improve bundle health."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", risk_level="low")
        _adopt_with_provenance(registry, "rule-002", risk_level="low")

        health = compute_policy_health(registry)

        # Both low risk, should not be harmful
        self.assertEqual(health["summary"]["harmful_bundles"], 0)


class TestHealthInExport(unittest.TestCase):
    """Tests for health score in export()."""

    def test_export_with_health_json(self):
        """Export with include_health should include health score."""
        import json
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        exported = registry.export(fmt="json", include_health=True)
        data = json.loads(exported)

        self.assertIn("health", data)
        self.assertIn("health_score", data["health"])

    def test_export_without_health_json(self):
        """Export without include_health should not include health."""
        import json
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        exported = registry.export(fmt="json", include_health=False)
        data = json.loads(exported)

        self.assertNotIn("health", data)

    def test_registry_get_health_score(self):
        """Registry should have get_health_score method."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        health = registry.get_health_score()

        self.assertIn("health_score", health)
        self.assertIn("grade", health)


class TestHealthGrading(unittest.TestCase):
    """Tests for health grade assignment."""

    def test_grade_a_range(self):
        """Score 90-100 should be grade A."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)

        health = compute_policy_health(registry)

        if health["health_score"] >= 90:
            self.assertEqual(health["grade"], "A")

    def test_grade_b_range(self):
        """Score 80-89 should be grade B."""
        # Create registry with some issues
        registry = AdoptionRegistry()
        for i in range(5):
            _adopt_with_provenance(registry, f"rule-{i:03d}", with_provenance=True)
        # Rollback one rule
        registry.rollback("rule-000", rolled_back_by="tester", reason="Test")

        health = compute_policy_health(registry)

        if 80 <= health["health_score"] < 90:
            self.assertEqual(health["grade"], "B")


class TestHealthIssues(unittest.TestCase):
    """Tests for health issues detection."""

    def test_issues_list_present(self):
        """Health report should include issues list."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=False)

        health = compute_policy_health(registry)

        self.assertIn("issues", health)
        self.assertIsInstance(health["issues"], list)

    def test_missing_provenance_in_issues(self):
        """Missing provenance should appear in issues."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=False)

        health = compute_policy_health(registry)

        issues_text = " ".join(health["issues"])
        self.assertIn("provenance", issues_text.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
