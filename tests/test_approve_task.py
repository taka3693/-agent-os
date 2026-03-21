from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path("/home/milky/agent-os")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def reload_modules():
    import execution.config as config
    import tools.approve_task as approve_task
    importlib.reload(config)
    importlib.reload(approve_task)
    return config, approve_task

class ApproveTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "agent-os"
        self.sessions = root / "sessions"
        self.archive = root / "archive"

        os.environ["AGENTOS_REPO_ROOT"] = str(self.repo)
        os.environ["AGENTOS_SESSIONS_DIR"] = str(self.sessions)
        os.environ["AGENTOS_ARCHIVE_ROOT"] = str(self.archive)

        self.config, self.approve_task_mod = reload_modules()
        self.config.ensure_dirs()

        self.task_id = "task-session-test123"
        payload = {
            "schema": "agentos.execution_task.v1",
            "task_id": self.task_id,
            "operation": "session_archive",
            "args": {"target_basename": "foo.jsonl"},
            "status": "awaiting_approval",
            "approval_required": True,
            "approved": False,
        }
        (self.config.AWAITING_APPROVAL_DIR / f"{self.task_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def tearDown(self):
        for k in ["AGENTOS_REPO_ROOT", "AGENTOS_SESSIONS_DIR", "AGENTOS_ARCHIVE_ROOT"]:
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def test_approve_moves_to_queued(self):
        dst = self.approve_task_mod.approve_task(self.task_id, approved_by="test")
        self.assertTrue(dst.exists())

    def test_reject_moves_to_failed(self):
        src = self.config.AWAITING_APPROVAL_DIR / f"{self.task_id}.json"
        if not src.exists():
            payload = {
                "schema": "agentos.execution_task.v1",
                "task_id": self.task_id,
                "operation": "session_archive",
                "args": {"target_basename": "foo.jsonl"},
                "status": "awaiting_approval",
                "approval_required": True,
                "approved": False,
            }
            src.write_text(json.dumps(payload), encoding="utf-8")
        dst = self.approve_task_mod.reject_task(self.task_id, reason="no")
        self.assertTrue(dst.exists())

if __name__ == "__main__":
    unittest.main()
