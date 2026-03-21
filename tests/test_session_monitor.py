from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path("/home/milky/agent-os")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def reload_modules():
    import execution.config as config
    import eval.session_monitor as session_monitor
    importlib.reload(config)
    importlib.reload(session_monitor)
    return config, session_monitor

class SessionMonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "agent-os"
        self.sessions = root / "sessions"
        self.archive = root / "archive"
        self.sessions.mkdir(parents=True, exist_ok=True)

        os.environ["AGENTOS_REPO_ROOT"] = str(self.repo)
        os.environ["AGENTOS_SESSIONS_DIR"] = str(self.sessions)
        os.environ["AGENTOS_ARCHIVE_ROOT"] = str(self.archive)
        os.environ["AGENTOS_AUTO_ARCHIVE_MIN_AGE_SECONDS"] = "1800"

        self.config, self.session_monitor = reload_modules()

    def tearDown(self):
        for k in ["AGENTOS_REPO_ROOT", "AGENTOS_SESSIONS_DIR", "AGENTOS_ARCHIVE_ROOT", "AGENTOS_AUTO_ARCHIVE_MIN_AGE_SECONDS"]:
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def _write_file(self, name: str, size: int, age_seconds: int = 0):
        path = self.sessions / name
        path.write_bytes(b"x" * size)
        if age_seconds:
            t = time.time() - age_seconds
            os.utime(path, (t, t))
        return path

    def test_healthy_report(self):
        self._write_file("a.jsonl", 1024, age_seconds=60)
        report = self.session_monitor.monitor_once()
        self.assertEqual(report["status"], "healthy")
        self.assertEqual(report["file_count"], 1)

    def test_auto_archive_task_created_for_old_non_active_large_file(self):
        self._write_file("old_large.jsonl", self.config.HIGH_BYTES + 100, age_seconds=7200)
        self._write_file("active_small.jsonl", 1024, age_seconds=10)
        report = self.session_monitor.monitor_once()
        self.assertEqual(report["status"], "high")
        queued = list((self.config.QUEUED_DIR).glob("*.json"))
        self.assertEqual(len(queued), 1)
        task = json.loads(queued[0].read_text(encoding="utf-8"))
        self.assertFalse(task["approval_required"])
        self.assertTrue(task["approved"])

    def test_manual_review_task_created_for_recent_non_active_large_file(self):
        self._write_file("old_small.jsonl", 2048, age_seconds=10000)
        self._write_file("recent_large.jsonl", self.config.HIGH_BYTES + 100, age_seconds=10)
        self._write_file("active_newer_small.jsonl", 1024, age_seconds=1)
        self.session_monitor.monitor_once()
        queued = list((self.config.QUEUED_DIR).glob("*.json"))
        self.assertEqual(len(queued), 1)
        task = json.loads(queued[0].read_text(encoding="utf-8"))
        self.assertTrue(task["approval_required"])
        self.assertFalse(task["approved"])

if __name__ == "__main__":
    unittest.main()
