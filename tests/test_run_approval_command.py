from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.approval_queue_store import append_approval_queue_entry
from runner.run_approval_command import run_approval_command


class RunApprovalCommandTests(unittest.TestCase):
    def test_run_approval_command_status(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = run_approval_command(
                state_root=Path(td),
                command="approval status",
            )

            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "status")
            self.assertIn("承認待ち", out["reply_text"])

    def test_run_approval_command_apply(self) -> None:
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

            out = run_approval_command(
                state_root=state_root,
                command="approval apply session.archive:old-1.jsonl approved",
                timestamp="2026-03-12T12:30:00Z",
                reason="operator approved",
            )

            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "decision")
            self.assertEqual(out["status"], "applied")

    def test_run_approval_command_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = run_approval_command(
                state_root=Path(td),
                command="approval unknown",
            )

            self.assertFalse(out["ok"])
            self.assertEqual(out["status"], "invalid_command")
            self.assertIn("invalid_command", out["reply_text"])

    def test_run_approval_command_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = run_approval_command(
                state_root=Path(td),
                command="",
            )

            self.assertFalse(out["ok"])
            self.assertEqual(out["status"], "empty_command")
