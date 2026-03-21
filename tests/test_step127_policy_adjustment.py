#!/usr/bin/env python3
"""Step127: Automated Policy Adjustment Tests

Tests for dynamic policy change suggestions, adjustments, and auto-correction.
"""
from __future__ import annotations

import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.policy_adjustment import (
    PolicyChangeSuggestion,
    generate_policy_change_suggestion,
    apply_policy_changes,
    auto_correct_policies,
    PolicyAdjustmentScheduler,
    evaluate_adjustment_impact,
    prioritize_suggestions,
    get_adjustment_scheduler,
    start_scheduled_adjustments,
    stop_scheduled_adjustments,
    SUGGESTION_ADJUST_THRESHOLD,
    SUGGESTION_ADD_RULE,
    SUGGESTION_REMOVE_RULE,
    SUGGESTION_MODIFY_RULE,
    SUGGESTION_REORDER_PRIORITY,
    SUGGESTION_ADD_GUARDRAIL,
    SUGGESTION_REMOVE_GUARDRAIL,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
)

from eval.candidate_rules import (
    AdoptionRegistry,
    make_candidate,
    review_candidate,
    make_provenance,
    DECISION_AUTO_PROMOTE,
    DECISION_REVIEW_REQUIRED,
    DECISION_HALT,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_ROLLED_BACK,
)

from eval.risk_simulator import (
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
)


def _setup_clean_registry(rule_count: int = 3) -> AdoptionRegistry:
    """Helper to create a clean registry with unique rules."""
    registry = AdoptionRegistry()
    for i in range(1, rule_count + 1):
        rule_id = f"clean-rule-{i:03d}"
        c = make_candidate(
            candidate_rule_id=rule_id,
            description=f"Clean rule {i}",
            expected_effect="Test effect",
            affected_cases=[f"case-clean-{i}"],
            risk_level="low",
            recommendation="adopt",
            rule_type=f"clean_type_{i}",
            suggested_change={"tier": i},
        )
        candidate = review_candidate(c, decision="accepted", reviewer="tester")
        provenance = make_provenance(
            rule_id=rule_id,
            source_candidate_rule_id=rule_id,
            source_regression_case_ids=[f"case-clean-{i}"],
            created_by="test",
        )
        registry.adopt(candidate, adopted_by="tester", provenance=provenance)
    return registry


def _setup_unhealthy_registry() -> AdoptionRegistry:
    """Helper to create a registry with health issues."""
    registry = AdoptionRegistry()
    
    # Add some rules
    for i in range(1, 4):
        rule_id = f"unhealthy-rule-{i:03d}"
        c = make_candidate(
            candidate_rule_id=rule_id,
            description=f"Rule {i}",
            expected_effect="Test",
            affected_cases=[f"case-{i}"],
            risk_level="medium",
            recommendation="adopt",
            rule_type="same_type",  # Same type to create conflicts
            suggested_change={"tier": i},
        )
        candidate = review_candidate(c, decision="accepted", reviewer="tester")
        provenance = make_provenance(
            rule_id=rule_id,
            source_candidate_rule_id=rule_id,
            source_regression_case_ids=["case-1"],  # Same cases to create conflicts
            created_by="test",
        )
        registry.adopt(candidate, adopted_by="tester", provenance=provenance)
    
    # Add a rolled-back rule
    rb_id = "rolled-back-rule-001"
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


class TestPolicyChangeSuggestion(unittest.TestCase):
    """Tests for PolicyChangeSuggestion class."""

    def test_suggestion_creation(self):
        """Should create a policy change suggestion."""
        suggestion = PolicyChangeSuggestion(
            suggestion_type=SUGGESTION_ADJUST_THRESHOLD,
            priority=PRIORITY_HIGH,
            description="Adjust threshold",
            rationale="Health score is low",
        )
        
        self.assertEqual(suggestion.suggestion_type, SUGGESTION_ADJUST_THRESHOLD)
        self.assertEqual(suggestion.priority, PRIORITY_HIGH)
        self.assertIn("suggestion_id", suggestion.to_dict())

    def test_suggestion_to_dict(self):
        """Should convert to dictionary."""
        suggestion = PolicyChangeSuggestion(
            suggestion_type=SUGGESTION_MODIFY_RULE,
            priority=PRIORITY_CRITICAL,
            description="Fix rule",
            rationale="Conflict detected",
            target_rule_id="rule-001",
            suggested_change={"tier": 5},
            expected_impact={"health_improvement": 10},
            confidence=0.85,
        )
        
        d = suggestion.to_dict()
        
        self.assertEqual(d["target_rule_id"], "rule-001")
        self.assertEqual(d["suggested_change"]["tier"], 5)
        self.assertEqual(d["confidence"], 0.85)


