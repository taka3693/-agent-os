#!/usr/bin/env python3
"""Step115: Policy Lineage Visualization Tests

Tests for building and rendering policy lineage trees/graphs.
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
    REVIEW_STATUS_ACCEPTED,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_ROLLED_BACK,
    PROMOTION_STATUS_PROMOTED,
    build_policy_lineage_graph,
    render_policy_lineage_tree,
    get_policy_evolution_summary,
    get_rule_lineage,
    make_provenance,
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
        rule_version=1,
    )
    return registry.adopt(candidate, adopted_by="tester", provenance=provenance)


class TestBuildLineageGraph(unittest.TestCase):
    """Tests for build_policy_lineage_graph()."""

    def test_empty_registry(self):
        """Empty registry should produce empty graph."""
        registry = AdoptionRegistry()
        graph = build_policy_lineage_graph(registry)

        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["edges"], [])
        self.assertEqual(graph["roots"], [])
        self.assertEqual(graph["summary"]["total_nodes"], 0)

    def test_single_rule_node(self):
        """Single rule should produce one node with no edges."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        graph = build_policy_lineage_graph(registry)

        self.assertEqual(len(graph["nodes"]), 1)
        self.assertEqual(graph["nodes"][0]["rule_id"], "rule-001")
        self.assertEqual(graph["nodes"][0]["status"], "adopted")
        self.assertEqual(graph["nodes"][0]["stage"], "adopted")
        self.assertEqual(graph["edges"], [])
        self.assertIn("rule-001", graph["roots"])

    def test_parent_child_edge(self):
        """Parent-child relationship should create an edge."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", parent_rule_id=None)
        _adopt_with_provenance(registry, "rule-002", parent_rule_id="rule-001")

        graph = build_policy_lineage_graph(registry)

        self.assertEqual(len(graph["nodes"]), 2)
        self.assertEqual(len(graph["edges"]), 1)
        self.assertEqual(graph["edges"][0]["from"], "rule-001")
        self.assertEqual(graph["edges"][0]["to"], "rule-002")
        self.assertEqual(graph["edges"][0]["type"], "parent")
        self.assertIn("rule-001", graph["roots"])
        self.assertNotIn("rule-002", graph["roots"])

    def test_status_appears_in_nodes(self):
        """Rule status should be visible in node data."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        graph = build_policy_lineage_graph(registry)

        node = graph["nodes"][0]
        self.assertIn("status", node)
        self.assertEqual(node["status"], "adopted")

    def test_rollback_visible_in_graph(self):
        """Rolled back rules should be visible in the graph."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Test rollback")

        graph = build_policy_lineage_graph(registry)

        node = graph["nodes"][0]
        self.assertEqual(node["stage"], "rolled_back")
        self.assertEqual(node["status"], "rolled_back")
        self.assertIn("rolled_back_at", node)
        self.assertEqual(node["rollback_reason"], "Test rollback")
        self.assertEqual(graph["summary"]["rollback_count"], 1)

    def test_promoted_stage(self):
        """Promoted rules should show promoted stage."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        shadow = create_shadow_evaluator(registry)
        promo = create_promotion_manager(shadow)

        # Create mock shadow result
        shadow._shadow_results["rule-001"] = {
            "source_candidate_rule_id": "rule-001",
            "shadowed_at": "2026-03-11T00:00:00Z",
            "shadowed_by": "tester",
            "comparison": {
                "regression_count": 0,
                "improvement_count": 1,
                "ok": True,
            },
            "promotion_status": PROMOTION_STATUS_PROMOTED,
            "gate_evaluation": {"passed": True},
        }

        promo._promotion_records["rule-001"] = {
            "source_candidate_rule_id": "rule-001",
            "promotion_status": PROMOTION_STATUS_PROMOTED,
            "promoted_at": "2026-03-11T00:01:00Z",
            "promoted_by": "tester",
        }

        graph = build_policy_lineage_graph(registry, promo)

        node = graph["nodes"][0]
        self.assertEqual(node["stage"], "promoted")

    def test_multiple_roots(self):
        """Multiple independent rules should be roots."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", parent_rule_id=None)
        _adopt_with_provenance(registry, "rule-002", parent_rule_id=None)
        _adopt_with_provenance(registry, "rule-003", parent_rule_id="rule-001")

        graph = build_policy_lineage_graph(registry)

        self.assertEqual(len(graph["roots"]), 2)
        self.assertIn("rule-001", graph["roots"])
        self.assertIn("rule-002", graph["roots"])


class TestRenderLineageTree(unittest.TestCase):
    """Tests for render_policy_lineage_tree()."""

    def test_empty_tree(self):
        """Empty registry should produce minimal output."""
        registry = AdoptionRegistry()
        tree = render_policy_lineage_tree(registry)

        self.assertIn("# Policy Lineage Tree", tree)
        self.assertIn("Total rules:** 0", tree)  # Markdown bold format

    def test_single_rule_tree(self):
        """Single rule should render as a tree node."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        tree = render_policy_lineage_tree(registry)

        self.assertIn("`rule-001`", tree)
        self.assertIn("[adopted]", tree)

    def test_parent_child_tree(self):
        """Parent-child should show tree structure."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001", parent_rule_id=None)
        _adopt_with_provenance(registry, "rule-002", parent_rule_id="rule-001")

        tree = render_policy_lineage_tree(registry)

        self.assertIn("`rule-001`", tree)
        self.assertIn("`rule-002`", tree)
        # Tree structure characters
        self.assertTrue("└──" in tree or "├──" in tree)

    def test_rollback_in_tree(self):
        """Rolled back rules should show rollback info."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Bad rule")

        tree = render_policy_lineage_tree(registry)

        self.assertTrue("rolled_back" in tree.lower() or "↩️" in tree)
        self.assertIn("Bad rule", tree)

    def test_with_provenance(self):
        """Provenance details should be included when requested."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(
            registry,
            "rule-001",
            source_cases=["case-1", "case-2"],
            source_packs=["pack-a"],
        )

        tree = render_policy_lineage_tree(registry, include_provenance=True)

        self.assertIn("case-1", tree)
        self.assertIn("pack-a", tree)


class TestPolicyEvolutionSummary(unittest.TestCase):
    """Tests for get_policy_evolution_summary()."""

    def test_summary_structure(self):
        """Evolution summary should have expected structure."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        summary = get_policy_evolution_summary(registry)

        self.assertIn("lineage_graph", summary)
        self.assertIn("evolution_metrics", summary)
        self.assertIn("rollback_history", summary)

    def test_evolution_metrics(self):
        """Evolution metrics should be accurate."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        _adopt_with_provenance(registry, "rule-002")
        registry.rollback("rule-002", rolled_back_by="tester", reason="Test")

        summary = get_policy_evolution_summary(registry)
        metrics = summary["evolution_metrics"]

        self.assertEqual(metrics["total_rules"], 2)
        self.assertEqual(metrics["active_rules"], 1)
        self.assertEqual(metrics["rolled_back_rules"], 1)
        self.assertEqual(metrics["rollback_rate"], 0.5)

    def test_rollback_history(self):
        """Rollback history should list rollbacks."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        _adopt_with_provenance(registry, "rule-002")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Reason 1")
        registry.rollback("rule-002", rolled_back_by="tester", reason="Reason 2")

        summary = get_policy_evolution_summary(registry)
        history = summary["rollback_history"]

        self.assertEqual(len(history), 2)
        reasons = [h["rollback_reason"] for h in history]
        self.assertIn("Reason 1", reasons)
        self.assertIn("Reason 2", reasons)


