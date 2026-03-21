#!/usr/bin/env python3
"""Step126 Phase 2: Governance Auto Audit

Automated scheduling and error detection for governance decisions.
Uses standard library (threading, time) for scheduling instead of external packages.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional

from eval.governance_audit import (
    GovernanceAuditLog,
    get_audit_log,
    log_governance_decision,
    validate_governance_decision,
    validate_all_decisions,
    get_governance_decision_summary,
    AUDIT_TYPE_GOVERNANCE_DECISION,
    VALIDATION_PASS,
    VALIDATION_FAIL,
    VALIDATION_WARNING,
)

from eval.candidate_rules import (
    AdoptionRegistry,
    DECISION_AUTO_PROMOTE,
    DECISION_REVIEW_REQUIRED,
    DECISION_HALT,
    DECISION_ROLLBACK_RECOMMENDED,
    DECISION_REJECT,
    DECISION_NO_ACTION,
    VALID_DECISIONS,
)


# Escalation levels
ESCALATION_INFO = "info"
ESCALATION_WARNING = "warning"
ESCALATION_CRITICAL = "critical"

VALID_ESCALATION_LEVELS = (ESCALATION_INFO, ESCALATION_WARNING, ESCALATION_CRITICAL)


class GovernanceViolation:
    """Represents a governance violation detected during audit."""
    
    def __init__(
        self,
        rule_id: str,
        decision: str,
        violation_type: str,
        severity: str,
        description: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.rule_id = rule_id
        self.decision = decision
        self.violation_type = violation_type
        self.severity = severity
        self.description = description
        self.context = context or {}
        self.detected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rule_id": self.rule_id,
            "decision": self.decision,
            "violation_type": self.violation_type,
            "severity": self.severity,
            "description": self.description,
            "context": self.context,
            "detected_at": self.detected_at,
        }


class AuditScheduler:
    """Scheduler for automated governance audits.
    
    Uses threading for background execution of periodic audits.
    """
    
    def __init__(
        self,
        audit_log: Optional[GovernanceAuditLog] = None,
        registry: Optional[AdoptionRegistry] = None,
    ):
        self.audit_log = audit_log or get_audit_log()
        self.registry = registry
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._interval_seconds = 86400  # Default: 24 hours
        self._on_audit_complete: Optional[Callable] = None
        self._on_violation_detected: Optional[Callable] = None
        self._last_audit_time: Optional[str] = None
        self._audit_count = 0
    
    def set_interval(self, hours: int = 24, minutes: int = 0) -> None:
        """Set the interval between audits.
        
        Args:
            hours: Hours between audits
            minutes: Additional minutes between audits
        """
        self._interval_seconds = hours * 3600 + minutes * 60
    
    def set_callbacks(
        self,
        on_audit_complete: Optional[Callable] = None,
        on_violation_detected: Optional[Callable] = None,
    ) -> None:
        """Set callback functions for audit events.
        
        Args:
            on_audit_complete: Called when audit completes (receives audit result)
            on_violation_detected: Called when violation detected (receives violation)
        """
        self._on_audit_complete = on_audit_complete
        self._on_violation_detected = on_violation_detected
    
    def start(self) -> None:
        """Start the scheduled audits."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        """Stop the scheduled audits."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
    
    def _run_loop(self) -> None:
        """Main loop for scheduled audits."""
        while self._running:
            # Run audit
            result = self.run_audit()
            
            # Call completion callback
            if self._on_audit_complete:
                try:
                    self._on_audit_complete(result)
                except Exception:
                    pass  # Don't let callback errors stop the scheduler
            
            # Wait for next interval
            start_wait = time.time()
            while self._running and (time.time() - start_wait) < self._interval_seconds:
                time.sleep(1)  # Check every second for stop signal
    
    def run_audit(self) -> Dict[str, Any]:
        """Run a governance audit.
        
        Returns:
            Audit result with:
            - audit_id: unique identifier
            - timestamp: when audit ran
            - summary: decision summary
            - violations: list of detected violations
            - validation_result: result of validate_all_decisions
        """
        self._audit_count += 1
        audit_id = f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{self._audit_count:04d}"
        
        # Get decision summary
        summary = get_governance_decision_summary(self.audit_log)
        
        # Validate all decisions
        validation_result = validate_all_decisions(self.audit_log)
        
        # Detect violations
        violations = detect_governance_violations(self.audit_log, self.registry)
        
        # Call violation callbacks
        for violation in violations:
            if self._on_violation_detected:
                try:
                    self._on_violation_detected(violation)
                except Exception:
                    pass
        
        self._last_audit_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        return {
            "audit_id": audit_id,
            "timestamp": self._last_audit_time,
            "summary": summary,
            "violations": [v.to_dict() for v in violations],
            "validation_result": validation_result,
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status.
        
        Returns:
            Status dict with running state, last audit time, etc.
        """
        return {
            "running": self._running,
            "interval_seconds": self._interval_seconds,
            "last_audit_time": self._last_audit_time,
            "audit_count": self._audit_count,
        }


def detect_governance_violations(
    audit_log: GovernanceAuditLog,
    registry: Optional[AdoptionRegistry] = None,
    policy_rules: Optional[Dict[str, Any]] = None,
) -> List[GovernanceViolation]:
    """Detect governance violations from audit log.
    
    Args:
        audit_log: Audit log to analyze
        registry: Optional registry for additional context
        policy_rules: Optional policy rules to check against
        
    Returns:
        List of detected violations
    """
    violations: List[GovernanceViolation] = []
    
    decisions = audit_log.get_entries(entry_type=AUDIT_TYPE_GOVERNANCE_DECISION)
    
    for entry in decisions:
        rule_id = entry.get("rule_id", "unknown")
        decision = entry.get("decision")
        reasons = entry.get("reasons", [])
        context = entry.get("context", {})
        
        # Violation 1: HALT decision but rule was promoted
        if decision == DECISION_HALT:
            # Check if registry shows this rule as promoted
            if registry:
                reg_entry = registry.get(rule_id)
                if reg_entry and reg_entry.get("adoption_status") == "adopted":
                    violations.append(GovernanceViolation(
                        rule_id=rule_id,
                        decision=decision,
                        violation_type="halt_but_promoted",
                        severity=ESCALATION_CRITICAL,
                        description=f"Rule was HALT but shows as promoted in registry",
                        context=context,
                    ))
        
        # Violation 2: AUTO_PROMOTE with low health
        if decision == DECISION_AUTO_PROMOTE:
            health_score = context.get("health_score", 100)
            if health_score < 70:
                violations.append(GovernanceViolation(
                    rule_id=rule_id,
                    decision=decision,
                    violation_type="auto_promote_low_health",
                    severity=ESCALATION_WARNING,
                    description=f"Auto-promote decision with low health score: {health_score}",
                    context=context,
                ))
        
        # Violation 3: No reasons provided
        if not reasons:
            violations.append(GovernanceViolation(
                rule_id=rule_id,
                decision=decision,
                violation_type="no_reasons",
                severity=ESCALATION_WARNING,
                description="Decision made without documented reasons",
                context=context,
            ))
        
        # Violation 4: ROLLBACK_RECOMMENDED for recently promoted rule
        if decision == DECISION_ROLLBACK_RECOMMENDED:
            adopted_at = context.get("adopted_at")
            if adopted_at:
                # Check if adopted very recently (within 1 hour)
                try:
                    adopt_time = datetime.fromisoformat(adopted_at.replace("Z", "+00:00"))
                    time_diff = datetime.now(timezone.utc) - adopt_time
                    if time_diff < timedelta(hours=1):
                        violations.append(GovernanceViolation(
                            rule_id=rule_id,
                            decision=decision,
                            violation_type="quick_rollback",
                            severity=ESCALATION_WARNING,
                            description=f"Rollback recommended shortly after promotion: {time_diff}",
                            context=context,
                        ))
                except (ValueError, TypeError):
                    pass
        
        # Violation 5: Invalid decision type
        if decision not in VALID_DECISIONS:
            violations.append(GovernanceViolation(
                rule_id=rule_id,
                decision=decision or "none",
                violation_type="invalid_decision",
                severity=ESCALATION_CRITICAL,
                description=f"Invalid decision type: {decision}",
                context=context,
            ))
    
    return violations


def generate_audit_report(
    audit_result: Dict[str, Any],
    format_type: str = "text",
) -> str:
    """Generate a human-readable audit report.
    
    Args:
        audit_result: Result from run_audit()
        format_type: Output format ("text" or "markdown")
        
    Returns:
        Formatted report string
    """
    lines: List[str] = []
    
    audit_id = audit_result.get("audit_id", "unknown")
    timestamp = audit_result.get("timestamp", "unknown")
    summary = audit_result.get("summary", {})
    violations = audit_result.get("violations", [])
    validation = audit_result.get("validation_result", {})
    
    if format_type == "markdown":
        lines.append(f"# Governance Audit Report")
        lines.append("")
        lines.append(f"**Audit ID:** {audit_id}")
        lines.append(f"**Timestamp:** {timestamp}")
        lines.append("")
        
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total Decisions:** {summary.get('total_decisions', 0)}")
        lines.append("")
        
        by_decision = summary.get("by_decision", {})
        lines.append("### By Decision Type")
        lines.append("")
        for dec, count in by_decision.items():
            if count > 0:
                lines.append(f"- {dec}: {count}")
        lines.append("")
        
        if violations:
            lines.append("## Violations Detected")
            lines.append("")
            for v in violations:
                severity = v.get("severity", "unknown")
                icon = "🔴" if severity == ESCALATION_CRITICAL else "🟡" if severity == ESCALATION_WARNING else "ℹ️"
                lines.append(f"### {icon} {v.get('violation_type', 'unknown')}")
                lines.append("")
                lines.append(f"- **Rule:** {v.get('rule_id')}")
                lines.append(f"- **Decision:** {v.get('decision')}")
                lines.append(f"- **Severity:** {severity}")
                lines.append(f"- **Description:** {v.get('description')}")
                lines.append("")
        else:
            lines.append("## ✅ No Violations Detected")
            lines.append("")
        
        lines.append("## Validation Results")
        lines.append("")
        lines.append(f"- **Passed:** {validation.get('passed', 0)}")
        lines.append(f"- **Warnings:** {validation.get('warnings', 0)}")
        lines.append(f"- **Failed:** {validation.get('failed', 0)}")
    else:
        # Plain text format
        lines.append(f"Governance Audit Report: {audit_id}")
        lines.append(f"Timestamp: {timestamp}")
        lines.append("")
        lines.append(f"Total Decisions: {summary.get('total_decisions', 0)}")
        lines.append("")
        
        if violations:
            lines.append(f"Violations Detected: {len(violations)}")
            for v in violations:
                lines.append(f"  - [{v.get('severity')}] {v.get('violation_type')}: {v.get('description')}")
        else:
            lines.append("No Violations Detected")
        
        lines.append("")
        lines.append(f"Validation: {validation.get('passed', 0)} passed, {validation.get('failed', 0)} failed")
    
    return "\n".join(lines)


class NotificationHandler:
    """Base class for notification handlers."""
    
    def __init__(self, name: str):
        self.name = name
        self._notifications_sent = 0
    
    def send(self, message: str, level: str = ESCALATION_INFO, **kwargs) -> bool:
        """Send a notification.
        
        Args:
            message: Message to send
            level: Escalation level
            **kwargs: Additional context
            
        Returns:
            True if sent successfully
        """
        self._notifications_sent += 1
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get notification statistics."""
        return {
            "name": self.name,
            "notifications_sent": self._notifications_sent,
        }


class LoggingNotificationHandler(NotificationHandler):
    """Notification handler that logs to a list (for testing and debugging)."""
    
    def __init__(self, name: str = "logging"):
        super().__init__(name)
        self.notifications: List[Dict[str, Any]] = []
    
    def send(self, message: str, level: str = ESCALATION_INFO, **kwargs) -> bool:
        """Log notification to internal list."""
        self.notifications.append({
            "message": message,
            "level": level,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "context": kwargs,
        })
        return super().send(message, level, **kwargs)
    
    def get_notifications(self) -> List[Dict[str, Any]]:
        """Get all logged notifications."""
        return list(self.notifications)
    
    def clear(self) -> None:
        """Clear all notifications."""
        self.notifications.clear()


class RealTimeGovernanceAuditor:
    """Real-time auditor that validates decisions as they happen."""
    
    def __init__(
        self,
        audit_log: Optional[GovernanceAuditLog] = None,
        notification_handler: Optional[NotificationHandler] = None,
    ):
        self.audit_log = audit_log or get_audit_log()
        self.notification_handler = notification_handler
        self._violations_detected = 0
        self._decisions_audited = 0
    
    def audit_decision(
        self,
        rule_id: str,
        decision: str,
        confidence: str,
        reasons: List[str],
        signals: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Audit a governance decision in real-time.
        
        Args:
            rule_id: Rule ID
            decision: Decision type
            confidence: Confidence level
            reasons: List of reasons
            signals: Optional signals
            context: Optional context
            
        Returns:
            Audit result with validation status
        """
        # Log the decision
        entry = log_governance_decision(
            rule_id=rule_id,
            decision=decision,
            confidence=confidence,
            reasons=reasons,
            signals=signals,
            context=context,
            audit_log=self.audit_log,
        )
        
        # Validate the decision
        validation = validate_governance_decision(entry, audit_log=self.audit_log)
        
        self._decisions_audited += 1
        
        # Check for violations
        if validation["validation_status"] != VALIDATION_PASS:
            self._violations_detected += 1
            
            # Send notification if handler configured
            if self.notification_handler:
                level = ESCALATION_CRITICAL if validation["validation_status"] == VALIDATION_FAIL else ESCALATION_WARNING
                self.notification_handler.send(
                    message=f"Governance violation detected for rule {rule_id}: {validation.get('violations', [])}",
                    level=level,
                    rule_id=rule_id,
                    decision=decision,
                    validation=validation,
                )
        
        return {
            "entry": entry,
            "validation": validation,
            "has_violations": validation["validation_status"] != VALIDATION_PASS,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get auditor statistics."""
        return {
            "decisions_audited": self._decisions_audited,
            "violations_detected": self._violations_detected,
            "violation_rate": self._violations_detected / max(1, self._decisions_audited),
        }


def run_scheduled_audit(
    audit_log: Optional[GovernanceAuditLog] = None,
    registry: Optional[AdoptionRegistry] = None,
    notification_handler: Optional[NotificationHandler] = None,
) -> Dict[str, Any]:
    """Run a scheduled audit and optionally send notifications.
    
    Args:
        audit_log: Audit log to audit
        registry: Optional registry for context
        notification_handler: Optional handler for notifications
        
    Returns:
        Audit result
    """
    log = audit_log or get_audit_log()
    
    scheduler = AuditScheduler(audit_log=log, registry=registry)
    result = scheduler.run_audit()
    
    # Send notification if violations detected and handler configured
    if result["violations"] and notification_handler:
        report = generate_audit_report(result, format_type="markdown")
        notification_handler.send(
            message=report,
            level=ESCALATION_WARNING if result["validation_result"].get("failed", 0) > 0 else ESCALATION_INFO,
            audit_id=result["audit_id"],
            violation_count=len(result["violations"]),
        )
    
    return result


# Global scheduler instance
_global_scheduler: Optional[AuditScheduler] = None


def get_scheduler(
    registry: Optional[AdoptionRegistry] = None,
) -> AuditScheduler:
    """Get or create global scheduler instance.
    
    Args:
        registry: Optional registry for context
        
    Returns:
        Global AuditScheduler instance
    """
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = AuditScheduler(registry=registry)
    return _global_scheduler


def start_scheduled_audits(
    interval_hours: int = 24,
    on_audit_complete: Optional[Callable] = None,
    on_violation_detected: Optional[Callable] = None,
) -> AuditScheduler:
    """Start the global scheduled audits.
    
    Args:
        interval_hours: Hours between audits
        on_audit_complete: Callback for audit completion
        on_violation_detected: Callback for violation detection
        
    Returns:
        The scheduler instance
    """
    scheduler = get_scheduler()
    scheduler.set_interval(hours=interval_hours)
    scheduler.set_callbacks(
        on_audit_complete=on_audit_complete,
        on_violation_detected=on_violation_detected,
    )
    scheduler.start()
    return scheduler


def stop_scheduled_audits() -> None:
    """Stop the global scheduled audits."""
    global _global_scheduler
    if _global_scheduler:
        _global_scheduler.stop()
