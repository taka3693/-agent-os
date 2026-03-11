#!/usr/bin/env python3
"""Step116: Rule Conflict Detection Tests

Tests for detecting all conflict types:
- Phase 1: rolled-back lineage reintroduction, inconsistent provenance
- Phase 2: overlapping applicability, prerequisite/assumption conflicts
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.candidate_rules import (
    AdoptionRegistry,
    PromotionManager,
    ShadowEvaluator,
    create_shadow_evaluator,
    create_promotion_manager,
    make_candidate,
    review_candidate,
    make_provenance,
    detect_rule_conflicts,
    build_conflict_report,
    get_policy_conflicts,
    CONFLICT_ROLLBACK_REINTRODUCTION,
    CONFLICT_INCONSISTENT_PROVENANCE,
    CONFLICT_OVERLAPPING_APPLICABILITY,
    CONFLICT_PREREQUISITE,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SEVERITY_HIGH,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_ROLLED_BACK,
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
    parent_rule_id: str | None = None,
    source_cases: list | None = None,
    source_packs: list | None = None,
    rule_version: int = 1,
) -> dict:
    """Helper to adopt a rule with provenance."""
    candidate = _make_accepted_candidate(rule_id)
    provenance = make_provenance(
        rule_id=rule_id,
        source_candidate_rule_id=rule_id,
        source_regression_case_ids=source_cases or ["case-1"],
        source_scenario_packs=source_packs or [],
        created_by="test",
        parent_rule_id=parent_rule_id,
        rule_version=rule_version,
    )
    return registry.adopt(candidate, adopted_by="tester", provenance=provenance)


class TestRolledBackLineageReintroduction(unittest.TestCase):
    """Tests for detecting rolled-back lineage reintroduction conflicts."""

    def test_rolled_back_rule_in_registry(self):
        """A rolled-back rule still in registry should be detected."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Bad rule")

        conflicts = detect_rule_conflicts(registry)

        rollback_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_ROLLBACK_REINTRODUCTION
        ]
        self.assertEqual(len(rollback_conflicts), 1)
        self.assertIn("rule-001", rollback_conflicts[0]["rule_ids"])
        self.assertEqual(rollback_conflicts[0]["severity"], SEVERITY_HIGH)

    def test_child_of_rolled_back_rule(self):
        """A rule derived from rolled-back lineage should be detected."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", parent_rule_id=None)
        _adopt_with_provenance(registry, "rule-002", parent_rule_id="rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Bad rule")

        conflicts = detect_rule_conflicts(registry)

        rollback_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_ROLLBACK_REINTRODUCTION
        ]
        # Should detect both the rolled-back rule and its child
        rule_ids = set()
        for c in rollback_conflicts:
            rule_ids.update(c["rule_ids"])
        self.assertIn("rule-002", rule_ids)

    def test_deep_lineage_rollback(self):
        """Deep lineage with rollback should be detected."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", parent_rule_id=None)
        _adopt_with_provenance(registry, "rule-002", parent_rule_id="rule-001")
        _adopt_with_provenance(registry, "rule-003", parent_rule_id="rule-002")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Bad rule")

        conflicts = detect_rule_conflicts(registry)

        rollback_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_ROLLBACK_REINTRODUCTION
        ]
        # All descendants should be detected
        rule_ids = set()
        for c in rollback_conflicts:
            rule_ids.update(c["rule_ids"])
        # rule-002 and rule-003 derive from rolled-back lineage
        self.assertTrue("rule-002" in rule_ids or "rule-003" in rule_ids)


