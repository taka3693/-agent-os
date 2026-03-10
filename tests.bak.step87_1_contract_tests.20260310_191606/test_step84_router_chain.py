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


class Step84RouterChainTests(unittest.TestCase):
    def test_router_policy_constants_exist(self):
        s = (ROOT / "bridge/route_to_task.py").read_text(encoding="utf-8")
        self.assertIn("ROUTER_CATEGORY_ORDER", s)
        self.assertIn("ROUTER_FALLBACK_ORDER", s)
        self.assertIn("ROUTER_MAX_CHAIN", s)

    def test_router_chain_helpers_exist(self):
        s = (ROOT / "bridge/route_to_task.py").read_text(encoding="utf-8")
        self.assertIn("_step84_detect_route_candidates", s)
        self.assertIn("_step84_build_route_result", s)
        self.assertIn("selected_skills", s)

    def test_build_route_result(self):
        mod = load_module("route_to_task_step84", ROOT / "bridge/route_to_task.py")
        result = mod._step84_build_route_result("比較して問題点を検証したい")
        self.assertIsInstance(result, dict)
        self.assertIn("selected_skill", result)
        self.assertIn("selected_skills", result)
        self.assertIn("route_reason", result)
        self.assertIn("router_policy", result)
        self.assertTrue(isinstance(result["selected_skills"], list))
        self.assertGreaterEqual(len(result["selected_skills"]), 1)
        self.assertLessEqual(len(result["selected_skills"]), 3)

    def test_fallback_research(self):
        mod = load_module("route_to_task_step84b", ROOT / "bridge/route_to_task.py")
        result = mod._step84_build_route_result("これはただの一般メッセージ")
        self.assertEqual(result.get("selected_skill"), "research")
        self.assertEqual(result.get("route_reason"), "fallback_research")


if __name__ == "__main__":
    unittest.main()
