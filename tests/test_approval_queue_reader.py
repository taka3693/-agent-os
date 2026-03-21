from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_queue_reader import (
    find_pending_approval_by_fingerprint,
    list_pending_approvals,
    load_approval_queue,
)
from ops.approval_queue_store import append_approval_queue_entry


class ApprovalQueueReaderTests(unittest.TestCase):
    def test_load_approval_queue_empty_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(load_approval_queue(Path(td)), [])

    def test_load_approval_queue_reads_jsonl_entries(self) -> None:
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

            rows = load_approval_queue(state_root)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["fingerprint"], "session.archive:old-1.jsonl")
            self.assertEqual(rows[1]["fingerprint"], "session.archive:old-2.jsonl")


    def test_list_pending_approvals_returns_newest_first_with_limit(self) -> None:
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

            rows = list_pending_approvals(state_root, limit=1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["fingerprint"], "session.archive:old-2.jsonl")


    def test_find_pending_approval_by_fingerprint(self) -> None:
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

            row = find_pending_approval_by_fingerprint(
                state_root,
                "session.archive:old-1.jsonl",
            )
            self.assertIsNotNone(row)
            self.assertEqual(row["action"], "session.archive")

    def test_find_pending_approval_by_fingerprint_returns_none_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            row = find_pending_approval_by_fingerprint(
                Path(td),
                "session.archive:missing.jsonl",
            )
            self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
