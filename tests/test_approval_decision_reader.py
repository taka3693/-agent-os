from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_decision_reader import (
    list_approval_decisions,
    load_approval_decisions,
)
from ops.approval_decision_store import append_approval_decision


class ApprovalDecisionReaderTests(unittest.TestCase):
    def test_load_approval_decisions_empty_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(load_approval_decisions(Path(td)), [])

    def test_load_approval_decisions_reads_jsonl_entries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)

            append_approval_decision(
                state_root,
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:old-1.jsonl",
                decision="approved",
                action="session.archive",
                args={"target_basename": "old-1.jsonl"},
                reason="operator approved",
                source="manual_review",
            )
            append_approval_decision(
                state_root,
                timestamp="2026-03-12T12:35:00Z",
                fingerprint="session.archive:old-2.jsonl",
                decision="rejected",
                action="session.archive",
                args={"target_basename": "old-2.jsonl"},
                reason="operator rejected",
                source="manual_review",
            )

            rows = load_approval_decisions(state_root)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["decision"], "approved")
            self.assertEqual(rows[1]["decision"], "rejected")

    def test_list_approval_decisions_returns_newest_first_with_limit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)

            append_approval_decision(
                state_root,
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:old-1.jsonl",
                decision="approved",
                action="session.archive",
                args={"target_basename": "old-1.jsonl"},
                reason="operator approved",
                source="manual_review",
            )
            append_approval_decision(
                state_root,
                timestamp="2026-03-12T12:35:00Z",
                fingerprint="session.archive:old-2.jsonl",
                decision="rejected",
                action="session.archive",
                args={"target_basename": "old-2.jsonl"},
                reason="operator rejected",
                source="manual_review",
            )

            rows = list_approval_decisions(state_root, limit=1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["fingerprint"], "session.archive:old-2.jsonl")


if __name__ == "__main__":
    unittest.main()
