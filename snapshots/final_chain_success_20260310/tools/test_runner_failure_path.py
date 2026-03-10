#!/usr/bin/env python3
import json
import subprocess
import time
from pathlib import Path

ROOT = Path("/home/milky/agent-os")
RUNNER = ROOT / "runner" / "run_research_task.py"
TASKS = ROOT / "state" / "tasks"

def fail(msg, **kw):
    print(json.dumps({"ok": False, "error": msg, **kw}, ensure_ascii=False, indent=2))
    raise SystemExit(1)

def main():
    if not RUNNER.exists():
        fail("runner not found", path=str(RUNNER))

    TASKS.mkdir(parents=True, exist_ok=True)
    task_path = TASKS / f"task-failure-test-{int(time.time())}.json"

    bad_task = {
        "task_id": task_path.stem,
        "source": "telegram",
        "selected_skill": "research",
        "status": "queued",
        "run_input": {
            # query を意図的に欠落させる
        },
        "result": {
            "summary": "",
            "findings": []
        }
    }

    task_path.write_text(json.dumps(bad_task, ensure_ascii=False, indent=2), encoding="utf-8")

    p = subprocess.run(
        ["python3", str(RUNNER), str(task_path)],
        text=True,
        capture_output=True,
        encoding="utf-8"
    )

    after = json.loads(task_path.read_text(encoding="utf-8"))

    status = after.get("status")
    error = after.get("error")
    result = after.get("result")

    if status != "failed":
        fail(
            "expected failed status",
            returncode=p.returncode,
            stdout=p.stdout,
            stderr=p.stderr,
            task=after
        )

    if not error:
        fail(
            "expected error field on failed task",
            returncode=p.returncode,
            stdout=p.stdout,
            stderr=p.stderr,
            task=after
        )

    print(json.dumps({
        "ok": True,
        "task_path": str(task_path),
        "returncode": p.returncode,
        "status": status,
        "error": error,
        "result": result,
        "stdout": p.stdout,
        "stderr": p.stderr
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
