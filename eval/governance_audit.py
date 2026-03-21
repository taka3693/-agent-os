#!/usr/bin/env python3
"""Step126: Governance Auto Audit

Provides functions for logging and validating governance decisions
to ensure accountability and compliance in the policy evolution system.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Import governance decision constants from candidate_rules
from eval.candidate_rules import (
    DECISION_AUTO_PROMOTE,
    DECISION_REVIEW_REQUIRED,
    DECISION_HALT,
    DECISION_ROLLBACK_RECOMMENDED,
    DECISION_REJECT,
    DECISION_NO_ACTION,
    VALID_DECISIONS,
    
    # Confidence levels
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    
    # Registry for context
    AdoptionRegistry,
)


# Audit log entry types
AUDIT_TYPE_GOVERNANCE_DECISION = "governance_decision"
AUDIT_TYPE_VALIDATION = "validation"
AUDIT_TYPE_POLICY_CHECK = "policy_check"

# Validation result status
VALIDATION_PASS = "pass"
VALIDATION_FAIL = "fail"
VALIDATION_WARNING = "warning"

VALID_VALIDATION_STATUSES = (VALIDATION_PASS, VALIDATION_FAIL, VALIDATION_WARNING)


class GovernanceAuditLog:
    """In-memory audit log for governance decisions.
    
    Stores a chronological record of governance decisions and validations
    for accountability and compliance checking.
    """
    
    def __init__(self):
        self._entries: List[Dict[str, Any]] = []
        self._created_at = datetime.now(timezone.utc)
    
    def add_entry(self, entry: Dict[str, Any]) -> int:
        """Add an entry to the audit log.
        
        Args:
            entry: Audit log entry dict
            
        Returns:
            Index of the added entry
        """
        # Ensure timestamp
        if "timestamp" not in entry:
            entry["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Ensure entry_id
        if "entry_id" not in entry:
            entry["entry_id"] = f"audit-{len(self._entries):06d}"
        
        self._entries.append(entry)
        return len(self._entries) - 1
    
    def get_entries(self, 
                    entry_type: Optional[str] = None,
                    rule_id: Optional[str] = None,
                    since: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get entries from the audit log with optional filters.
        
        Args:
            entry_type: Filter by entry type
            rule_id: Filter by rule ID
            since: Filter entries after this timestamp
            
        Returns:
            List of matching entries
        """
        results = []
        
        for entry in self._entries:
            if entry_type and entry.get("entry_type") != entry_type:
                continue
            if rule_id and entry.get("rule_id") != rule_id:
                continue
            if since and entry.get("timestamp", "") < since:
                continue
            results.append(entry)
        
        return results
    
    def get_all_entries(self) -> List[Dict[str, Any]]:
        """Get all entries from the audit log.
        
        Returns:
            List of all entries
        """
        return list(self._entries)
    
    def clear(self) -> None:
        """Clear all entries from the audit log."""
        self._entries.clear()
    
    def count(self) -> int:
        """Get the number of entries in the audit log.
        
        Returns:
            Entry count
        """
        return len(self._entries)


# Global audit log instance
_global_audit_log: Optional[GovernanceAuditLog] = None


def get_audit_log() -> GovernanceAuditLog:
    """Get the global audit log instance.
    
    Returns:
        Global GovernanceAuditLog instance
    """
    global _global_audit_log
    if _global_audit_log is None:
        _global_audit_log = GovernanceAuditLog()
    return _global_audit_log


def reset_audit_log() -> None:
    """Reset the global audit log (mainly for testing)."""
    global _global_audit_log
    _global_audit_log = GovernanceAuditLog()


def log_governance_decision(
    rule_id: str,
    decision: str,
    confidence: str,
    reasons: List[str],
    signals: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    registry: Optional[AdoptionRegistry] = None,
    audit_log: Optional[GovernanceAuditLog] = None,
) -> Dict[str, Any]:
    """Log a governance decision to the audit log.
    
    Records a governance decision with full context for accountability
    and later validation.
    
    Args:
        rule_id: The rule ID the decision was made for
        decision: The decision type (auto_promote, review_required, halt, etc.)
        confidence: Confidence level (high, medium, low)
        reasons: List of human-readable reasons for the decision
        signals: Optional dict of signal values that influenced the decision
        context: Optional additional context (health_score, conflicts, etc.)
        registry: Optional registry for additional context extraction
        audit_log: Optional audit log to use (defaults to global)
        
    Returns:
        Audit log entry dict with:
        - entry_id: unique identifier
        - entry_type: "governance_decision"
        - timestamp: ISO 8601 timestamp
        - rule_id: the rule ID
        - decision: the decision type
        - confidence: confidence level
        - reasons: list of reasons
        - signals: signal values
        - context: additional context
        - valid: True (decisions are logged before validation)
    """
    # Validate decision type
    if decision not in VALID_DECISIONS:
        raise ValueError(f"Invalid decision type: {decision}. Must be one of {VALID_DECISIONS}")
    
    # Validate confidence
    valid_confidences = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW)
    if confidence not in valid_confidences:
        raise ValueError(f"Invalid confidence level: {confidence}. Must be one of {valid_confidences}")
    
    # Use provided audit log or global
    log = audit_log if audit_log is not None else get_audit_log()
    
    # Build context
    full_context = dict(context) if context else {}
    
    # Extract additional context from registry if provided
    if registry:
        entry = registry.get(rule_id)
        if entry:
            full_context["rule_type"] = entry.get("rule_type")
            full_context["adoption_status"] = entry.get("adoption_status")
            full_context["risk_level"] = entry.get("risk_level")
    
    # Build audit entry
    audit_entry = {
        "entry_type": AUDIT_TYPE_GOVERNANCE_DECISION,
        "rule_id": rule_id,
        "decision": decision,
        "confidence": confidence,
        "reasons": list(reasons),
        "signals": dict(signals) if signals else {},
        "context": full_context,
        "valid": True,  # Logged before validation, assume valid initially
    }
    
    # Add to log
    log.add_entry(audit_entry)
    
    return audit_entry


