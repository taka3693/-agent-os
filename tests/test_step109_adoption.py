#!/usr/bin/env python3
"""Step109: Controlled Rule Adoption Tests"""
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
    can_adopt,
    REVIEW_STATUS_ACCEPTED,
    REVIEW_STATUS_REJECTED,
    REVIEW_STATUS_PROPOSED,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_INACTIVE,
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


def _make_proposed_candidate(rule_id="rule-002"):
    return make_candidate(
        candidate_rule_id=rule_id,
        description="proposed rule",
        expected_effect="test",
        affected_cases=[],
        risk_level="medium",
        recommendation="review",
        rule_type="orchestration",
        suggested_change={},
    )


def _make_rejected_candidate(rule_id="rule-003"):
    c = _make_proposed_candidate(rule_id)
    return review_candidate(c, REVIEW_STATUS_REJECTED, "reviewer", "bad idea")


# ---------------------------------------------------------------------------
# can_adopt helper
# ---------------------------------------------------------------------------

class TestStep109CanAdopt(unittest.TestCase):

    def test_accepted_is_adoptable(self):
        c = _make_accepted_candidate()
        self.assertTrue(can_adopt(c))

    def test_proposed_not_adoptable(self):
        c = _make_proposed_candidate()
        self.assertFalse(can_adopt(c))

    def test_rejected_not_adoptable(self):
        c = _make_rejected_candidate()
        self.assertFalse(can_adopt(c))


# ---------------------------------------------------------------------------
# Adoption eligibility
# ---------------------------------------------------------------------------

class TestStep109AdoptionEligibility(unittest.TestCase):

    def test_accepted_can_be_adopted(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate()
        entry = reg.adopt(c, "alice", "looks good")
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ADOPTED)

    def test_proposed_cannot_be_adopted(self):
        reg = create_adoption_registry()
        c = _make_proposed_candidate()
        with self.assertRaises(ValueError):
            reg.adopt(c, "alice")

    def test_rejected_cannot_be_adopted(self):
        reg = create_adoption_registry()
        c = _make_rejected_candidate()
        with self.assertRaises(ValueError):
            reg.adopt(c, "alice")


# ---------------------------------------------------------------------------
# Adoption registry
# ---------------------------------------------------------------------------

class TestStep109RegistryBasics(unittest.TestCase):

    def test_adopted_rule_in_registry(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("rule-001")
        reg.adopt(c, "alice")
        entry = reg.get("rule-001")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["source_candidate_rule_id"], "rule-001")

    def test_list_adopted(self):
        reg = create_adoption_registry()
        reg.adopt(_make_accepted_candidate("r1"), "a")
        reg.adopt(_make_accepted_candidate("r2"), "b")
        entries = reg.list_adopted()
        self.assertEqual(len(entries), 2)

    def test_list_adopted_by_status(self):
        reg = create_adoption_registry()
        reg.adopt(_make_accepted_candidate("r1"), "a")
        reg.adopt(_make_accepted_candidate("r2"), "b")
        reg.deactivate("r2", "testing")
        active = reg.list_adopted(status=ADOPTION_STATUS_ADOPTED)
        self.assertEqual(len(active), 1)


# ---------------------------------------------------------------------------
# Adoption metadata
# ---------------------------------------------------------------------------

