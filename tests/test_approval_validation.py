from __future__ import annotations

import unittest

from ops.approval_validation import validate_approval_decision_input


class ApprovalValidationTests(unittest.TestCase):
    def test_validate_approval_decision_input_ok(self) -> None:
        out = validate_approval_decision_input(
            fingerprint="session.archive:old-1.jsonl",
            decision="approved",
        )
        self.assertTrue(out["ok"])

    def test_validate_approval_decision_input_invalid_fingerprint(self) -> None:
        out = validate_approval_decision_input(
            fingerprint="",
            decision="approved",
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "invalid_fingerprint")

    def test_validate_approval_decision_input_invalid_decision(self) -> None:
        out = validate_approval_decision_input(
            fingerprint="session.archive:old-1.jsonl",
            decision="maybe",
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "invalid_decision")


if __name__ == "__main__":
    unittest.main()
