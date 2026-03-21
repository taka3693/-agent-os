from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.approval_decision_store import (
    approval_decision_log_path,
    append_approval_decision,
)


class ApprovalDecisionStoreTests(unittest.TestCase):
    def test_approval_decision_log_path(self) -> None:
        state_root = Path("/tmp/agent-os-state")
        self.assertEqual(
            approval_decision_log_path(state_root),
            state_root / "approval_decisions.jsonl",
        )

    def test_append_approval_decision_appends_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)

            path = append_approval_decision(
                state_root,
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:old-1.jsonl",
                decision="approved",
                action="session.archive",
                args={"target_basename": "old-1.jsonl"},
                reason="operator approved",
                source="manual_review",
            )

            self.assertEqual(path, state_root / "approval_decisions.jsonl")
            self.assertTrue(path.exists())

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

            payload = json.loads(lines[0])
            self.assertEqual(payload["timestamp"], "2026-03-12T12:30:00Z")
            self.assertEqual(payload["fingerprint"], "session.archive:old-1.jsonl")
            self.assertEqual(payload["decision"], "approved")
            self.assertEqual(payload["action"], "session.archive")
            self.assertEqual(payload["args"], {"target_basename": "old-1.jsonl"})
            self.assertEqual(payload["reason"], "operator approved")
            self.assertEqual(payload["source"], "manual_review")


if __name__ == "__main__":
    unittest.main()
