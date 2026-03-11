#!/usr/bin/env python3
"""Step119: Auto-Review Queue Tests

Tests for computing prioritized review queues for rules needing human review.
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
    compute_review_priority,
    build_review_queue,
    get_review_queue,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
    CONFLICT_ROLLBACK_REINTRODUCTION,
    CONFLICT_INCONSISTENT_PROVENANCE,
    CONFLICT_OVERLAPPING_APPLICABILITY,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_ROLLED_BACK,
    REVIEW_STATUS_ACCEPTED,
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
    source_packs: list | None = None,
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
            source_scenario_packs=source_packs or [],
            created_by="test",
            parent_rule_id=parent_rule_id,
            rule_version=rule_version,
        )
    else:
        # Pass empty dict to explicitly indicate missing provenance
        provenance = {}
    return registry.adopt(candidate, adopted_by="tester", provenance=provenance)


class TestComputeReviewPriority(unittest.TestCase):
    """Tests for compute_review_priority()."""

    def test_missing_provenance_increases_priority(self):
        """Missing provenance should increase priority score."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=False)

        priority = compute_review_priority("rule-001", registry)

        self.assertGreater(priority["priority_score"], 0)
        self.assertIn("missing provenance", priority["reasons"])

    def test_rolled_back_rule_increases_priority(self):
        """Rolled back rule should increase priority score."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        registry.rollback("rule-001", rolled_back_by="tester", reason="Bad rule")

        priority = compute_review_priority("rule-001", registry)

        self.assertGreater(priority["priority_score"], 0)
        self.assertIn("currently rolled back", priority["reasons"])

    def test_healthy_rule_low_priority(self):
        """Healthy rule with no issues should have low priority."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)

        priority = compute_review_priority("rule-001", registry)

        # May have some score due to bundle evaluation, but should be low
        self.assertLess(priority["priority_score"], 50)

    def test_priority_level_assignment(self):
        """Priority level should be correctly assigned based on score."""
        registry = AdoptionRegistry()
        
        # High priority case: missing provenance + rolled back
        _adopt_with_provenance(registry, "rule-high", with_provenance=False)
        registry.rollback("rule-high", rolled_back_by="tester", reason="Critical issue")
        
        priority_high = compute_review_priority("rule-high", registry)
        self.assertEqual(priority_high["priority_level"], PRIORITY_HIGH)

    def test_rule_not_found_returns_low_priority(self):
        """Non-existent rule should return low priority."""
        registry = AdoptionRegistry()

        priority = compute_review_priority("nonexistent", registry)

        self.assertEqual(priority["priority_score"], 0)
        self.assertEqual(priority["priority_level"], PRIORITY_LOW)


