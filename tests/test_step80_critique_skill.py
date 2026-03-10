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


class Step80CritiqueSkillTests(unittest.TestCase):
    def test_critique_impl_run(self):
        mod = load_module("critique_impl", ROOT / "skills/critique/critique_impl.py")
        result = mod.run("この案の問題点と改善点を批評して")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("skill"), "critique")
        self.assertIn("summary", result)
        self.assertIn("findings", result)
        self.assertTrue(isinstance(result["findings"], list))
        self.assertGreaterEqual(len(result["findings"]), 1)

    def test_runner_dispatch_has_critique(self):
        s = (ROOT / "runner/run_task_once.py").read_text(encoding="utf-8")
        self.assertIn("critique_impl", s)
        self.assertTrue('"critique": critique_impl' in s or "'critique': critique_impl" in s)

    def test_router_has_critique_keywords_and_reason(self):
        s = (ROOT / "bridge/route_to_task.py").read_text(encoding="utf-8")
        self.assertIn("CRITIQUE_KEYWORDS", s)
        self.assertIn("critique_keyword_match", s)
        self.assertIn("selected_skill", s)
        self.assertIn("critique", s)


if __name__ == "__main__":
    unittest.main()
