from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path("/home/milky/agent-os")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bridge.telegram_agent_os_entry import handle_message


class TelegramRouteApprovalEntryTests(unittest.TestCase):
    def _write_task(self, root: Path, task_id: str) -> Path:
        task_path = root / f"{task_id}.json"
        task_path.write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "status": "completed",
                    "route_execution": {
                        "status": "approval_required",
                        "action": "direct install path for unknownpkg",
                        "handler": "handle_direct_install",
                        "chosen_route": "direct_install",
                        "target": "unknownpkg",
                    },
                    "approval_state": {
                        "status": "approval_required",
                        "reason": "unknownpkg は allowlist 外のため確認待ち",
                        "route_handler": "handle_direct_install",
                        "target": "unknownpkg",
                        "created_at": "2026-03-26T00:00:00+00:00",
                    },
                    "route_result": {
                        "status": "approval_required",
                        "summary": "unknownpkg は allowlist 外のため確認待ち",
                        "route_handler": "handle_direct_install",
                        "target": "unknownpkg",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return task_path

    def test_handle_message_approve_by_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tasks_dir = Path(td)
            task_path = self._write_task(tasks_dir, "task-route-approve")

            with patch("bridge.telegram_agent_os_entry.TASKS_DIR", tasks_dir):
                out = handle_message("aos approve task-route-approve")

            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "route_approval")
            self.assertEqual(out["decision"], "approve")
            self.assertEqual(out["approval_state"]["status"], "approved")
            self.assertEqual(out["route_execution"]["status"], "planned")
            self.assertEqual(out["route_result"]["status"], "approved")
            self.assertEqual(out["task_path"], str(task_path.resolve()))
            self.assertIn("route approve: task-route-approve", out["reply_text"])

    def test_handle_message_reject_by_task_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tasks_dir = Path(td)
            task_path = self._write_task(tasks_dir, "task-route-reject")

            out = handle_message(f"aos reject {task_path}")

            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "route_approval")
            self.assertEqual(out["decision"], "reject")
            self.assertEqual(out["approval_state"]["status"], "rejected")
            self.assertEqual(out["route_execution"]["status"], "rejected")
            self.assertEqual(out["route_result"]["status"], "rejected")
            self.assertIn("route reject: task-route-reject", out["reply_text"])

    def test_handle_message_route_approval_missing_task(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tasks_dir = Path(td)

            with patch("bridge.telegram_agent_os_entry.TASKS_DIR", tasks_dir):
                out = handle_message("aos approve task-route-missing")

            self.assertFalse(out["ok"])
            self.assertEqual(out["mode"], "route_approval")
            self.assertEqual(out["status"], "task_not_found")


if __name__ == "__main__":
    unittest.main()