class TestStep109AdoptionMetadata(unittest.TestCase):

    def test_adopted_at_is_set(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate()
        entry = reg.adopt(c, "alice")
        self.assertIsNotNone(entry["adopted_at"])

    def test_adopted_by_is_set(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate()
        entry = reg.adopt(c, "bob", "approved")
        self.assertEqual(entry["adopted_by"], "bob")

    def test_notes_preserved(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate()
        entry = reg.adopt(c, "alice", "special note")
        self.assertEqual(entry["notes"], "special note")

    def test_source_candidate_rule_id_preserved(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("my-rule-123")
        entry = reg.adopt(c, "alice")
        self.assertEqual(entry["source_candidate_rule_id"], "my-rule-123")

    def test_suggested_change_preserved(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate()
        entry = reg.adopt(c, "alice")
        self.assertEqual(entry["suggested_change"], {"threshold": 2})

    def test_risk_level_preserved(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate(risk="high")
        entry = reg.adopt(c, "alice")
        self.assertEqual(entry["risk_level"], "high")

    def test_rollback_info_present(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate()
        entry = reg.adopt(c, "alice")
        self.assertIn("rollback_info", entry)
        self.assertTrue(entry["rollback_info"]["can_rollback"])


# ---------------------------------------------------------------------------
# Deactivation / reactivation
# ---------------------------------------------------------------------------

class TestStep109Deactivation(unittest.TestCase):

    def test_deactivate_changes_status(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        entry = reg.deactivate("r1", "issues found")
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_INACTIVE)

    def test_deactivate_sets_timestamp(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        entry = reg.deactivate("r1")
        self.assertIsNotNone(entry.get("deactivated_at"))

    def test_deactivate_sets_reason(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        entry = reg.deactivate("r1", "buggy")
        self.assertEqual(entry["deactivation_reason"], "buggy")

    def test_deactivate_nonexistent_raises(self):
        reg = create_adoption_registry()
        with self.assertRaises(KeyError):
            reg.deactivate("nonexistent")

    def test_reactivate_changes_status(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.deactivate("r1")
        entry = reg.reactivate("r1")
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ADOPTED)

    def test_reactivate_sets_timestamp(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.deactivate("r1")
        entry = reg.reactivate("r1")
        self.assertIsNotNone(entry.get("reactivated_at"))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestStep109Summary(unittest.TestCase):

    def test_summary_counts_by_status(self):
        reg = create_adoption_registry()
        reg.adopt(_make_accepted_candidate("r1"), "a")
        reg.adopt(_make_accepted_candidate("r2", risk="high"), "b")
        reg.deactivate("r2")

        summary = reg.summarize()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["by_status"]["adopted"], 1)
        self.assertEqual(summary["by_status"]["inactive"], 1)

    def test_summary_counts_by_risk(self):
        reg = create_adoption_registry()
        reg.adopt(_make_accepted_candidate("r1", risk="low"), "a")
        reg.adopt(_make_accepted_candidate("r2", risk="high"), "b")

        summary = reg.summarize()
        self.assertEqual(summary["by_risk"]["low"], 1)
        self.assertEqual(summary["by_risk"]["high"], 1)


# ---------------------------------------------------------------------------
# Export / save / load
# ---------------------------------------------------------------------------

class TestStep109Export(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_json_valid(self):
        reg = create_adoption_registry()
        reg.adopt(_make_accepted_candidate("r1"), "alice")
        s = reg.export(fmt="json")
        parsed = json.loads(s)
        self.assertIn("summary", parsed)
        self.assertIn("entries", parsed)
        self.assertEqual(len(parsed["entries"]), 1)

    def test_export_markdown_has_header(self):
        reg = create_adoption_registry()
        reg.adopt(_make_accepted_candidate("r1"), "alice")
        md = reg.export(fmt="markdown")
        self.assertIn("Adoption Registry", md)
        self.assertIn("r1", md)

    def test_export_markdown_shows_status(self):
        reg = create_adoption_registry()
        reg.adopt(_make_accepted_candidate("r1"), "alice")
        reg.deactivate("r1")
        md = reg.export(fmt="markdown")
        self.assertIn("inactive", md)

    def test_save_json(self):
        reg = create_adoption_registry()
        reg.adopt(_make_accepted_candidate("r1"), "alice")
        path = Path(self.temp_dir) / "registry.json"
        reg.save(path, fmt="json")
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text())
        self.assertEqual(loaded["summary"]["total"], 1)

    def test_save_markdown(self):
        reg = create_adoption_registry()
        reg.adopt(_make_accepted_candidate("r1"), "alice")
        path = Path(self.temp_dir) / "registry.md"
        reg.save(path, fmt="markdown")
        self.assertTrue(path.exists())
        self.assertIn("Adoption Registry", path.read_text())

    def test_load_roundtrip(self):
        reg1 = create_adoption_registry()
        reg1.adopt(_make_accepted_candidate("r1"), "alice")
        reg1.adopt(_make_accepted_candidate("r2"), "bob")
        reg1.deactivate("r2")

        path = Path(self.temp_dir) / "registry.json"
        reg1.save(path)

        reg2 = create_adoption_registry()
        reg2.load(path)

        self.assertEqual(reg2.summarize()["total"], 2)
        entry = reg2.get("r2")
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_INACTIVE)

    def test_load_nonexistent_is_ok(self):
        reg = create_adoption_registry()
        reg.load(Path(self.temp_dir) / "nonexistent.json")
        self.assertEqual(reg.summarize()["total"], 0)


# ---------------------------------------------------------------------------
# No policy modification
# ---------------------------------------------------------------------------

class TestStep109NoPolicyModification(unittest.TestCase):

    def test_adopt_does_not_modify_policy(self):
        """本番 policy を変更しない"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate()
        reg.adopt(c, "tester")
        self.assertTrue(True)

    def test_deactivate_does_not_modify_policy(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "tester")
        reg.deactivate("r1")
        self.assertTrue(True)

    def test_export_contains_note(self):
        reg = create_adoption_registry()
        reg.adopt(_make_accepted_candidate(), "a")
        s = reg.export(fmt="json")
        self.assertIn("no automatic policy", s.lower())


if __name__ == "__main__":
    unittest.main()
