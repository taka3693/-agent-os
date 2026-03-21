#!/usr/bin/env python3
"""Step126 Phase 2: Governance Auto Audit Tests

Tests for automated scheduling, violation detection, and notifications.
"""
from __future__ import annotations

import sys
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.governance_audit import (
    GovernanceAuditLog,
    log_governance_decision,
    reset_audit_log,
    VALIDATION_PASS,
    VALIDATION_FAIL,
    VALIDATION_WARNING,
)

from eval.governance_auto_audit import (
    AuditScheduler,
    GovernanceViolation,
    detect_governance_violations,
    generate_audit_report,
    NotificationHandler,
    LoggingNotificationHandler,
    RealTimeGovernanceAuditor,
    run_scheduled_audit,
    get_scheduler,
    start_scheduled_audits,
    stop_scheduled_audits,
    ESCALATION_INFO,
    ESCALATION_WARNING,
    ESCALATION_CRITICAL,
)

from eval.candidate_rules import (
    AdoptionRegistry,
    make_candidate,
    review_candidate,
    make_provenance,
    DECISION_AUTO_PROMOTE,
    DECISION_REVIEW_REQUIRED,
    DECISION_HALT,
    DECISION_ROLLBACK_RECOMMENDED,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
)


class TestGovernanceViolation(unittest.TestCase):
    """Tests for GovernanceViolation class."""

    def test_violation_creation(self):
        """Should create a violation."""
        v = GovernanceViolation(
            rule_id="test-rule",
            decision=DECISION_HALT,
            violation_type="test_violation",
            severity=ESCALATION_CRITICAL,
            description="Test description",
        )
        
        self.assertEqual(v.rule_id, "test-rule")
        self.assertEqual(v.decision, DECISION_HALT)
        self.assertEqual(v.violation_type, "test_violation")
        self.assertEqual(v.severity, ESCALATION_CRITICAL)
        self.assertIn("detected_at", v.to_dict())

    def test_violation_to_dict(self):
        """Should convert to dictionary."""
        v = GovernanceViolation(
            rule_id="r1",
            decision=DECISION_AUTO_PROMOTE,
            violation_type="no_reasons",
            severity=ESCALATION_WARNING,
            description="No reasons provided",
            context={"health": 50},
        )
        
        d = v.to_dict()
        
        self.assertEqual(d["rule_id"], "r1")
        self.assertEqual(d["context"]["health"], 50)


class TestDetectGovernanceViolations(unittest.TestCase):
    """Tests for detect_governance_violations function."""

    def setUp(self):
        """Set up test fixtures."""
        self.log = GovernanceAuditLog()
    
    def test_no_violations(self):
        """Should return empty list for valid decisions."""
        log_governance_decision(
            rule_id="good-rule",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Good health", "No conflicts"],
            context={"health_score": 95},
            audit_log=self.log,
        )
        
        violations = detect_governance_violations(self.log)
        
        self.assertEqual(len(violations), 0)
    
    def test_no_reasons_violation(self):
        """Should detect missing reasons."""
        self.log.add_entry({
            "entry_type": "governance_decision",
            "rule_id": "no-reason-rule",
            "decision": DECISION_AUTO_PROMOTE,
            "confidence": CONFIDENCE_HIGH,
            "reasons": [],  # No reasons
            "signals": {},
            "context": {},
        })
        
        violations = detect_governance_violations(self.log)
        
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].violation_type, "no_reasons")
    
    def test_auto_promote_low_health_violation(self):
        """Should detect auto-promote with low health."""
        log_governance_decision(
            rule_id="low-health-rule",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Approved"],
            context={"health_score": 50},  # Low health
            audit_log=self.log,
        )
        
        violations = detect_governance_violations(self.log)
        
        self.assertTrue(any(v.violation_type == "auto_promote_low_health" for v in violations))
    
    def test_invalid_decision_violation(self):
        """Should detect invalid decision type."""
        self.log.add_entry({
            "entry_type": "governance_decision",
            "rule_id": "invalid-rule",
            "decision": "invalid_decision_type",
            "confidence": CONFIDENCE_HIGH,
            "reasons": ["Test"],
            "signals": {},
            "context": {},
        })
        
        violations = detect_governance_violations(self.log)
        
        self.assertTrue(any(v.violation_type == "invalid_decision" for v in violations))


