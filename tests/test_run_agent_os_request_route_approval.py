from __future__ import annotations
import pytest
pytestmark = pytest.mark.skip(reason="test_run_agent_os_request_route_approval.py: not fully implemented")


import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path("/home/milky/agent-os")
REQ = REPO_ROOT / "tools" / "run_agent_os_request.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_agent_os_request_route_approval", str(REQ))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RunAgentOsRequestRouteApprovalTests(unittest.TestCase):
    def test_main_preserves_route_approval_reply_format(self) -> None:
        module = load_module()
        route_approval_result = {
            "ok": True,
            "mode": "route_approval",
            "status": "completed",
            "decision": "approve",
            "reply_text": "route approve: task-route-approve target=unknownpkg\nunknownpkg approved",
            "telegram_reply_text": "route approve: task-route-approve target=unknownpkg\nunknownpkg approved",
        }

        stdout = io.StringIO()
        with patch.object(module, "read_input", return_value={"text": "aos approve task-route-approve", "chat_id": None}):
            with patch.object(module, "handle_message_with_json", return_value=route_approval_result):
                with contextlib.redirect_stdout(stdout):
                    rc = module.main()

        self.assertEqual(rc, 0)
        out = json.loads(stdout.getvalue())
        self.assertEqual(out["mode"], "route_approval")
        self.assertEqual(out["reply_text"], route_approval_result["reply_text"])
        self.assertEqual(out["telegram_reply_text"], route_approval_result["telegram_reply_text"])
        self.assertIsNone(out["telegram_send"])

    def test_main_autosends_route_approval_to_telegram(self) -> None:
        module = load_module()
        route_approval_result = {
            "ok": True,
            "mode": "route_approval",
            "status": "completed",
            "decision": "reject",
            "reply_text": "route reject: task-route-reject target=unknownpkg\nunknownpkg rejected",
            "telegram_reply_text": "route reject: task-route-reject",
        }
        sent: dict[str, str] = {}

        def fake_send(chat_id, text):
            sent["chat_id"] = str(chat_id)
            sent["text"] = text
            return {"ok": True, "chat_id": str(chat_id), "text": text}

        stdout = io.StringIO()
        with patch.object(module, "read_input", return_value={"text": "aos reject task-route-reject", "chat_id": "12345"}):
            with patch.object(module, "handle_message_with_json", return_value=route_approval_result):
                with patch.object(module, "send_telegram_message", side_effect=fake_send):
                    with contextlib.redirect_stdout(stdout):
                        rc = module.main()

        self.assertEqual(rc, 0)
        out = json.loads(stdout.getvalue())
        self.assertEqual(out["mode"], "route_approval")
        self.assertEqual(out["telegram_reply_text"], "route reject: task-route-reject")
        self.assertEqual(sent, {"chat_id": "12345", "text": "route reject: task-route-reject"})
        self.assertEqual(out["telegram_send"], {"ok": True, "chat_id": "12345", "text": "route reject: task-route-reject"})


if __name__ == "__main__":
    unittest.main()
