#!/usr/bin/env python3
"""Step128: Policy Conflict Resolution System

Automatic detection and resolution of policy conflicts.
Reuses conflict detection from Step116 and adds resolution strategies.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from eval.candidate_rules import (
    AdoptionRegistry,
    detect_rule_conflicts,
    build_conflict_report,
    compute_policy_health,
    make_provenance,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_ROLLED_BACK,
    CONFLICT_OVERLAPPING_APPLICABILITY,
    CONFLICT_PREREQUISITE,
    CONFLICT_ROLLBACK_REINTRODUCTION,
    CONFLICT_INCONSISTENT_PROVENANCE,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
)


# Resolution strategies
RESOLUTION_PRIORITY_OVERRIDE = "priority_override"
RESOLUTION_MERGE_RULES = "merge_rules"
RESOLUTION_DISABLE_LOWER_PRIORITY = "disable_lower_priority"
RESOLUTION_ESCALATE_FOR_REVIEW = "escalate_for_review"
RESOLUTION_AUTO_SELECT_BEST = "auto_select_best"
RESOLUTION_NO_ACTION = "no_action"

VALID_RESOLUTION_STRATEGIES = (
    RESOLUTION_PRIORITY_OVERRIDE,
    RESOLUTION_MERGE_RULES,
    RESOLUTION_DISABLE_LOWER_PRIORITY,
    RESOLUTION_ESCALATE_FOR_REVIEW,
    RESOLUTION_AUTO_SELECT_BEST,
    RESOLUTION_NO_ACTION,
)

# Resolution outcomes
RESOLUTION_SUCCESS = "success"
RESOLUTION_FAILED = "failed"
RESOLUTION_SKIPPED = "skipped"
RESOLUTION_PENDING = "pending"


class ConflictResolutionPolicy:
    """Policy defining how to resolve different types of conflicts."""
    
    def __init__(
        self,
        default_strategy: str = RESOLUTION_ESCALATE_FOR_REVIEW,
        auto_resolve_low_severity: bool = True,
        auto_resolve_medium_severity: bool = False,
        auto_resolve_high_severity: bool = False,
        priority_rules: Optional[Dict[str, int]] = None,
    ):
        self.default_strategy = default_strategy
        self.auto_resolve_low_severity = auto_resolve_low_severity
        self.auto_resolve_medium_severity = auto_resolve_medium_severity
        self.auto_resolve_high_severity = auto_resolve_high_severity
        self.priority_rules = priority_rules or {}
    
    def get_strategy_for_conflict(self, conflict: Dict[str, Any]) -> str:
        """Determine the resolution strategy for a conflict.
        
        Args:
            conflict: Conflict dict from detect_rule_conflicts
            
        Returns:
            Resolution strategy to use
        """
        conflict_type = conflict.get("type")
        severity = conflict.get("severity")
        
        # High severity conflicts should always be escalated unless explicitly configured
        if severity == SEVERITY_HIGH and not self.auto_resolve_high_severity:
            return RESOLUTION_ESCALATE_FOR_REVIEW
        
        # Medium severity conflicts
        if severity == SEVERITY_MEDIUM and not self.auto_resolve_medium_severity:
            return RESOLUTION_ESCALATE_FOR_REVIEW
        
        # Type-specific strategies
        if conflict_type == CONFLICT_OVERLAPPING_APPLICABILITY:
            return RESOLUTION_PRIORITY_OVERRIDE
        
        if conflict_type == CONFLICT_PREREQUISITE:
            return RESOLUTION_ESCALATE_FOR_REVIEW
        
        if conflict_type == CONFLICT_ROLLBACK_REINTRODUCTION:
            return RESOLUTION_DISABLE_LOWER_PRIORITY
        
        if conflict_type == CONFLICT_INCONSISTENT_PROVENANCE:
            if severity == SEVERITY_LOW:
                return RESOLUTION_AUTO_SELECT_BEST
            return RESOLUTION_ESCALATE_FOR_REVIEW
        
        return self.default_strategy
    
    def should_auto_resolve(self, conflict: Dict[str, Any]) -> bool:
        """Determine if a conflict should be auto-resolved.
        
        Args:
            conflict: Conflict dict
            
        Returns:
            True if should auto-resolve
        """
        severity = conflict.get("severity")
        
        if severity == SEVERITY_LOW and self.auto_resolve_low_severity:
            return True
        if severity == SEVERITY_MEDIUM and self.auto_resolve_medium_severity:
            return True
        if severity == SEVERITY_HIGH and self.auto_resolve_high_severity:
            return True
        
        return False
    
    def get_rule_priority(self, rule_id: str) -> int:
        """Get priority for a rule.
        
        Args:
            rule_id: Rule ID
            
        Returns:
            Priority value (higher = more important)
        """
        return self.priority_rules.get(rule_id, 0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "default_strategy": self.default_strategy,
            "auto_resolve_low_severity": self.auto_resolve_low_severity,
            "auto_resolve_medium_severity": self.auto_resolve_medium_severity,
            "auto_resolve_high_severity": self.auto_resolve_high_severity,
            "priority_rules": self.priority_rules,
        }


class ConflictResolution:
    """Represents a conflict resolution action."""
    
    def __init__(
        self,
        conflict: Dict[str, Any],
        strategy: str,
        outcome: str,
        resolved_rule_ids: List[str],
        action_taken: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        self.conflict = conflict
        self.strategy = strategy
        self.outcome = outcome
        self.resolved_rule_ids = resolved_rule_ids
        self.action_taken = action_taken
        self.notes = notes
        self.resolution_id = f"resolution-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{id(self):08x}"
        self.resolved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resolution_id": self.resolution_id,
            "conflict": self.conflict,
            "strategy": self.strategy,
            "outcome": self.outcome,
            "resolved_rule_ids": self.resolved_rule_ids,
            "action_taken": self.action_taken,
            "notes": self.notes,
            "resolved_at": self.resolved_at,
        }


class ConflictResolutionLog:
    """Log of all conflict resolutions."""
    
    def __init__(self):
        self._resolutions: List[ConflictResolution] = []
        self._created_at = datetime.now(timezone.utc)
    
    def add_resolution(self, resolution: ConflictResolution) -> None:
        """Add a resolution to the log."""
        self._resolutions.append(resolution)
    
    def get_resolutions(
        self,
        outcome: Optional[str] = None,
        strategy: Optional[str] = None,
        rule_id: Optional[str] = None,
    ) -> List[ConflictResolution]:
        """Get resolutions with optional filters."""
        results = []
        
        for resolution in self._resolutions:
            if outcome and resolution.outcome != outcome:
                continue
            if strategy and resolution.strategy != strategy:
                continue
            if rule_id and rule_id not in resolution.resolved_rule_ids:
                continue
            results.append(resolution)
        
        return results
    
    def get_all_resolutions(self) -> List[ConflictResolution]:
        """Get all resolutions."""
        return list(self._resolutions)
    
    def count(self) -> int:
        """Get count of resolutions."""
        return len(self._resolutions)
    
    def clear(self) -> None:
        """Clear all resolutions."""
        self._resolutions.clear()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of resolutions."""
        outcomes = {}
        strategies = {}
        
        for resolution in self._resolutions:
            outcomes[resolution.outcome] = outcomes.get(resolution.outcome, 0) + 1
            strategies[resolution.strategy] = strategies.get(resolution.strategy, 0) + 1
        
        return {
            "total_resolutions": len(self._resolutions),
            "by_outcome": outcomes,
            "by_strategy": strategies,
        }


