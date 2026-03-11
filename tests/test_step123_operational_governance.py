#!/usr/bin/env python3
"""Step123: Operational Governance Layer Tests

Tests for operational governance policy including roles, guardrails, and metrics.
"""
from __future__ import annotations

import json
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
    get_governance_roles,
    get_promotion_guardrails,
    get_operational_metrics,
    build_operational_governance_policy,
    get_governance_policy,
    compute_operational_metrics_report,
    ROLE_POLICY_MAINTAINER,
    ROLE_SAFETY_REVIEWER,
    ROLE_SYSTEM_AUDITOR,
    ROLE_OPERATOR,
    DECISION_AUTO_PROMOTE,
    DECISION_REVIEW_REQUIRED,
    DECISION_HALT,
)


def _make_accepted_candidate(rule_id: str, risk_level: str = "low") -> dict:
    """Helper to create an accepted candidate."""
    c = make_candidate(
        candidate_rule_id=rule_id,
        description="Test rule",
        expected_effect="Test effect",
        affected_cases=["case-1"],
        risk_level=risk_level,
        recommendation="adopt",
        rule_type="tier_threshold",
        suggested_change={"test": 1},
    )
    return review_candidate(c, decision="accepted", reviewer="tester")


def _adopt_with_provenance(
    registry: AdoptionRegistry,
    rule_id: str,
    with_provenance: bool = True,
) -> dict:
    """Helper to adopt a rule with provenance."""
    candidate = _make_accepted_candidate(rule_id)
    if with_provenance:
        provenance = make_provenance(
            rule_id=rule_id,
            source_candidate_rule_id=rule_id,
            source_regression_case_ids=["case-1"],
            created_by="test",
        )
    else:
        provenance = {}
    return registry.adopt(candidate, adopted_by="tester", provenance=provenance)


class TestGetGovernanceRoles(unittest.TestCase):
    """Tests for get_governance_roles()."""

    def test_roles_returned(self):
        """Roles should be returned."""
        roles = get_governance_roles()
        
        self.assertIsInstance(roles, list)
        self.assertGreater(len(roles), 0)

    def test_all_required_roles_present(self):
        """All required roles should be defined."""
        roles = get_governance_roles()
        role_names = {r["role_name"] for r in roles}
        
        self.assertIn(ROLE_POLICY_MAINTAINER, role_names)
        self.assertIn(ROLE_SAFETY_REVIEWER, role_names)
        self.assertIn(ROLE_SYSTEM_AUDITOR, role_names)
        self.assertIn(ROLE_OPERATOR, role_names)

    def test_roles_have_required_fields(self):
        """Each role should have required fields."""
        roles = get_governance_roles()
        
        for role in roles:
            self.assertIn("role_name", role)
            self.assertIn("responsibilities", role)
            self.assertIn("can_approve", role)
            self.assertIn("can_block", role)
            self.assertIn("review_scope", role)


class TestGetPromotionGuardrails(unittest.TestCase):
    """Tests for get_promotion_guardrails()."""

    def test_guardrails_returned(self):
        """Guardrails should be returned."""
        guardrails = get_promotion_guardrails()
        
        self.assertIsInstance(guardrails, list)
        self.assertGreater(len(guardrails), 0)

    def test_guardrails_have_required_fields(self):
        """Each guardrail should have required fields."""
        guardrails = get_promotion_guardrails()
        
        for guardrail in guardrails:
            self.assertIn("name", guardrail)
            self.assertIn("condition", guardrail)
            self.assertIn("action", guardrail)
            self.assertIn("rationale", guardrail)

    def test_high_conflict_guardrail_exists(self):
        """Guardrail for high severity conflict should exist."""
        guardrails = get_promotion_guardrails()
        
        high_conflict_guardrails = [
            g for g in guardrails
            if "high" in g.get("condition", "").lower() and "conflict" in g.get("condition", "").lower()
        ]
        
        self.assertGreater(len(high_conflict_guardrails), 0)

    def test_provenance_missing_guardrail_exists(self):
        """Guardrail for provenance missing should exist."""
        guardrails = get_promotion_guardrails()
        
        prov_guardrails = [
            g for g in guardrails
            if "provenance" in g.get("condition", "").lower()
        ]
        
        self.assertGreater(len(prov_guardrails), 0)

    def test_rollback_lineage_guardrail_exists(self):
        """Guardrail for rollback lineage reintroduction should exist."""
        guardrails = get_promotion_guardrails()
        
        rollback_guardrails = [
            g for g in guardrails
            if "rollback" in g.get("condition", "").lower()
        ]
        
        self.assertGreater(len(rollback_guardrails), 0)