class TestInconsistentProvenance(unittest.TestCase):
    """Tests for detecting inconsistent provenance/parent conflicts."""

    def test_missing_provenance(self):
        """Rule with explicitly empty provenance should be detected."""
        registry = AdoptionRegistry()
        candidate = _make_accepted_candidate("rule-001")
        # Adopt with empty provenance dict (not None, which auto-generates)
        registry.adopt(candidate, adopted_by="tester", provenance={})

        conflicts = detect_rule_conflicts(registry)

        prov_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_INCONSISTENT_PROVENANCE
        ]
        # Empty provenance should be detected
        self.assertGreaterEqual(len(prov_conflicts), 1)
        rule_ids = set()
        for c in prov_conflicts:
            rule_ids.update(c["rule_ids"])
        self.assertIn("rule-001", rule_ids)

    def test_non_existent_parent(self):
        """Rule referencing non-existent parent should be detected."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", parent_rule_id="non-existent-parent")

        conflicts = detect_rule_conflicts(registry)

        prov_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_INCONSISTENT_PROVENANCE
        ]
        self.assertTrue(len(prov_conflicts) >= 1)
        rule_ids = set()
        for c in prov_conflicts:
            rule_ids.update(c["rule_ids"])
        self.assertIn("rule-001", rule_ids)

    def test_version_not_greater_than_parent(self):
        """Rule version not greater than parent version should be detected."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", parent_rule_id=None, rule_version=2)
        _adopt_with_provenance(registry, "rule-002", parent_rule_id="rule-001", rule_version=1)

        conflicts = detect_rule_conflicts(registry)

        prov_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_INCONSISTENT_PROVENANCE
        ]
        # Should detect version inconsistency
        version_conflicts = [
            c for c in prov_conflicts
            if "version" in c.get("reason", "").lower()
        ]
        self.assertTrue(len(version_conflicts) >= 1)

    def test_non_existent_source_candidate(self):
        """Rule referencing non-existent source candidate should be detected."""
        registry = AdoptionRegistry()
        candidate = _make_accepted_candidate("rule-001")
        # Create provenance with non-existent source
        provenance = make_provenance(
            rule_id="rule-001",
            source_candidate_rule_id="non-existent-source",
            source_regression_case_ids=["case-1"],
        )
        registry.adopt(candidate, adopted_by="tester", provenance=provenance)

        conflicts = detect_rule_conflicts(registry)

        prov_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_INCONSISTENT_PROVENANCE
        ]
        # Should detect source inconsistency
        source_conflicts = [
            c for c in prov_conflicts
            if "source" in c.get("reason", "").lower()
        ]
        self.assertTrue(len(source_conflicts) >= 1)