# Global resolution log
_global_resolution_log: Optional[ConflictResolutionLog] = None


def get_resolution_log() -> ConflictResolutionLog:
    """Get the global resolution log."""
    global _global_resolution_log
    if _global_resolution_log is None:
        _global_resolution_log = ConflictResolutionLog()
    return _global_resolution_log


def reset_resolution_log() -> None:
    """Reset the global resolution log."""
    global _global_resolution_log
    _global_resolution_log = ConflictResolutionLog()


def resolve_conflict(
    conflict: Dict[str, Any],
    registry: AdoptionRegistry,
    policy: Optional[ConflictResolutionPolicy] = None,
    resolution_log: Optional[ConflictResolutionLog] = None,
    dry_run: bool = False,
) -> ConflictResolution:
    """Resolve a single conflict.
    
    Args:
        conflict: Conflict dict from detect_rule_conflicts
        registry: AdoptionRegistry to modify
        policy: Resolution policy to use
        resolution_log: Optional log to record resolution
        dry_run: If True, don't actually modify registry
        
    Returns:
        ConflictResolution with outcome
    """
    if policy is None:
        policy = ConflictResolutionPolicy()
    
    log = resolution_log or get_resolution_log()
    
    strategy = policy.get_strategy_for_conflict(conflict)
    rule_ids = conflict.get("rule_ids", [])
    conflict_type = conflict.get("type")
    severity = conflict.get("severity")
    
    resolved_ids: List[str] = []
    action_taken: Optional[str] = None
    notes: Optional[str] = None
    outcome = RESOLUTION_SUCCESS
    
    # Check if auto-resolution is allowed
    if not policy.should_auto_resolve(conflict) and strategy != RESOLUTION_ESCALATE_FOR_REVIEW:
        outcome = RESOLUTION_SKIPPED
        notes = "Auto-resolution not allowed for this severity level"
    
    elif strategy == RESOLUTION_PRIORITY_OVERRIDE:
        # Higher priority rule wins
        if len(rule_ids) >= 2:
            priorities = [(rid, policy.get_rule_priority(rid)) for rid in rule_ids]
            priorities.sort(key=lambda x: x[1], reverse=True)
            winner_id = priorities[0][0]
            
            if not dry_run:
                # In real implementation, would disable/modify lower priority rules
                action_taken = f"Rule {winner_id} takes priority"
            
            resolved_ids = [winner_id]
            notes = f"Priority override: {winner_id} wins with priority {priorities[0][1]}"
    
    elif strategy == RESOLUTION_DISABLE_LOWER_PRIORITY:
        # Disable the lower priority rule
        if len(rule_ids) >= 2:
            priorities = [(rid, policy.get_rule_priority(rid)) for rid in rule_ids]
            priorities.sort(key=lambda x: x[1], reverse=True)
            loser_id = priorities[-1][0]
            
            if not dry_run:
                # In real implementation, would rollback the lower priority rule
                action_taken = f"Rule {loser_id} flagged for disable"
            
            resolved_ids = [loser_id]
            notes = f"Lower priority rule {loser_id} to be disabled"
    
    elif strategy == RESOLUTION_MERGE_RULES:
        # Merge conflicting rules
        if not dry_run:
            action_taken = f"Rules {rule_ids} flagged for merge"
        
        resolved_ids = rule_ids
        notes = "Rules require manual merge"
        outcome = RESOLUTION_PENDING
    
    elif strategy == RESOLUTION_AUTO_SELECT_BEST:
        # Automatically select the best rule based on criteria
        if len(rule_ids) >= 1:
            # Simple heuristic: prefer most recently adopted rule
            best_id = rule_ids[0]
            
            if not dry_run:
                action_taken = f"Rule {best_id} auto-selected"
            
            resolved_ids = [best_id]
            notes = f"Auto-selected {best_id} as best option"
    
    elif strategy == RESOLUTION_ESCALATE_FOR_REVIEW:
        # Escalate for manual review
        if not dry_run:
            action_taken = f"Conflict escalated for manual review"
        
        resolved_ids = rule_ids
        notes = "Requires manual review"
        outcome = RESOLUTION_PENDING
    
    else:
        # No action
        outcome = RESOLUTION_SKIPPED
        notes = f"Unknown strategy: {strategy}"
    
    resolution = ConflictResolution(
        conflict=conflict,
        strategy=strategy,
        outcome=outcome,
        resolved_rule_ids=resolved_ids,
        action_taken=action_taken,
        notes=notes,
    )
    
    if not dry_run:
        log.add_resolution(resolution)
    
    return resolution


