from __future__ import annotations

import unittest

from ops.action_fingerprint import build_action_fingerprint


class TestActionFingerprint(unittest.TestCase):
    def test_session_archive_includes_target_basename(self) -> None:
        key = build_action_fingerprint(
            {
                "action": "session.archive",
                "args": {"target_basename": "old-big.jsonl"},
            }
        )
        self.assertEqual(key, "session.archive:old-big.jsonl")

    def test_non_archive_uses_action_name(self) -> None:
        key = build_action_fingerprint(
            {"action": "service.restart_openclaw_gateway"}
        )
        self.assertEqual(key, "service.restart_openclaw_gateway")

    def test_missing_action_returns_unknown(self) -> None:
        key = build_action_fingerprint({})
        self.assertEqual(key, "unknown")


if __name__ == "__main__":
    unittest.main()
