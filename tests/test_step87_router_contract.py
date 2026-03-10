import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "run_agent_os_request.py"


def run_cli(*args: str):
    proc = subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return proc


def parse_json_output(stdout: str):
    text = (stdout or "").strip()
    if not text:
        raise AssertionError("CLI stdout is empty")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise AssertionError(f"stdout is not valid JSON:\n{text}") from e


class Step87RouterContractTests(unittest.TestCase):
    maxDiff = None

    def run_router(self, command_name: str, query: str):
        proc = run_cli(command_name, query)
        self.assertEqual(
            proc.returncode, 0,
            msg=f"CLI failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        data = parse_json_output(proc.stdout)
        self.assertIsInstance(data, dict)
        return data

    def assert_router_contract(self, data: dict):
        self.assertTrue(data.get("ok"), msg=f"ok was not true: {data}")
        self.assertEqual(data.get("mode"), "router")
        self.assertEqual(data.get("status"), "completed")

        self.assertIn("task_id", data)
        self.assertTrue(data.get("task_id"))

        self.assertIn("task_path", data)
        self.assertTrue(data.get("task_path"))

        self.assertIn("selected_skill", data)
        self.assertTrue(data.get("selected_skill"))

        self.assertIn("selected_skills", data)
        self.assertIsInstance(data.get("selected_skills"), list)
        self.assertGreaterEqual(len(data.get("selected_skills")), 1)

        self.assertIn("route_reason", data)
        self.assertTrue(data.get("route_reason"))

        self.assertIn("router_policy", data)
        self.assertIsInstance(data.get("router_policy"), dict)

        self.assertIn("pipeline", data)
        self.assertIsInstance(data.get("pipeline"), dict)

        self.assertIn("plan", data)
        self.assertIsInstance(data.get("plan"), dict)

        self.assertIn("planning_mode", data)
        self.assertEqual(data.get("planning_mode"), "autonomous")

        self.assertIn("router_result", data)
        self.assertIsInstance(data.get("router_result"), dict)

        self.assertIn("reply_text", data)
        self.assertIsInstance(data.get("reply_text"), str)
        self.assertTrue(data.get("reply_text").strip())

        self.assertIn("telegram_reply_text", data)
        self.assertEqual(data.get("reply_text"), data.get("telegram_reply_text"))

        router_result = data["router_result"]
        self.assertEqual(router_result.get("task_id"), data.get("task_id"))
        self.assertEqual(router_result.get("task_path"), data.get("task_path"))

    def test_router_command_contract(self):
        data = self.run_router("router", "比較して整理したい")
        self.assert_router_contract(data)

    def test_route_alias_contract(self):
        data = self.run_router("route", "比較して整理したい")
        self.assert_router_contract(data)

    def test_reply_text_contains_required_lines(self):
        data = self.run_router("router", "比較して整理したい")
        text = data["reply_text"]

        self.assertIn("router 受付完了", text)
        self.assertIn(f"task: {data['task_id']}", text)
        self.assertIn(f"selected_skill: {data['selected_skill']}", text)
        self.assertIn(f"route_reason: {data['route_reason']}", text)
        self.assertIn(
            f"bridge: selected_skill={data['selected_skill']} route_reason={data['route_reason']}",
            text,
        )

    def test_pipeline_shape(self):
        data = self.run_router("router", "比較して整理したい")
        pipeline = data["pipeline"]

        for key in ("primary_skill", "skill_chain", "chain_length", "max_chain"):
            self.assertIn(key, pipeline, msg=f"pipeline missing {key}: {pipeline}")

        self.assertIsInstance(pipeline["skill_chain"], list)
        self.assertGreaterEqual(len(pipeline["skill_chain"]), 1)
        self.assertEqual(pipeline["chain_length"], len(pipeline["skill_chain"]))

    def test_plan_shape(self):
        data = self.run_router("router", "比較して整理したい")
        plan = data["plan"]

        for key in ("goal", "steps", "step_count", "mode"):
            self.assertIn(key, plan, msg=f"plan missing {key}: {plan}")

        self.assertEqual(plan["mode"], "autonomous_planning")
        self.assertIsInstance(plan["steps"], list)
        self.assertEqual(plan["step_count"], len(plan["steps"]))

        self.assertGreaterEqual(len(plan["steps"]), 1)
        for i, step in enumerate(plan["steps"], start=1):
            self.assertIsInstance(step, dict, msg=f"step#{i} is not dict: {step}")
            for key in ("skill", "purpose", "done_when"):
                self.assertIn(key, step, msg=f"plan step#{i} missing {key}: {step}")

    def test_route_reason_literals(self):
        cases = [
            ("この案を批判的にレビューして", "critique", "critique_keyword_match"),
            ("どれを選ぶべきか決めたい", "decision", "decision_keyword_match"),
            ("仮説検証したい", "experiment", "experiment_keyword_match"),
            ("実装して", "execution", "execution_keyword_match"),
            ("振り返りしたい", "retrospective", "retrospective_keyword_match"),
            ("関連情報を調査して", "research", "fallback_research"),
        ]

        for query, expected_skill, expected_reason in cases:
            with self.subTest(query=query):
                data = self.run_router("router", query)
                self.assertEqual(data.get("selected_skill"), expected_skill)
                self.assertEqual(data.get("route_reason"), expected_reason)
                self.assertIn(expected_skill, data.get("selected_skills", []))


if __name__ == "__main__":
    unittest.main()
