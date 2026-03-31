from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.approval_queue import (
    approval_queue_path,
    append_approval_queue_entry,
    load_existing_approval_fingerprints,
)


class ApprovalQueueStoreTests(unittest.TestCase):
    def test_approval_queue_path(self) -> None:
        state_root = Path("/tmp/agent-os-state")
        self.assertEqual(
            approval_queue_path(state_root),
            state_root / "approval_queue.jsonl",
        )

    def test_load_existing_approval_fingerprints_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(load_existing_approval_fingerprints(Path(td)), set())

    def test_append_approval_queue_entry_appends_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)

            path = append_approval_queue_entry(
                state_root,
                timestamp="2026-03-12T12:00:00Z",
                fingerprint="session.archive:old.jsonl",
                action="session.archive",
                args={"target_basename": "old.jsonl"},
                policy="approval_required",
                reason="archive old session",
                source="self_operation",
            )

            self.assertEqual(path, state_root / "approval_queue.jsonl")
            self.assertTrue(path.exists())

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

            payload = json.loads(lines[0])
            self.assertEqual(payload["timestamp"], "2026-03-12T12:00:00Z")
            self.assertEqual(payload["fingerprint"], "session.archive:old.jsonl")
            self.assertEqual(payload["action"], "session.archive")
            self.assertEqual(payload["args"], {"target_basename": "old.jsonl"})
            self.assertEqual(payload["policy"], "approval_required")
            self.assertEqual(payload["reason"], "archive old session")
            self.assertEqual(payload["source"], "self_operation")

    def test_append_approval_queue_entry_skips_duplicate_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)

            first = append_approval_queue_entry(
                state_root,
                timestamp="2026-03-12T12:00:00Z",
                fingerprint="session.archive:old.jsonl",
                action="session.archive",
                args={"target_basename": "old.jsonl"},
                policy="approval_required",
                reason="archive old session",
                source="self_operation",
            )
            second = append_approval_queue_entry(
                state_root,
                timestamp="2026-03-12T12:05:00Z",
                fingerprint="session.archive:old.jsonl",
                action="session.archive",
                args={"target_basename": "old.jsonl"},
                policy="approval_required",
                reason="archive old session again",
                source="self_operation",
            )

            self.assertIsNotNone(first)
            self.assertIsNone(second)

            lines = (state_root / "approval_queue.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(len(lines), 1)


if __name__ == "__main__":
    unittest.main()
