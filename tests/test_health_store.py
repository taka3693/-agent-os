from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.health import (
    append_health_history,
    write_latest_health,
)


class TestHealthStore(unittest.TestCase):
    def test_write_latest_health_creates_latest_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = {"a": 1, "b": "x"}

            path = write_latest_health(root, payload)

            self.assertTrue(path.exists())
            self.assertEqual(path.name, "latest.json")
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded, payload)

    def test_append_health_history_writes_jsonl_line(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload1 = {"n": 1}
            payload2 = {"n": 2}

            path = append_health_history(root, payload1)
            append_health_history(root, payload2)

            self.assertTrue(path.exists())
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0]), payload1)
            self.assertEqual(json.loads(lines[1]), payload2)


if __name__ == "__main__":
    unittest.main()
