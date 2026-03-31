from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_decision import append_approval_decision
from ops.approval_queue import append_approval_queue_entry
from ops.approval_status import render_approval_status


class ApprovalStatusViewTests(unittest.TestCase):
    def test_render_approval_status_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = render_approval_status(Path(td))
            self.assertTrue(out["ok"])
            self.assertEqual(out["pending_count"], 0)
            self.assertEqual(out["decision_count"], 0)
            self.assertIn("承認待ち: 0件", out["text"])
            self.assertIn("承認決定履歴: 0件", out["text"])

    def test_render_approval_status_with_limits(self) -> None:
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
            append_approval_decision(
                state_root,
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:done-1.jsonl",
                decision="approved",
                action="session.archive",
                args={"target_basename": "done-1.jsonl"},
                reason="operator approved",
                source="manual_review",
            )

            out = render_approval_status(
                state_root,
                pending_limit=1,
                decision_limit=1,
            )

            self.assertTrue(out["ok"])
            self.assertEqual(out["pending_count"], 1)
            self.assertEqual(out["decision_count"], 1)
            self.assertIn("承認待ち: 1件", out["pending_text"])
            self.assertIn("承認決定履歴: 1件", out["decision_text"])


if __name__ == "__main__":
    unittest.main()
