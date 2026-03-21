from __future__ import annotations

import unittest

from ops.approval_decision_formatter import format_approval_decisions


class ApprovalDecisionFormatterTests(unittest.TestCase):
    def test_format_approval_decisions_empty(self) -> None:
        self.assertEqual(format_approval_decisions([]), "承認決定履歴: 0件")

    def test_format_approval_decisions_rows(self) -> None:
        text = format_approval_decisions(
            [
                {
                    "decision": "rejected",
                    "action": "session.archive",
                    "fingerprint": "session.archive:old-2.jsonl",
                },
                {
                    "decision": "approved",
                    "action": "session.archive",
                    "fingerprint": "session.archive:old-1.jsonl",
                },
            ]
        )

        self.assertIn("承認決定履歴: 2件", text)
        self.assertIn(
            "1. rejected | action=session.archive | fp=session.archive:old-2.jsonl",
            text,
        )
        self.assertIn(
            "2. approved | action=session.archive | fp=session.archive:old-1.jsonl",
            text,
        )


if __name__ == "__main__":
    unittest.main()
