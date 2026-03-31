from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.cooldown import filter_actions_by_cooldown
from ops.cooldown import mark_emitted


class TestCooldownFilter(unittest.TestCase):
    def test_filter_actions_by_cooldown_allows_first_emit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            out = filter_actions_by_cooldown(
                state_root=root,
                actions=[
                    {
                        "action": "session.archive",
                        "args": {"target_basename": "old-big.jsonl"},
                        "policy": "approval_required",
                    }
                ],
                now_iso="2026-03-12T09:00:00+00:00",
                cooldown_seconds=300,
            )

            self.assertEqual(len(out), 1)
            self.assertEqual(
                out[0]["fingerprint"],
                "session.archive:old-big.jsonl",
            )

    def test_filter_actions_by_cooldown_suppresses_within_window(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mark_emitted(
                root,
                "session.archive:old-big.jsonl",
                "2026-03-12T09:00:00+00:00",
            )

            out = filter_actions_by_cooldown(
                state_root=root,
                actions=[
                    {
                        "action": "session.archive",
                        "args": {"target_basename": "old-big.jsonl"},
                        "policy": "approval_required",
                    }
                ],
                now_iso="2026-03-12T09:04:59+00:00",
                cooldown_seconds=300,
            )

            self.assertEqual(out, [])

    def test_filter_actions_by_cooldown_allows_after_window(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mark_emitted(
                root,
                "session.archive:old-big.jsonl",
                "2026-03-12T09:00:00+00:00",
            )

            out = filter_actions_by_cooldown(
                state_root=root,
                actions=[
                    {
                        "action": "session.archive",
                        "args": {"target_basename": "old-big.jsonl"},
                        "policy": "approval_required",
                    }
                ],
                now_iso="2026-03-12T09:05:00+00:00",
                cooldown_seconds=300,
            )

            self.assertEqual(len(out), 1)
            self.assertEqual(
                out[0]["fingerprint"],
                "session.archive:old-big.jsonl",
            )


if __name__ == "__main__":
    unittest.main()
