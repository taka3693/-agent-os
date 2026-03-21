from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_queue_store import append_approval_queue_entry
from ops.approval_queue_view import render_pending_approvals


class ApprovalQueueViewTests(unittest.TestCase):
    def test_render_pending_approvals_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            text = render_pending_approvals(Path(td))
            self.assertEqual(text, "承認待ち: 0件")

    def test_render_pending_approvals_uses_newest_first_and_limit(self) -> None:
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

            text = render_pending_approvals(state_root, limit=1)
            self.assertIn("承認待ち: 1件", text)
            self.assertIn("1. session.archive | fp=session.archive:old-2.jsonl | source=session_hygiene", text)
            self.assertNotIn("old-1.jsonl", text)


if __name__ == "__main__":
    unittest.main()
