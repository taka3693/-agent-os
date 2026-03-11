from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "tools" / "lib"

if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from json_batch_runner import run_json_batch_request  # noqa: E402


class Step90JsonBatchRunnerTests(unittest.TestCase):
    def test_passthrough_when_not_json_batch(self):
        out = run_json_batch_request("aos ls", command_handler=lambda cmd: {"ok": True})
        self.assertIsNone(out)

    def test_validate_only_contract(self):
        def handler(cmd: str):
            if cmd == "aos validate aos ls workspace":
                return {
                    "ok": True,
                    "mode": "validation",
                    "validation_action": "plan_step",
                    "reply_text": "検証OK\n実行は未実施",
                }
            if cmd == "aos validate aos rm x":
                return {
                    "ok": False,
                    "mode": "policy",
                    "policy_action": "delete_blocked",
                    "reason": "delete_disabled",
                    "validation_action": "policy_check",
                    "reply_text": "検証NG\n削除コマンドは未対応\n理由: 誤削除防止のため",
                }
            if cmd == "aos validate aos read notes/todo.md":
                return {
                    "ok": True,
                    "mode": "validation",
                    "validation_action": "plan_step",
                    "reply_text": "検証OK\n実行は未実施",
                }
            return {"ok": False, "mode": "execution", "error": f"unexpected:{cmd}"}

        text = (
            'aos json {"validate_only": true, "steps": ['
            '{"id":"scan","command":"aos ls workspace"},'
            '{"id":"danger","command":"aos rm x","continue_on_error":true},'
            '{"id":"read","command":"aos read notes/todo.md"}'
            ']}'
        )

        out = run_json_batch_request(text, command_handler=handler)
        self.assertIsInstance(out, dict)
        self.assertFalse(out["ok"])
        self.assertTrue(out["is_json_batch"])
        self.assertEqual(out["ok_count"], 2)
        self.assertEqual(out["ng_count"], 1)
        self.assertEqual(out["first_failed_step_id"], "danger")
        self.assertEqual(out["first_failed_mode"], "policy")
        self.assertEqual(out["first_failed_reason"], "delete_disabled")
        self.assertIn("補足: NG後も継続", out["telegram_reply_text"])


if __name__ == "__main__":
    unittest.main()
