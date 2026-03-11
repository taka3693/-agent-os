#!/usr/bin/env python3
"""Step122: Explainable Decision Report Tests

Tests for generating human-readable explanations of auto-evolution decisions.
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
    build_decision_explanation,
    build_explainable_decision_report,
    get_decision_explanation,
    DECISION_AUTO_PROMOTE,
    DECISION_REVIEW_REQUIRED,
    DECISION_HALT,
    DECISION_ROLLBACK_RECOMMENDED,
    DECISION_REJECT,
    DECISION_NO_ACTION,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_ROLLED_BACK,
    SEVERITY_HIGH,
    PRIORITY_HIGH,
    PRIORITY_LOW,
)


def _make_accepted_candidate(rule_id: str, rule_type: str = "tier_threshold", risk_level: str = "low") -> dict:
    """Helper to create an accepted candidate."""
    c = make_candidate(
        candidate_rule_id=rule_id,
        description="Test rule",
        expected_effect="Test effect",
        affected_cases=["case-1"],
        risk_level=risk_level,
        recommendation="adopt",
        rule_type=rule_type,
        suggested_change={"test": 1},
    )
    return review_candidate(c, decision="accepted", reviewer="tester")


def _adopt_with_provenance(
    registry: AdoptionRegistry,
    rule_id: str,
    parent_rule_id: str | None = None,
    source_cases: list | None = None,
    rule_version: int = 1,
    with_provenance: bool = True,
    risk_level: str = "low",
    rule_type: str = "tier_threshold",
) -> dict:
    """Helper to adopt a rule with provenance."""
    candidate = _make_accepted_candidate(rule_id, rule_type=rule_type, risk_level=risk_level)
    if with_provenance:
        provenance = make_provenance(
            rule_id=rule_id,
            source_candidate_rule_id=rule_id,
            source_regression_case_ids=source_cases or ["case-1"],
            source_scenario_packs=[],
            created_by="test",
            parent_rule_id=parent_rule_id,
            rule_version=rule_version,
        )
    else:
        provenance = {}
    return registry.adopt(candidate, adopted_by="tester", provenance=provenance)


class TestBuildDecisionExplanation(unittest.TestCase):
    """Tests for build_decision_explanation()."""

    def test_explanation_has_required_fields(self):
        """Explanation should have all required fields."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)

        explanation = build_decision_explanation("rule-001", registry)

        # Required fields
        self.assertIn("rule_id", explanation)
        self.assertIn("decision", explanation)
        self.assertIn("confidence", explanation)
        self.assertIn("reasons", explanation)
        self.assertIn("signals", explanation)
        self.assertIn("provenance", explanation)
        self.assertIn("lineage", explanation)
        self.assertIn("conflicts", explanation)
        self.assertIn("bundle", explanation)
        self.assertIn("health", explanation)
        self.assertIn("review", explanation)
        self.assertIn("human_summary", explanation)

    def test_rule_not_found_returns_reject_explanation(self):
        """Non-existent rule should return reject explanation."""
        registry = AdoptionRegistry()

        explanation = build_decision_explanation("nonexistent", registry)

        self.assertEqual(explanation["decision"], DECISION_REJECT)
        self.assertIn("reject", explanation["human_summary"].lower())

    def test_provenance_summary_populated(self):
        """Provenance summary should be populated for rules with provenance."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(
            registry, "rule-001",
            parent_rule_id="parent-001",
            rule_version=2,
            with_provenance=True
        )

        explanation = build_decision_explanation("rule-001", registry)

        prov = explanation["provenance"]
        self.assertIsNotNone(prov)
        self.assertEqual(prov.get("source_candidate_rule_id"), "rule-001")
        self.assertEqual(prov.get("parent_rule_id"), "parent-001")
        self.assertEqual(prov.get("rule_version"), 2)

    def test_lineage_summary_populated(self):
        """Lineage summary should be populated."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-parent", with_provenance=True)
        _adopt_with_provenance(
            registry, "rule-child",
            parent_rule_id="rule-parent",
            rule_version=2
        )

        explanation = build_decision_explanation("rule-child", registry)

        lineage = explanation["lineage"]
        self.assertIn("depth", lineage)
        self.assertIn("has_parent", lineage)
        self.assertEqual(lineage["depth"], 1)
        self.assertTrue(lineage["has_parent"])


