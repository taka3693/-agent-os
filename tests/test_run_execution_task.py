import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _base_task(actions, approval_required=False, approved=False):
    return {
        "task_id": "test_task",
        "type": "execution",
        "approval_required": approval_required,
        "approved": approved,
        "execution": {"actions": actions},
        "args": {},
        "result": {},
    }


class _RunnerTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.repo = Path(self._tmp) / "agent-os"
        os.environ["AGENTOS_REPO_ROOT"] = str(self.repo)
        os.environ["AGENTOS_SESSIONS_DIR"] = str(self.repo / "sessions")
        os.environ["AGENTOS_ARCHIVE_ROOT"] = str(self.repo / "archive")

        import execution.config
        import runner.run_execution_task as rmod
        importlib.reload(execution.config)
        importlib.reload(rmod)
        self.run_task = rmod.run_task

    def tearDown(self):
        for key in ("AGENTOS_REPO_ROOT", "AGENTOS_SESSIONS_DIR", "AGENTOS_ARCHIVE_ROOT"):
            os.environ.pop(key, None)

    def _write_task(self, data: dict) -> str:
        queued = self.repo / "state" / "tasks" / "queued"
        queued.mkdir(parents=True, exist_ok=True)
        p = queued / "test_task.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return str(p)


class TestRunTaskGuards(_RunnerTestBase):
    def test_unknown_action_raises(self):
        path = self._write_task(
            _base_task([{"action_id": "totally.unknown", "args": {}}])
        )
        with self.assertRaises(ValueError) as ctx:
            self.run_task(path)
        self.assertIn("Unknown action_id", str(ctx.exception))

    def test_restart_sole_action_raises(self):
        path = self._write_task(
            _base_task(
                [{"action_id": "service.restart_openclaw_gateway", "args": {}}],
                approval_required=True,
                approved=True,
            )
        )
        with self.assertRaises(ValueError) as ctx:
            self.run_task(path)
        self.assertIn("sole action", str(ctx.exception))

    def test_approval_required_without_flag_raises(self):
        path = self._write_task(
            _base_task(
                [
                    {"action_id": "service.restart_openclaw_gateway", "args": {}},
                    {"action_id": "service.status_openclaw_gateway", "args": {}},
                ],
                approval_required=False,
            )
        )
        with self.assertRaises(ValueError) as ctx:
            self.run_task(path)
        self.assertIn("approval_required", str(ctx.exception))


class TestRunTaskSuccess(_RunnerTestBase):
    @patch("execution.executor.subprocess.run")
    def test_read_only_actions_complete(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="## main",
            stderr="",
        )
        path = self._write_task(
            _base_task([
                {"action_id": "git.status_repo", "args": {"repo_path": "/home/milky/agent-os"}},
                {"action_id": "service.status_openclaw_gateway", "args": {}},
            ])
        )
        result = self.run_task(path)

        self.assertEqual(result["status"], "completed")

        completed = self.repo / "state" / "tasks" / "completed" / "test_task.json"
        self.assertTrue(completed.exists())

        saved = json.loads(completed.read_text(encoding="utf-8"))
        self.assertTrue(saved["result"]["execution"]["ok"])


if __name__ == "__main__":
    unittest.main()
