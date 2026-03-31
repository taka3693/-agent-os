from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.health import build_health_snapshot, count_task_files


class TestHealthSnapshot(unittest.TestCase):
    def test_count_task_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "queued").mkdir()
            (root / "completed").mkdir()
            (root / "queued" / "a.json").write_text("{}", encoding="utf-8")
            (root / "queued" / "b.json").write_text("{}", encoding="utf-8")
            (root / "completed" / "c.json").write_text("{}", encoding="utf-8")

            counts = count_task_files(root)

            self.assertEqual(counts["queued"], 2)
            self.assertEqual(counts["completed"], 1)
            self.assertEqual(counts["failed"], 0)

    def test_build_health_snapshot_sorts_sessions_and_caps_top(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "queued").mkdir()

            snap = build_health_snapshot(
                tasks_root=root,
                session_sizes=[
                    {"basename": "a.jsonl", "bytes": 10},
                    {"basename": "b.jsonl", "bytes": 50},
                    {"basename": "c.jsonl", "bytes": 20},
                ],
            )

            self.assertEqual(snap["tasks"]["total"], 0)
            self.assertEqual(snap["sessions"]["count"], 3)
            self.assertEqual(snap["sessions"]["largest_bytes"], 50)
            self.assertEqual(snap["sessions"]["top"][0]["basename"], "b.jsonl")


if __name__ == "__main__":
    unittest.main()
