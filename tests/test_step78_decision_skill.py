#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import uuid
from pathlib import Path

BASE_DIR = Path("/home/milky/agent-os")
RUNNER = BASE_DIR / "runner" / "run_task_once.py"
TASKS_DIR = BASE_DIR / "state" / "tasks"
DECISION = BASE_DIR / "skills" / "decision" / "decision_impl.py"

def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_decision_impl():
    mod = load(DECISION, "decision_impl")
    out = mod.run_decision("AとBを比較して決めたい")
    assert isinstance(out, dict)
    assert "summary" in out
    assert "findings" in out
    assert isinstance(out["findings"], list)

def test_runner_dispatch_decision():
    task_id = f"task-step78-{uuid.uuid4().hex[:8]}"
    task_path = TASKS_DIR / f"{task_id}.json"
    task = {
        "task_id": task_id,
        "status": "queued",
        "selected_skill": "decision",
        "query": "AとBを比較して決めたい",
    }
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        cp = subprocess.run(
            ["python3", str(RUNNER), str(task_path)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
        assert cp.returncode == 0, cp.stdout + "\n" + cp.stderr
        out = json.loads(cp.stdout)
        assert out["ok"] is True
        assert out["status"] == "completed"

        saved = json.loads(task_path.read_text(encoding="utf-8"))
        assert saved["status"] == "completed"
        assert saved["selected_skill"] == "decision"
        assert isinstance(saved["result"], dict)
        assert "summary" in saved["result"]
        assert "findings" in saved["result"]
    finally:
        if task_path.exists():
            task_path.unlink()

if __name__ == "__main__":
    test_decision_impl()
    test_runner_dispatch_decision()
    print("PASS: Step78 decision skill OK")
