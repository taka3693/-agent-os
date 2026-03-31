from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_queue import append_approval_queue_entry
from runner.run_approval_ops import run_approval_ops


class RunApprovalOpsTests(unittest.TestCase):
    def test_run_approval_ops_status(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)

            out = run_approval_ops(
                state_root=state_root,
                mode="status",
            )

            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "status")
            self.assertEqual(out["pending_count"], 0)
            self.assertEqual(out["decision_count"], 0)
            self.assertEqual(out["reply_text"], out["text"])

    def test_run_approval_ops_apply(self) -> None:
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

            out = run_approval_ops(
                state_root=state_root,
                mode="apply",
                timestamp="2026-03-12T12:30:00Z",
                fingerprint="session.archive:old-1.jsonl",
                decision="approved",
                reason="operator approved",
            )

            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "decision")
            self.assertEqual(out["status"], "applied")
            self.assertEqual(out["reply_text"], out["text"])

    def test_run_approval_ops_invalid_mode(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = run_approval_ops(
                state_root=Path(td),
                mode="unknown",
            )

            self.assertFalse(out["ok"])
            self.assertEqual(out["status"], "invalid_mode")
            self.assertIn("invalid_mode", out["reply_text"])

    def test_run_approval_ops_apply_invalid_args(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = run_approval_ops(
                state_root=Path(td),
                mode="apply",
            )

            self.assertFalse(out["ok"])
            self.assertEqual(out["status"], "invalid_args")
            self.assertIn("invalid_args", out["reply_text"])