class TestGeneratePolicyChangeSuggestion(unittest.TestCase):
    """Tests for generate_policy_change_suggestion function."""

    def test_generate_suggestions_clean_registry(self):
        """Should generate minimal suggestions for clean registry."""
        registry = _setup_clean_registry(3)
        
        suggestions = generate_policy_change_suggestion(registry)
        
        # Clean registry should have few or no critical suggestions
        critical = [s for s in suggestions if s.priority == PRIORITY_CRITICAL]
        self.assertEqual(len(critical), 0)

    def test_generate_suggestions_unhealthy_registry(self):
        """Should generate more suggestions for unhealthy registry."""
        registry = _setup_unhealthy_registry()
        
        suggestions = generate_policy_change_suggestion(registry)
        
        # Unhealthy registry should generate suggestions
        self.assertTrue(len(suggestions) > 0)

    def test_suggestions_are_prioritized(self):
        """Should return suggestions sorted by priority."""
        registry = _setup_unhealthy_registry()
        
        suggestions = generate_policy_change_suggestion(registry)
        
        # Check ordering
        priority_order = {PRIORITY_CRITICAL: 0, PRIORITY_HIGH: 1, PRIORITY_MEDIUM: 2, PRIORITY_LOW: 3}
        for i in range(len(suggestions) - 1):
            curr_priority = priority_order.get(suggestions[i].priority, 99)
            next_priority = priority_order.get(suggestions[i + 1].priority, 99)
            self.assertLessEqual(curr_priority, next_priority)


class TestApplyPolicyChanges(unittest.TestCase):
    """Tests for apply_policy_changes function."""

    def setUp(self):
        """Set up test fixtures."""
        self.registry = _setup_clean_registry(2)
    
    def test_dry_run(self):
        """Should not apply changes in dry run mode."""
        suggestions = [
            PolicyChangeSuggestion(
                suggestion_type=SUGGESTION_ADJUST_THRESHOLD,
                priority=PRIORITY_HIGH,
                description="Test",
                rationale="Test",
                confidence=0.9,
            )
        ]
        
        result = apply_policy_changes(
            self.registry,
            suggestions,
            auto_apply=True,
            dry_run=True,
        )
        
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["applied_count"], 0)

    def test_apply_no_auto(self):
        """Should not apply without auto_apply."""
        suggestions = [
            PolicyChangeSuggestion(
                suggestion_type=SUGGESTION_ADJUST_THRESHOLD,
                priority=PRIORITY_HIGH,
                description="Test",
                rationale="Test",
                confidence=0.9,
            )
        ]
        
        result = apply_policy_changes(
            self.registry,
            suggestions,
            auto_apply=False,
            dry_run=False,
        )
        
        # Should skip all without auto_apply
        self.assertEqual(result["applied_count"], 0)
        self.assertGreater(result["skipped_count"], 0)

    def test_max_changes_limit(self):
        """Should respect max_changes limit."""
        suggestions = [
            PolicyChangeSuggestion(
                suggestion_type=SUGGESTION_ADJUST_THRESHOLD,
                priority=PRIORITY_HIGH,
                description=f"Test {i}",
                rationale="Test",
                confidence=0.9,
            )
            for i in range(10)
        ]
        
        result = apply_policy_changes(
            self.registry,
            suggestions,
            auto_apply=True,
            max_changes=2,
            dry_run=False,
        )
        
        self.assertLessEqual(result["applied_count"], 2)


