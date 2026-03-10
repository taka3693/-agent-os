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


class Step83RetrospectiveSkillTests(unittest.TestCase):
    def test_retrospective_impl_run(self):
        mod = load_module("retrospective_impl", ROOT / "skills/retrospective/retrospective_impl.py")
        result = mod.run("この作業の振り返りをしたい")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("skill"), "retrospective")
        self.assertIn("summary", result)
        self.assertIn("went_well", result)
        self.assertIn("problems", result)
        self.assertIn("actions", result)
        self.assertTrue(isinstance(result["actions"], list))
        self.assertGreaterEqual(len(result["actions"]), 1)

    def test_runner_dispatch_has_retrospective(self):
        s = (ROOT / "runner/run_task_once.py").read_text(encoding="utf-8")
        self.assertIn("retrospective_impl", s)
        self.assertTrue('"retrospective": retrospective_impl' in s or "'retrospective': retrospective_impl" in s)

    def test_router_has_retrospective_keywords_and_reason(self):
        s = (ROOT / "bridge/route_to_task.py").read_text(encoding="utf-8")
        self.assertIn("RETROSPECTIVE_KEYWORDS", s)
        self.assertIn("retrospective_keyword_match", s)
        self.assertIn("retrospective", s)


if __name__ == "__main__":
    unittest.main()
