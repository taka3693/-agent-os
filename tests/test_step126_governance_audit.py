#!/usr/bin/env python3
"""Step126: Governance Auto Audit Tests - Phase 1

Tests for log_governance_decision and validate_governance_decision functions.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.governance_audit import (
    GovernanceAuditLog,
    get_audit_log,
    reset_audit_log,
    log_governance_decision,
    validate_governance_decision,
    validate_all_decisions,
    get_governance_decision_summary,
    export_audit_log_json,
    AUDIT_TYPE_GOVERNANCE_DECISION,
    AUDIT_TYPE_VALIDATION,
    VALIDATION_PASS,
    VALIDATION_FAIL,
    VALIDATION_WARNING,
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
    DECISION_REJECT,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
)


class TestGovernanceAuditLog(unittest.TestCase):
    """Tests for GovernanceAuditLog class."""

    def setUp(self):
        """Set up test fixtures."""
        self.log = GovernanceAuditLog()
    
    def test_add_entry(self):
        """Should add entry to log."""
        entry = {
            "entry_type": AUDIT_TYPE_GOVERNANCE_DECISION,
            "rule_id": "test-rule-001",
            "decision": DECISION_AUTO_PROMOTE,
        }
        
        index = self.log.add_entry(entry)
        
        self.assertEqual(index, 0)
        self.assertEqual(self.log.count(), 1)
    
    def test_add_entry_auto_timestamp(self):
        """Should add timestamp automatically."""
        entry = {
            "entry_type": AUDIT_TYPE_GOVERNANCE_DECISION,
            "rule_id": "test-rule-001",
            "decision": DECISION_AUTO_PROMOTE,
        }
        
        self.log.add_entry(entry)
        
        entries = self.log.get_all_entries()
        self.assertIn("timestamp", entries[0])
    
    def test_add_entry_auto_entry_id(self):
        """Should add entry_id automatically."""
        entry = {
            "entry_type": AUDIT_TYPE_GOVERNANCE_DECISION,
            "rule_id": "test-rule-001",
            "decision": DECISION_AUTO_PROMOTE,
        }
        
        self.log.add_entry(entry)
        
        entries = self.log.get_all_entries()
        self.assertIn("entry_id", entries[0])
        self.assertTrue(entries[0]["entry_id"].startswith("audit-"))
    
    def test_get_entries_by_type(self):
        """Should filter entries by type."""
        self.log.add_entry({"entry_type": AUDIT_TYPE_GOVERNANCE_DECISION, "rule_id": "r1"})
        self.log.add_entry({"entry_type": AUDIT_TYPE_VALIDATION, "rule_id": "r1"})
        
        decisions = self.log.get_entries(entry_type=AUDIT_TYPE_GOVERNANCE_DECISION)
        
        self.assertEqual(len(decisions), 1)
    
    def test_get_entries_by_rule_id(self):
        """Should filter entries by rule_id."""
        self.log.add_entry({"entry_type": AUDIT_TYPE_GOVERNANCE_DECISION, "rule_id": "r1"})
        self.log.add_entry({"entry_type": AUDIT_TYPE_GOVERNANCE_DECISION, "rule_id": "r2"})
        
        r1_entries = self.log.get_entries(rule_id="r1")
        
        self.assertEqual(len(r1_entries), 1)
        self.assertEqual(r1_entries[0]["rule_id"], "r1")
    
    def test_clear(self):
        """Should clear all entries."""
        self.log.add_entry({"entry_type": "test"})
        self.log.clear()
        
        self.assertEqual(self.log.count(), 0)


class TestLogGovernanceDecision(unittest.TestCase):
    """Tests for log_governance_decision function."""

    def setUp(self):
        """Set up test fixtures."""
        self.log = GovernanceAuditLog()
    
    def test_log_valid_decision(self):
        """Should log a valid governance decision."""
        entry = log_governance_decision(
            rule_id="test-rule-001",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Health score is good", "No conflicts detected"],
            audit_log=self.log,
        )
        
        self.assertIn("entry_id", entry)
        self.assertEqual(entry["rule_id"], "test-rule-001")
        self.assertEqual(entry["decision"], DECISION_AUTO_PROMOTE)
        self.assertEqual(entry["confidence"], CONFIDENCE_HIGH)
        self.assertEqual(len(entry["reasons"]), 2)
    
    def test_log_decision_with_signals(self):
        """Should log decision with signals."""
        signals = {
            "health_score": 95,
            "conflict_count": 0,
            "review_priority": 10,
        }
        
        entry = log_governance_decision(
            rule_id="test-rule-002",
            decision=DECISION_REVIEW_REQUIRED,
            confidence=CONFIDENCE_MEDIUM,
            reasons=["Needs review"],
            signals=signals,
            audit_log=self.log,
        )
        
        self.assertEqual(entry["signals"]["health_score"], 95)
    
    def test_log_decision_with_context(self):
        """Should log decision with context."""
        context = {
            "health_score": 85,
            "conflict_count": 1,
        }
        
        entry = log_governance_decision(
            rule_id="test-rule-003",
            decision=DECISION_HALT,
            confidence=CONFIDENCE_HIGH,
            reasons=["Health score too low"],
            context=context,
            audit_log=self.log,
        )
        
        self.assertEqual(entry["context"]["health_score"], 85)
    
    def test_log_decision_with_registry(self):
        """Should extract context from registry."""
        registry = AdoptionRegistry()
        
        c = make_candidate(
            candidate_rule_id="reg-rule-001",
            description="Test",
            expected_effect="Test",
            affected_cases=["case-1"],
            risk_level="low",
            recommendation="adopt",
            rule_type="tier_threshold",
            suggested_change={"tier": 1},
        )
        candidate = review_candidate(c, decision="accepted", reviewer="tester")
        provenance = make_provenance(
            rule_id="reg-rule-001",
            source_candidate_rule_id="reg-rule-001",
            source_regression_case_ids=["case-1"],
            created_by="test",
        )
        registry.adopt(candidate, adopted_by="tester", provenance=provenance)
        
        entry = log_governance_decision(
            rule_id="reg-rule-001",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Good rule"],
            registry=registry,
            audit_log=self.log,
        )
        
        self.assertEqual(entry["context"]["rule_type"], "tier_threshold")
    
    def test_log_invalid_decision_raises(self):
        """Should raise on invalid decision type."""
        with self.assertRaises(ValueError):
            log_governance_decision(
                rule_id="test-rule",
                decision="invalid_decision",
                confidence=CONFIDENCE_HIGH,
                reasons=["Test"],
                audit_log=self.log,
            )
    
    def test_log_invalid_confidence_raises(self):
        """Should raise on invalid confidence level."""
        with self.assertRaises(ValueError):
            log_governance_decision(
                rule_id="test-rule",
                decision=DECISION_AUTO_PROMOTE,
                confidence="invalid",
                reasons=["Test"],
                audit_log=self.log,
            )


class TestValidateGovernanceDecision(unittest.TestCase):
    """Tests for validate_governance_decision function."""

    def setUp(self):
        """Set up test fixtures."""
        self.log = GovernanceAuditLog()
    
    def test_validate_valid_decision(self):
        """Should pass validation for valid decision."""
        entry = log_governance_decision(
            rule_id="test-rule-001",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Good health", "No conflicts"],
            audit_log=self.log,
        )
        
        result = validate_governance_decision(entry, audit_log=self.log)
        
        self.assertEqual(result["validation_status"], VALIDATION_PASS)
        self.assertEqual(len(result["violations"]), 0)
    
    def test_validate_no_reasons_fails(self):
        """Should fail when no reasons provided and required."""
        entry = {
            "entry_id": "audit-001",
            "entry_type": AUDIT_TYPE_GOVERNANCE_DECISION,
            "rule_id": "test-rule",
            "decision": DECISION_AUTO_PROMOTE,
            "confidence": CONFIDENCE_HIGH,
            "reasons": [],  # No reasons
            "signals": {},
            "context": {},
        }
        
        result = validate_governance_decision(entry)
        
        self.assertEqual(result["validation_status"], VALIDATION_FAIL)
        self.assertTrue(any("reasons" in v.lower() for v in result["violations"]))
    
    def test_validate_auto_promote_disabled(self):
        """Should fail when auto_promote is disabled by policy."""
        entry = log_governance_decision(
            rule_id="test-rule",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Good"],
            audit_log=self.log,
        )
        
        policy = {"allow_auto_promote": False}
        result = validate_governance_decision(entry, policy_rules=policy)
        
        self.assertEqual(result["validation_status"], VALIDATION_FAIL)
        self.assertTrue(any("auto" in v.lower() for v in result["violations"]))
    
    def test_validate_halt_disabled(self):
        """Should fail when halt is disabled by policy."""
        entry = log_governance_decision(
            rule_id="test-rule",
            decision=DECISION_HALT,
            confidence=CONFIDENCE_HIGH,
            reasons=["Bad health"],
            audit_log=self.log,
        )
        
        policy = {"allow_halt": False}
        result = validate_governance_decision(entry, policy_rules=policy)
        
        self.assertEqual(result["validation_status"], VALIDATION_FAIL)
        self.assertTrue(any("halt" in v.lower() for v in result["violations"]))
    
    def test_validate_halt_high_health_warning(self):
        """Should warn when halt at high health score."""
        entry = {
            "entry_id": "audit-001",
            "entry_type": AUDIT_TYPE_GOVERNANCE_DECISION,
            "rule_id": "test-rule",
            "decision": DECISION_HALT,
            "confidence": CONFIDENCE_MEDIUM,
            "reasons": ["Manual halt"],
            "signals": {},
            "context": {"health_score": 90},  # High health
        }
        
        result = validate_governance_decision(entry)
        
        self.assertTrue(any("health" in w.lower() for w in result["warnings"]))
    
    def test_validate_invalid_decision_type(self):
        """Should fail on invalid decision type."""
        entry = {
            "entry_id": "audit-001",
            "entry_type": AUDIT_TYPE_GOVERNANCE_DECISION,
            "rule_id": "test-rule",
            "decision": "invalid_type",
            "confidence": CONFIDENCE_HIGH,
            "reasons": ["Test"],
            "signals": {},
            "context": {},
        }
        
        result = validate_governance_decision(entry)
        
        self.assertEqual(result["validation_status"], VALIDATION_FAIL)
        self.assertTrue(any("invalid" in v.lower() for v in result["violations"]))
    
    def test_validate_logs_result(self):
        """Should log validation result when audit_log provided."""
        entry = log_governance_decision(
            rule_id="test-rule",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Good"],
            audit_log=self.log,
        )
        
        initial_count = self.log.count()
        validate_governance_decision(entry, audit_log=self.log)
        
        self.assertEqual(self.log.count(), initial_count + 1)
    
    def test_validate_require_signals(self):
        """Should warn when signals required but not provided."""
        entry = {
            "entry_id": "audit-001",
            "entry_type": AUDIT_TYPE_GOVERNANCE_DECISION,
            "rule_id": "test-rule",
            "decision": DECISION_AUTO_PROMOTE,
            "confidence": CONFIDENCE_HIGH,
            "reasons": ["Good"],
            "signals": {},  # No signals
            "context": {},
        }
        
        policy = {"require_signals": True}
        result = validate_governance_decision(entry, policy_rules=policy)
        
        self.assertTrue(any("signals" in w.lower() for w in result["warnings"]))


class TestValidateAllDecisions(unittest.TestCase):
    """Tests for validate_all_decisions function."""

    def setUp(self):
        """Set up test fixtures."""
        self.log = GovernanceAuditLog()
    
    def test_validate_all_empty(self):
        """Should handle empty log."""
        result = validate_all_decisions(audit_log=self.log)
        
        self.assertEqual(result["total_decisions"], 0)
        self.assertEqual(result["passed"], 0)
    
    def test_validate_all_mixed(self):
        """Should validate all decisions."""
        # Valid decision
        log_governance_decision(
            rule_id="r1",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Good"],
            audit_log=self.log,
        )
        
        # Invalid decision (no reasons)
        self.log.add_entry({
            "entry_type": AUDIT_TYPE_GOVERNANCE_DECISION,
            "rule_id": "r2",
            "decision": DECISION_AUTO_PROMOTE,
            "confidence": CONFIDENCE_HIGH,
            "reasons": [],
            "signals": {},
            "context": {},
        })
        
        result = validate_all_decisions(audit_log=self.log)
        
        self.assertEqual(result["total_decisions"], 2)
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["failed"], 1)


class TestGetGovernanceDecisionSummary(unittest.TestCase):
    """Tests for get_governance_decision_summary function."""

    def setUp(self):
        """Set up test fixtures."""
        self.log = GovernanceAuditLog()
    
    def test_summary_empty(self):
        """Should handle empty log."""
        summary = get_governance_decision_summary(audit_log=self.log)
        
        self.assertEqual(summary["total_decisions"], 0)
    
    def test_summary_with_decisions(self):
        """Should summarize decisions."""
        log_governance_decision(
            rule_id="r1",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Good"],
            audit_log=self.log,
        )
        log_governance_decision(
            rule_id="r2",
            decision=DECISION_REVIEW_REQUIRED,
            confidence=CONFIDENCE_MEDIUM,
            reasons=["Check"],
            audit_log=self.log,
        )
        log_governance_decision(
            rule_id="r3",
            decision=DECISION_HALT,
            confidence=CONFIDENCE_LOW,
            reasons=["Bad"],
            audit_log=self.log,
        )
        
        summary = get_governance_decision_summary(audit_log=self.log)
        
        self.assertEqual(summary["total_decisions"], 3)
        self.assertEqual(summary["by_decision"][DECISION_AUTO_PROMOTE], 1)
        self.assertEqual(summary["by_decision"][DECISION_REVIEW_REQUIRED], 1)
        self.assertEqual(summary["by_decision"][DECISION_HALT], 1)
        self.assertEqual(summary["by_confidence"][CONFIDENCE_HIGH], 1)
        self.assertEqual(summary["by_confidence"][CONFIDENCE_MEDIUM], 1)
        self.assertEqual(summary["by_confidence"][CONFIDENCE_LOW], 1)


class TestGlobalAuditLog(unittest.TestCase):
    """Tests for global audit log functions."""

    def setUp(self):
        """Reset global audit log before each test."""
        reset_audit_log()
    
    def tearDown(self):
        """Reset global audit log after each test."""
        reset_audit_log()
    
    def test_get_audit_log(self):
        """Should return global audit log."""
        log = get_audit_log()
        
        self.assertIsInstance(log, GovernanceAuditLog)
    
    def test_log_to_global(self):
        """Should log to global audit log."""
        log_governance_decision(
            rule_id="global-test",
            decision=DECISION_AUTO_PROMOTE,
            confidence=CONFIDENCE_HIGH,
            reasons=["Test"],
        )
        
        log = get_audit_log()
        self.assertEqual(log.count(), 1)


class TestExportAuditLogJson(unittest.TestCase):
    """Tests for export_audit_log_json function."""

    def test_export_empty(self):
        """Should export empty log."""
        log = GovernanceAuditLog()
        json_str = export_audit_log_json(log)
        
        self.assertEqual(json_str, "[]")
    
    def test_export_with_entries(self):
        """Should export log with entries."""
        log = GovernanceAuditLog()
        log.add_entry({"test": "entry"})
        
        json_str = export_audit_log_json(log)
        
        self.assertIn("test", json_str)
        self.assertIn("entry", json_str)


if __name__ == "__main__":
    unittest.main()