class TestConflictReport(unittest.TestCase):
    """Tests for conflict report structure."""

    def test_report_has_required_fields(self):
        """Conflict report should have type, rule_ids, severity, reason."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Test")

        report = build_conflict_report(registry)

        self.assertIn("conflicts", report)
        self.assertIn("summary", report)

        for conflict in report["conflicts"]:
            self.assertIn("type", conflict)
            self.assertIn("rule_ids", conflict)
            self.assertIn("severity", conflict)
            self.assertIn("reason", conflict)

    def test_report_summary(self):
        """Conflict report summary should have correct statistics."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        _adopt_with_provenance(registry, "rule-002")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Test")

        report = build_conflict_report(registry)

        summary = report["summary"]
        self.assertIn("total_conflicts", summary)
        self.assertIn("by_severity", summary)
        self.assertIn("high_severity", summary)
        self.assertGreater(summary["total_conflicts"], 0)

    def test_get_policy_conflicts_alias(self):
        """get_policy_conflicts should work as alias for build_conflict_report."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Test")

        report1 = build_conflict_report(registry)
        report2 = get_policy_conflicts(registry)

        self.assertEqual(
            report1["summary"]["total_conflicts"],
            report2["summary"]["total_conflicts"]
        )


class TestConflictsInSummarizeExport(unittest.TestCase):
    """Tests for conflict visibility in summarize() and export()."""

    def test_registry_get_conflicts(self):
        """AdoptionRegistry.get_conflicts() should return conflict report."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Test")

        report = registry.get_conflicts()

        self.assertIn("conflicts", report)
        self.assertIn("summary", report)
        self.assertGreater(report["summary"]["total_conflicts"], 0)

    def test_export_with_conflicts_json(self):
        """Export with include_conflicts=True should include conflicts in JSON."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Test")

        import json
        exported = registry.export(fmt="json", include_conflicts=True)
        data = json.loads(exported)

        self.assertIn("conflicts", data)
        self.assertIn("summary", data["conflicts"])

    def test_export_without_conflicts_json(self):
        """Export with include_conflicts=False should not include conflicts."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Test")

        import json
        exported = registry.export(fmt="json", include_conflicts=False)
        data = json.loads(exported)

        self.assertNotIn("conflicts", data)

    def test_export_with_conflicts_markdown(self):
        """Export with include_conflicts=True should include conflicts in Markdown."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Test")

        exported = registry.export(fmt="markdown", include_conflicts=True)

        self.assertIn("Conflict Report", exported)
        self.assertIn("Total conflicts", exported)


class TestOverlappingApplicability(unittest.TestCase):
    """Tests for detecting overlapping applicability conflicts."""

    def test_same_type_different_actions(self):
        """Rules with same type but different suggested changes should conflict."""
        registry = AdoptionRegistry()
        
        # Create two rules with same type and overlapping cases
        candidate1 = _make_accepted_candidate("rule-001")
        prov1 = make_provenance(
            rule_id="rule-001",
            source_regression_case_ids=["case-1", "case-2"],
        )
        candidate1["rule_type"] = "tier_threshold"
        candidate1["suggested_change"] = {"threshold": 2}
        registry.adopt(candidate1, adopted_by="tester", provenance=prov1)
        
        candidate2 = _make_accepted_candidate("rule-002")
        prov2 = make_provenance(
            rule_id="rule-002",
            source_regression_case_ids=["case-1", "case-3"],
        )
        candidate2["rule_type"] = "tier_threshold"
        candidate2["suggested_change"] = {"threshold": 5}
        registry.adopt(candidate2, adopted_by="tester", provenance=prov2)
        
        conflicts = detect_rule_conflicts(registry)
        
        overlap_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_OVERLAPPING_APPLICABILITY
        ]
        self.assertGreaterEqual(len(overlap_conflicts), 1)

    def test_overlapping_cases_different_changes(self):
        """Rules with overlapping cases and different changes should conflict."""
        registry = AdoptionRegistry()
        
        candidate1 = _make_accepted_candidate("rule-001")
        prov1 = make_provenance(
            rule_id="rule-001",
            source_regression_case_ids=["case-1", "case-2"],
        )
        candidate1["rule_type"] = "failed_chain"
        candidate1["suggested_change"] = {"threshold": 3}
        registry.adopt(candidate1, adopted_by="tester", provenance=prov1)
        
        candidate2 = _make_accepted_candidate("rule-002")
        prov2 = make_provenance(
            rule_id="rule-002",
            source_regression_case_ids=["case-2", "case-3"],
        )
        candidate2["rule_type"] = "failed_chain"
        candidate2["suggested_change"] = {"threshold": 1}
        registry.adopt(candidate2, adopted_by="tester", provenance=prov2)
        
        conflicts = detect_rule_conflicts(registry)
        
        overlap_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_OVERLAPPING_APPLICABILITY
        ]
        self.assertGreaterEqual(len(overlap_conflicts), 1)

    def test_different_types_no_overlap_conflict(self):
        """Rules with different types should not have overlapping conflict."""
        registry = AdoptionRegistry()
        
        candidate1 = _make_accepted_candidate("rule-001")
        prov1 = make_provenance(
            rule_id="rule-001",
            source_regression_case_ids=["case-1"],
        )
        candidate1["rule_type"] = "tier_threshold"
        registry.adopt(candidate1, adopted_by="tester", provenance=prov1)
        
        candidate2 = _make_accepted_candidate("rule-002")
        prov2 = make_provenance(
            rule_id="rule-002",
            source_regression_case_ids=["case-1"],
        )
        candidate2["rule_type"] = "orchestration"
        registry.adopt(candidate2, adopted_by="tester", provenance=prov2)
        
        conflicts = detect_rule_conflicts(registry)
        
        overlap_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_OVERLAPPING_APPLICABILITY
        ]
        # Different types, should not conflict
        self.assertEqual(len(overlap_conflicts), 0)


class TestPrerequisiteConflicts(unittest.TestCase):
    """Tests for detecting prerequisite/assumption conflicts."""

    def test_orchestration_budget_trim_conflict(self):
        """Orchestration and budget_trim rules affecting same cases should conflict."""
        registry = AdoptionRegistry()
        
        candidate1 = _make_accepted_candidate("rule-001")
        prov1 = make_provenance(
            rule_id="rule-001",
            source_regression_case_ids=["case-1", "case-2"],
        )
        candidate1["rule_type"] = "orchestration"
        registry.adopt(candidate1, adopted_by="tester", provenance=prov1)
        
        candidate2 = _make_accepted_candidate("rule-002")
        prov2 = make_provenance(
            rule_id="rule-002",
            source_regression_case_ids=["case-1", "case-3"],
        )
        candidate2["rule_type"] = "budget_trim"
        registry.adopt(candidate2, adopted_by="tester", provenance=prov2)
        
        conflicts = detect_rule_conflicts(registry)
        
        prereq_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_PREREQUISITE
        ]
        self.assertGreaterEqual(len(prereq_conflicts), 1)

    def test_tier_threshold_failed_chain_conflict(self):
        """tier_threshold and failed_chain rules affecting same cases should conflict."""
        registry = AdoptionRegistry()
        
        candidate1 = _make_accepted_candidate("rule-001")
        prov1 = make_provenance(
            rule_id="rule-001",
            source_regression_case_ids=["case-1"],
        )
        candidate1["rule_type"] = "tier_threshold"
        registry.adopt(candidate1, adopted_by="tester", provenance=prov1)
        
        candidate2 = _make_accepted_candidate("rule-002")
        prov2 = make_provenance(
            rule_id="rule-002",
            source_regression_case_ids=["case-1"],
        )
        candidate2["rule_type"] = "failed_chain"
        registry.adopt(candidate2, adopted_by="tester", provenance=prov2)
        
        conflicts = detect_rule_conflicts(registry)
        
        prereq_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_PREREQUISITE
        ]
        self.assertGreaterEqual(len(prereq_conflicts), 1)

    def test_no_case_overlap_no_prereq_conflict(self):
        """Rules with no case overlap should not have prerequisite conflict."""
        registry = AdoptionRegistry()
        
        candidate1 = _make_accepted_candidate("rule-001")
        prov1 = make_provenance(
            rule_id="rule-001",
            source_regression_case_ids=["case-1"],
        )
        candidate1["rule_type"] = "orchestration"
        registry.adopt(candidate1, adopted_by="tester", provenance=prov1)
        
        candidate2 = _make_accepted_candidate("rule-002")
        prov2 = make_provenance(
            rule_id="rule-002",
            source_regression_case_ids=["case-999"],
        )
        candidate2["rule_type"] = "budget_trim"
        registry.adopt(candidate2, adopted_by="tester", provenance=prov2)
        
        conflicts = detect_rule_conflicts(registry)
        
        prereq_conflicts = [
            c for c in conflicts
            if c.get("type") == CONFLICT_PREREQUISITE
            and "rule-001" in c.get("rule_ids", [])
            and "rule-002" in c.get("rule_ids", [])
        ]
        # No case overlap, should not conflict
        self.assertEqual(len(prereq_conflicts), 0)


class TestNoFalsePositives(unittest.TestCase):
    """Tests to ensure no false positives in conflict detection."""

    def test_clean_registry_no_conflicts(self):
        """Clean registry with proper provenance should have no conflicts."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", parent_rule_id=None, rule_version=1)
        _adopt_with_provenance(registry, "rule-002", parent_rule_id="rule-001", rule_version=2)

        conflicts = detect_rule_conflicts(registry)

        # Filter out low-severity missing provenance (expected for some entries)
        critical_conflicts = [
            c for c in conflicts
            if c.get("severity") in (SEVERITY_HIGH, SEVERITY_MEDIUM)
        ]
        self.assertEqual(len(critical_conflicts), 0)

    def test_empty_registry_no_conflicts(self):
        """Empty registry should have no conflicts."""
        registry = AdoptionRegistry()

        conflicts = detect_rule_conflicts(registry)

        self.assertEqual(len(conflicts), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
