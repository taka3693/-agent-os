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


class Step81ExperimentSkillTests(unittest.TestCase):
    def test_experiment_impl_run(self):
        mod = load_module("experiment_impl", ROOT / "skills/experiment/experiment_impl.py")
        result = mod.run("この案を小さく検証したい")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("skill"), "experiment")
        self.assertIn("summary", result)
        self.assertIn("hypothesis", result)
        self.assertIn("experiments", result)
        self.assertTrue(isinstance(result["experiments"], list))
        self.assertGreaterEqual(len(result["experiments"]), 1)

    def test_runner_dispatch_has_experiment(self):
        s = (ROOT / "runner/run_task_once.py").read_text(encoding="utf-8")
        self.assertIn("experiment_impl", s)
        self.assertTrue('"experiment": experiment_impl' in s or "'experiment': experiment_impl" in s)

    def test_router_has_experiment_keywords_and_reason(self):
        s = (ROOT / "bridge/route_to_task.py").read_text(encoding="utf-8")
        self.assertIn("EXPERIMENT_KEYWORDS", s)
        self.assertIn("experiment_keyword_match", s)
        self.assertIn("experiment", s)


if __name__ == "__main__":
    unittest.main()