class TestGetOperationalMetrics(unittest.TestCase):
    """Tests for get_operational_metrics()."""

    def test_metrics_returned(self):
        """Metrics should be returned."""
        metrics = get_operational_metrics()
        
        self.assertIsInstance(metrics, list)
        self.assertGreater(len(metrics), 0)

    def test_metrics_have_required_fields(self):
        """Each metric should have required fields."""
        metrics = get_operational_metrics()
        
        for metric in metrics:
            self.assertIn("metric_name", metric)
            self.assertIn("description", metric)
            self.assertIn("interpretation", metric)
            self.assertIn("risk_signal", metric)

    def test_required_metrics_present(self):
        """Required metrics should be defined."""
        metrics = get_operational_metrics()
        metric_names = {m["metric_name"] for m in metrics}
        
        required_metrics = [
            "health_score_trend",
            "conflict_rate",
            "rollback_rate",
            "auto_promote_ratio",
            "review_required_ratio",
            "halt_ratio",
            "harmful_bundle_ratio",
        ]
        
        for required in required_metrics:
            self.assertIn(required, metric_names, f"Missing required metric: {required}")


class TestBuildOperationalGovernancePolicy(unittest.TestCase):
    """Tests for build_operational_governance_policy()."""

    def test_policy_has_required_sections(self):
        """Governance policy should have roles, guardrails, and metrics."""
        policy = build_operational_governance_policy()
        
        self.assertIn("roles", policy)
        self.assertIn("guardrails", policy)
        self.assertIn("metrics", policy)

    def test_policy_roles_match_standalone(self):
        """Policy roles should match get_governance_roles()."""
        policy = build_operational_governance_policy()
        roles = get_governance_roles()
        
        self.assertEqual(len(policy["roles"]), len(roles))

    def test_policy_guardrails_match_standalone(self):
        """Policy guardrails should match get_promotion_guardrails()."""
        policy = build_operational_governance_policy()
        guardrails = get_promotion_guardrails()
        
        self.assertEqual(len(policy["guardrails"]), len(guardrails))

    def test_policy_metrics_match_standalone(self):
        """Policy metrics should match get_operational_metrics()."""
        policy = build_operational_governance_policy()
        metrics = get_operational_metrics()
        
        self.assertEqual(len(policy["metrics"]), len(metrics))


class TestGetGovernancePolicyAlias(unittest.TestCase):
    """Tests for get_governance_policy alias function."""

    def test_alias_returns_same_as_build(self):
        """get_governance_policy should return same as build_operational_governance_policy."""
        policy1 = build_operational_governance_policy()
        policy2 = get_governance_policy()
        
        self.assertEqual(len(policy1["roles"]), len(policy2["roles"]))
        self.assertEqual(len(policy1["guardrails"]), len(policy2["guardrails"]))
        self.assertEqual(len(policy1["metrics"]), len(policy2["metrics"]))


