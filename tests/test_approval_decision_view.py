from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_decision_view import apply_approval_decision_view
from ops.approval_queue_store import append_approval_queue_entry


class ApprovalDecisionViewTests(unittest.TestCase):
    def test_apply_approval_decision_view_success(self) -> None:
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

            out = apply_approval_decision_view(
                state_root,
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:old-1.jsonl",
                decision="approved",
                reason="operator approved",
            )

            self.assertTrue(out["ok"])
            self.assertIn("承認決定: approved", out["text"])
            self.assertIn("pending_count: 0", out["text"])
            self.assertIn("decision_count: 1", out["text"])

    def test_apply_approval_decision_view_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = apply_approval_decision_view(
                Path(td),
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:missing.jsonl",
                decision="approved",
            )

            self.assertFalse(out["ok"])
            self.assertIn("承認決定失敗", out["text"])
            self.assertIn("status=not_found", out["text"])


if __name__ == "__main__":
    unittest.main()
