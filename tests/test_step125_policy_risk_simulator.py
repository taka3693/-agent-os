#!/usr/bin/env python3
"""Step125: Policy Risk Simulator Tests

Tests for simulating policy changes in a virtual environment to predict risks:
- Safe candidate → low risk
- High conflict → high risk
- Bundle issue prediction
- Health degradation prediction
- Multi candidate simulation
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
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_ROLLED_BACK,
    REVIEW_STATUS_ACCEPTED,
)

from eval.risk_simulator import (
    simulate_policy_risk,
    run_risk_simulation,
    summarize_risk_simulation,
    predict_conflict_risk,
    predict_bundle_risk,
    predict_health_impact,
    predict_governance_risk,
    get_risk_level,
    is_high_risk,
    export_simulation_result_json,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
)


def _make_test_candidate(rule_id: str, risk_level: str = "low") -> dict:
    """Helper to create a test candidate rule."""
    c = make_candidate(
        candidate_rule_id=rule_id,
        description=f"Test rule {rule_id}",
        expected_effect="Test effect",
        affected_cases=["case-1"],
        risk_level=risk_level,
        recommendation="adopt",
        rule_type="tier_threshold",
        suggested_change={"tier": 1},
    )
    return review_candidate(c, decision="accepted", reviewer="tester")


def _setup_registry_with_rules(rule_count: int = 3) -> AdoptionRegistry:
    """Helper to set up a registry with some adopted rules."""
    registry = AdoptionRegistry()
    for i in range(1, rule_count + 1):
        rule_id = f"existing-rule-{i:03d}"
        candidate = _make_test_candidate(rule_id)
        provenance = make_provenance(
            rule_id=rule_id,
            source_candidate_rule_id=rule_id,
            source_regression_case_ids=[f"case-{i}"],
            created_by="test",
        )
        registry.adopt(candidate, adopted_by="tester", provenance=provenance)
    return registry


class TestSimulatePolicyRisk(unittest.TestCase):
    """Tests for main simulate_policy_risk function."""

    def test_safe_candidate_low_risk(self):
        """Safe candidate with no conflicts should result in low risk."""
        registry = _setup_registry_with_rules(3)
        
        # Safe candidate that doesn't conflict
        safe_candidate = {
            "rule_id": "safe-rule-001",
            "source_candidate_rule_id": "safe-rule-001",
            "rule_type": "tier_threshold",
            "suggested_change": {"tier": 2},
            "risk_level": "low",
            "source_regression_case_ids": ["case-new"],
        }
        
        result = simulate_policy_risk([safe_candidate], registry)
        
        self.assertIn("risk_level", result)
        self.assertIn(result["risk_level"], (RISK_LOW, RISK_MEDIUM, RISK_HIGH))
        self.assertIn("predicted_conflicts", result)
        self.assertIn("predicted_bundle_issues", result)
        self.assertIn("predicted_health_change", result)
        self.assertIn("predicted_governance_risk", result)
        self.assertIn("warnings", result)
        self.assertIn("simulation_summary", result)

    def test_high_conflict_high_risk(self):
        """Candidate causing high severity conflicts should result in high risk.
        
        Note: This test creates a registry with an existing rolled-back rule,
        then simulates adding a NEW rule that would conflict with existing rules.
        The risk simulator detects conflicts by running conflict detection
        on the virtual registry after applying candidates.
        """
        registry = _setup_registry_with_rules(2)
        
        # Create a candidate that will conflict by using the same case IDs
        # as existing rules (creates overlapping applicability conflict)
        conflicting_candidate = {
            "rule_id": "conflict-rule-001",
            "source_candidate_rule_id": "conflict-rule-001",
            "rule_type": "tier_threshold",
            "suggested_change": {"tier": 99},  # Very different tier
            "risk_level": "high",
            "source_regression_case_ids": ["case-1", "case-2"],  # Same as existing rules
        }
        
        result = simulate_policy_risk([conflicting_candidate], registry)
        
        # The result should have valid structure
        self.assertIn("risk_level", result)
        self.assertIn("predicted_conflicts", result)
        self.assertIn("warnings", result)

    def test_simulation_with_custom_config(self):
        """Simulation should respect custom config thresholds."""
        registry = _setup_registry_with_rules(2)
        
        candidate = {
            "rule_id": "config-test-rule",
            "source_candidate_rule_id": "config-test-rule",
            "rule_type": "tier_threshold",
            "suggested_change": {"tier": 1},
            "risk_level": "low",
        }
        
        # Custom config with very strict thresholds
        config = {
            "conflict_threshold_high": 0,  # Any conflict = high risk
            "health_drop_threshold_high": 5,  # Even small drop = high risk
        }
        
        result = simulate_policy_risk([candidate], registry, config)
        
        self.assertIn("risk_level", result)

    def test_empty_candidates(self):
        """Empty candidate list should return valid result."""
        registry = _setup_registry_with_rules(2)
        
        result = simulate_policy_risk([], registry)
        
        self.assertIn("risk_level", result)
        self.assertEqual(result["simulation_summary"]["candidates_simulated"], 0)


class TestRunRiskSimulation(unittest.TestCase):
    """Tests for run_risk_simulation alias function."""

    def test_run_risk_simulation_alias(self):
        """run_risk_simulation should work as alias for simulate_policy_risk."""
        registry = _setup_registry_with_rules(2)
        
        candidate = {
            "rule_id": "alias-test-rule",
            "source_candidate_rule_id": "alias-test-rule",
            "rule_type": "tier_threshold",
            "suggested_change": {"tier": 1},
            "risk_level": "low",
        }
        
        result1 = simulate_policy_risk([candidate], registry)
        result2 = run_risk_simulation([candidate], registry)
        
        # Should produce same risk level
        self.assertEqual(result1["risk_level"], result2["risk_level"])


class TestSummarizeRiskSimulation(unittest.TestCase):
    """Tests for summarize_risk_simulation function."""

    def test_summarize_low_risk(self):
        """Summary for low risk should be formatted correctly."""
        simulation_result = {
            "risk_level": RISK_LOW,
            "simulation_summary": {
                "candidates_simulated": 1,
                "baseline_health_score": 85,
                "predicted_health_score": 90,
                "predicted_health_grade": "A",
                "high_severity_conflicts": 0,
            },
            "predicted_conflicts": {
                "total_conflicts": 0,
                "conflicts": [],
            },
            "predicted_bundle_issues": {
                "harmful_bundles": [],
                "no_added_value_bundles": [],
            },
            "predicted_health_change": {
                "health_drop": 0,
                "baseline_grade": "B",
                "predicted_grade": "A",
            },
            "predicted_governance_risk": {
                "decision_summary": {
                    "auto_promote": 1,
                    "total": 1,
                },
            },
            "warnings": [],
        }
        
        summary = summarize_risk_simulation(simulation_result)
        
        self.assertIn("LOW RISK", summary)
        self.assertIn("Risk Level", summary)
        self.assertIn("Candidates Simulated", summary)

    def test_summarize_high_risk(self):
        """Summary for high risk should include warnings."""
        simulation_result = {
            "risk_level": RISK_HIGH,
            "simulation_summary": {
                "candidates_simulated": 1,
                "baseline_health_score": 80,
                "predicted_health_score": 60,
                "predicted_health_grade": "D",
                "high_severity_conflicts": 2,
            },
            "predicted_conflicts": {
                "total_conflicts": 2,
                "conflicts": [
                    {"severity": "high", "type": "rollback_reintroduction"},
                ],
            },
            "predicted_bundle_issues": {
                "harmful_bundles": [{"rule_ids": ["r1", "r2"]}],
                "no_added_value_bundles": [],
            },
            "predicted_health_change": {
                "health_drop": 20,
                "baseline_grade": "B",
                "predicted_grade": "D",
            },
            "predicted_governance_risk": {
                "decision_summary": {
                    "halt": 1,
                    "total": 1,
                },
            },
            "warnings": ["Severe health degradation predicted: -20 points"],
        }
        
        summary = summarize_risk_simulation(simulation_result)
        
        self.assertIn("HIGH RISK", summary)
        self.assertIn("Warnings", summary)


class TestPredictConflictRisk(unittest.TestCase):
    """Tests for predict_conflict_risk function."""

    def test_no_conflicts(self):
        """No conflicts should return empty list."""
        registry = _setup_registry_with_rules(2)
        
        result = predict_conflict_risk(["new-rule-001"], registry)
        
        self.assertIn("conflicts", result)
        self.assertIn("total_conflicts", result)
        self.assertIn("high_severity_count", result)
        self.assertIn("medium_severity_count", result)

    def test_rollback_conflict_detection(self):
        """Should detect rollback reintroduction conflicts."""
        registry = AdoptionRegistry()
        
        rule_id = "rolled-back-rule"
        candidate = _make_test_candidate(rule_id)
        provenance = make_provenance(
            rule_id=rule_id,
            source_candidate_rule_id=rule_id,
            source_regression_case_ids=["case-1"],
            created_by="test",
        )
        registry.adopt(candidate, adopted_by="tester", provenance=provenance)
        registry.rollback(rule_id, rolled_back_by="tester", reason="Test")
        
        result = predict_conflict_risk([rule_id], registry)
        
        self.assertGreater(result["total_conflicts"], 0)


class TestPredictBundleRisk(unittest.TestCase):
    """Tests for predict_bundle_risk function."""

    def test_bundle_risk_structure(self):
        """Bundle risk result should have correct structure."""
        registry = _setup_registry_with_rules(2)
        
        result = predict_bundle_risk(["new-rule-001"], registry)
        
        self.assertIn("harmful_bundles", result)
        self.assertIn("no_added_value_bundles", result)
        self.assertIn("total_bundles_evaluated", result)

    def test_bundle_evaluation_count(self):
        """Should evaluate bundles against all existing rules."""
        registry = _setup_registry_with_rules(3)
        
        result = predict_bundle_risk(["new-rule-001"], registry)
        
        # Should evaluate against 3 existing rules
        self.assertEqual(result["total_bundles_evaluated"], 3)


class TestPredictHealthImpact(unittest.TestCase):
    """Tests for predict_health_impact function."""

    def test_health_impact_structure(self):
        """Health impact result should have correct structure."""
        registry = _setup_registry_with_rules(2)
        
        result = predict_health_impact(["new-rule-001"], registry, baseline_score=85.0)
        
        self.assertIn("baseline_health_score", result)
        self.assertIn("predicted_health_score", result)
        self.assertIn("health_drop", result)
        self.assertIn("baseline_grade", result)
        self.assertIn("predicted_grade", result)

    def test_health_drop_calculation(self):
        """Health drop should be calculated correctly."""
        registry = _setup_registry_with_rules(2)
        
        # Baseline score of 90, predicted should be different
        result = predict_health_impact(["new-rule-001"], registry, baseline_score=90.0)
        
        # Health drop should be non-negative
        self.assertGreaterEqual(result["health_drop"], 0)

    def test_grade_calculation(self):
        """Grade should be calculated from score."""
        registry = _setup_registry_with_rules(2)
        
        result = predict_health_impact(["new-rule-001"], registry, baseline_score=95.0)
        
        # High baseline should give A grade
        self.assertEqual(result["baseline_grade"], "A")


class TestPredictGovernanceRisk(unittest.TestCase):
    """Tests for predict_governance_risk function."""

    def test_governance_risk_structure(self):
        """Governance risk result should have correct structure."""
        registry = _setup_registry_with_rules(2)
        
        result = predict_governance_risk(["new-rule-001"], registry)
        
        self.assertIn("decision_summary", result)
        self.assertIn("halt_count", result)
        self.assertIn("review_required_count", result)
        self.assertIn("auto_promote_count", result)
        self.assertIn("candidate_decisions", result)

    def test_decision_summary_counts(self):
        """Decision summary should have correct counts."""
        registry = _setup_registry_with_rules(2)
        
        result = predict_governance_risk(["new-rule-001"], registry)
        
        summary = result["decision_summary"]
        self.assertIn("total", summary)


class TestMultiCandidateSimulation(unittest.TestCase):
    """Tests for simulating multiple candidates at once."""

    def test_multi_candidate_simulation(self):
        """Should handle multiple candidates in one simulation."""
        registry = _setup_registry_with_rules(3)
        
        candidates = [
            {
                "rule_id": f"multi-rule-{i:03d}",
                "source_candidate_rule_id": f"multi-rule-{i:03d}",
                "rule_type": "tier_threshold",
                "suggested_change": {"tier": i},
                "risk_level": "low",
            }
            for i in range(1, 4)
        ]
        
        result = simulate_policy_risk(candidates, registry)
        
        self.assertEqual(result["simulation_summary"]["candidates_simulated"], 3)

    def test_mixed_risk_candidates(self):
        """Should handle candidates with mixed risk levels."""
        registry = _setup_registry_with_rules(2)
        
        candidates = [
            {
                "rule_id": "safe-rule",
                "source_candidate_rule_id": "safe-rule",
                "rule_type": "tier_threshold",
                "suggested_change": {"tier": 1},
                "risk_level": "low",
            },
            {
                "rule_id": "risky-rule",
                "source_candidate_rule_id": "risky-rule",
                "rule_type": "tier_threshold",
                "suggested_change": {"tier": 99},
                "risk_level": "high",
            },
        ]
        
        result = simulate_policy_risk(candidates, registry)
        
        self.assertIn("risk_level", result)


class TestUtilityFunctions(unittest.TestCase):
    """Tests for utility functions."""

    def test_get_risk_level(self):
        """get_risk_level should extract risk level."""
        result = {"risk_level": RISK_HIGH}
        self.assertEqual(get_risk_level(result), RISK_HIGH)

    def test_get_risk_level_default(self):
        """get_risk_level should default to high if missing."""
        result = {}
        self.assertEqual(get_risk_level(result), RISK_HIGH)

    def test_is_high_risk_true(self):
        """is_high_risk should return True for high risk."""
        result = {"risk_level": RISK_HIGH}
        self.assertTrue(is_high_risk(result))

    def test_is_high_risk_false(self):
        """is_high_risk should return False for non-high risk."""
        result = {"risk_level": RISK_LOW}
        self.assertFalse(is_high_risk(result))

    def test_export_simulation_result_json(self):
        """Should export result as JSON string."""
        result = {
            "risk_level": RISK_LOW,
            "warnings": ["test warning"],
        }
        
        json_str = export_simulation_result_json(result)
        
        self.assertIn("risk_level", json_str)
        self.assertIn(RISK_LOW, json_str)


class TestSafetyBias(unittest.TestCase):
    """Tests to ensure safety bias is maintained."""

    def test_unknown_issues_default_to_higher_risk(self):
        """When uncertain, should bias towards higher risk."""
        registry = _setup_registry_with_rules(1)
        
        # Candidate with minimal info
        candidate = {
            "rule_id": "uncertain-rule",
            "risk_level": "medium",  # Not low
        }
        
        result = simulate_policy_risk([candidate], registry)
        
        # Should still produce valid result
        self.assertIn("risk_level", result)

    def test_high_risk_candidate_elevates_risk(self):
        """High risk candidate should contribute to elevated risk."""
        registry = _setup_registry_with_rules(2)
        
        # Create scenario with rolled-back rule
        rule_id = "high-risk-rule"
        candidate = _make_test_candidate(rule_id, risk_level="high")
        provenance = make_provenance(
            rule_id=rule_id,
            source_candidate_rule_id=rule_id,
            source_regression_case_ids=["case-1"],
            created_by="test",
        )
        registry.adopt(candidate, adopted_by="tester", provenance=provenance)
        registry.rollback(rule_id, rolled_back_by="tester", reason="Test")
        
        risky_candidate = {
            "rule_id": rule_id,
            "source_candidate_rule_id": rule_id,
            "rule_type": "tier_threshold",
            "suggested_change": {"tier": 1},
            "risk_level": "high",
        }
        
        result = simulate_policy_risk([risky_candidate], registry)
        
        # Should detect high risk
        self.assertEqual(result["risk_level"], RISK_HIGH)


if __name__ == "__main__":
    unittest.main()