def resolve_all_conflicts(
    registry: AdoptionRegistry,
    policy: Optional[ConflictResolutionPolicy] = None,
    resolution_log: Optional[ConflictResolutionLog] = None,
    max_resolutions: int = 10,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Resolve all conflicts in the registry.
    
    Args:
        registry: AdoptionRegistry to analyze and modify
        policy: Resolution policy to use
        resolution_log: Optional log to record resolutions
        max_resolutions: Maximum resolutions to apply
        dry_run: If True, don't actually modify registry
        
    Returns:
        Result dict with resolutions and summary
    """
    if policy is None:
        policy = ConflictResolutionPolicy()
    
    log = resolution_log or get_resolution_log()
    
    # Detect conflicts
    conflicts = detect_rule_conflicts(registry)
    
    # Sort by severity (high first)
    severity_order = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}
    conflicts.sort(key=lambda c: severity_order.get(c.get("severity"), 99))
    
    resolutions: List[ConflictResolution] = []
    applied_count = 0
    skipped_count = 0
    pending_count = 0
    
    for conflict in conflicts[:max_resolutions * 2]:
        if applied_count >= max_resolutions:
            break
        
        resolution = resolve_conflict(
            conflict=conflict,
            registry=registry,
            policy=policy,
            resolution_log=log,
            dry_run=dry_run,
        )
        
        resolutions.append(resolution)
        
        if resolution.outcome == RESOLUTION_SUCCESS:
            applied_count += 1
        elif resolution.outcome == RESOLUTION_PENDING:
            pending_count += 1
        else:
            skipped_count += 1
    
    return {
        "total_conflicts": len(conflicts),
        "resolutions_attempted": len(resolutions),
        "applied_count": applied_count,
        "skipped_count": skipped_count,
        "pending_count": pending_count,
        "resolutions": [r.to_dict() for r in resolutions],
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def get_conflict_resolution_summary(
    resolution_log: Optional[ConflictResolutionLog] = None,
) -> Dict[str, Any]:
    """Get a summary of conflict resolutions.
    
    Args:
        resolution_log: Optional resolution log
        
    Returns:
        Summary dict
    """
    log = resolution_log or get_resolution_log()
    return log.get_summary()


def generate_resolution_report(
    resolutions: List[ConflictResolution],
    format_type: str = "text",
) -> str:
    """Generate a human-readable resolution report.
    
    Args:
        resolutions: List of resolutions
        format_type: Output format ("text" or "markdown")
        
    Returns:
        Formatted report string
    """
    lines: List[str] = []
    
    if format_type == "markdown":
        lines.append("# Conflict Resolution Report")
        lines.append("")
        
        # Summary
        outcomes = {}
        for r in resolutions:
            outcomes[r.outcome] = outcomes.get(r.outcome, 0) + 1
        
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total Resolutions:** {len(resolutions)}")
        for outcome, count in outcomes.items():
            lines.append(f"- {outcome}: {count}")
        lines.append("")
        
        # Details
        lines.append("## Resolutions")
        lines.append("")
        
        for r in resolutions[:10]:  # Limit to 10
            conflict = r.conflict
            lines.append(f"### {conflict.get('type', 'unknown')}")
            lines.append("")
            lines.append(f"- **Strategy:** {r.strategy}")
            lines.append(f"- **Outcome:** {r.outcome}")
            lines.append(f"- **Rules:** {', '.join(r.resolved_rule_ids)}")
            if r.notes:
                lines.append(f"- **Notes:** {r.notes}")
            lines.append("")
    else:
        lines.append(f"Conflict Resolution Report")
        lines.append(f"Total: {len(resolutions)}")
        lines.append("")
        
        for r in resolutions[:5]:
            lines.append(f"- [{r.outcome}] {r.conflict.get('type')}: {r.notes}")
    
    return "\n".join(lines)


def estimate_resolution_impact(
    conflict: Dict[str, Any],
    registry: AdoptionRegistry,
) -> Dict[str, Any]:
    """Estimate the impact of resolving a conflict.
    
    Args:
        conflict: Conflict to analyze
        registry: Current registry
        
    Returns:
        Impact assessment dict
    """
    conflict_type = conflict.get("type")
    severity = conflict.get("severity")
    rule_ids = conflict.get("rule_ids", [])
    
    # Count affected rules
    affected_count = len(rule_ids)
    
    # Estimate health impact
    health_impact = "neutral"
    if severity == SEVERITY_HIGH:
        health_impact = "positive"  # Resolving high severity helps
    elif severity == SEVERITY_LOW:
        health_impact = "minimal"
    
    # Estimate risk
    resolution_risk = RISK_LOW if severity == SEVERITY_LOW else RISK_MEDIUM if severity == SEVERITY_MEDIUM else RISK_HIGH
    
    # Recommendation
    if conflict_type == CONFLICT_ROLLBACK_REINTRODUCTION:
        recommendation = "resolve_immediately"
    elif conflict_type == CONFLICT_OVERLAPPING_APPLICABILITY:
        recommendation = "resolve_safely"
    elif conflict_type == CONFLICT_INCONSISTENT_PROVENANCE:
        recommendation = "review_first"
    else:
        recommendation = "evaluate_manually"
    
    return {
        "conflict_type": conflict_type,
        "severity": severity,
        "affected_rules": affected_count,
        "health_impact": health_impact,
        "resolution_risk": resolution_risk,
        "recommendation": recommendation,
    }


# Import RISK constants for local use
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
