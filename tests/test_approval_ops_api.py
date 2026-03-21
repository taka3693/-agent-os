from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_ops_api import (
    apply_pending_approval_text,
    get_pending_approvals_text,
)
from ops.approval_queue_store import append_approval_queue_entry


class ApprovalOpsApiTests(unittest.TestCase):
    def test_get_pending_approvals_text_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = get_pending_approvals_text(Path(td))
            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "list")
            self.assertEqual(out["text"], "承認待ち: 0件")

    def test_apply_pending_approval_text_success(self) -> None:
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

            out = apply_pending_approval_text(
                state_root,
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:old-1.jsonl",
                decision="approved",
                reason="operator approved",
            )

            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "decision")
            self.assertIn("承認決定: approved", out["text"])


if __name__ == "__main__":
    unittest.main()
