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


class Step82ExecutionSkillTests(unittest.TestCase):
    def test_execution_impl_run(self):
        mod = load_module("execution_impl", ROOT / "skills/execution/execution_impl.py")
        result = mod.run("この作業を実行したい")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("skill"), "execution")
        self.assertIn("summary", result)
        self.assertIn("output", result)
        self.assertIn("steps", result)
        self.assertTrue(isinstance(result["steps"], list))
        self.assertGreaterEqual(len(result["steps"]), 1)

    def test_runner_dispatch_has_execution(self):
        s = (ROOT / "runner/run_task_once.py").read_text(encoding="utf-8")
        self.assertIn("execution_impl", s)
        self.assertTrue('"execution": execution_impl' in s or "'execution': execution_impl" in s)

    def test_router_has_execution_keywords_and_reason(self):
        s = (ROOT / "bridge/route_to_task.py").read_text(encoding="utf-8")
        self.assertIn("EXECUTION_KEYWORDS", s)
        self.assertIn("execution_keyword_match", s)
        self.assertIn("execution", s)


if __name__ == "__main__":
    unittest.main()
