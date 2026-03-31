from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_queue import get_pending_approvals_payload
from ops.approval_queue import append_approval_queue_entry


class ApprovalQueueApiTests(unittest.TestCase):
    def test_get_pending_approvals_payload_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = get_pending_approvals_payload(Path(td))
            self.assertTrue(out["ok"])
            self.assertEqual(out["count"], 0)
            self.assertEqual(out["items"], [])
            self.assertEqual(out["text"], "承認待ち: 0件")

    def test_get_pending_approvals_payload_with_limit(self) -> None:
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
            append_approval_queue_entry(
                state_root,
                timestamp="2026-03-12T12:05:00Z",
                fingerprint="session.archive:old-2.jsonl",
                action="session.archive",
                args={"target_basename": "old-2.jsonl"},
                policy="approval_required",
                reason="archive old session",
                source="session_hygiene",
            )

            out = get_pending_approvals_payload(state_root, limit=1)
            self.assertTrue(out["ok"])
            self.assertEqual(out["count"], 1)
            self.assertEqual(len(out["items"]), 1)
            self.assertEqual(out["items"][0]["fingerprint"], "session.archive:old-2.jsonl")
            self.assertIn("承認待ち: 1件", out["text"])


if __name__ == "__main__":
    unittest.main()
