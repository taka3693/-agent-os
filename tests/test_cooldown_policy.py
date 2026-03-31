from __future__ import annotations

import unittest

from ops.cooldown import should_emit_by_cooldown


class TestCooldownPolicy(unittest.TestCase):
    def test_should_emit_when_no_last_emitted_at(self) -> None:
        ok = should_emit_by_cooldown(
            now_iso="2026-03-12T09:00:00+00:00",
            last_emitted_at=None,
            cooldown_seconds=300,
        )
        self.assertTrue(ok)

    def test_should_not_emit_within_cooldown(self) -> None:
        ok = should_emit_by_cooldown(
            now_iso="2026-03-12T09:04:59+00:00",
            last_emitted_at="2026-03-12T09:00:00+00:00",
            cooldown_seconds=300,
        )
        self.assertFalse(ok)

    def test_should_emit_after_cooldown(self) -> None:
        ok = should_emit_by_cooldown(
            now_iso="2026-03-12T09:05:00+00:00",
            last_emitted_at="2026-03-12T09:00:00+00:00",
            cooldown_seconds=300,
        )
        self.assertTrue(ok)

    def test_should_emit_when_timestamp_invalid(self) -> None:
        ok = should_emit_by_cooldown(
            now_iso="bad-time",
            last_emitted_at="2026-03-12T09:00:00+00:00",
            cooldown_seconds=300,
        )
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
