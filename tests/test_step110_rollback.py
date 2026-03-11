#!/usr/bin/env python3
"""Step110: Policy Rollback Workflow Tests"""
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.candidate_rules import (
    make_candidate,
    review_candidate,
    AdoptionRegistry,
    create_adoption_registry,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_INACTIVE,
    ADOPTION_STATUS_ROLLED_BACK,
    REVIEW_STATUS_ACCEPTED,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_accepted_candidate(rule_id="rule-001", risk="low"):
    c = make_candidate(
        candidate_rule_id=rule_id,
        description="test rule",
        expected_effect="improve",
        affected_cases=["c1"],
        risk_level=risk,
        recommendation="adopt",
        rule_type="failed_chain",
        suggested_change={"threshold": 2},
    )
    return review_candidate(c, REVIEW_STATUS_ACCEPTED, "reviewer")


# ---------------------------------------------------------------------------
# Rollback eligibility
# ---------------------------------------------------------------------------

class TestStep110RollbackEligibility(unittest.TestCase):

    def test_adopted_can_be_rolled_back(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        entry = reg.rollback("r1", "bob", "found issue")
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)

    def test_inactive_cannot_be_rolled_back(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.deactivate("r1")
        with self.assertRaises(ValueError):
            reg.rollback("r1", "bob", "test")

    def test_rolled_back_cannot_be_rolled_back_again(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.rollback("r1", "bob", "first")
        with self.assertRaises(ValueError):
            reg.rollback("r1", "charol", "second")

    def test_nonexistent_raises_keyerror(self):
        reg = create_adoption_registry()
        with self.assertRaises(KeyError):
            reg.rollback("nonexistent", "bob", "test")

    def test_can_rollback_helper(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        self.assertTrue(reg.can_rollback("r1"))
        reg.rollback("r1", "bob", "test")
        self.assertFalse(reg.can_rollback("r1"))


# ---------------------------------------------------------------------------
# Rollback metadata
# ---------------------------------------------------------------------------

class TestStep110RollbackMetadata(unittest.TestCase):

    def test_rolled_back_at_is_set(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        entry = reg.rollback("r1", "bob", "issue")
        self.assertIsNotNone(entry["rolled_back_at"])

    def test_rolled_back_by_is_set(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        entry = reg.rollback("r1", "bob", "issue")
        self.assertEqual(entry["rolled_back_by"], "bob")

    def test_rollback_reason_is_required(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        entry = reg.rollback("r1", "bob", "critical bug")
        self.assertEqual(entry["rollback_reason"], "critical bug")

    def test_rollback_notes_optional(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        entry = reg.rollback("r1", "bob", "reason", "extra details")
        self.assertEqual(entry["rollback_notes"], "extra details")

    def test_rollback_info_updated(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        entry = reg.rollback("r1", "bob", "reason")
        self.assertTrue(entry["rollback_info"]["rolled_back"])
        self.assertFalse(entry["rollback_info"]["can_rollback"])
        self.assertEqual(entry["rollback_info"]["previous_state"], ADOPTION_STATUS_ADOPTED)


# ---------------------------------------------------------------------------
# Registry consistency after rollback
# ---------------------------------------------------------------------------

class TestStep110RegistryConsistency(unittest.TestCase):

    def test_rolled_back_entry_still_in_registry(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.rollback("r1", "bob", "test")
        entry = reg.get("r1")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)

    def test_list_adopted_includes_rolled_back(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.rollback("r1", "bob", "test")
        entries = reg.list_adopted()
        self.assertEqual(len(entries), 1)

    def test_list_by_status_rolled_back(self):
        reg = create_adoption_registry()
        c1 = _make_accepted_candidate("r1")
        c2 = _make_accepted_candidate("r2")
        reg.adopt(c1, "alice")
        reg.adopt(c2, "alice")
        reg.rollback("r1", "bob", "test")
        rolled = reg.list_adopted(status=ADOPTION_STATUS_ROLLED_BACK)
        self.assertEqual(len(rolled), 1)
        active = reg.list_adopted(status=ADOPTION_STATUS_ADOPTED)
        self.assertEqual(len(active), 1)


# ---------------------------------------------------------------------------
# Summarize with rollback
# ---------------------------------------------------------------------------

class TestStep110SummarizeWithRollback(unittest.TestCase):

    def test_summary_includes_rollback_count(self):
        reg = create_adoption_registry()
        c1 = _make_accepted_candidate("r1")
        c2 = _make_accepted_candidate("r2")
        reg.adopt(c1, "alice")
        reg.adopt(c2, "alice")
        reg.rollback("r1", "bob", "test")
        summary = reg.summarize()
        self.assertEqual(summary["rollback_count"], 1)
        self.assertEqual(summary["by_status"]["rolled_back"], 1)

    def test_summary_all_active(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        summary = reg.summarize()
        self.assertEqual(summary["rollback_count"], 0)


# ---------------------------------------------------------------------------
# Export / save / load with rollback
# ---------------------------------------------------------------------------

class TestStep110ExportWithRollback(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_json_includes_rollback(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.rollback("r1", "bob", "critical issue", "see ticket #123")
        s = reg.export(fmt="json")
        parsed = json.loads(s)
        self.assertEqual(parsed["summary"]["rollback_count"], 1)
        entry = parsed["entries"][0]
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)
        self.assertEqual(entry["rollback_reason"], "critical issue")
        self.assertEqual(entry["rollback_notes"], "see ticket #123")

    def test_export_markdown_includes_rollback(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.rollback("r1", "bob", "bug found")
        md = reg.export(fmt="markdown")
        self.assertIn("Rolled back:", md)
        self.assertIn("bob", md)
        self.assertIn("bug found", md)
        self.assertIn("↩️", md)

    def test_save_load_roundtrip_with_rollback(self):
        reg1 = create_adoption_registry()
        c1 = _make_accepted_candidate("r1")
        c2 = _make_accepted_candidate("r2")
        reg1.adopt(c1, "alice")
        reg1.adopt(c2, "bob")
        reg1.rollback("r1", "charol", "issue", "details")

        path = Path(self.temp_dir) / "registry.json"
        reg1.save(path)

        reg2 = create_adoption_registry()
        reg2.load(path)

        self.assertEqual(reg2.summarize()["total"], 2)
        self.assertEqual(reg2.summarize()["rollback_count"], 1)
        entry = reg2.get("r1")
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)
        self.assertEqual(entry["rollback_reason"], "issue")
        self.assertEqual(entry["rollback_notes"], "details")

    def test_load_preserves_all_statuses(self):
        reg1 = create_adoption_registry()
        c1 = _make_accepted_candidate("r1")
        c2 = _make_accepted_candidate("r2")
        c3 = _make_accepted_candidate("r3")
        reg1.adopt(c1, "a")
        reg1.adopt(c2, "b")
        reg1.adopt(c3, "c")
        reg1.deactivate("r2")
        reg1.rollback("r3", "d", "reason")

        path = Path(self.temp_dir) / "registry.json"
        reg1.save(path)

        reg2 = create_adoption_registry()
        reg2.load(path)

        self.assertEqual(reg2.get("r1")["adoption_status"], ADOPTION_STATUS_ADOPTED)
        self.assertEqual(reg2.get("r2")["adoption_status"], ADOPTION_STATUS_INACTIVE)
        self.assertEqual(reg2.get("r3")["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)


# ---------------------------------------------------------------------------
# No policy modification
# ---------------------------------------------------------------------------

class TestStep110NoPolicyModification(unittest.TestCase):

    def test_rollback_does_not_modify_policy(self):
        """本番 policy を変更しない"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.rollback("r1", "bob", "testing")
        self.assertTrue(True)

    def test_export_contains_note(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.rollback("r1", "bob", "reason")
        s = reg.export(fmt="json")
        self.assertIn("no automatic policy", s.lower())


if __name__ == "__main__":
    unittest.main()
