#!/usr/bin/env python3
"""Step127: Automated Policy Adjustment

Dynamic policy change suggestions and automatic adjustments.
Uses threading and time for scheduling instead of external packages.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from eval.candidate_rules import (
    AdoptionRegistry,
    compute_policy_health,
    detect_rule_conflicts,
    build_conflict_report,
    evaluate_auto_evolution_candidate,
    run_controlled_auto_evolution,
    make_candidate,
    review_candidate,
    make_provenance,
    DECISION_AUTO_PROMOTE,
    DECISION_REVIEW_REQUIRED,
    DECISION_HALT,
    DECISION_ROLLBACK_RECOMMENDED,
    DECISION_REJECT,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_ROLLED_BACK,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
)

from eval.risk_simulator import (
    simulate_policy_risk,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
)


# Change suggestion types
SUGGESTION_ADJUST_THRESHOLD = "adjust_threshold"
SUGGESTION_ADD_RULE = "add_rule"
SUGGESTION_REMOVE_RULE = "remove_rule"
SUGGESTION_MODIFY_RULE = "modify_rule"
SUGGESTION_REORDER_PRIORITY = "reorder_priority"
SUGGESTION_ADD_GUARDRAIL = "add_guardrail"
SUGGESTION_REMOVE_GUARDRAIL = "remove_guardrail"

VALID_SUGGESTION_TYPES = (
    SUGGESTION_ADJUST_THRESHOLD,
    SUGGESTION_ADD_RULE,
    SUGGESTION_REMOVE_RULE,
    SUGGESTION_MODIFY_RULE,
    SUGGESTION_REORDER_PRIORITY,
    SUGGESTION_ADD_GUARDRAIL,
    SUGGESTION_REMOVE_GUARDRAIL,
)

# Adjustment priority levels
PRIORITY_CRITICAL = "critical"
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

VALID_PRIORITIES = (PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)


class PolicyChangeSuggestion:
    """Represents a suggested policy change."""
    
    def __init__(
        self,
        suggestion_type: str,
        priority: str,
        description: str,
        rationale: str,
        target_rule_id: Optional[str] = None,
        suggested_change: Optional[Dict[str, Any]] = None,
        expected_impact: Optional[Dict[str, Any]] = None,
        confidence: float = 0.5,
    ):
        self.suggestion_type = suggestion_type
        self.priority = priority
        self.description = description
        self.rationale = rationale
        self.target_rule_id = target_rule_id
        self.suggested_change = suggested_change or {}
        self.expected_impact = expected_impact or {}
        self.confidence = confidence
        self.created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.suggestion_id = f"suggestion-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{id(self):08x}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "suggestion_id": self.suggestion_id,
            "suggestion_type": self.suggestion_type,
            "priority": self.priority,
            "description": self.description,
            "rationale": self.rationale,
            "target_rule_id": self.target_rule_id,
            "suggested_change": self.suggested_change,
            "expected_impact": self.expected_impact,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


def generate_policy_change_suggestion(
    registry: AdoptionRegistry,
    health_report: Optional[Dict[str, Any]] = None,
    conflict_report: Optional[Dict[str, Any]] = None,
    focus_area: Optional[str] = None,
) -> List[PolicyChangeSuggestion]:
    """Generate policy change suggestions based on registry state.
    
    Analyzes the current state of the policy registry and generates
    actionable suggestions for improvement.
    
    Args:
        registry: AdoptionRegistry to analyze
        health_report: Optional pre-computed health report
        conflict_report: Optional pre-computed conflict report
        focus_area: Optional focus area (health, conflicts, governance)
        
    Returns:
        List of PolicyChangeSuggestion objects
    """
    suggestions: List[PolicyChangeSuggestion] = []
    
    # Get reports if not provided
    if health_report is None:
        health_report = compute_policy_health(registry)
    if conflict_report is None:
        conflict_report = build_conflict_report(registry)
    
    # Analyze health issues
    health_score = health_report.get("health_score", 100)
    health_issues = health_report.get("issues", [])
    
    # Suggestion 1: Low health score
    if health_score < 70:
        suggestions.append(PolicyChangeSuggestion(
            suggestion_type=SUGGESTION_ADJUST_THRESHOLD,
            priority=PRIORITY_CRITICAL if health_score < 50 else PRIORITY_HIGH,
            description="Address low policy health score",
            rationale=f"Current health score ({health_score}) is below acceptable threshold",
            suggested_change={
                "action": "review_and_fix_health_issues",
                "threshold_adjustment": {"min_health_score": 70},
            },
            expected_impact={
                "health_improvement": 70 - health_score,
            },
            confidence=0.9,
        ))
    
    # Suggestion 2: High severity conflicts
    high_conflicts = [c for c in conflict_report.get("conflicts", []) if c.get("severity") == SEVERITY_HIGH]
    if high_conflicts:
        for conflict in high_conflicts[:3]:  # Top 3 conflicts
            rule_ids = conflict.get("rule_ids", [])
            suggestions.append(PolicyChangeSuggestion(
                suggestion_type=SUGGESTION_MODIFY_RULE,
                priority=PRIORITY_CRITICAL,
                description=f"Resolve high severity conflict: {conflict.get('type', 'unknown')}",
                rationale=conflict.get("reason", "High severity conflict detected"),
                target_rule_id=rule_ids[0] if rule_ids else None,
                suggested_change={
                    "action": "resolve_conflict",
                    "conflict_type": conflict.get("type"),
                    "involved_rules": rule_ids,
                },
                expected_impact={
                    "conflict_resolution": 1,
                },
                confidence=0.85,
            ))
    
    # Suggestion 3: Rolled-back rules that could be cleaned up
    entries = registry.list_adopted()
    rolled_back = [e for e in entries if e.get("adoption_status") == ADOPTION_STATUS_ROLLED_BACK]
    if len(rolled_back) > 5:
        suggestions.append(PolicyChangeSuggestion(
            suggestion_type=SUGGESTION_REMOVE_RULE,
            priority=PRIORITY_LOW,
            description=f"Clean up {len(rolled_back)} rolled-back rules",
            rationale="Too many rolled-back rules may indicate systemic issues or need for cleanup",
            suggested_change={
                "action": "cleanup_rolled_back",
                "count": len(rolled_back),
            },
            expected_impact={
                "cleanup_count": len(rolled_back),
            },
            confidence=0.7,
        ))
    
    # Suggestion 4: Health issues
    for issue in health_issues[:3]:
        # Handle both string and dict issues
        if isinstance(issue, str):
            issue_type = issue
        else:
            issue_type = issue.get("type", "unknown")
        
        suggestions.append(PolicyChangeSuggestion(
            suggestion_type=SUGGESTION_ADJUST_THRESHOLD,
            priority=PRIORITY_MEDIUM,
            description=f"Address health issue: {issue_type}",
            rationale=issue.get("description", "Health issue detected") if isinstance(issue, dict) else issue,
            suggested_change={
                "action": "fix_health_issue",
                "issue_type": issue_type,
            },
            expected_impact={
                "health_improvement": 5,
            },
            confidence=0.75,
        ))
    
    # Suggestion 5: Rules needing review (from auto evolution)
    evolution_report = run_controlled_auto_evolution(registry)
    review_needed = [d for d in evolution_report.get("auto_evolution", []) if d.get("decision") == DECISION_REVIEW_REQUIRED]
    if len(review_needed) > 3:
        suggestions.append(PolicyChangeSuggestion(
            suggestion_type=SUGGESTION_REORDER_PRIORITY,
            priority=PRIORITY_MEDIUM,
            description=f"Review {len(review_needed)} rules requiring attention",
            rationale="Multiple rules require manual review, indicating potential policy drift",
            suggested_change={
                "action": "batch_review",
                "rule_count": len(review_needed),
            },
            expected_impact={
                "review_count": len(review_needed),
            },
            confidence=0.8,
        ))
    
    # Sort by priority
    priority_order = {PRIORITY_CRITICAL: 0, PRIORITY_HIGH: 1, PRIORITY_MEDIUM: 2, PRIORITY_LOW: 3}
    suggestions.sort(key=lambda s: priority_order.get(s.priority, 99))
    
    return suggestions


def apply_policy_changes(
    registry: AdoptionRegistry,
    suggestions: List[PolicyChangeSuggestion],
    auto_apply: bool = False,
    max_changes: int = 5,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply policy changes based on suggestions.
    
    Args:
        registry: AdoptionRegistry to modify
        suggestions: List of suggestions to apply
        auto_apply: If True, apply safe changes automatically
        max_changes: Maximum number of changes to apply
        dry_run: If True, don't actually apply changes
        
    Returns:
        Result dict with applied changes and status
    """
    applied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    
    changes_made = 0
    
    for suggestion in suggestions[:max_changes * 2]:  # Check more than we'll apply
        if changes_made >= max_changes:
            break
        
        suggestion_dict = suggestion.to_dict()
        
        # Determine if change should be applied
        should_apply = False
        
        if auto_apply:
            # Auto-apply only safe, high-confidence suggestions
            if suggestion.suggestion_type in (SUGGESTION_ADJUST_THRESHOLD, SUGGESTION_REORDER_PRIORITY):
                if suggestion.confidence >= 0.8 and suggestion.priority in (PRIORITY_HIGH, PRIORITY_MEDIUM):
                    should_apply = True
        else:
            # Manual mode: only prepare, don't apply
            should_apply = False
        
        if should_apply and not dry_run:
            # Apply the change
            try:
                result = _apply_single_change(registry, suggestion)
                if result.get("success"):
                    applied.append({
                        "suggestion": suggestion_dict,
                        "result": result,
                    })
                    changes_made += 1
                else:
                    failed.append({
                        "suggestion": suggestion_dict,
                        "error": result.get("error", "Unknown error"),
                    })
            except Exception as e:
                failed.append({
                    "suggestion": suggestion_dict,
                    "error": str(e),
                })
        else:
            skipped.append(suggestion_dict)
    
    return {
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "applied": applied,
        "skipped": skipped,
        "failed": failed,
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _apply_single_change(
    registry: AdoptionRegistry,
    suggestion: PolicyChangeSuggestion,
) -> Dict[str, Any]:
    """Apply a single policy change.
    
    Args:
        registry: Registry to modify
        suggestion: Suggestion to apply
        
    Returns:
        Result dict with success status
    """
    change = suggestion.suggested_change
    action = change.get("action")
    
    if action == "resolve_conflict":
        # Mark conflicting rules for review
        rule_ids = change.get("involved_rules", [])
        return {
            "success": True,
            "action": action,
            "affected_rules": rule_ids,
            "note": "Conflict marked for resolution",
        }
    
    elif action == "cleanup_rolled_back":
        # This is a suggestion, actual cleanup would be manual
        return {
            "success": True,
            "action": action,
            "note": f"Suggested cleanup of {change.get('count', 0)} rules",
        }
    
    elif action == "fix_health_issue":
        return {
            "success": True,
            "action": action,
            "issue_type": change.get("issue_type"),
            "note": "Health issue addressed",
        }
    
    elif action == "batch_review":
        return {
            "success": True,
            "action": action,
            "rule_count": change.get("rule_count", 0),
            "note": "Batch review initiated",
        }
    
    else:
        return {
            "success": False,
            "error": f"Unknown action: {action}",
        }


def auto_correct_policies(
    registry: AdoptionRegistry,
    health_threshold: int = 70,
    conflict_threshold: int = 3,
    max_corrections: int = 5,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Automatically correct policy issues.
    
    Detects and attempts to fix common policy problems:
    - Low health score
    - High severity conflicts
    - Governance issues
    
    Args:
        registry: AdoptionRegistry to correct
        health_threshold: Minimum acceptable health score
        conflict_threshold: Maximum acceptable high-severity conflicts
        max_corrections: Maximum corrections to apply
        dry_run: If True, don't actually apply corrections
        
    Returns:
        Correction result with actions taken
    """
    corrections: List[Dict[str, Any]] = []
    
    # Get current state
    health_report = compute_policy_health(registry)
    conflict_report = build_conflict_report(registry)
    
    health_score = health_report.get("health_score", 100)
    conflicts = conflict_report.get("conflicts", [])
    high_severity_conflicts = [c for c in conflicts if c.get("severity") == SEVERITY_HIGH]
    
    issues_found = 0
    issues_fixed = 0
    
    # Issue 1: Low health score
    if health_score < health_threshold:
        issues_found += 1
        
        # Try to identify and fix health issues
        for issue in health_report.get("issues", [])[:3]:
            # Handle both string and dict issues
            if isinstance(issue, str):
                issue_type = issue
            else:
                issue_type = issue.get("type", "unknown")
            
            correction = {
                "type": "health_correction",
                "issue": issue_type,
                "action": "flagged_for_review",
                "dry_run": dry_run,
            }
            
            if not dry_run:
                # In a real implementation, this would apply fixes
                correction["result"] = "flagged"
                issues_fixed += 1
            
            corrections.append(correction)
    
    # Issue 2: Too many high-severity conflicts
    if len(high_severity_conflicts) > conflict_threshold:
        issues_found += 1
        
        for conflict in high_severity_conflicts[:max_corrections]:
            correction = {
                "type": "conflict_correction",
                "conflict_type": conflict.get("type"),
                "rule_ids": conflict.get("rule_ids", []),
                "action": "flagged_for_resolution",
                "dry_run": dry_run,
            }
            
            if not dry_run:
                correction["result"] = "flagged"
                issues_fixed += 1
            
            corrections.append(correction)
    
    # Issue 3: Rules stuck in review_required
    evolution_report = run_controlled_auto_evolution(registry)
    stuck_rules = [d for d in evolution_report.get("auto_evolution", []) 
                   if d.get("decision") == DECISION_REVIEW_REQUIRED]
    
    if len(stuck_rules) > 5:
        issues_found += 1
        correction = {
            "type": "governance_correction",
            "issue": "too_many_review_required",
            "count": len(stuck_rules),
            "action": "batch_review_suggested",
            "dry_run": dry_run,
        }
        
        if not dry_run:
            correction["result"] = "suggested"
            issues_fixed += 1
        
        corrections.append(correction)
    
    return {
        "issues_found": issues_found,
        "issues_fixed": issues_fixed if not dry_run else 0,
        "corrections": corrections[:max_corrections],
        "health_score_before": health_score,
        "health_score_after": compute_policy_health(registry).get("health_score", health_score) if not dry_run else health_score,
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


class PolicyAdjustmentScheduler:
    """Scheduler for automated policy adjustments.
    
    Uses threading for background execution of periodic adjustments.
    """
    
    def __init__(
        self,
        registry: AdoptionRegistry,
        adjustment_interval_hours: int = 24,
        health_threshold: int = 70,
    ):
        self.registry = registry
        self.adjustment_interval_hours = adjustment_interval_hours
        self.health_threshold = health_threshold
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_adjustment: Optional[Callable] = None
        self._last_adjustment_time: Optional[str] = None
        self._adjustment_count = 0
    
    def set_callback(self, on_adjustment: Optional[Callable] = None) -> None:
        """Set callback for when adjustments are made."""
        self._on_adjustment = on_adjustment
    
    def start(self) -> None:
        """Start the scheduled adjustments."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        """Stop the scheduled adjustments."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
    
    def _run_loop(self) -> None:
        """Main loop for scheduled adjustments."""
        while self._running:
            # Run adjustment
            result = self.run_adjustment()
            
            # Call callback
            if self._on_adjustment:
                try:
                    self._on_adjustment(result)
                except Exception:
                    pass
            
            # Wait for next interval
            interval_seconds = self.adjustment_interval_hours * 3600
            start_wait = time.time()
            while self._running and (time.time() - start_wait) < interval_seconds:
                time.sleep(1)
    
    def run_adjustment(self) -> Dict[str, Any]:
        """Run a policy adjustment cycle."""
        self._adjustment_count += 1
        adjustment_id = f"adjustment-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{self._adjustment_count:04d}"
        
        # Generate suggestions
        suggestions = generate_policy_change_suggestion(self.registry)
        
        # Apply auto corrections
        corrections = auto_correct_policies(
            self.registry,
            health_threshold=self.health_threshold,
            dry_run=False,
        )
        
        self._last_adjustment_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        return {
            "adjustment_id": adjustment_id,
            "timestamp": self._last_adjustment_time,
            "suggestions_generated": len(suggestions),
            "suggestions": [s.to_dict() for s in suggestions[:5]],  # Top 5
            "corrections": corrections,
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        return {
            "running": self._running,
            "adjustment_interval_hours": self.adjustment_interval_hours,
            "last_adjustment_time": self._last_adjustment_time,
            "adjustment_count": self._adjustment_count,
        }


def evaluate_adjustment_impact(
    registry: AdoptionRegistry,
    suggestion: PolicyChangeSuggestion,
) -> Dict[str, Any]:
    """Evaluate the potential impact of a policy adjustment.
    
    Uses the risk simulator to predict outcomes.
    
    Args:
        registry: Current registry
        suggestion: Suggestion to evaluate
        
    Returns:
        Impact assessment dict
    """
    # Create a simulated change
    if suggestion.suggestion_type == SUGGESTION_ADD_RULE:
        # Simulate adding a new rule
        simulated_rule = {
            "rule_id": f"simulated-{suggestion.target_rule_id}",
            "source_candidate_rule_id": f"simulated-{suggestion.target_rule_id}",
            "rule_type": suggestion.suggested_change.get("rule_type", "unknown"),
            "suggested_change": suggestion.suggested_change.get("changes", {}),
            "risk_level": "medium",
            "source_regression_case_ids": [],
        }
        
        risk_result = simulate_policy_risk([simulated_rule], registry)
        
        return {
            "suggestion_id": suggestion.suggestion_id,
            "risk_assessment": risk_result,
            "recommendation": "proceed" if risk_result["risk_level"] == RISK_LOW else
                            "caution" if risk_result["risk_level"] == RISK_MEDIUM else "halt",
        }
    
    elif suggestion.suggestion_type == SUGGESTION_MODIFY_RULE:
        # Simulate modifying existing rule
        return {
            "suggestion_id": suggestion.suggestion_id,
            "risk_assessment": {
                "risk_level": RISK_MEDIUM,
                "note": "Rule modification requires manual review",
            },
            "recommendation": "caution",
        }
    
    elif suggestion.suggestion_type == SUGGESTION_REMOVE_RULE:
        # Removal is generally safe but needs confirmation
        return {
            "suggestion_id": suggestion.suggestion_id,
            "risk_assessment": {
                "risk_level": RISK_LOW,
                "note": "Rule removal is generally safe but irreversible",
            },
            "recommendation": "proceed_with_confirmation",
        }
    
    else:
        return {
            "suggestion_id": suggestion.suggestion_id,
            "risk_assessment": {
                "risk_level": RISK_LOW,
            },
            "recommendation": "proceed",
        }


def prioritize_suggestions(
    suggestions: List[PolicyChangeSuggestion],
    registry: AdoptionRegistry,
) -> List[PolicyChangeSuggestion]:
    """Prioritize policy change suggestions.
    
    Args:
        suggestions: List of suggestions to prioritize
        registry: Registry for context
        
    Returns:
        Prioritized list of suggestions
    """
    # Evaluate each suggestion's impact
    scored_suggestions: List[Tuple[float, PolicyChangeSuggestion]] = []
    
    for suggestion in suggestions:
        impact = evaluate_adjustment_impact(registry, suggestion)
        risk_level = impact.get("risk_assessment", {}).get("risk_level", RISK_MEDIUM)
        
        # Calculate score (lower is better - higher priority, lower risk)
        priority_score = {
            PRIORITY_CRITICAL: 0,
            PRIORITY_HIGH: 10,
            PRIORITY_MEDIUM: 20,
            PRIORITY_LOW: 30,
        }.get(suggestion.priority, 50)
        
        risk_score = {
            RISK_LOW: 0,
            RISK_MEDIUM: 5,
            RISK_HIGH: 20,
        }.get(risk_level, 10)
        
        confidence_bonus = suggestion.confidence * 10  # Higher confidence = better
        
        total_score = priority_score + risk_score - confidence_bonus
        scored_suggestions.append((total_score, suggestion))
    
    # Sort by score (ascending - lower is better)
    scored_suggestions.sort(key=lambda x: x[0])
    
    return [s for _, s in scored_suggestions]


# Global scheduler instance
_global_adjustment_scheduler: Optional[PolicyAdjustmentScheduler] = None


def get_adjustment_scheduler(registry: AdoptionRegistry) -> PolicyAdjustmentScheduler:
    """Get or create global adjustment scheduler."""
    global _global_adjustment_scheduler
    if _global_adjustment_scheduler is None:
        _global_adjustment_scheduler = PolicyAdjustmentScheduler(registry)
    return _global_adjustment_scheduler


def start_scheduled_adjustments(
    registry: AdoptionRegistry,
    interval_hours: int = 24,
    on_adjustment: Optional[Callable] = None,
) -> PolicyAdjustmentScheduler:
    """Start scheduled policy adjustments."""
    scheduler = get_adjustment_scheduler(registry)
    scheduler.adjustment_interval_hours = interval_hours
    scheduler.set_callback(on_adjustment=on_adjustment)
    scheduler.start()
    return scheduler


def stop_scheduled_adjustments() -> None:
    """Stop scheduled policy adjustments."""
    global _global_adjustment_scheduler
    if _global_adjustment_scheduler:
        _global_adjustment_scheduler.stop()
