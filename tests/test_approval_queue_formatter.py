from __future__ import annotations

import unittest

from ops.approval_queue import format_pending_approvals


class ApprovalQueueFormatterTests(unittest.TestCase):
    def test_format_pending_approvals_empty(self) -> None:
        self.assertEqual(format_pending_approvals([]), "承認待ち: 0件")

    def test_format_pending_approvals_rows(self) -> None:
        text = format_pending_approvals(
            [
                {
                    "action": "session.archive",
                    "fingerprint": "session.archive:old-2.jsonl",
                    "source": "session_hygiene",
                },
                {
                    "action": "session.archive",
                    "fingerprint": "session.archive:old-1.jsonl",
                    "source": "evaluation",
                },
            ]
        )

        self.assertIn("承認待ち: 2件", text)
        self.assertIn("1. session.archive | fp=session.archive:old-2.jsonl | source=session_hygiene", text)
        self.assertIn("2. session.archive | fp=session.archive:old-1.jsonl | source=evaluation", text)


if __name__ == "__main__":
    unittest.main()
