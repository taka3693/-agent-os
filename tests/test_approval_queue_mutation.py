from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_queue_mutation import remove_pending_approval_by_fingerprint
from ops.approval_queue_reader import load_approval_queue
from ops.approval_queue_store import append_approval_queue_entry


class ApprovalQueueMutationTests(unittest.TestCase):
    def test_remove_pending_approval_by_fingerprint_removes_one(self) -> None:
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

            out = remove_pending_approval_by_fingerprint(
                state_root,
                "session.archive:old-2.jsonl",
            )

            self.assertTrue(out["ok"])
            self.assertTrue(out["removed"])
            self.assertEqual(out["count"], 1)

            rows = load_approval_queue(state_root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["fingerprint"], "session.archive:old-1.jsonl")

    def test_remove_pending_approval_by_fingerprint_missing_queue(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = remove_pending_approval_by_fingerprint(
                Path(td),
                "session.archive:missing.jsonl",
            )
            self.assertFalse(out["ok"])
            self.assertFalse(out["removed"])
            self.assertEqual(out["count"], 0)

    def test_remove_pending_approval_by_fingerprint_not_found(self) -> None:
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

            out = remove_pending_approval_by_fingerprint(
                state_root,
                "session.archive:missing.jsonl",
            )

            self.assertTrue(out["ok"])
            self.assertFalse(out["removed"])
            self.assertEqual(out["count"], 1)

            rows = load_approval_queue(state_root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["fingerprint"], "session.archive:old-1.jsonl")


if __name__ == "__main__":
    unittest.main()
