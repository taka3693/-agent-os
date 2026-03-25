#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LightCheckPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_module("light_check_policy", ROOT / "policy" / "light_check_policy.py")
        cls.runner = load_module("run_task_once", ROOT / "runner" / "run_task_once.py")

    def test_record_light_check_writes_jsonl(self):
        evaluation = self.policy.evaluate_light_check(
            "では改めScraplingをインストールしよう。",
            recent_actions=[{"action": "uninstall", "target": "scrapling"}],
        )
        self.assertTrue(evaluation["check_required"])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "light_checks.jsonl"
            original = self.policy.LIGHT_CHECK_LOG
            self.policy.LIGHT_CHECK_LOG = path
            try:
                ok = self.policy.record_light_check(evaluation, answer="direct_install", suppressed=False)
                self.assertTrue(ok)
                lines = path.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(lines), 1)
                obj = json.loads(lines[0])
                self.assertEqual(obj["topic_key"], "scrapling_install_route")
                self.assertEqual(obj["answer"], "direct_install")
            finally:
                self.policy.LIGHT_CHECK_LOG = original

    def test_record_light_check_appends_expected_fields(self):
        evaluation = self.policy.evaluate_light_check(
            "では改めScraplingをインストールしよう。",
            recent_actions=[{"action": "uninstall", "target": "scrapling"}],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "light_checks.jsonl"
            self.policy._append_jsonl_record(
                {
                    "timestamp": "2026-03-26T01:00:00+09:00",
                    "topic_key": evaluation["topic_key"],
                    "reason_codes": evaluation["reason_codes"],
                    "question": evaluation["question"],
                    "answer": "direct_install",
                    "ttl_scope": evaluation["ttl_scope"],
                    "recheck_suppressed": False,
                },
                path,
            )
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            obj = json.loads(lines[0])
            self.assertEqual(obj["topic_key"], "scrapling_install_route")
            self.assertEqual(obj["answer"], "direct_install")
            self.assertFalse(obj["recheck_suppressed"])

    def test_scrapling_install_requires_check_after_recent_uninstall(self):
        result = self.policy.evaluate_light_check(
            "では改めScraplingをインストールしよう。",
            recent_actions=[{"action": "uninstall", "target": "scrapling"}],
        )
        self.assertTrue(result["check_required"])
        self.assertEqual(result["action"], "install")
        self.assertEqual(result["target"], "scrapling")
        self.assertIn("LAYER_COLLISION", result["reason_codes"])
        self.assertIn("RECENT_REVERSE_ACTION", result["reason_codes"])
        self.assertIn("ROUTE_AMBIGUITY", result["reason_codes"])
        self.assertEqual(result["topic_key"], "scrapling_install_route")
        self.assertEqual(len(result["choices"]), 2)

    def test_non_install_text_does_not_trigger(self):
        result = self.policy.evaluate_light_check("Scraplingについて調べて。")
        self.assertFalse(result["check_required"])
        self.assertIsNone(result["action"])

    def test_install_without_known_target_does_not_trigger(self):
        result = self.policy.evaluate_light_check("これをインストールして。")
        self.assertFalse(result["check_required"])
        self.assertEqual(result["action"], "install")
        self.assertIsNone(result["target"])

    def test_runner_returns_awaiting_check_payload(self):
        task = {
            "task_id": "task-light-check-1",
            "status": "queued",
            "selected_skill": "research",
            "query": "では改めScraplingをインストールしよう。",
            "recent_actions": [
                {"action": "uninstall", "target": "scrapling"}
            ],
        }
        payload = self.runner.execute_task(task)
        self.assertIn("light_check", payload)
        self.assertTrue(payload["light_check"]["check_required"])
        self.assertEqual(payload["result"]["skill"], "light_check")
        self.assertIn("light check required", payload["result"]["summary"])

    def test_completed_topic_key_suppresses_recheck(self):
        result = self.policy.evaluate_light_check(
            "では改めScraplingをインストールしよう。",
            recent_actions=[{"action": "uninstall", "target": "scrapling"}],
            completed_topic_keys=["scrapling_install_route"],
        )
        self.assertFalse(result["check_required"])
        self.assertTrue(result["suppressed"])
        self.assertEqual(result["topic_key"], "scrapling_install_route")

    def test_apply_light_check_answer_marks_topic_completed(self):
        task = {
            "task_id": "task-light-check-3",
            "status": "awaiting_check",
            "light_check": {
                "topic_key": "scrapling_install_route"
            }
        }
        updated = self.runner.apply_light_check_answer(task, "direct_install")
        self.assertEqual(updated["status"], "queued")
        self.assertEqual(updated["light_check_answer"], "direct_install")
        self.assertIn("scrapling_install_route", updated["completed_light_checks"])
        self.assertIn("light_check_resolved_at", updated)

    def test_route_answer_is_exposed_on_next_execution(self):
        task = {
            "task_id": "task-light-check-4",
            "status": "queued",
            "selected_skill": "research",
            "query": "では改めScraplingをインストールしよう。",
            "recent_actions": [{"action": "uninstall", "target": "scrapling"}],
            "completed_light_checks": ["scrapling_install_route"],
            "light_check_answer": "direct_install",
        }
        payload = self.runner.execute_task(task)
        self.assertEqual(payload["chosen_route"], "direct_install")
        self.assertTrue(payload["light_check"]["suppressed"])
        self.assertFalse(payload["light_check"]["check_required"])
        self.assertEqual(payload["result"].get("execution_route"), "direct_install")
        self.assertEqual(payload["result"].get("route_target"), "scrapling")
        self.assertEqual(payload["route_context"].get("target"), "scrapling")
        self.assertEqual(payload["route_context"].get("chosen_route"), "direct_install")
        self.assertEqual(payload["result"].get("route_decision", {}).get("dispatch_mode"), "route-aware")

    def test_runner_no_check_for_regular_research_query(self):
        task = {
            "task_id": "task-light-check-2",
            "status": "queued",
            "selected_skill": "research",
            "query": "OpenClawの現状を要約して。",
        }
        payload = self.runner.execute_task(task)
        self.assertIn("light_check", payload)
        self.assertFalse(payload["light_check"]["check_required"])
        self.assertEqual(payload["result"].get("skill"), "research")


if __name__ == "__main__":
    unittest.main()