class TestComputeOperationalMetricsReport(unittest.TestCase):
    """Tests for compute_operational_metrics_report()."""

    def test_empty_registry(self):
        """Empty registry should return empty metrics."""
        registry = AdoptionRegistry()
        report = compute_operational_metrics_report(registry)
        
        self.assertIn("metrics", report)
        self.assertIn("summary", report)
        self.assertEqual(report["summary"]["total_rules"], 0)

    def test_healthy_registry_metrics(self):
        """Healthy registry should have good metrics."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        
        report = compute_operational_metrics_report(registry)
        
        self.assertIn("metrics", report)
        metrics = report["metrics"]
        
        self.assertEqual(metrics["total_rules"], 1)
        self.assertEqual(metrics["provenance_completeness"], 1.0)
        self.assertEqual(metrics["conflict_rate"], 0.0)
        self.assertEqual(metrics["rollback_rate"], 0.0)

    def test_registry_with_issues(self):
        """Registry with issues should reflect in metrics."""
        registry = AdoptionRegistry()
        
        # Add rule with provenance
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        
        # Add rule without provenance
        _adopt_with_provenance(registry, "rule-002", with_provenance=False)
        
        # Rollback one rule
        registry.rollback("rule-001", rolled_back_by="tester", reason="Test")
        
        report = compute_operational_metrics_report(registry)
        
        metrics = report["metrics"]
        
        self.assertEqual(metrics["total_rules"], 2)
        self.assertLess(metrics["provenance_completeness"], 1.0)
        self.assertGreater(metrics["rollback_rate"], 0)


class TestRegistryGovernanceMethods(unittest.TestCase):
    """Tests for AdoptionRegistry governance methods."""

    def test_get_governance_policy(self):
        """Registry should have get_governance_policy method."""
        registry = AdoptionRegistry()
        
        policy = registry.get_governance_policy()
        
        self.assertIn("roles", policy)
        self.assertIn("guardrails", policy)
        self.assertIn("metrics", policy)

    def test_compute_operational_metrics(self):
        """Registry should have compute_operational_metrics method."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        
        report = registry.compute_operational_metrics()
        
        self.assertIn("metrics", report)
        self.assertEqual(report["metrics"]["total_rules"], 1)


class TestExportWithGovernance(unittest.TestCase):
    """Tests for export() with include_governance option."""

    def test_export_json_with_governance(self):
        """Export with include_governance should include governance section."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        
        exported = registry.export(fmt="json", include_governance=True)
        data = json.loads(exported)
        
        self.assertIn("governance", data)
        self.assertIn("operational_metrics", data)
        
        # Verify governance structure
        self.assertIn("roles", data["governance"])
        self.assertIn("guardrails", data["governance"])
        self.assertIn("metrics", data["governance"])

    def test_export_json_without_governance(self):
        """Export without include_governance should not include governance section."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        
        exported = registry.export(fmt="json", include_governance=False)
        data = json.loads(exported)
        
        self.assertNotIn("governance", data)
        self.assertNotIn("operational_metrics", data)


class TestGuardrailCoverage(unittest.TestCase):
    """Tests for guardrail coverage of decision types."""

    def test_no_auto_promote_without_provenance(self):
        """Provenance missing should prevent auto_promote."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=False)
        
        # Import here to avoid circular import
        from eval.candidate_rules import evaluate_auto_evolution_candidate
        
        decision = evaluate_auto_evolution_candidate("rule-001", registry)
        
        # Should be reject, not auto_promote
        self.assertNotEqual(decision["decision"], DECISION_AUTO_PROMOTE)

    def test_no_auto_promote_on_high_conflict(self):
        """High severity conflict should prevent auto_promote."""
        registry = AdoptionRegistry()
        
        # Create rolled-back parent and child (creates high conflict)
        _adopt_with_provenance(registry, "rule-parent")
        registry.rollback("rule-parent", rolled_back_by="tester", reason="Bad")
        
        _adopt_with_provenance(
            registry, "rule-child",
        )
        # Manually set parent to create rollback lineage
        entry = registry.get("rule-child")
        entry["provenance"]["parent_rule_id"] = "rule-parent"
        
        from eval.candidate_rules import evaluate_auto_evolution_candidate
        
        decision = evaluate_auto_evolution_candidate("rule-child", registry)
        
        # Should be halt, not auto_promote
        self.assertEqual(decision["decision"], DECISION_HALT)


class TestMetricsDefinitions(unittest.TestCase):
    """Tests for operational metrics definitions."""

    def test_metrics_have_interpretation(self):
        """Each metric should have interpretation guidance."""
        metrics = get_operational_metrics()
        
        for metric in metrics:
            self.assertIn("interpretation", metric)
            self.assertIsInstance(metric["interpretation"], str)
            self.assertGreater(len(metric["interpretation"]), 0)

    def test_metrics_have_risk_signal(self):
        """Each metric should have risk signal level."""
        metrics = get_operational_metrics()
        
        valid_risk_signals = {"low", "medium", "high"}
        
        for metric in metrics:
            risk_signal = metric.get("risk_signal", "").lower()
            self.assertIn(risk_signal, valid_risk_signals)


if __name__ == "__main__":
    unittest.main(verbosity=2)