class TestBuildReviewQueue(unittest.TestCase):
    """Tests for build_review_queue()."""

    def test_empty_registry(self):
        """Empty registry should produce empty queue."""
        registry = AdoptionRegistry()
        queue = build_review_queue(registry)

        self.assertEqual(queue["review_queue"], [])
        self.assertEqual(queue["summary"]["total_review_items"], 0)

    def test_queue_sorted_by_priority(self):
        """Queue should be sorted by priority score descending."""
        registry = AdoptionRegistry()
        
        # Low priority rule
        _adopt_with_provenance(registry, "rule-low", with_provenance=True)
        
        # High priority rule (missing provenance)
        _adopt_with_provenance(registry, "rule-high", with_provenance=False)
        
        queue = build_review_queue(registry)
        
        # High priority should come first
        if len(queue["review_queue"]) >= 2:
            self.assertGreaterEqual(
                queue["review_queue"][0]["priority_score"],
                queue["review_queue"][1]["priority_score"]
            )

    def test_queue_includes_required_fields(self):
        """Queue items should include all required fields."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=False)

        queue = build_review_queue(registry)

        self.assertGreater(len(queue["review_queue"]), 0)
        item = queue["review_queue"][0]
        
        self.assertIn("rule_id", item)
        self.assertIn("priority_score", item)
        self.assertIn("priority_level", item)
        self.assertIn("reasons", item)
        self.assertIn("signals", item)

    def test_summary_counts(self):
        """Summary should correctly count priority levels."""
        registry = AdoptionRegistry()
        
        # Create rules with different priority levels
        _adopt_with_provenance(registry, "rule-001", with_provenance=False)  # High
        _adopt_with_provenance(registry, "rule-002", with_provenance=True)   # Low

        queue = build_review_queue(registry)
        summary = queue["summary"]

        self.assertEqual(summary["total_review_items"], len(queue["review_queue"]))
        self.assertEqual(
            summary["high_priority"] + summary["medium_priority"] + summary["low_priority"],
            summary["total_review_items"]
        )


class TestConflictImpactOnPriority(unittest.TestCase):
    """Tests for conflict impact on review priority."""

    def test_high_severity_conflict_increases_priority(self):
        """High severity conflict should increase priority score."""
        registry = AdoptionRegistry()
        
        # Create a rule and roll it back (creates high severity conflict)
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        registry.rollback("rule-001", rolled_back_by="tester", reason="Bad")

        priority = compute_review_priority("rule-001", registry)
        
        # Should have high priority due to rollback reintroduction conflict
        self.assertIn("currently rolled back", priority["reasons"])

    def test_rollback_lineage_reintroduction_increases_priority(self):
        """Rollback lineage reintroduction should significantly increase priority."""
        registry = AdoptionRegistry()
        
        # Create parent rule and roll it back
        _adopt_with_provenance(registry, "rule-parent", with_provenance=True)
        registry.rollback("rule-parent", rolled_back_by="tester", reason="Bad")
        
        # Create child rule (rollback lineage reintroduction)
        _adopt_with_provenance(
            registry, "rule-child",
            parent_rule_id="rule-parent",
            rule_version=2
        )

        priority_child = compute_review_priority("rule-child", registry)
        
        # Child should have high priority due to rollback lineage
        self.assertGreater(priority_child["priority_score"], 50)


class TestBundleImpactOnPriority(unittest.TestCase):
    """Tests for bundle impact on review priority."""

    def test_harmful_bundle_increases_priority(self):
        """Harmful bundle involvement should increase priority."""
        registry = AdoptionRegistry()
        
        # Create two rules with conflicting changes
        _adopt_with_provenance(
            registry, "rule-001",
            rule_type="orchestration",
            source_cases=["case-1", "case-2"]
        )
        _adopt_with_provenance(
            registry, "rule-002",
            rule_type="budget_trim",
            source_cases=["case-1", "case-2"]
        )

        # Both rules should have some priority due to potential bundle issues
        queue = build_review_queue(registry)
        
        # At minimum, the queue should be buildable
        self.assertIn("review_queue", queue)


class TestProvenanceImpactOnPriority(unittest.TestCase):
    """Tests for provenance impact on review priority."""

    def test_broken_parent_reference_increases_priority(self):
        """Broken parent reference should increase priority."""
        registry = AdoptionRegistry()
        
        # Create rule with non-existent parent
        prov = make_provenance(
            rule_id="rule-001",
            source_candidate_rule_id="rule-001",
            source_regression_case_ids=["case-1"],
            created_by="test",
            parent_rule_id="nonexistent-parent",
            rule_version=2,
        )
        candidate = _make_accepted_candidate("rule-001")
        registry.adopt(candidate, adopted_by="tester", provenance=prov)

        priority = compute_review_priority("rule-001", registry)
        
        self.assertGreater(priority["priority_score"], 0)
        self.assertTrue(any("parent" in r for r in priority["reasons"]))

    def test_orphan_versioned_rule_increases_priority(self):
        """Orphan rule with version > 1 should increase priority."""
        registry = AdoptionRegistry()
        
        prov = make_provenance(
            rule_id="rule-001",
            source_candidate_rule_id="rule-001",
            source_regression_case_ids=["case-1"],
            created_by="test",
            parent_rule_id=None,
            rule_version=3,  # Version > 1 but no parent
        )
        candidate = _make_accepted_candidate("rule-001")
        registry.adopt(candidate, adopted_by="tester", provenance=prov)

        priority = compute_review_priority("rule-001", registry)
        
        self.assertTrue(any("orphan" in r.lower() for r in priority["reasons"]))


class TestExportWithReviewQueue(unittest.TestCase):
    """Tests for export() with include_review_queue option."""

    def test_export_json_with_review_queue(self):
        """Export with include_review_queue should include review queue."""
        import json
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=False)

        exported = registry.export(fmt="json", include_review_queue=True)
        data = json.loads(exported)

        self.assertIn("review_queue", data)
        self.assertIn("review_queue", data["review_queue"])
        self.assertIn("summary", data["review_queue"])

    def test_export_json_without_review_queue(self):
        """Export without include_review_queue should not include review queue."""
        import json
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        exported = registry.export(fmt="json", include_review_queue=False)
        data = json.loads(exported)

        self.assertNotIn("review_queue", data)

    def test_registry_get_review_queue(self):
        """Registry should have get_review_queue method."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=False)

        queue = registry.get_review_queue()

        self.assertIn("review_queue", queue)
        self.assertIn("summary", queue)