def validate_governance_decision(
    decision_entry: Dict[str, Any],
    policy_rules: Optional[Dict[str, Any]] = None,
    audit_log: Optional[GovernanceAuditLog] = None,
) -> Dict[str, Any]:
    """Validate a governance decision against policy rules.
    
    Checks that a governance decision complies with operational policies
    and governance constraints.
    
    Args:
        decision_entry: The decision entry to validate (from log_governance_decision)
        policy_rules: Optional policy rules to validate against
            - allow_auto_promote: bool (default True)
            - allow_halt: bool (default True)
            - allow_rollback: bool (default True)
            - require_reasons: bool (default True)
            - min_reasons_count: int (default 1)
            - require_confidence: bool (default False)
            - require_signals: bool (default False)
            - max_health_score_for_halt: int (default 50)
        audit_log: Optional audit log to log the validation result
        
    Returns:
        Validation result dict with:
        - entry_id: the decision entry ID
        - validation_status: "pass" | "fail" | "warning"
        - validation_checks: list of check results
        - violations: list of policy violations (if any)
        - warnings: list of warnings (if any)
        - validated_at: ISO 8601 timestamp
    """
    # Default policy rules
    default_policy = {
        "allow_auto_promote": True,
        "allow_halt": True,
        "allow_rollback": True,
        "require_reasons": True,
        "min_reasons_count": 1,
        "require_confidence": False,
        "require_signals": False,
        "max_health_score_for_halt": 50,
    }
    
    if policy_rules:
        default_policy.update(policy_rules)
    policy = default_policy
    
    # Extract decision info
    decision = decision_entry.get("decision")
    confidence = decision_entry.get("confidence")
    reasons = decision_entry.get("reasons", [])
    signals = decision_entry.get("signals", {})
    context = decision_entry.get("context", {})
    entry_id = decision_entry.get("entry_id", "unknown")
    
    validation_checks: List[Dict[str, Any]] = []
    violations: List[str] = []
    warnings: List[str] = []
    
    # Check 1: Valid decision type
    check = {
        "check": "valid_decision_type",
        "passed": decision in VALID_DECISIONS,
        "expected": list(VALID_DECISIONS),
        "actual": decision,
    }
    validation_checks.append(check)
    if not check["passed"]:
        violations.append(f"Invalid decision type: {decision}")
    
    # Check 2: Decision type allowed by policy
    if decision == DECISION_AUTO_PROMOTE and not policy["allow_auto_promote"]:
        check = {"check": "auto_promote_allowed", "passed": False}
        validation_checks.append(check)
        violations.append("Auto-promote decisions are not allowed by policy")
    
    if decision == DECISION_HALT and not policy["allow_halt"]:
        check = {"check": "halt_allowed", "passed": False}
        validation_checks.append(check)
        violations.append("Halt decisions are not allowed by policy")
    
    if decision == DECISION_ROLLBACK_RECOMMENDED and not policy["allow_rollback"]:
        check = {"check": "rollback_allowed", "passed": False}
        validation_checks.append(check)
        violations.append("Rollback recommendations are not allowed by policy")
    
    # Check 3: Reasons provided
    if policy["require_reasons"]:
        check = {
            "check": "reasons_provided",
            "passed": len(reasons) >= policy["min_reasons_count"],
            "expected": f">= {policy['min_reasons_count']}",
            "actual": len(reasons),
        }
        validation_checks.append(check)
        if not check["passed"]:
            violations.append(f"Insufficient reasons: {len(reasons)} < {policy['min_reasons_count']}")
    
    # Check 4: Confidence provided (if required)
    if policy["require_confidence"]:
        check = {
            "check": "confidence_provided",
            "passed": confidence is not None,
            "actual": confidence,
        }
        validation_checks.append(check)
        if not check["passed"]:
            warnings.append("Confidence level not provided")
    
    # Check 5: Signals provided (if required)
    if policy["require_signals"]:
        check = {
            "check": "signals_provided",
            "passed": bool(signals),
            "actual": list(signals.keys()) if signals else [],
        }
        validation_checks.append(check)
        if not check["passed"]:
            warnings.append("No signals provided with decision")
    
    # Check 6: Health score constraint for halt
    if decision == DECISION_HALT:
        health_score = context.get("health_score", 100)
        max_health = policy["max_health_score_for_halt"]
        check = {
            "check": "health_score_for_halt",
            "passed": health_score <= max_health,
            "expected": f"<= {max_health}",
            "actual": health_score,
        }
        validation_checks.append(check)
        if not check["passed"]:
            warnings.append(f"Halt decision at high health score: {health_score}")
    
    # Check 7: Decision consistency (halt should have low confidence or bad signals)
    if decision == DECISION_HALT and confidence == CONFIDENCE_HIGH:
        # High confidence halt might indicate over-certainty
        check = {
            "check": "halt_confidence_consistency",
            "passed": True,  # Not a violation, just a warning
            "note": "High confidence halt decision",
        }
        validation_checks.append(check)
        warnings.append("Halt decision with high confidence - verify signals support this")
    
    # Determine overall status
    if violations:
        validation_status = VALIDATION_FAIL
    elif warnings:
        validation_status = VALIDATION_WARNING
    else:
        validation_status = VALIDATION_PASS
    
    # Build result
    result = {
        "entry_id": entry_id,
        "validation_status": validation_status,
        "validation_checks": validation_checks,
        "violations": violations,
        "warnings": warnings,
        "validated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    
    # Log validation result if audit log provided
    if audit_log:
        log_entry = {
            "entry_type": AUDIT_TYPE_VALIDATION,
            "rule_id": decision_entry.get("rule_id"),
            "validation_result": result,
            "original_decision": decision,
        }
        audit_log.add_entry(log_entry)
    
    return result


def validate_all_decisions(
    audit_log: Optional[GovernanceAuditLog] = None,
    policy_rules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate all governance decisions in the audit log.
    
    Args:
        audit_log: Optional audit log (defaults to global)
        policy_rules: Optional policy rules to validate against
        
    Returns:
        Summary dict with:
        - total_decisions: int
        - passed: int
        - warnings: int
        - failed: int
        - validation_results: list of validation results
    """
    log = audit_log if audit_log is not None else get_audit_log()
    
    decisions = log.get_entries(entry_type=AUDIT_TYPE_GOVERNANCE_DECISION)
    
    results = []
    passed = 0
    warning_count = 0
    failed = 0
    
    for decision_entry in decisions:
        result = validate_governance_decision(decision_entry, policy_rules, audit_log=log)
        results.append(result)
        
        if result["validation_status"] == VALIDATION_PASS:
            passed += 1
        elif result["validation_status"] == VALIDATION_WARNING:
            warning_count += 1
        else:
            failed += 1
    
    return {
        "total_decisions": len(decisions),
        "passed": passed,
        "warnings": warning_count,
        "failed": failed,
        "validation_results": results,
    }


def get_governance_decision_summary(
    audit_log: Optional[GovernanceAuditLog] = None,
) -> Dict[str, Any]:
    """Get a summary of governance decisions from the audit log.
    
    Args:
        audit_log: Optional audit log (defaults to global)
        
    Returns:
        Summary dict with decision counts by type and confidence
    """
    log = audit_log if audit_log is not None else get_audit_log()
    
    decisions = log.get_entries(entry_type=AUDIT_TYPE_GOVERNANCE_DECISION)
    
    decision_counts = {d: 0 for d in VALID_DECISIONS}
    confidence_counts = {
        CONFIDENCE_HIGH: 0,
        CONFIDENCE_MEDIUM: 0,
        CONFIDENCE_LOW: 0,
    }
    
    for entry in decisions:
        decision = entry.get("decision")
        confidence = entry.get("confidence")
        
        if decision in decision_counts:
            decision_counts[decision] += 1
        if confidence in confidence_counts:
            confidence_counts[confidence] += 1
    
    return {
        "total_decisions": len(decisions),
        "by_decision": decision_counts,
        "by_confidence": confidence_counts,
    }


def export_audit_log_json(audit_log: Optional[GovernanceAuditLog] = None) -> str:
    """Export audit log as JSON string.
    
    Args:
        audit_log: Optional audit log (defaults to global)
        
    Returns:
        JSON string of all audit log entries
    """
    log = audit_log if audit_log is not None else get_audit_log()
    return json.dumps(log.get_all_entries(), ensure_ascii=False, indent=2)