class TestAutoPromoteExplanation(unittest.TestCase):
    """Tests for auto_promote decision explanations."""

    def test_auto_promote_explanation_generated(self):
        """Auto-promote decision should have appropriate explanation."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)

        explanation = build_decision_explanation("rule-001", registry)

        self.assertEqual(explanation["decision"], DECISION_AUTO_PROMOTE)
        self.assertIn("auto_promote", explanation["human_summary"].lower())


class TestHaltExplanation(unittest.TestCase):
    """Tests for halt decision explanations."""

    def test_halt_explanation_for_rollback_reintroduction(self):
        """Halt decision for rollback reintroduction should have appropriate explanation."""
        registry = AdoptionRegistry()
        
        # Create rolled-back parent
        _adopt_with_provenance(registry, "rule-parent", with_provenance=True)
        registry.rollback("rule-parent", rolled_back_by="tester", reason="Bad")
        
        # Create child from rolled-back parent
        _adopt_with_provenance(
            registry, "rule-child",
            parent_rule_id="rule-parent",
            rule_version=2
        )

        explanation = build_decision_explanation("rule-child", registry)

        self.assertEqual(explanation["decision"], DECISION_HALT)
        self.assertIn("halt", explanation["human_summary"].lower())
        
        # Conflicts should show rollback reintroduction
        conflicts = explanation["conflicts"]
        self.assertIn("rollback_lineage_reintroduction", conflicts.get("types", []))


class TestReviewRequiredExplanation(unittest.TestCase):
    """Tests for review_required decision explanations."""

    def test_review_required_explanation_generated(self):
        """Review_required decision should have appropriate explanation."""
        registry = AdoptionRegistry()
        
        # Create rules with deep lineage (triggers review_required)
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        _adopt_with_provenance(
            registry, "rule-002",
            parent_rule_id="rule-001",
            rule_version=2
        )
        _adopt_with_provenance(
            registry, "rule-003",
            parent_rule_id="rule-002",
            rule_version=3
        )
        _adopt_with_provenance(
            registry, "rule-004",
            parent_rule_id="rule-003",
            rule_version=4
        )

        explanation = build_decision_explanation("rule-004", registry)

        # Should be review_required due to deep lineage
        self.assertEqual(explanation["decision"], DECISION_REVIEW_REQUIRED)
        self.assertIn("review", explanation["human_summary"].lower())


class TestRejectExplanation(unittest.TestCase):
    """Tests for reject decision explanations."""

    def test_reject_explanation_for_missing_provenance(self):
        """Reject decision for missing provenance should have appropriate explanation."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=False)

        explanation = build_decision_explanation("rule-001", registry)

        self.assertEqual(explanation["decision"], DECISION_REJECT)
        self.assertIn("provenance", explanation["human_summary"].lower())


class TestNoActionExplanation(unittest.TestCase):
    """Tests for no_action decision explanations."""

    def test_no_action_for_rolled_back_rule(self):
        """No_action decision for rolled-back rule should have appropriate explanation."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        registry.rollback("rule-001", rolled_back_by="tester", reason="Test")

        explanation = build_decision_explanation("rule-001", registry)

        self.assertEqual(explanation["decision"], DECISION_NO_ACTION)
        self.assertIn("rolled_back", explanation["human_summary"].lower())


class TestBuildExplainableDecisionReport(unittest.TestCase):
    """Tests for build_explainable_decision_report()."""

    def test_report_has_explanations_and_summary(self):
        """Report should have explanations list and summary dict."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        _adopt_with_provenance(registry, "rule-002", with_provenance=False)

        report = build_explainable_decision_report(registry)

        self.assertIn("explanations", report)
        self.assertIn("summary", report)
        self.assertIsInstance(report["explanations"], list)
        self.assertEqual(len(report["explanations"]), 2)

    def test_summary_counts_by_decision(self):
        """Summary should count explanations by decision type."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        _adopt_with_provenance(registry, "rule-002", with_provenance=False)

        report = build_explainable_decision_report(registry)

        summary = report["summary"]
        self.assertIn(DECISION_AUTO_PROMOTE, summary)
        self.assertIn(DECISION_REJECT, summary)
        self.assertIn("total", summary)
        
        # Total should match sum
        total = sum(v for k, v in summary.items() if k != "total")
        self.assertEqual(total, summary["total"])

    def test_specific_rule_ids_explained(self):
        """Can explain specific rule IDs only."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        _adopt_with_provenance(registry, "rule-002", with_provenance=True)
        _adopt_with_provenance(registry, "rule-003", with_provenance=True)

        report = build_explainable_decision_report(
            registry,
            rule_ids=["rule-001", "rule-003"]
        )

        self.assertEqual(len(report["explanations"]), 2)
        rule_ids = {e["rule_id"] for e in report["explanations"]}
        self.assertIn("rule-001", rule_ids)
        self.assertIn("rule-003", rule_ids)
        self.assertNotIn("rule-002", rule_ids)