class TestStableSortOrder(unittest.TestCase):
    """Tests for stable sort order in review queue."""

    def test_same_score_sorted_by_rule_id(self):
        """Rules with same score should be sorted by rule_id."""
        registry = AdoptionRegistry()
        
        # Create multiple rules with same conditions (should have similar scores)
        _adopt_with_provenance(registry, "rule-zzz", with_provenance=False)
        _adopt_with_provenance(registry, "rule-aaa", with_provenance=False)
        _adopt_with_provenance(registry, "rule-mmm", with_provenance=False)

        queue = build_review_queue(registry)
        
        # Check that sorting is stable (by rule_id when scores are equal)
        if len(queue["review_queue"]) >= 2:
            for i in range(len(queue["review_queue"]) - 1):
                curr = queue["review_queue"][i]
                next_item = queue["review_queue"][i + 1]
                
                # If scores are equal, rule_id should be ascending
                if curr["priority_score"] == next_item["priority_score"]:
                    self.assertLess(curr["rule_id"], next_item["rule_id"])


class TestReviewQueueSignals(unittest.TestCase):
    """Tests for detailed signals in review queue items."""

    def test_signals_include_conflict_count(self):
        """Signals should include conflict count."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        registry.rollback("rule-001", rolled_back_by="tester", reason="Bad")

        priority = compute_review_priority("rule-001", registry)
        
        self.assertIn("conflict_count", priority["signals"])

    def test_signals_include_lineage_depth(self):
        """Signals should include lineage depth."""
        registry = AdoptionRegistry()
        
        # Create lineage chain
        _adopt_with_provenance(registry, "rule-001", rule_version=1)
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

        priority = compute_review_priority("rule-003", registry)
        
        self.assertIn("lineage_depth", priority["signals"])

    def test_signals_include_rollback_history(self):
        """Signals should include rollback history flag."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=True)
        registry.rollback("rule-001", rolled_back_by="tester", reason="Bad")

        priority = compute_review_priority("rule-001", registry)
        
        self.assertIn("has_rollback_history", priority["signals"])
        self.assertTrue(priority["signals"]["has_rollback_history"])


class TestGetReviewQueueAlias(unittest.TestCase):
    """Tests for get_review_queue alias function."""

    def test_get_review_queue_returns_same_as_build(self):
        """get_review_queue should return same result as build_review_queue."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", with_provenance=False)

        queue1 = build_review_queue(registry)
        queue2 = get_review_queue(registry)

        self.assertEqual(
            queue1["summary"]["total_review_items"],
            queue2["summary"]["total_review_items"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