class TestAuditScheduler(unittest.TestCase):
    """Tests for AuditScheduler class."""

    def setUp(self):
        """Set up test fixtures."""
        self.log = GovernanceAuditLog()
        self.scheduler = AuditScheduler(audit_log=self.log)
    
    def tearDown(self):
        """Clean up after tests."""
        self.scheduler.stop()
    
    def test_scheduler_initial_state(self):
        """Should have correct initial state."""
        status = self.scheduler.get_status()
        
        self.assertFalse(status["running"])
        self.assertEqual(status["audit_count"], 0)
    
    def test_set_interval(self):
        """Should set interval correctly."""
        self.scheduler.set_interval(hours=12, minutes=30)
        
        status = self.scheduler.get_status()
        self.assertEqual(status["interval_seconds"], 12 * 3600 + 30 * 60)
    
    def test_run_audit(self):
        """Should run audit and return result."""
        log_governance_decision(
            rule_id="test-rule",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Good"],
            audit_log=self.log,
        )
        
        result = self.scheduler.run_audit()
        
        self.assertIn("audit_id", result)
        self.assertIn("timestamp", result)
        self.assertIn("summary", result)
        self.assertIn("violations", result)
        self.assertIn("validation_result", result)
    
    def test_run_audit_increments_count(self):
        """Should increment audit count."""
        self.scheduler.run_audit()
        self.scheduler.run_audit()
        
        status = self.scheduler.get_status()
        self.assertEqual(status["audit_count"], 2)
    
    def test_start_stop(self):
        """Should start and stop scheduler."""
        self.scheduler.set_interval(hours=0, minutes=0)  # Run immediately for test
        
        callback_called = []
        
        def on_complete(result):
            callback_called.append(result)
        
        self.scheduler.set_callbacks(on_audit_complete=on_complete)
        self.scheduler.start()
        
        # Wait briefly for first audit
        time.sleep(0.5)
        
        self.scheduler.stop()
        
        self.assertTrue(len(callback_called) > 0)


class TestGenerateAuditReport(unittest.TestCase):
    """Tests for generate_audit_report function."""

    def test_generate_text_report(self):
        """Should generate text format report."""
        audit_result = {
            "audit_id": "test-audit-001",
            "timestamp": "2026-03-11T10:00:00Z",
            "summary": {
                "total_decisions": 5,
                "by_decision": {"auto_promote": 3, "halt": 2},
            },
            "violations": [],
            "validation_result": {"passed": 5, "warnings": 0, "failed": 0},
        }
        
        report = generate_audit_report(audit_result, format_type="text")
        
        self.assertIn("test-audit-001", report)
        self.assertIn("5", report)  # Total decisions
    
    def test_generate_markdown_report(self):
        """Should generate markdown format report."""
        audit_result = {
            "audit_id": "test-audit-002",
            "timestamp": "2026-03-11T10:00:00Z",
            "summary": {
                "total_decisions": 3,
                "by_decision": {"auto_promote": 3},
            },
            "violations": [
                {
                    "rule_id": "bad-rule",
                    "decision": "auto_promote",
                    "violation_type": "no_reasons",
                    "severity": ESCALATION_WARNING,
                    "description": "No reasons provided",
                }
            ],
            "validation_result": {"passed": 2, "warnings": 1, "failed": 0},
        }
        
        report = generate_audit_report(audit_result, format_type="markdown")
        
        self.assertIn("# Governance Audit Report", report)
        self.assertIn("test-audit-002", report)
        self.assertIn("Violations Detected", report)
    
    def test_report_no_violations(self):
        """Should handle no violations."""
        audit_result = {
            "audit_id": "clean-audit",
            "timestamp": "2026-03-11T10:00:00Z",
            "summary": {"total_decisions": 1, "by_decision": {}},
            "violations": [],
            "validation_result": {"passed": 1, "warnings": 0, "failed": 0},
        }
        
        report = generate_audit_report(audit_result, format_type="markdown")
        
        self.assertIn("No Violations Detected", report)


class TestNotificationHandler(unittest.TestCase):
    """Tests for NotificationHandler base class."""

    def test_base_handler(self):
        """Should track notifications sent."""
        handler = NotificationHandler("test")
        
        result = handler.send("Test message", level=ESCALATION_INFO)
        
        self.assertTrue(result)
        self.assertEqual(handler.get_stats()["notifications_sent"], 1)


class TestLoggingNotificationHandler(unittest.TestCase):
    """Tests for LoggingNotificationHandler class."""

    def setUp(self):
        """Set up test fixtures."""
        self.handler = LoggingNotificationHandler()
    
    def test_log_notifications(self):
        """Should log notifications to list."""
        self.handler.send("Message 1", level=ESCALATION_INFO)
        self.handler.send("Message 2", level=ESCALATION_WARNING)
        
        notifications = self.handler.get_notifications()
        
        self.assertEqual(len(notifications), 2)
        self.assertEqual(notifications[0]["message"], "Message 1")
    
    def test_clear_notifications(self):
        """Should clear logged notifications."""
        self.handler.send("Test", level=ESCALATION_INFO)
        self.handler.clear()
        
        self.assertEqual(len(self.handler.get_notifications()), 0)