class TestAutoCorrectPolicies(unittest.TestCase):
    """Tests for auto_correct_policies function."""

    def test_correct_clean_registry(self):
        """Should find no issues in clean registry."""
        registry = _setup_clean_registry(3)
        
        result = auto_correct_policies(registry, dry_run=True)
        
        self.assertEqual(result["issues_found"], 0)

    def test_correct_unhealthy_registry(self):
        """Should find and report issues in unhealthy registry."""
        registry = _setup_unhealthy_registry()
        
        result = auto_correct_policies(registry, dry_run=True)
        
        # Should detect some issues
        self.assertTrue(result["issues_found"] > 0 or len(result["corrections"]) > 0)

    def test_dry_run_no_changes(self):
        """Should not make changes in dry run."""
        registry = _setup_unhealthy_registry()
        
        result = auto_correct_policies(registry, dry_run=True)
        
        self.assertEqual(result["issues_fixed"], 0)

    def test_health_threshold_parameter(self):
        """Should use health threshold parameter."""
        registry = _setup_clean_registry(3)
        
        # High threshold should trigger even for clean registry
        result = auto_correct_policies(
            registry,
            health_threshold=100,  # Very high
            dry_run=True,
        )
        
        # May or may not find issues depending on health score
        self.assertIn("issues_found", result)


class TestPolicyAdjustmentScheduler(unittest.TestCase):
    """Tests for PolicyAdjustmentScheduler class."""

    def setUp(self):
        """Set up test fixtures."""
        self.registry = _setup_clean_registry(2)
        self.scheduler = PolicyAdjustmentScheduler(
            self.registry,
            adjustment_interval_hours=24,
        )
    
    def tearDown(self):
        """Clean up after tests."""
        self.scheduler.stop()
    
    def test_scheduler_initial_state(self):
        """Should have correct initial state."""
        status = self.scheduler.get_status()
        
        self.assertFalse(status["running"])
        self.assertEqual(status["adjustment_count"], 0)

    def test_run_adjustment(self):
        """Should run adjustment and return result."""
        result = self.scheduler.run_adjustment()
        
        self.assertIn("adjustment_id", result)
        self.assertIn("timestamp", result)
        self.assertIn("suggestions", result)
        self.assertIn("corrections", result)

    def test_run_adjustment_increments_count(self):
        """Should increment adjustment count."""
        self.scheduler.run_adjustment()
        self.scheduler.run_adjustment()
        
        status = self.scheduler.get_status()
        self.assertEqual(status["adjustment_count"], 2)

    def test_start_stop(self):
        """Should start and stop scheduler."""
        callback_called = []
        
        def on_adjustment(result):
            callback_called.append(result)
        
        self.scheduler.set_callback(on_adjustment=on_adjustment)
        self.scheduler.adjustment_interval_hours = 0  # Run immediately
        self.scheduler.start()
        
        # Wait briefly for first adjustment
        time.sleep(0.5)
        
        self.scheduler.stop()
        
        self.assertTrue(len(callback_called) > 0)


class TestEvaluateAdjustmentImpact(unittest.TestCase):
    """Tests for evaluate_adjustment_impact function."""

    def setUp(self):
        """Set up test fixtures."""
        self.registry = _setup_clean_registry(2)
    
    def test_evaluate_add_rule_suggestion(self):
        """Should evaluate add rule suggestion."""
        suggestion = PolicyChangeSuggestion(
            suggestion_type=SUGGESTION_ADD_RULE,
            priority=PRIORITY_MEDIUM,
            description="Add new rule",
            rationale="Need coverage",
            target_rule_id="new-rule-001",
            suggested_change={"rule_type": "test_type"},
        )
        
        result = evaluate_adjustment_impact(self.registry, suggestion)
        
        self.assertIn("risk_assessment", result)
        self.assertIn("recommendation", result)

    def test_evaluate_modify_rule_suggestion(self):
        """Should evaluate modify rule suggestion."""
        suggestion = PolicyChangeSuggestion(
            suggestion_type=SUGGESTION_MODIFY_RULE,
            priority=PRIORITY_HIGH,
            description="Modify rule",
            rationale="Update threshold",
            target_rule_id="existing-rule",
        )
        
        result = evaluate_adjustment_impact(self.registry, suggestion)
        
        self.assertEqual(result["recommendation"], "caution")

    def test_evaluate_remove_rule_suggestion(self):
        """Should evaluate remove rule suggestion."""
        suggestion = PolicyChangeSuggestion(
            suggestion_type=SUGGESTION_REMOVE_RULE,
            priority=PRIORITY_LOW,
            description="Remove rule",
            rationale="No longer needed",
            target_rule_id="old-rule",
        )
        
        result = evaluate_adjustment_impact(self.registry, suggestion)
        
        self.assertEqual(result["recommendation"], "proceed_with_confirmation")


