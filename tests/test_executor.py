from __future__ import annotations

import importlib
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
    import execution.executor as executor
    importlib.reload(config)
    importlib.reload(executor)
    return config, executor

class ExecutorTests(unittest.TestCase):
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

        self.config, self.executor = reload_modules()

    def tearDown(self):
        for k in ["AGENTOS_REPO_ROOT", "AGENTOS_SESSIONS_DIR", "AGENTOS_ARCHIVE_ROOT"]:
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def _write_file(self, name: str, size: int, age_seconds: int = 0):
        path = self.sessions / name
        path.write_bytes(b"x" * size)
        if age_seconds:
            t = time.time() - age_seconds
            os.utime(path, (t, t))
        return path

    def test_invalid_basename_rejected(self):
        with self.assertRaises(ValueError):
            self.executor.archive_session("../evil.jsonl")

    def test_active_candidate_rejected(self):
        self._write_file("old.jsonl", 100, age_seconds=3600)
        self._write_file("new.jsonl", 100, age_seconds=1)
        with self.assertRaises(ValueError):
            self.executor.archive_session("new.jsonl")

    def test_archive_non_active_success(self):
        self._write_file("old_big.jsonl", 100, age_seconds=3600)
        self._write_file("new_small.jsonl", 10, age_seconds=1)
        result = self.executor.archive_session("old_big.jsonl")
        self.assertTrue(result["ok"])

if __name__ == "__main__":
    unittest.main()
