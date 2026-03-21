from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_decision_api import apply_approval_decision_payload
from ops.approval_queue_store import append_approval_queue_entry


class ApprovalDecisionApiTests(unittest.TestCase):
    def test_apply_approval_decision_payload_success(self) -> None:
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

            out = apply_approval_decision_payload(
                state_root,
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:old-1.jsonl",
                decision="approved",
                reason="operator approved",
            )

            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "applied")
            self.assertEqual(out["pending_count"], 0)
            self.assertEqual(out["pending_items"], [])
            self.assertEqual(out["decision_count"], 1)
            self.assertEqual(out["decision_items"][0]["decision"], "approved")

    def test_apply_approval_decision_payload_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = apply_approval_decision_payload(
                Path(td),
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:missing.jsonl",
                decision="approved",
            )

            self.assertFalse(out["ok"])
            self.assertEqual(out["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
