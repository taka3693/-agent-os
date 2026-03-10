import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Step86AutonomousPlanningTests(unittest.TestCase):
    def test_router_plan_helpers_exist(self):
        s = (ROOT / "bridge/route_to_task.py").read_text(encoding="utf-8")
        self.assertIn("_step86_make_plan_outline", s)
        self.assertIn("_step86_attach_autonomous_plan", s)
        self.assertIn('"planning_mode"', s)

    def test_router_plan_attached(self):
        mod = load_module("route_to_task_step86", ROOT / "bridge/route_to_task.py")
        route = {
            "selected_skill": "critique",
            "selected_skills": ["critique", "execution"],
            "route_reason": "critique_keyword_match",
        }
        result = mod._step86_attach_autonomous_plan(route, "この案を批評して改善まで進めたい")
        self.assertIn("plan", result)
        self.assertEqual(result.get("planning_mode"), "autonomous")
        self.assertEqual(result["plan"]["mode"], "autonomous_planning")
        self.assertEqual(result["plan"]["step_count"], 2)

    def test_runner_has_plan_helper(self):
        s = (ROOT / "runner/run_task_once.py").read_text(encoding="utf-8")
        self.assertIn("_step86_extract_plan", s)
        self.assertIn("planning_mode", s)

    def test_request_tool_has_plan_normalizer(self):
        p = ROOT / "tools/run_agent_os_request.py"
        if p.exists():
            s = p.read_text(encoding="utf-8")
            self.assertIn("_step86_normalize_plan", s)
            self.assertIn("planning_mode", s)


if __name__ == "__main__":
    unittest.main()
