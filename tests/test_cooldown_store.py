from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.cooldown_store import (
    get_last_emitted_at,
    load_cooldowns,
    mark_emitted,
)


class TestCooldownStore(unittest.TestCase):
    def test_load_cooldowns_returns_empty_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = load_cooldowns(root)
            self.assertEqual(data, {"items": {}})

    def test_mark_emitted_and_get_last_emitted_at(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            mark_emitted(root, "session.archive:old-big.jsonl", "2026-03-12T08:00:00+00:00")

            value = get_last_emitted_at(root, "session.archive:old-big.jsonl")
            self.assertEqual(value, "2026-03-12T08:00:00+00:00")

            path = root / "ops_cooldowns.json"
            self.assertTrue(path.exists())

            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("items", loaded)
            self.assertIn("session.archive:old-big.jsonl", loaded["items"])

    def test_get_last_emitted_at_returns_none_for_unknown_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mark_emitted(root, "x", "2026-03-12T08:00:00+00:00")
            self.assertIsNone(get_last_emitted_at(root, "missing"))


if __name__ == "__main__":
    unittest.main()
