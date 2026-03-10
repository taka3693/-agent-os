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


class Step85MultiSkillPipelineTests(unittest.TestCase):
    def test_router_pipeline_helpers_exist(self):
        s = (ROOT / "bridge/route_to_task.py").read_text(encoding="utf-8")
        self.assertIn("_step85_normalize_selected_skills", s)
        self.assertIn("_step85_build_pipeline", s)
        self.assertIn('"pipeline"', s)

    def test_router_pipeline_result(self):
        mod = load_module("route_to_task_step85", ROOT / "bridge/route_to_task.py")
        base = {
            "selected_skill": "critique",
            "selected_skills": ["critique", "decision", "critique", "execution"],
            "route_reason": "critique_keyword_match",
        }
        result = mod._step85_build_pipeline(base)
        self.assertEqual(result["selected_skill"], "critique")
        self.assertEqual(result["selected_skills"], ["critique", "decision", "execution"][: result["pipeline"]["max_chain"]])
        self.assertIn("pipeline", result)
        self.assertEqual(result["pipeline"]["primary_skill"], "critique")
        self.assertGreaterEqual(result["pipeline"]["chain_length"], 1)

    def test_runner_has_pipeline_helpers(self):
        s = (ROOT / "runner/run_task_once.py").read_text(encoding="utf-8")
        self.assertIn("_step85_pick_selected_skill", s)
        self.assertIn("_step85_pipeline_meta", s)

    def test_request_tool_has_route_normalizer(self):
        p = ROOT / "tools/run_agent_os_request.py"
        if p.exists():
            s = p.read_text(encoding="utf-8")
            self.assertIn("_step85_normalize_route_result", s)


if __name__ == "__main__":
    unittest.main()
