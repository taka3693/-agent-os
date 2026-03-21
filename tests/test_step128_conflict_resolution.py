#!/usr/bin/env python3
"""Step128: Policy Conflict Resolution Tests

Tests for automatic conflict detection and resolution strategies.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.conflict_resolution import (
    ConflictResolutionPolicy,
    ConflictResolution,
    ConflictResolutionLog,
    resolve_conflict,
    resolve_all_conflicts,
    get_resolution_log,
    reset_resolution_log,
    get_conflict_resolution_summary,
    generate_resolution_report,
    estimate_resolution_impact,
    RESOLUTION_PRIORITY_OVERRIDE,
    RESOLUTION_MERGE_RULES,
    RESOLUTION_DISABLE_LOWER_PRIORITY,
    RESOLUTION_ESCALATE_FOR_REVIEW,
    RESOLUTION_AUTO_SELECT_BEST,
    RESOLUTION_NO_ACTION,
    RESOLUTION_SUCCESS,
    RESOLUTION_FAILED,
    RESOLUTION_SKIPPED,
    RESOLUTION_PENDING,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
)

from eval.candidate_rules import (
    AdoptionRegistry,
    make_candidate,
    review_candidate,
    make_provenance,
    detect_rule_conflicts,
    CONFLICT_OVERLAPPING_APPLICABILITY,
    CONFLICT_PREREQUISITE,
    CONFLICT_ROLLBACK_REINTRODUCTION,
    CONFLICT_INCONSISTENT_PROVENANCE,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
)


def _setup_clean_registry() -> AdoptionRegistry:
    """Helper to create a clean registry."""
    registry = AdoptionRegistry()
    for i in range(1, 4):
        rule_id = f"clean-rule-{i:03d}"
        c = make_candidate(
            candidate_rule_id=rule_id,
            description=f"Clean rule {i}",
            expected_effect="Test",
            affected_cases=[f"case-{i}"],
            risk_level="low",
            recommendation="adopt",
            rule_type=f"type_{i}",
            suggested_change={"tier": i},
        )
        candidate = review_candidate(c, decision="accepted", reviewer="tester")
        provenance = make_provenance(
            rule_id=rule_id,
            source_candidate_rule_id=rule_id,
            source_regression_case_ids=[f"case-{i}"],
            created_by="test",
        )
        registry.adopt(candidate, adopted_by="tester", provenance=provenance)
    return registry


def _setup_conflicting_registry() -> AdoptionRegistry:
    """Helper to create a registry with conflicts."""
    registry = AdoptionRegistry()
    
    # Add rules with same type and overlapping cases (will conflict)
    for i in range(1, 3):
        rule_id = f"conflict-rule-{i:03d}"
        c = make_candidate(
            candidate_rule_id=rule_id,
            description=f"Conflicting rule {i}",
            expected_effect="Test",
            affected_cases=["case-shared"],  # Same cases
            risk_level="medium",
            recommendation="adopt",
            rule_type="same_type",  # Same type
            suggested_change={"tier": i},  # Different tier
        )
        candidate = review_candidate(c, decision="accepted", reviewer="tester")
        provenance = make_provenance(
            rule_id=rule_id,
            source_candidate_rule_id=rule_id,
            source_regression_case_ids=["case-shared"],
            created_by="test",
        )
        registry.adopt(candidate, adopted_by="tester", provenance=provenance)
    
    # Add a rolled-back rule
    rb_id = "rolled-back-rule"
    c = make_candidate(
        candidate_rule_id=rb_id,
        description="Rolled back",
        expected_effect="Test",
        affected_cases=["case-rb"],
        risk_level="high",
        recommendation="adopt",
        rule_type="rb_type",
        suggested_change={"tier": 99},
    )
    candidate = review_candidate(c, decision="accepted", reviewer="tester")
    provenance = make_provenance(
        rule_id=rb_id,
        source_candidate_rule_id=rb_id,
        source_regression_case_ids=["case-rb"],
        created_by="test",
    )
    registry.adopt(candidate, adopted_by="tester", provenance=provenance)
    registry.rollback(rb_id, rolled_back_by="tester", reason="Bad rule")
    
    return registry


class TestConflictResolutionPolicy(unittest.TestCase):
    """Tests for ConflictResolutionPolicy class."""

    def test_default_policy(self):
        """Should create default policy."""
        policy = ConflictResolutionPolicy()
        
        self.assertEqual(policy.default_strategy, RESOLUTION_ESCALATE_FOR_REVIEW)
        self.assertTrue(policy.auto_resolve_low_severity)

    def test_get_strategy_for_high_severity(self):
        """Should escalate high severity conflicts."""
        policy = ConflictResolutionPolicy()
        
        conflict = {
            "type": CONFLICT_OVERLAPPING_APPLICABILITY,
            "severity": SEVERITY_HIGH,
            "rule_ids": ["r1", "r2"],
        }
        
        strategy = policy.get_strategy_for_conflict(conflict)
        
        self.assertEqual(strategy, RESOLUTION_ESCALATE_FOR_REVIEW)

    def test_get_strategy_for_low_severity(self):
        """Should auto-resolve low severity conflicts."""
        policy = ConflictResolutionPolicy(auto_resolve_low_severity=True)
        
        conflict = {
            "type": CONFLICT_INCONSISTENT_PROVENANCE,
            "severity": SEVERITY_LOW,
            "rule_ids": ["r1"],
        }
        
        strategy = policy.get_strategy_for_conflict(conflict)
        
        self.assertEqual(strategy, RESOLUTION_AUTO_SELECT_BEST)

    def test_get_strategy_for_rollback_reintroduction(self):
        """Should use disable strategy for rollback reintroduction."""
        policy = ConflictResolutionPolicy(auto_resolve_high_severity=True)
        
        conflict = {
            "type": CONFLICT_ROLLBACK_REINTRODUCTION,
            "severity": SEVERITY_HIGH,
            "rule_ids": ["r1"],
        }
        
        strategy = policy.get_strategy_for_conflict(conflict)
        
        self.assertEqual(strategy, RESOLUTION_DISABLE_LOWER_PRIORITY)

    def test_should_auto_resolve(self):
        """Should determine auto-resolution correctly."""
        policy = ConflictResolutionPolicy(
            auto_resolve_low_severity=True,
            auto_resolve_medium_severity=False,
            auto_resolve_high_severity=False,
        )
        
        low_conflict = {"severity": SEVERITY_LOW}
        medium_conflict = {"severity": SEVERITY_MEDIUM}
        high_conflict = {"severity": SEVERITY_HIGH}
        
        self.assertTrue(policy.should_auto_resolve(low_conflict))
        self.assertFalse(policy.should_auto_resolve(medium_conflict))
        self.assertFalse(policy.should_auto_resolve(high_conflict))

    def test_priority_rules(self):
        """Should use priority rules."""
        policy = ConflictResolutionPolicy(
            priority_rules={"rule-a": 10, "rule-b": 5}
        )
        
        self.assertEqual(policy.get_rule_priority("rule-a"), 10)
        self.assertEqual(policy.get_rule_priority("rule-b"), 5)
        self.assertEqual(policy.get_rule_priority("unknown"), 0)

    def test_to_dict(self):
        """Should convert to dictionary."""
        policy = ConflictResolutionPolicy(default_strategy=RESOLUTION_MERGE_RULES)
        
        d = policy.to_dict()
        
        self.assertEqual(d["default_strategy"], RESOLUTION_MERGE_RULES)


class TestConflictResolution(unittest.TestCase):
    """Tests for ConflictResolution class."""

    def test_resolution_creation(self):
        """Should create a resolution."""
        conflict = {
            "type": CONFLICT_OVERLAPPING_APPLICABILITY,
            "severity": SEVERITY_MEDIUM,
            "rule_ids": ["r1", "r2"],
        }
        
        resolution = ConflictResolution(
            conflict=conflict,
            strategy=RESOLUTION_PRIORITY_OVERRIDE,
            outcome=RESOLUTION_SUCCESS,
            resolved_rule_ids=["r1"],
            action_taken="Priority override",
            notes="r1 wins",
        )
        
        self.assertEqual(resolution.strategy, RESOLUTION_PRIORITY_OVERRIDE)
        self.assertEqual(resolution.outcome, RESOLUTION_SUCCESS)
        self.assertIn("resolution_id", resolution.to_dict())

    def test_resolution_to_dict(self):
        """Should convert to dictionary."""
        conflict = {"type": "test", "severity": "low"}
        
        resolution = ConflictResolution(
            conflict=conflict,
            strategy=RESOLUTION_AUTO_SELECT_BEST,
            outcome=RESOLUTION_SUCCESS,
            resolved_rule_ids=["r1"],
        )
        
        d = resolution.to_dict()
        
        self.assertIn("resolution_id", d)
        self.assertIn("resolved_at", d)
        self.assertEqual(d["strategy"], RESOLUTION_AUTO_SELECT_BEST)


class TestConflictResolutionLog(unittest.TestCase):
    """Tests for ConflictResolutionLog class."""

    def setUp(self):
        """Set up test fixtures."""
        self.log = ConflictResolutionLog()
    
    def test_add_resolution(self):
        """Should add resolution to log."""
        resolution = ConflictResolution(
            conflict={"type": "test"},
            strategy=RESOLUTION_ESCALATE_FOR_REVIEW,
            outcome=RESOLUTION_PENDING,
            resolved_rule_ids=["r1"],
        )
        
        self.log.add_resolution(resolution)
        
        self.assertEqual(self.log.count(), 1)

    def test_get_resolutions_by_outcome(self):
        """Should filter by outcome."""
        r1 = ConflictResolution(
            conflict={"type": "a"},
            strategy=RESOLUTION_AUTO_SELECT_BEST,
            outcome=RESOLUTION_SUCCESS,
            resolved_rule_ids=["r1"],
        )
        r2 = ConflictResolution(
            conflict={"type": "b"},
            strategy=RESOLUTION_ESCALATE_FOR_REVIEW,
            outcome=RESOLUTION_PENDING,
            resolved_rule_ids=["r2"],
        )
        
        self.log.add_resolution(r1)
        self.log.add_resolution(r2)
        
        success = self.log.get_resolutions(outcome=RESOLUTION_SUCCESS)
        
        self.assertEqual(len(success), 1)

    def test_get_resolutions_by_rule_id(self):
        """Should filter by rule_id."""
        r1 = ConflictResolution(
            conflict={"type": "a"},
            strategy=RESOLUTION_AUTO_SELECT_BEST,
            outcome=RESOLUTION_SUCCESS,
            resolved_rule_ids=["r1", "r2"],
        )
        r2 = ConflictResolution(
            conflict={"type": "b"},
            strategy=RESOLUTION_ESCALATE_FOR_REVIEW,
            outcome=RESOLUTION_PENDING,
            resolved_rule_ids=["r3"],
        )
        
        self.log.add_resolution(r1)
        self.log.add_resolution(r2)
        
        with_r1 = self.log.get_resolutions(rule_id="r1")
        
        self.assertEqual(len(with_r1), 1)

    def test_get_summary(self):
        """Should get summary."""
        r1 = ConflictResolution(
            conflict={"type": "a"},
            strategy=RESOLUTION_AUTO_SELECT_BEST,
            outcome=RESOLUTION_SUCCESS,
            resolved_rule_ids=["r1"],
        )
        r2 = ConflictResolution(
            conflict={"type": "b"},
            strategy=RESOLUTION_ESCALATE_FOR_REVIEW,
            outcome=RESOLUTION_PENDING,
            resolved_rule_ids=["r2"],
        )
        
        self.log.add_resolution(r1)
        self.log.add_resolution(r2)
        
        summary = self.log.get_summary()
        
        self.assertEqual(summary["total_resolutions"], 2)
        self.assertEqual(summary["by_outcome"][RESOLUTION_SUCCESS], 1)
        self.assertEqual(summary["by_strategy"][RESOLUTION_ESCALATE_FOR_REVIEW], 1)

    def test_clear(self):
        """Should clear log."""
        self.log.add_resolution(ConflictResolution(
            conflict={"type": "test"},
            strategy=RESOLUTION_NO_ACTION,
            outcome=RESOLUTION_SKIPPED,
            resolved_rule_ids=[],
        ))
        
        self.log.clear()
        
        self.assertEqual(self.log.count(), 0)


class TestResolveConflict(unittest.TestCase):
    """Tests for resolve_conflict function."""

    def setUp(self):
        """Set up test fixtures."""
        self.registry = _setup_conflicting_registry()
        self.log = ConflictResolutionLog()
        self.policy = ConflictResolutionPolicy(auto_resolve_high_severity=True)
    
    def test_resolve_priority_override(self):
        """Should resolve with priority override."""
        conflicts = detect_rule_conflicts(self.registry)
        overlapping = [c for c in conflicts if c.get("type") == CONFLICT_OVERLAPPING_APPLICABILITY]
        
        if overlapping:
            resolution = resolve_conflict(
                conflict=overlapping[0],
                registry=self.registry,
                policy=self.policy,
                resolution_log=self.log,
            )
            
            self.assertEqual(resolution.strategy, RESOLUTION_PRIORITY_OVERRIDE)

    def test_resolve_dry_run(self):
        """Should not modify in dry run."""
        conflicts = detect_rule_conflicts(self.registry)
        
        if conflicts:
            resolution = resolve_conflict(
                conflict=conflicts[0],
                registry=self.registry,
                policy=self.policy,
                resolution_log=self.log,
                dry_run=True,
            )
            
            # Dry run should still return a resolution
            self.assertIsNotNone(resolution)

    def test_resolve_escalate_for_review(self):
        """Should escalate when not auto-resolving."""
        policy = ConflictResolutionPolicy(auto_resolve_high_severity=False)
        
        conflicts = detect_rule_conflicts(self.registry)
        high_conflicts = [c for c in conflicts if c.get("severity") == SEVERITY_HIGH]
        
        if high_conflicts:
            resolution = resolve_conflict(
                conflict=high_conflicts[0],
                registry=self.registry,
                policy=policy,
                resolution_log=self.log,
            )
            
            self.assertEqual(resolution.strategy, RESOLUTION_ESCALATE_FOR_REVIEW)
            self.assertEqual(resolution.outcome, RESOLUTION_PENDING)


class TestResolveAllConflicts(unittest.TestCase):
    """Tests for resolve_all_conflicts function."""

    def setUp(self):
        """Set up test fixtures."""
        self.registry = _setup_conflicting_registry()
        self.log = ConflictResolutionLog()
    
    def test_resolve_all(self):
        """Should resolve all conflicts."""
        policy = ConflictResolutionPolicy(
            auto_resolve_high_severity=True,
            auto_resolve_medium_severity=True,
            auto_resolve_low_severity=True,
        )
        
        result = resolve_all_conflicts(
            registry=self.registry,
            policy=policy,
            resolution_log=self.log,
            max_resolutions=5,
        )
        
        self.assertIn("total_conflicts", result)
        self.assertIn("resolutions", result)

    def test_max_resolutions_limit(self):
        """Should respect max_resolutions limit."""
        policy = ConflictResolutionPolicy(auto_resolve_high_severity=True)
        
        result = resolve_all_conflicts(
            registry=self.registry,
            policy=policy,
            resolution_log=self.log,
            max_resolutions=1,
        )
        
        self.assertLessEqual(result["applied_count"], 1)

    def test_dry_run(self):
        """Should not modify in dry run."""
        result = resolve_all_conflicts(
            registry=self.registry,
            resolution_log=self.log,
            dry_run=True,
        )
        
        self.assertTrue(result["dry_run"])


class TestGlobalResolutionLog(unittest.TestCase):
    """Tests for global resolution log functions."""

    def setUp(self):
        """Reset global log before each test."""
        reset_resolution_log()
    
    def tearDown(self):
        """Reset global log after each test."""
        reset_resolution_log()
    
    def test_get_resolution_log(self):
        """Should return global log."""
        log = get_resolution_log()
        
        self.assertIsInstance(log, ConflictResolutionLog)

    def test_global_log_persists(self):
        """Should persist across calls."""
        log1 = get_resolution_log()
        log2 = get_resolution_log()
        
        self.assertIs(log1, log2)


class TestGenerateResolutionReport(unittest.TestCase):
    """Tests for generate_resolution_report function."""

    def test_generate_text_report(self):
        """Should generate text report."""
        resolutions = [
            ConflictResolution(
                conflict={"type": "test", "severity": "low"},
                strategy=RESOLUTION_AUTO_SELECT_BEST,
                outcome=RESOLUTION_SUCCESS,
                resolved_rule_ids=["r1"],
                notes="Test note",
            )
        ]
        
        report = generate_resolution_report(resolutions, format_type="text")
        
        self.assertIn("Conflict Resolution Report", report)

    def test_generate_markdown_report(self):
        """Should generate markdown report."""
        resolutions = [
            ConflictResolution(
                conflict={"type": CONFLICT_OVERLAPPING_APPLICABILITY, "severity": "high"},
                strategy=RESOLUTION_PRIORITY_OVERRIDE,
                outcome=RESOLUTION_SUCCESS,
                resolved_rule_ids=["r1", "r2"],
                notes="Priority override",
            )
        ]
        
        report = generate_resolution_report(resolutions, format_type="markdown")
        
        self.assertIn("# Conflict Resolution Report", report)
        self.assertIn("Priority", report)

    def test_empty_resolutions(self):
        """Should handle empty list."""
        report = generate_resolution_report([], format_type="text")
        
        self.assertIn("0", report)


class TestEstimateResolutionImpact(unittest.TestCase):
    """Tests for estimate_resolution_impact function."""

    def setUp(self):
        """Set up test fixtures."""
        self.registry = _setup_clean_registry()
    
    def test_estimate_high_severity_impact(self):
        """Should estimate positive impact for high severity."""
        conflict = {
            "type": CONFLICT_OVERLAPPING_APPLICABILITY,
            "severity": SEVERITY_HIGH,
            "rule_ids": ["r1", "r2"],
        }
        
        impact = estimate_resolution_impact(conflict, self.registry)
        
        self.assertEqual(impact["health_impact"], "positive")
        self.assertEqual(impact["resolution_risk"], RISK_HIGH)

    def test_estimate_low_severity_impact(self):
        """Should estimate minimal impact for low severity."""
        conflict = {
            "type": CONFLICT_INCONSISTENT_PROVENANCE,
            "severity": SEVERITY_LOW,
            "rule_ids": ["r1"],
        }
        
        impact = estimate_resolution_impact(conflict, self.registry)
        
        self.assertEqual(impact["health_impact"], "minimal")
        self.assertEqual(impact["resolution_risk"], RISK_LOW)

    def test_recommendation_by_type(self):
        """Should provide appropriate recommendations."""
        # Rollback reintroduction should resolve immediately
        conflict = {
            "type": CONFLICT_ROLLBACK_REINTRODUCTION,
            "severity": SEVERITY_HIGH,
            "rule_ids": ["r1"],
        }
        
        impact = estimate_resolution_impact(conflict, self.registry)
        
        self.assertEqual(impact["recommendation"], "resolve_immediately")


class TestResolutionStrategies(unittest.TestCase):
    """Tests for different resolution strategies."""

    def setUp(self):
        """Set up test fixtures."""
        self.registry = _setup_conflicting_registry()
        self.log = ConflictResolutionLog()
    
    def test_priority_override_strategy(self):
        """Test priority override strategy."""
        policy = ConflictResolutionPolicy(
            auto_resolve_high_severity=True,
            priority_rules={"conflict-rule-001": 10, "conflict-rule-002": 5},
        )
        
        conflicts = detect_rule_conflicts(self.registry)
        overlapping = [c for c in conflicts if c.get("type") == CONFLICT_OVERLAPPING_APPLICABILITY]
        
        if overlapping:
            resolution = resolve_conflict(
                conflict=overlapping[0],
                registry=self.registry,
                policy=policy,
                resolution_log=self.log,
            )
            
            # Should have resolved
            self.assertEqual(resolution.outcome, RESOLUTION_SUCCESS)

    def test_escalate_for_review_strategy(self):
        """Test escalate for review strategy."""
        policy = ConflictResolutionPolicy(auto_resolve_high_severity=False)
        
        conflicts = detect_rule_conflicts(self.registry)
        high_conflicts = [c for c in conflicts if c.get("severity") == SEVERITY_HIGH]
        
        if high_conflicts:
            resolution = resolve_conflict(
                conflict=high_conflicts[0],
                registry=self.registry,
                policy=policy,
                resolution_log=self.log,
            )
            
            self.assertEqual(resolution.outcome, RESOLUTION_PENDING)


class TestIntegration(unittest.TestCase):
    """Integration tests for conflict resolution."""

    def test_full_resolution_flow(self):
        """Test complete conflict resolution flow."""
        # Create conflicting registry
        registry = _setup_conflicting_registry()
        
        # Detect conflicts
        conflicts = detect_rule_conflicts(registry)
        self.assertTrue(len(conflicts) > 0)
        
        # Create policy
        policy = ConflictResolutionPolicy(
            auto_resolve_low_severity=True,
            auto_resolve_medium_severity=True,
            auto_resolve_high_severity=True,
        )
        
        # Resolve all
        log = ConflictResolutionLog()
        result = resolve_all_conflicts(
            registry=registry,
            policy=policy,
            resolution_log=log,
            max_resolutions=5,
        )
        
        # Check result
        self.assertIn("total_conflicts", result)
        self.assertIn("resolutions", result)
        
        # Get summary
        summary = get_conflict_resolution_summary(log)
        self.assertIn("total_resolutions", summary)


if __name__ == "__main__":
    unittest.main()