class TestHumanSummary(unittest.TestCase):
    """Tests for human_summary content."""

    def test_human_summary_includes_decision_reason(self):
        """Human summary should include the reason for the decision."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)

        explanation = build_decision_explanation("rule-001", registry)

        # Human summary should be non-empty string
        self.assertIsInstance(explanation["human_summary"], str)
        self.assertGreater(len(explanation["human_summary"]), 0)

    def test_human_summary_for_halt_mentions_reason(self):
        """Human summary for halt should mention the halt reason."""
        registry = AdoptionRegistry()
        
        # Create rolled-back parent
        _adopt_with_provenance(registry, "rule-parent", with_provenance=True)
        registry.rollback("rule-parent", rolled_back_by="tester", reason="Bad")
        
        # Create child from rolled-back parent
        _adopt_with_provenance(
            registry, "rule-child",
            parent_rule_id="rule-parent",
            rule_version=2
        )

        explanation = build_decision_explanation("rule-child", registry)

        # Should mention rollback in human summary
        summary = explanation["human_summary"].lower()
        self.assertTrue(
            "rollback" in summary or "系統" in explanation["human_summary"],
            f"Expected rollback mention in: {explanation['human_summary']}"
        )


class TestExportWithExplanations(unittest.TestCase):
    """Tests for export() with include_explanations option."""

    def test_export_json_with_explanations(self):
        """Export with include_explanations should include explanations."""
        import json
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)

        exported = registry.export(fmt="json", include_explanations=True)
        data = json.loads(exported)

        self.assertIn("explanations", data)
        self.assertIn("explanations", data["explanations"])
        self.assertIn("summary", data["explanations"])

    def test_export_json_without_explanations(self):
        """Export without include_explanations should not include explanations."""
        import json
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        exported = registry.export(fmt="json", include_explanations=False)
        data = json.loads(exported)

        self.assertNotIn("explanations", data)

    def test_registry_get_decision_explanation(self):
        """Registry should have get_decision_explanation method."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)

        report = registry.get_decision_explanation()

        self.assertIn("explanations", report)
        self.assertIn("summary", report)


class TestExplanationSignals(unittest.TestCase):
    """Tests for signals in explanations."""

    def test_signals_include_health_score(self):
        """Signals should include health_score."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)

        explanation = build_decision_explanation("rule-001", registry)

        self.assertIn("health_score", explanation["signals"])

    def test_signals_include_review_priority(self):
        """Signals should include review priority score."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)

        explanation = build_decision_explanation("rule-001", registry)

        self.assertIn("review_priority_score", explanation["signals"])

    def test_review_summary_includes_priority(self):
        """Review summary should include priority score and level."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)

        explanation = build_decision_explanation("rule-001", registry)

        review = explanation["review"]
        self.assertIn("priority_score", review)
        self.assertIn("priority_level", review)


class TestExplanationConsistency(unittest.TestCase):
    """Tests for consistency between decision and explanation."""

    def test_decision_matches_explanation(self):
        """Decision in explanation should match the auto-evolution decision."""
        registry = AdoptionRegistry()
        
        # Create rules with different characteristics
        _adopt_with_provenance(registry, "rule-safe", with_provenance=True)
        _adopt_with_provenance(registry, "rule-noprov", with_provenance=False)

        report = build_explainable_decision_report(registry)

        # Each explanation's decision should be valid
        for exp in report["explanations"]:
            self.assertIn(
                exp["decision"],
                [
                    DECISION_AUTO_PROMOTE,
                    DECISION_REVIEW_REQUIRED,
                    DECISION_HALT,
                    DECISION_ROLLBACK_RECOMMENDED,
                    DECISION_REJECT,
                    DECISION_NO_ACTION,
                ]
            )

    def test_summary_counts_match_explanations(self):
        """Summary counts should match actual explanation counts."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        _adopt_with_provenance(registry, "rule-002", with_provenance=False)
        _adopt_with_provenance(registry, "rule-003", with_provenance=True)

        report = build_explainable_decision_report(registry)

        # Count by decision
        decision_counts = {}
        for exp in report["explanations"]:
            d = exp["decision"]
            decision_counts[d] = decision_counts.get(d, 0) + 1

        # Verify summary matches
        summary = report["summary"]
        for decision, count in decision_counts.items():
            self.assertEqual(summary.get(decision, 0), count)


class TestGetDecisionExplanationAlias(unittest.TestCase):
    """Tests for get_decision_explanation alias function."""

    def test_get_decision_explanation_returns_same_as_build(self):
        """get_decision_explanation should return same as build_explainable_decision_report."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)

        report1 = build_explainable_decision_report(registry)
        report2 = get_decision_explanation(registry)

        self.assertEqual(len(report1["explanations"]), len(report2["explanations"]))
        self.assertEqual(report1["summary"]["total"], report2["summary"]["total"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
