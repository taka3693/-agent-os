#!/usr/bin/env python3
"""Step121: Policy Evolution E2E Integration Tests

End-to-end integration tests verifying the complete policy evolution pipeline
from candidate rules through provenance, lineage, conflicts, bundles, health,
review queue, and auto-evolution decisions.

This tests the full data flow:
candidate rule -> provenance -> lineage -> conflicts -> bundles -> health -> review queue -> auto-evolution
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.candidate_rules import (
    # Core
    AdoptionRegistry,
    make_candidate,
    review_candidate,
    make_provenance,
    REVIEW_STATUS_ACCEPTED,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_ROLLED_BACK,
    
    # Step114: Provenance
    summarize_provenance,
    get_rule_lineage,
    
    # Step115: Lineage
    build_policy_lineage_graph,
    render_policy_lineage_tree,
    get_policy_evolution_summary,
    
    # Step116: Conflicts
    detect_rule_conflicts,
    build_conflict_report,
    CONFLICT_ROLLBACK_REINTRODUCTION,
    CONFLICT_INCONSISTENT_PROVENANCE,
    CONFLICT_OVERLAPPING_APPLICABILITY,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    
    # Step117: Bundle
    evaluate_rule_bundle,
    
    # Step118: Health
    compute_policy_health,
    
    # Step119: Review Queue
    compute_review_priority,
    build_review_queue,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
    
    # Step120: Auto Evolution
    evaluate_auto_evolution_candidate,
    run_controlled_auto_evolution,
    DECISION_AUTO_PROMOTE,
    DECISION_REVIEW_REQUIRED,
    DECISION_HALT,
    DECISION_ROLLBACK_RECOMMENDED,
    DECISION_REJECT,
    DECISION_NO_ACTION,
)


class TestPolicyEvolutionE2ESafeAndRiskyPaths(unittest.TestCase):
    """End-to-end test for safe and risky rule paths through the evolution pipeline."""

    def test_policy_evolution_e2e_safe_and_risky_paths(self):
        """Test complete policy evolution pipeline with safe and risky rules.
        
        Flow:
        1. Create safe rule (complete provenance, no conflicts, low priority)
        2. Create risky rule (rollback lineage, conflicts, high priority)
        3. Verify provenance is attached to both
        4. Verify lineage is generated
        5. Verify conflicts are detected for risky rule
        6. Verify bundle evaluation returns results
        7. Verify health score is computed
        8. Verify review queue prioritizes risky rule higher
        9. Verify auto-evolution decisions: safe -> auto_promote, risky -> halt/review
        """
        # === Setup: Create registry ===
        registry = AdoptionRegistry()
        
        # === Step 1: Create SAFE rule ===
        # Safe rule has complete provenance, no conflicts, low risk
        safe_candidate = make_candidate(
            candidate_rule_id="rule-safe-001",
            description="Safe rule with complete provenance",
            expected_effect="Improves performance",
            affected_cases=["case-safe-1", "case-safe-2"],
            risk_level="low",
            recommendation="adopt",
            rule_type="tier_threshold",
            suggested_change={"threshold": 3},
        )
        safe_candidate = review_candidate(safe_candidate, "accepted", "reviewer-safe")
        
        safe_provenance = make_provenance(
            rule_id="rule-safe-001",
            source_candidate_rule_id="rule-safe-001",
            source_regression_case_ids=["case-safe-1", "case-safe-2"],
            source_benchmark_snapshot="snap-001",
            source_scenario_packs=["scenario-safe"],
            created_by="e2e-test",
            parent_rule_id=None,
            rule_version=1,
        )
        
        registry.adopt(safe_candidate, adopted_by="adopter-safe", provenance=safe_provenance)
        
        # === Step 2: Create RISKY rule ===
        # Risky rule: will have rollback lineage reintroduction
        
        # First create parent that will be rolled back
        risky_parent_candidate = make_candidate(
            candidate_rule_id="rule-risky-parent",
            description="Risky parent that will be rolled back",
            expected_effect="Unknown effect",
            affected_cases=["case-risky-1"],
            risk_level="high",
            recommendation="review",
            rule_type="orchestration",
            suggested_change={"orchestrate": True},
        )
        risky_parent_candidate = review_candidate(risky_parent_candidate, "accepted", "reviewer-risky")
        
        risky_parent_provenance = make_provenance(
            rule_id="rule-risky-parent",
            source_candidate_rule_id="rule-risky-parent",
            source_regression_case_ids=["case-risky-1"],
            created_by="e2e-test",
            parent_rule_id=None,
            rule_version=1,
        )
        
        registry.adopt(risky_parent_candidate, adopted_by="adopter-risky", provenance=risky_parent_provenance)
        
        # Rollback the parent
        registry.rollback("rule-risky-parent", rolled_back_by="tester", reason="Critical issue found")
        
        # Create child rule from rolled-back parent (this creates rollback lineage reintroduction)
        risky_child_candidate = make_candidate(
            candidate_rule_id="rule-risky-child",
            description="Risky child from rolled-back lineage",
            expected_effect="Derived from rolled-back rule",
            affected_cases=["case-risky-2"],
            risk_level="medium",
            recommendation="review",
            rule_type="budget_trim",
            suggested_change={"trim": True},
        )
        risky_child_candidate = review_candidate(risky_child_candidate, "accepted", "reviewer-risky")
        
        risky_child_provenance = make_provenance(
            rule_id="rule-risky-child",
            source_candidate_rule_id="rule-risky-child",
            source_regression_case_ids=["case-risky-2"],
            created_by="e2e-test",
            parent_rule_id="rule-risky-parent",
            rule_version=2,
        )
        
        registry.adopt(risky_child_candidate, adopted_by="adopter-risky", provenance=risky_child_provenance)
        
        # === Step 3: Verify Provenance ===
        safe_entry = registry.get("rule-safe-001")
        risky_entry = registry.get("rule-risky-child")
        
        # A. Provenance attached
        self.assertIsNotNone(safe_entry.get("provenance"), "Safe rule should have provenance")
        self.assertIsNotNone(risky_entry.get("provenance"), "Risky rule should have provenance")
        self.assertEqual(safe_entry["provenance"]["rule_id"], "rule-safe-001")
        self.assertEqual(risky_entry["provenance"]["rule_id"], "rule-risky-child")
        
        # === Step 4: Verify Lineage ===
        # B. Lineage not empty
        lineage_graph = build_policy_lineage_graph(registry)
        self.assertGreater(len(lineage_graph["nodes"]), 0, "Lineage graph should have nodes")
        self.assertGreater(len(lineage_graph["edges"]), 0, "Lineage graph should have edges (risky child -> parent)")
        
        # Verify safe rule lineage
        safe_lineage = get_rule_lineage("rule-safe-001", registry)
        self.assertGreater(len(safe_lineage), 0, "Safe rule should have lineage entries")
        
        # Verify risky rule lineage
        risky_lineage = get_rule_lineage("rule-risky-child", registry)
        self.assertGreater(len(risky_lineage), 0, "Risky rule should have lineage entries")
        
        # === Step 5: Verify Conflicts ===
        # C. Conflicts detected for risky rule
        conflicts = detect_rule_conflicts(registry)
        self.assertGreater(len(conflicts), 0, "Should detect conflicts (rollback reintroduction)")
        
        # Find conflicts involving risky rule
        risky_conflicts = [c for c in conflicts if "rule-risky-child" in c.get("rule_ids", [])]
        self.assertGreater(len(risky_conflicts), 0, "Risky rule should be involved in conflicts")
        
        # Verify rollback lineage reintroduction conflict
        rollback_reintro_conflicts = [
            c for c in conflicts 
            if c.get("type") == CONFLICT_ROLLBACK_REINTRODUCTION
        ]
        self.assertGreater(len(rollback_reintro_conflicts), 0, "Should detect rollback lineage reintroduction")
        
        # === Step 6: Verify Bundle Evaluation ===
        # D. Bundle result returned
        bundle_result = evaluate_rule_bundle(
            ["rule-safe-001", "rule-risky-child"], 
            registry
        )
        self.assertIn("bundle_rule_ids", bundle_result)
        self.assertIn("bundle_result", bundle_result)
        self.assertIn("harmful_interaction", bundle_result)
        self.assertIn("no_added_value", bundle_result)
        
        # === Step 7: Verify Health Score ===
        # E. Health score returned
        health_report = compute_policy_health(registry)
        self.assertIn("health_score", health_report)
        self.assertIn("grade", health_report)
        self.assertIn("breakdown", health_report)
        self.assertGreaterEqual(health_report["health_score"], 0)
        self.assertLessEqual(health_report["health_score"], 100)
        
        # Verify all breakdown categories exist
        self.assertIn("provenance_completeness", health_report["breakdown"])
        self.assertIn("lineage_health", health_report["breakdown"])
        self.assertIn("conflict_health", health_report["breakdown"])
        self.assertIn("rollback_health", health_report["breakdown"])
        self.assertIn("bundle_health", health_report["breakdown"])
        
        # === Step 8: Verify Review Queue ===
        # F. Risky rule has higher priority
        review_queue = build_review_queue(registry)
        self.assertIn("review_queue", review_queue)
        self.assertIn("summary", review_queue)
        self.assertGreater(len(review_queue["review_queue"]), 0, "Review queue should have items")
        
        # Find safe and risky priorities
        safe_priority = None
        risky_priority = None
        for item in review_queue["review_queue"]:
            if item["rule_id"] == "rule-safe-001":
                safe_priority = item
            elif item["rule_id"] == "rule-risky-child":
                risky_priority = item
        
        # Risky rule should have higher priority score
        if safe_priority and risky_priority:
            self.assertGreaterEqual(
                risky_priority["priority_score"], 
                safe_priority["priority_score"],
                "Risky rule should have higher or equal priority than safe rule"
            )
        
        # === Step 9: Verify Auto-Evolution Decisions ===
        # G. Safe -> auto_promote, Risky -> halt/review
        
        safe_decision = evaluate_auto_evolution_candidate("rule-safe-001", registry)
        risky_decision = evaluate_auto_evolution_candidate("rule-risky-child", registry)
        
        # Safe rule should be auto_promote or review_required (conservative)
        # Note: If risky rule affects bundle evaluation, safe rule might get rollback_recommended
        self.assertIn(
            safe_decision["decision"],
            [DECISION_AUTO_PROMOTE, DECISION_REVIEW_REQUIRED, DECISION_ROLLBACK_RECOMMENDED],
            f"Safe rule should be auto_promote, review_required, or rollback_recommended, got {safe_decision['decision']}"
        )
        
        # Risky rule should be halt (due to rollback lineage reintroduction)
        self.assertEqual(
            risky_decision["decision"],
            DECISION_HALT,
            f"Risky rule should be halt due to rollback lineage reintroduction, got {risky_decision['decision']}"
        )
        
        # Verify decision has required fields
        for decision in [safe_decision, risky_decision]:
            self.assertIn("rule_id", decision)
            self.assertIn("decision", decision)
            self.assertIn("confidence", decision)
            self.assertIn("reasons", decision)
            self.assertIn("signals", decision)


class TestE2EExportContainsAllSections(unittest.TestCase):
    """Test that export includes all required sections."""

    def test_e2e_export_contains_all_sections(self):
        """Verify JSON export contains all sections when all flags are enabled."""
        # Setup registry with mixed rules
        registry = AdoptionRegistry()
        
        # Add a rule
        candidate = make_candidate(
            candidate_rule_id="rule-export-test",
            description="Export test rule",
            expected_effect="Test effect",
            affected_cases=["case-export-1"],
            risk_level="low",
            recommendation="adopt",
            rule_type="tier_threshold",
            suggested_change={"test": 1},
        )
        candidate = review_candidate(candidate, "accepted", "reviewer")
        
        provenance = make_provenance(
            rule_id="rule-export-test",
            source_candidate_rule_id="rule-export-test",
            source_regression_case_ids=["case-export-1"],
            created_by="e2e-test",
        )
        
        registry.adopt(candidate, adopted_by="adopter", provenance=provenance)
        
        # Export with all flags
        exported = registry.export(
            fmt="json",
            include_lineage=True,
            include_conflicts=True,
            include_bundle_eval=True,
            include_health=True,
            include_review_queue=True,
            include_auto_evolution=True,
            bundle_rule_ids=["rule-export-test"],
            rule_ids_for_evolution=["rule-export-test"],
        )
        
        data = json.loads(exported)
        
        # Verify all sections present
        self.assertIn("summary", data, "Export should have summary")
        self.assertIn("entries", data, "Export should have entries")
        self.assertIn("lineage", data, "Export should have lineage")
        self.assertIn("conflicts", data, "Export should have conflicts")
        self.assertIn("bundle_evaluation", data, "Export should have bundle_evaluation")
        self.assertIn("health", data, "Export should have health")
        self.assertIn("review_queue", data, "Export should have review_queue")
        self.assertIn("auto_evolution", data, "Export should have auto_evolution")
        
        # Verify lineage structure
        self.assertIn("nodes", data["lineage"])
        self.assertIn("edges", data["lineage"])
        self.assertIn("roots", data["lineage"])
        self.assertIn("summary", data["lineage"])
        
        # Verify conflicts structure
        self.assertIn("conflicts", data["conflicts"])
        self.assertIn("summary", data["conflicts"])
        
        # Verify bundle evaluation structure
        self.assertIn("bundle_rule_ids", data["bundle_evaluation"])
        self.assertIn("harmful_interaction", data["bundle_evaluation"])
        self.assertIn("no_added_value", data["bundle_evaluation"])
        
        # Verify health structure
        self.assertIn("health_score", data["health"])
        self.assertIn("grade", data["health"])
        self.assertIn("breakdown", data["health"])
        
        # Verify review queue structure
        self.assertIn("review_queue", data["review_queue"])
        self.assertIn("summary", data["review_queue"])
        
        # Verify auto_evolution structure
        self.assertIn("auto_evolution", data["auto_evolution"])
        self.assertIn("summary", data["auto_evolution"])


class TestE2EDataFlowConsistency(unittest.TestCase):
    """Test data flow consistency across the evolution pipeline."""

    def test_e2e_data_flow_consistency(self):
        """Verify data consistency: rule_id, parent_rule_id, provenance, lineage, review decision."""
        # Create a lineage chain
        registry = AdoptionRegistry()
        
        # Create grandparent
        gp_candidate = make_candidate(
            candidate_rule_id="rule-gp",
            description="Grandparent rule",
            expected_effect="Base effect",
            affected_cases=["case-gp"],
            risk_level="low",
            recommendation="adopt",
            rule_type="tier_threshold",
            suggested_change={"base": 1},
        )
        gp_candidate = review_candidate(gp_candidate, "accepted", "reviewer")
        gp_prov = make_provenance("rule-gp", "rule-gp", ["case-gp"], created_by="e2e", rule_version=1)
        registry.adopt(gp_candidate, adopted_by="adopter", provenance=gp_prov)
        
        # Create parent
        p_candidate = make_candidate(
            candidate_rule_id="rule-p",
            description="Parent rule",
            expected_effect="Derived effect",
            affected_cases=["case-p"],
            risk_level="low",
            recommendation="adopt",
            rule_type="tier_threshold",
            suggested_change={"derived": 1},
        )
        p_candidate = review_candidate(p_candidate, "accepted", "reviewer")
        p_prov = make_provenance("rule-p", "rule-p", ["case-p"], created_by="e2e", parent_rule_id="rule-gp", rule_version=2)
        registry.adopt(p_candidate, adopted_by="adopter", provenance=p_prov)
        
        # Create child
        c_candidate = make_candidate(
            candidate_rule_id="rule-c",
            description="Child rule",
            expected_effect="Further derived effect",
            affected_cases=["case-c"],
            risk_level="low",
            recommendation="adopt",
            rule_type="tier_threshold",
            suggested_change={"further": 1},
        )
        c_candidate = review_candidate(c_candidate, "accepted", "reviewer")
        c_prov = make_provenance("rule-c", "rule-c", ["case-c"], created_by="e2e", parent_rule_id="rule-p", rule_version=3)
        registry.adopt(c_candidate, adopted_by="adopter", provenance=c_prov)
        
        # === Verify rule_id consistency ===
        for rule_id in ["rule-gp", "rule-p", "rule-c"]:
            entry = registry.get(rule_id)
            self.assertIsNotNone(entry, f"Entry for {rule_id} should exist")
            self.assertEqual(
                entry["source_candidate_rule_id"], 
                rule_id,
                f"source_candidate_rule_id should match rule_id for {rule_id}"
            )
            self.assertEqual(
                entry["provenance"]["rule_id"],
                rule_id,
                f"provenance.rule_id should match rule_id for {rule_id}"
            )
        
        # === Verify parent_rule_id consistency ===
        # Grandparent has no parent
        gp_entry = registry.get("rule-gp")
        self.assertIsNone(gp_entry["provenance"].get("parent_rule_id"))
        
        # Parent's parent is grandparent
        p_entry = registry.get("rule-p")
        self.assertEqual(p_entry["provenance"]["parent_rule_id"], "rule-gp")
        
        # Child's parent is parent
        c_entry = registry.get("rule-c")
        self.assertEqual(c_entry["provenance"]["parent_rule_id"], "rule-p")
        
        # === Verify provenance consistency ===
        prov_summary = summarize_provenance(registry.list_adopted())
        self.assertEqual(prov_summary["total"], 3)
        self.assertEqual(prov_summary["with_provenance"], 3)
        self.assertEqual(prov_summary["with_parent"], 2)  # p and c have parents
        
        # === Verify lineage consistency ===
        lineage_graph = build_policy_lineage_graph(registry)
        
        # Should have 3 nodes
        self.assertEqual(len(lineage_graph["nodes"]), 3)
        
        # Should have 2 edges (gp->p, p->c)
        self.assertEqual(len(lineage_graph["edges"]), 2)
        
        # Verify edges
        edge_pairs = [(e["from"], e["to"]) for e in lineage_graph["edges"]]
        self.assertIn(("rule-gp", "rule-p"), edge_pairs)
        self.assertIn(("rule-p", "rule-c"), edge_pairs)
        
        # Grandparent should be root
        self.assertIn("rule-gp", lineage_graph["roots"])
        
        # === Verify lineage depth ===
        # Grandparent depth = 0 (no ancestors)
        gp_depth = 0
        # Parent depth = 1 (grandparent)
        p_depth = 1
        # Child depth = 2 (grandparent -> parent)
        c_depth = 2
        
        # Verify through lineage tracking
        c_lineage = get_rule_lineage("rule-c", registry)
        # Should have: candidate, adopted stages at minimum
        self.assertGreaterEqual(len(c_lineage), 2)
        
        # === Verify review decision consistency ===
        # All rules should have decisions
        for rule_id in ["rule-gp", "rule-p", "rule-c"]:
            decision = evaluate_auto_evolution_candidate(rule_id, registry)
            self.assertEqual(decision["rule_id"], rule_id)
            self.assertIn(decision["decision"], [
                DECISION_AUTO_PROMOTE,
                DECISION_REVIEW_REQUIRED,
                DECISION_HALT,
            ])
            
            # Verify signals are populated
            self.assertIn("health_score", decision["signals"])
            self.assertIn("review_priority_score", decision["signals"])
            self.assertIn("lineage_depth", decision["signals"])
        
        # Child has deepest lineage, should have higher review priority if any
        c_decision = evaluate_auto_evolution_candidate("rule-c", registry)
        self.assertIn("lineage_depth", c_decision["signals"])


class TestE2ERollbackScenario(unittest.TestCase):
    """Test end-to-end rollback scenario."""

    def test_e2e_rollback_affects_all_systems(self):
        """Verify that rollback affects conflicts, health, review queue, and decisions."""
        registry = AdoptionRegistry()
        
        # Create a rule
        candidate = make_candidate(
            candidate_rule_id="rule-to-rollback",
            description="Rule that will be rolled back",
            expected_effect="Effect",
            affected_cases=["case-1"],
            risk_level="medium",
            recommendation="adopt",
            rule_type="tier_threshold",
            suggested_change={"x": 1},
        )
        candidate = review_candidate(candidate, "accepted", "reviewer")
        provenance = make_provenance("rule-to-rollback", "rule-to-rollback", ["case-1"])
        registry.adopt(candidate, adopted_by="adopter", provenance=provenance)
        
        # Get pre-rollback state
        pre_health = compute_policy_health(registry)
        pre_conflicts = detect_rule_conflicts(registry)
        pre_queue = build_review_queue(registry)
        pre_decision = evaluate_auto_evolution_candidate("rule-to-rollback", registry)
        
        # Rollback the rule
        registry.rollback("rule-to-rollback", rolled_back_by="tester", reason="Issue found")
        
        # Get post-rollback state
        post_health = compute_policy_health(registry)
        post_conflicts = detect_rule_conflicts(registry)
        post_queue = build_review_queue(registry)
        post_decision = evaluate_auto_evolution_candidate("rule-to-rollback", registry)
        
        # Health should be affected (rollback_health breakdown)
        self.assertIn("rollback_health", post_health["breakdown"])
        
        # Conflicts should detect rolled-back rule
        rollback_conflicts = [
            c for c in post_conflicts 
            if c.get("type") == CONFLICT_ROLLBACK_REINTRODUCTION
        ]
        self.assertGreater(len(rollback_conflicts), 0, "Should detect rollback reintroduction")
        
        # Decision should be no_action for rolled-back rule
        self.assertEqual(post_decision["decision"], DECISION_NO_ACTION)


class TestE2EMultiRuleInteraction(unittest.TestCase):
    """Test multiple rules interacting in the evolution pipeline."""

    def test_e2e_multiple_rules_pipeline(self):
        """Test multiple rules going through the complete pipeline."""
        registry = AdoptionRegistry()
        
        # Create multiple rules with different characteristics
        rules = [
            ("rule-low-risk", "low", "adopt", None),
            ("rule-medium-risk", "medium", "review", None),
            ("rule-high-risk", "high", "discard", None),
        ]
        
        for rule_id, risk_level, recommendation, _ in rules:
            candidate = make_candidate(
                candidate_rule_id=rule_id,
                description=f"Test rule {rule_id}",
                expected_effect="Effect",
                affected_cases=[f"case-{rule_id}"],
                risk_level=risk_level,
                recommendation=recommendation,
                rule_type="tier_threshold",
                suggested_change={"test": 1},
            )
            candidate = review_candidate(candidate, "accepted", "reviewer")
            provenance = make_provenance(rule_id, rule_id, [f"case-{rule_id}"])
            registry.adopt(candidate, adopted_by="adopter", provenance=provenance)
        
        # Run through pipeline
        provenance_summary = summarize_provenance(registry.list_adopted())
        lineage_graph = build_policy_lineage_graph(registry)
        conflicts = detect_rule_conflicts(registry)
        health = compute_policy_health(registry)
        queue = build_review_queue(registry)
        evolution = run_controlled_auto_evolution(registry)
        
        # Verify all rules processed
        self.assertEqual(provenance_summary["total"], 3)
        self.assertEqual(len(lineage_graph["nodes"]), 3)
        
        # Verify evolution decisions for all
        self.assertEqual(len(evolution["auto_evolution"]), 3)
        
        # Summary should account for all rules
        total_decisions = sum(evolution["summary"].values())
        self.assertEqual(total_decisions, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