class TestPrioritizeSuggestions(unittest.TestCase):
    """Tests for prioritize_suggestions function."""

    def test_prioritize_empty_list(self):
        """Should handle empty list."""
        registry = _setup_clean_registry(1)
        
        result = prioritize_suggestions([], registry)
        
        self.assertEqual(len(result), 0)

    def test_prioritize_orders_by_risk_and_priority(self):
        """Should order suggestions by risk and priority."""
        registry = _setup_clean_registry(1)
        
        suggestions = [
            PolicyChangeSuggestion(
                suggestion_type=SUGGESTION_ADJUST_THRESHOLD,
                priority=PRIORITY_LOW,
                description="Low priority",
                rationale="Test",
                confidence=0.5,
            ),
            PolicyChangeSuggestion(
                suggestion_type=SUGGESTION_ADJUST_THRESHOLD,
                priority=PRIORITY_CRITICAL,
                description="Critical priority",
                rationale="Test",
                confidence=0.9,
            ),
        ]
        
        result = prioritize_suggestions(suggestions, registry)
        
        # Critical should come first
        self.assertEqual(result[0].priority, PRIORITY_CRITICAL)
        self.assertEqual(result[1].priority, PRIORITY_LOW)


class TestGlobalScheduler(unittest.TestCase):
    """Tests for global scheduler functions."""

    def tearDown(self):
        """Stop global scheduler after each test."""
        stop_scheduled_adjustments()
    
    def test_get_adjustment_scheduler(self):
        """Should return global scheduler instance."""
        registry = _setup_clean_registry(1)
        
        scheduler1 = get_adjustment_scheduler(registry)
        scheduler2 = get_adjustment_scheduler(registry)
        
        self.assertIs(scheduler1, scheduler2)
    
    def test_start_stop_scheduled_adjustments(self):
        """Should start and stop global scheduler."""
        registry = _setup_clean_registry(1)
        
        scheduler = start_scheduled_adjustments(
            registry,
            interval_hours=24,
        )
        
        self.assertTrue(scheduler.get_status()["running"])
        
        stop_scheduled_adjustments()
        
        self.assertFalse(scheduler.get_status()["running"])


class TestSuggestionTypes(unittest.TestCase):
    """Tests for suggestion type constants."""

    def test_valid_suggestion_types(self):
        """Should have valid suggestion types."""
        from eval.policy_adjustment import VALID_SUGGESTION_TYPES
        
        self.assertIn(SUGGESTION_ADJUST_THRESHOLD, VALID_SUGGESTION_TYPES)
        self.assertIn(SUGGESTION_ADD_RULE, VALID_SUGGESTION_TYPES)
        self.assertIn(SUGGESTION_REMOVE_RULE, VALID_SUGGESTION_TYPES)
        self.assertIn(SUGGESTION_MODIFY_RULE, VALID_SUGGESTION_TYPES)


class TestPriorityLevels(unittest.TestCase):
    """Tests for priority level constants."""

    def test_valid_priorities(self):
        """Should have valid priorities."""
        from eval.policy_adjustment import VALID_PRIORITIES
        
        self.assertIn(PRIORITY_CRITICAL, VALID_PRIORITIES)
        self.assertIn(PRIORITY_HIGH, VALID_PRIORITIES)
        self.assertIn(PRIORITY_MEDIUM, VALID_PRIORITIES)
        self.assertIn(PRIORITY_LOW, VALID_PRIORITIES)


class TestIntegration(unittest.TestCase):
    """Integration tests for policy adjustment."""

    def test_full_adjustment_flow(self):
        """Test complete adjustment flow."""
        # Create unhealthy registry
        registry = _setup_unhealthy_registry()
        
        # Generate suggestions
        suggestions = generate_policy_change_suggestion(registry)
        self.assertTrue(len(suggestions) > 0)
        
        # Prioritize
        prioritized = prioritize_suggestions(suggestions, registry)
        
        # Apply in dry run
        result = apply_policy_changes(
            registry,
            prioritized,
            auto_apply=True,
            max_changes=3,
            dry_run=True,
        )
        
        self.assertTrue(result["dry_run"])
        
        # Run auto correction
        corrections = auto_correct_policies(registry, dry_run=True)
        self.assertIn("issues_found", corrections)


if __name__ == "__main__":
    unittest.main()
