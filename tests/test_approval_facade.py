from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_facade import apply_approval, get_approval_status
from ops.approval_queue_store import append_approval_queue_entry


class ApprovalFacadeTests(unittest.TestCase):
    def test_get_approval_status_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = get_approval_status(Path(td))
            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "status")
            self.assertEqual(out["pending_count"], 0)
            self.assertEqual(out["decision_count"], 0)

    def test_apply_approval_success(self) -> None:
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

            out = apply_approval(
                state_root,
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:old-1.jsonl",
                decision="approved",
                reason="operator approved",
            )

            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "decision")
            self.assertEqual(out["status"], "applied")
            self.assertIn("承認決定: approved", out["text"])


if __name__ == "__main__":
    unittest.main()
