#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "apply_light_check_answer.py"


class ApplyLightCheckAnswerTests(unittest.TestCase):
    def test_apply_light_check_answer_updates_task_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = Path(tmpdir) / "task-light-check.json"
            task = {
                "task_id": "task-light-check",
                "status": "awaiting_check",
                "light_check": {
                    "topic_key": "scrapling_install_route"
                }
            }
            task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            cp = subprocess.run(
                ["python3", str(SCRIPT), str(task_path), "direct_install"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(cp.returncode, 0, cp.stdout + "\n" + cp.stderr)

            out = json.loads(cp.stdout)
            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "queued")
            self.assertIn("scrapling_install_route", out["completed_light_checks"])
            self.assertEqual(out["light_check_answer"], "direct_install")

            updated = json.loads(task_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["status"], "queued")
            self.assertEqual(updated["light_check_answer"], "direct_install")
            self.assertIn("scrapling_install_route", updated["completed_light_checks"])
            self.assertIn("light_check_resolved_at", updated)


if __name__ == "__main__":
    unittest.main()