class TestRealTimeGovernanceAuditor(unittest.TestCase):
    """Tests for RealTimeGovernanceAuditor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.log = GovernanceAuditLog()
        self.handler = LoggingNotificationHandler()
        self.auditor = RealTimeGovernanceAuditor(
            audit_log=self.log,
            notification_handler=self.handler,
        )
    
    def test_audit_valid_decision(self):
        """Should audit and validate a valid decision."""
        result = self.auditor.audit_decision(
            rule_id="good-rule",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Good health", "No conflicts"],
            context={"health_score": 95},
        )
        
        self.assertIn("entry", result)
        self.assertIn("validation", result)
        self.assertFalse(result["has_violations"])
    
    def test_audit_invalid_decision_triggers_notification(self):
        """Should send notification for invalid decision."""
        result = self.auditor.audit_decision(
            rule_id="bad-rule",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=[],  # No reasons - will fail validation
            context={},
        )
        
        self.assertTrue(result["has_violations"])
        
        notifications = self.handler.get_notifications()
        self.assertEqual(len(notifications), 1)
    
    def test_get_stats(self):
        """Should return auditor statistics."""
        self.auditor.audit_decision(
            rule_id="r1",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Good"],
        )
        self.auditor.audit_decision(
            rule_id="r2",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=[],  # Invalid
        )
        
        stats = self.auditor.get_stats()
        
        self.assertEqual(stats["decisions_audited"], 2)
        self.assertEqual(stats["violations_detected"], 1)


class TestRunScheduledAudit(unittest.TestCase):
    """Tests for run_scheduled_audit function."""

    def test_run_scheduled_audit(self):
        """Should run audit and return result."""
        log = GovernanceAuditLog()
        
        log_governance_decision(
            rule_id="test-rule",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Good"],
            audit_log=log,
        )
        
        result = run_scheduled_audit(audit_log=log)
        
        self.assertIn("audit_id", result)
        self.assertIn("summary", result)
    
    def test_run_with_notification_handler(self):
        """Should send notification when violations detected."""
        log = GovernanceAuditLog()
        handler = LoggingNotificationHandler()
        
        # Add decision that will trigger violation (no reasons)
        log.add_entry({
            "entry_type": "governance_decision",
            "rule_id": "bad-rule",
            "decision": DECISION_AUTO_PROMOTE,
            "confidence": CONFIDENCE_HIGH,
            "reasons": [],
            "signals": {},
            "context": {},
        })
        
        result = run_scheduled_audit(audit_log=log, notification_handler=handler)
        
        # Should have violations
        self.assertTrue(len(result["violations"]) > 0)
        
        # Should have sent notification
        self.assertTrue(len(handler.get_notifications()) > 0)


class TestGlobalScheduler(unittest.TestCase):
    """Tests for global scheduler functions."""

    def tearDown(self):
        """Stop global scheduler after each test."""
        stop_scheduled_audits()
    
    def test_get_scheduler(self):
        """Should return global scheduler instance."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()
        
        self.assertIs(scheduler1, scheduler2)
    
    def test_start_stop_scheduled_audits(self):
        """Should start and stop global scheduler."""
        scheduler = start_scheduled_audits(interval_hours=24)
        
        self.assertTrue(scheduler.get_status()["running"])
        
        stop_scheduled_audits()
        
        self.assertFalse(scheduler.get_status()["running"])


class TestViolationSeverityLevels(unittest.TestCase):
    """Tests for violation severity classification."""

    def setUp(self):
        """Set up test fixtures."""
        self.log = GovernanceAuditLog()
    
    def test_no_reasons_is_warning(self):
        """Missing reasons should be WARNING severity."""
        self.log.add_entry({
            "entry_type": "governance_decision",
            "rule_id": "r1",
            "decision": DECISION_AUTO_PROMOTE,
            "confidence": CONFIDENCE_HIGH,
            "reasons": [],
            "signals": {},
            "context": {},
        })
        
        violations = detect_governance_violations(self.log)
        
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, ESCALATION_WARNING)
    
    def test_invalid_decision_is_critical(self):
        """Invalid decision type should be CRITICAL severity."""
        self.log.add_entry({
            "entry_type": "governance_decision",
            "rule_id": "r1",
            "decision": "invalid_type",
            "confidence": CONFIDENCE_HIGH,
            "reasons": ["Test"],
            "signals": {},
            "context": {},
        })
        
        violations = detect_governance_violations(self.log)
        
        # Find the invalid_decision violation
        invalid_violations = [v for v in violations if v.violation_type == "invalid_decision"]
        self.assertEqual(len(invalid_violations), 1)
        self.assertEqual(invalid_violations[0].severity, ESCALATION_CRITICAL)


class TestIntegration(unittest.TestCase):
    """Integration tests for governance auto audit."""

    def setUp(self):
        """Set up test fixtures."""
        self.log = GovernanceAuditLog()
        self.handler = LoggingNotificationHandler()
        self.auditor = RealTimeGovernanceAuditor(
            audit_log=self.log,
            notification_handler=self.handler,
        )
    
    def test_full_audit_flow(self):
        """Test complete audit flow from decision to notification."""
        # Make several decisions
        self.auditor.audit_decision(
            rule_id="good-rule",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Excellent health"],
            context={"health_score": 95},
        )
        
        self.auditor.audit_decision(
            rule_id="bad-rule",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=[],  # Will trigger violation
            context={"health_score": 60},
        )
        
        # Run scheduled audit
        result = run_scheduled_audit(audit_log=self.log, notification_handler=self.handler)
        
        # Verify audit result
        self.assertEqual(result["summary"]["total_decisions"], 2)
        self.assertTrue(len(result["violations"]) > 0)
        
        # Verify notification was sent
        notifications = self.handler.get_notifications()
        self.assertTrue(len(notifications) >= 1)  # At least one from audit


if __name__ == "__main__":
    unittest.main()