class TestRuleLineage(unittest.TestCase):
    """Tests for get_rule_lineage()."""

    def test_lineage_for_single_rule(self):
        """Lineage should show candidate → adopted stages."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")

        lineage = get_rule_lineage("rule-001", registry)

        self.assertGreaterEqual(len(lineage), 2)
        stages = [l["stage"] for l in lineage]
        self.assertIn("candidate", stages)
        self.assertIn("adopted", stages)

    def test_lineage_with_rollback(self):
        """Lineage should include rollback stage."""
        registry = AdoptionRegistry()
        _adopt_with_provenance(registry, "rule-001")
        registry.rollback("rule-001", rolled_back_by="tester", reason="Test")

        lineage = get_rule_lineage("rule-001", registry)

        stages = [l["stage"] for l in lineage]
        self.assertIn("rolled_back", stages)

    def test_lineage_for_unknown_rule(self):
        """Unknown rule should return empty lineage."""
        registry = AdoptionRegistry()

        lineage = get_rule_lineage("unknown-rule", registry)

        self.assertEqual(lineage, [])


class TestLineageIntegration(unittest.TestCase):
    """Integration tests for lineage with full workflow."""

    def test_full_workflow_lineage(self):
        """Full workflow should produce correct lineage."""
        registry = AdoptionRegistry()

        # Create and adopt rule
        _adopt_with_provenance(registry, "rule-001", source_cases=["case-1"])

        # Shadow evaluate
        shadow = create_shadow_evaluator(registry)
        shadow._shadow_results["rule-001"] = {
            "source_candidate_rule_id": "rule-001",
            "shadowed_at": "2026-03-11T00:00:00Z",
            "shadowed_by": "tester",
            "comparison": {
                "regression_count": 0,
                "improvement_count": 2,
                "ok": True,
            },
        }

        # Promote
        promo = create_promotion_manager(shadow)
        promo.evaluate_for_promotion("rule-001")
        promo.promote("rule-001", promoted_by="tester")  # Actually promote

        # Build lineage
        graph = build_policy_lineage_graph(registry, promo)
        tree = render_policy_lineage_tree(registry, promo)

        self.assertEqual(len(graph["nodes"]), 1)
        self.assertEqual(graph["nodes"][0]["stage"], "promoted")
        self.assertIn("rule-001", tree)

    def test_multi_version_lineage(self):
        """Multi-version rules should show lineage depth."""
        registry = AdoptionRegistry()

        # Version 1
        _adopt_with_provenance(registry, "rule-001", parent_rule_id=None)

        # Version 2 (derived from v1)
        _adopt_with_provenance(registry, "rule-002", parent_rule_id="rule-001")

        # Version 3 (derived from v2)
        _adopt_with_provenance(registry, "rule-003", parent_rule_id="rule-002")

        graph = build_policy_lineage_graph(registry)
        summary = get_policy_evolution_summary(registry)

        self.assertEqual(len(graph["edges"]), 2)
        self.assertEqual(summary["evolution_metrics"]["lineage_depth"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
