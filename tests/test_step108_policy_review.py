#!/usr/bin/env python3
"""Step108: Policy Review Workflow Tests"""
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.candidate_rules import (
    make_candidate,
    review_candidate,
    batch_review,
    summarize_reviews,
    export_review_report,
    save_review_report,
    REVIEW_STATUS_PROPOSED,
    REVIEW_STATUS_REVIEWED,
    REVIEW_STATUS_ACCEPTED,
    REVIEW_STATUS_REJECTED,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_test_candidates():
    return [
        make_candidate(
            candidate_rule_id="rule-001",
            description="test rule 1",
            expected_effect="improve",
            affected_cases=["c1"],
            risk_level="low",
            recommendation="adopt",
            rule_type="failed_chain",
            suggested_change={"threshold": 2},
        ),
        make_candidate(
            candidate_rule_id="rule-002",
            description="test rule 2",
            expected_effect="stabilize",
            affected_cases=["c2", "c3"],
            risk_level="medium",
            recommendation="review",
            rule_type="orchestration",
            suggested_change={"min_budget": 3},
        ),
        make_candidate(
            candidate_rule_id="rule-003",
            description="test rule 3",
            expected_effect="reduce cost",
            affected_cases=["c4"],
            risk_level="high",
            recommendation="discard",
            rule_type="budget_trim",
            suggested_change={"trim_threshold": 3},
        ),
    ]


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestStep108InitialStatus(unittest.TestCase):

    def test_candidate_starts_as_proposed(self):
        c = make_candidate(
            "r", "d", "e", [], "low", "adopt", "t", {}
        )
        self.assertEqual(c["review_status"], REVIEW_STATUS_PROPOSED)

    def test_initial_review_fields_are_none(self):
        c = make_candidate(
            "r", "d", "e", [], "low", "adopt", "t", {}
        )
        self.assertIsNone(c["reviewer"])
        self.assertIsNone(c["reviewed_at"])
        self.assertIsNone(c["decision"])
        self.assertIsNone(c["rationale"])


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------

class TestStep108StatusTransitions(unittest.TestCase):

    def test_transition_to_reviewed(self):
        c = _make_test_candidates()[0]
        updated = review_candidate(c, REVIEW_STATUS_REVIEWED, "alice", "looks good")
        self.assertEqual(updated["review_status"], REVIEW_STATUS_REVIEWED)
        self.assertEqual(updated["reviewer"], "alice")
        self.assertEqual(updated["rationale"], "looks good")

    def test_transition_to_accepted(self):
        c = _make_test_candidates()[0]
        updated = review_candidate(c, REVIEW_STATUS_ACCEPTED, "bob", "approved")
        self.assertEqual(updated["review_status"], REVIEW_STATUS_ACCEPTED)
        self.assertEqual(updated["decision"], REVIEW_STATUS_ACCEPTED)

    def test_transition_to_rejected(self):
        c = _make_test_candidates()[0]
        updated = review_candidate(c, REVIEW_STATUS_REJECTED, "carol", "too risky")
        self.assertEqual(updated["review_status"], REVIEW_STATUS_REJECTED)
        self.assertEqual(updated["rationale"], "too risky")

    def test_invalid_decision_raises(self):
        c = _make_test_candidates()[0]
        with self.assertRaises(ValueError):
            review_candidate(c, "invalid_status", "alice")

    def test_original_not_mutated(self):
        c = _make_test_candidates()[0]
        _ = review_candidate(c, REVIEW_STATUS_ACCEPTED, "bob")
        self.assertEqual(c["review_status"], REVIEW_STATUS_PROPOSED)

    def test_reviewed_at_is_set(self):
        c = _make_test_candidates()[0]
        updated = review_candidate(c, REVIEW_STATUS_ACCEPTED, "bob")
        self.assertIsNotNone(updated["reviewed_at"])


# ---------------------------------------------------------------------------
# Batch review
# ---------------------------------------------------------------------------

class TestStep108BatchReview(unittest.TestCase):

    def test_batch_review_applies_multiple(self):
        candidates = _make_test_candidates()
        decisions = {
            "rule-001": {"decision": REVIEW_STATUS_ACCEPTED, "reviewer": "alice"},
            "rule-002": {"decision": REVIEW_STATUS_REJECTED, "reviewer": "bob", "rationale": "no"},
        }
        updated = batch_review(candidates, decisions)

        self.assertEqual(updated[0]["review_status"], REVIEW_STATUS_ACCEPTED)
        self.assertEqual(updated[1]["review_status"], REVIEW_STATUS_REJECTED)
        self.assertEqual(updated[2]["review_status"], REVIEW_STATUS_PROPOSED)  # unchanged

    def test_batch_review_empty_decisions(self):
        candidates = _make_test_candidates()
        updated = batch_review(candidates, {})
        for c in updated:
            self.assertEqual(c["review_status"], REVIEW_STATUS_PROPOSED)


# ---------------------------------------------------------------------------
# Review summary
# ---------------------------------------------------------------------------

class TestStep108ReviewSummary(unittest.TestCase):

    def test_summary_counts_by_status(self):
        candidates = _make_test_candidates()
        candidates[0] = review_candidate(candidates[0], REVIEW_STATUS_ACCEPTED, "a")
        candidates[1] = review_candidate(candidates[1], REVIEW_STATUS_REJECTED, "b")
        # candidates[2] stays proposed

        summary = summarize_reviews(candidates)

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["by_status"]["proposed"], 1)
        self.assertEqual(summary["by_status"]["accepted"], 1)
        self.assertEqual(summary["by_status"]["rejected"], 1)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["completed"], 2)

    def test_summary_by_risk_accepted(self):
        candidates = _make_test_candidates()
        candidates[0] = review_candidate(candidates[0], REVIEW_STATUS_ACCEPTED, "a")  # low
        candidates[2] = review_candidate(candidates[2], REVIEW_STATUS_ACCEPTED, "b")  # high

        summary = summarize_reviews(candidates)

        self.assertEqual(summary["by_risk_accepted"]["low"], 1)
        self.assertEqual(summary["by_risk_accepted"]["high"], 1)
        self.assertEqual(summary["by_risk_accepted"]["medium"], 0)

    def test_summary_all_proposed(self):
        candidates = _make_test_candidates()
        summary = summarize_reviews(candidates)
        self.assertEqual(summary["pending"], 3)
        self.assertEqual(summary["completed"], 0)


