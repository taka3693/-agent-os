from __future__ import annotations

import unittest

from runner.parse_approval_command import parse_approval_command


class ParseApprovalCommandTests(unittest.TestCase):
    def test_parse_approval_command_status(self) -> None:
        out = parse_approval_command("approval status")
        self.assertTrue(out["ok"])
        self.assertEqual(out["mode"], "status")

    def test_parse_approval_command_apply(self) -> None:
        out = parse_approval_command(
            "approval apply session.archive:old-1.jsonl approved"
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["mode"], "apply")
        self.assertEqual(out["fingerprint"], "session.archive:old-1.jsonl")
        self.assertEqual(out["decision"], "approved")

    def test_parse_approval_command_invalid(self) -> None:
        out = parse_approval_command("approval unknown")
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "invalid_command")

    def test_parse_approval_command_empty(self) -> None:
        out = parse_approval_command("")
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "empty_command")


if __name__ == "__main__":
    unittest.main()
