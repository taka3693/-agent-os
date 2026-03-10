#!/usr/bin/env python3
import json
import subprocess
import uuid
from pathlib import Path

BASE_DIR = Path("/home/milky/agent-os")
TASKS_DIR = BASE_DIR / "state" / "tasks"
RUNNER = BASE_DIR / "runner" / "run_task_once.py"

def make_task() -> Path:
    task_id = f"task-step74-{uuid.uuid4().hex[:8]}"
    p = TASKS_DIR / f"{task_id}.json"
    obj = {
        "task_id": task_id,
        "status": "queued",
        "selected_skill": "research",
        "query": "比較して整理したい",
    }
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p

def main() -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    task_path = make_task()
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

        task = json.loads(task_path.read_text(encoding="utf-8"))
        assert task["status"] == "completed"
        assert task["selected_skill"] == "research"
        assert task["query"] == "比較して整理したい"
        assert isinstance(task.get("result"), dict)
        assert "summary" in task["result"]
        assert "findings" in task["result"]

        print("PASS: Step74 runner once OK")
    finally:
        if task_path.exists():
            task_path.unlink()

if __name__ == "__main__":
    main()