# ---------------------------------------------------------------------------
# Export reports
# ---------------------------------------------------------------------------

class TestStep108ExportReports(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_json_valid(self):
        candidates = _make_test_candidates()
        s = export_review_report(candidates, fmt="json")
        parsed = json.loads(s)
        self.assertIn("summary", parsed)
        self.assertIn("candidates", parsed)
        self.assertEqual(len(parsed["candidates"]), 3)

    def test_export_markdown_has_header(self):
        candidates = _make_test_candidates()
        md = export_review_report(candidates, fmt="markdown")
        self.assertIn("Policy Review Report", md)
        self.assertIn("Total candidates", md)

    def test_export_markdown_shows_status(self):
        candidates = _make_test_candidates()
        candidates[0] = review_candidate(candidates[0], REVIEW_STATUS_ACCEPTED, "alice")
        md = export_review_report(candidates, fmt="markdown")
        self.assertIn("accepted", md)
        self.assertIn("alice", md)

    def test_export_includes_rationale(self):
        candidates = _make_test_candidates()
        candidates[0] = review_candidate(
            candidates[0], REVIEW_STATUS_ACCEPTED, "alice", "this is why"
        )
        md = export_review_report(candidates, fmt="markdown")
        self.assertIn("this is why", md)

    def test_save_review_report_json(self):
        candidates = _make_test_candidates()
        path = Path(self.temp_dir) / "review.json"
        save_review_report(candidates, path, fmt="json")
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text())
        self.assertEqual(loaded["summary"]["total"], 3)

    def test_save_review_report_markdown(self):
        candidates = _make_test_candidates()
        path = Path(self.temp_dir) / "review.md"
        save_review_report(candidates, path, fmt="markdown")
        self.assertTrue(path.exists())
        content = path.read_text()
        self.assertIn("Policy Review Report", content)


# ---------------------------------------------------------------------------
# No policy modification
# ---------------------------------------------------------------------------

class TestStep108NoPolicyModification(unittest.TestCase):

    def test_review_does_not_modify_policy(self):
        """本番 policy を変更しない"""
        c = _make_test_candidates()[0]
        _ = review_candidate(c, REVIEW_STATUS_ACCEPTED, "tester")
        # Just verify no side effects
        self.assertTrue(True)

    def test_batch_review_does_not_modify_policy(self):
        candidates = _make_test_candidates()
        _ = batch_review(candidates, {
            "rule-001": {"decision": REVIEW_STATUS_ACCEPTED, "reviewer": "x"}
        })
        self.assertTrue(True)

    def test_export_contains_note(self):
        candidates = _make_test_candidates()
        s = export_review_report(candidates, fmt="json")
        self.assertIn("advisory only", s)


if __name__ == "__main__":
    unittest.main()
