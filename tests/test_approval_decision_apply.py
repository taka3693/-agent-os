from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_decision_apply import apply_approval_decision
from ops.approval_decision_reader import load_approval_decisions
from ops.approval_queue_reader import load_approval_queue
from ops.approval_queue_store import append_approval_queue_entry


class ApprovalDecisionApplyTests(unittest.TestCase):
    def test_apply_approval_decision_approved(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)

            append_approval_queue_entry(
                state_root,
                timestamp="2026-03-12T12:00:00Z",
                fingerprint="session.archive:old-1.jsonl",
                action="session.archive",
                args={"target_basename": "old-1.jsonl"},
                policy="approval_required",
                reason="archive old session",
                source="evaluation",
            )

            out = apply_approval_decision(
                state_root,
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:old-1.jsonl",
                decision="approved",
                reason="operator approved",
            )

            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "applied")
            self.assertEqual(out["decision"], "approved")
            self.assertTrue(out["removed"])
            self.assertEqual(load_approval_queue(state_root), [])

            rows = load_approval_decisions(state_root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["decision"], "approved")

    def test_apply_approval_decision_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)

            append_approval_queue_entry(
                state_root,
                timestamp="2026-03-12T12:00:00Z",
                fingerprint="session.archive:old-2.jsonl",
                action="session.archive",
                args={"target_basename": "old-2.jsonl"},
                policy="approval_required",
                reason="archive old session",
                source="session_hygiene",
            )

            out = apply_approval_decision(
                state_root,
                timestamp="2026-03-12T12:35:00Z",
                fingerprint="session.archive:old-2.jsonl",
                decision="rejected",
                reason="operator rejected",
            )

            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "applied")
            self.assertEqual(out["decision"], "rejected")
            self.assertEqual(load_approval_queue(state_root), [])

            rows = load_approval_decisions(state_root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["decision"], "rejected")

    def test_apply_approval_decision_missing_item(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = apply_approval_decision(
                Path(td),
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:missing.jsonl",
                decision="approved",
            )

            self.assertFalse(out["ok"])
            self.assertEqual(out["status"], "not_found")


    def test_apply_approval_decision_invalid_decision(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)

            append_approval_queue_entry(
                state_root,
                timestamp="2026-03-12T12:00:00Z",
                fingerprint="session.archive:old-3.jsonl",
                action="session.archive",
                args={"target_basename": "old-3.jsonl"},
                policy="approval_required",
                reason="archive old session",
                source="evaluation",
            )

            out = apply_approval_decision(
                state_root,
                timestamp="2026-03-12T12:40:00Z",
                fingerprint="session.archive:old-3.jsonl",
                decision="maybe",
            )

            self.assertFalse(out["ok"])
            self.assertEqual(out["status"], "invalid_decision")
            self.assertEqual(len(load_approval_queue(state_root)), 1)
            self.assertEqual(load_approval_decisions(state_root), [])


if __name__ == "__main__":
    unittest.main()
