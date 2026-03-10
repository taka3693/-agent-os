#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

BASE_DIR = Path("/home/milky/agent-os")
REQ = BASE_DIR / "tools" / "run_agent_os_request.py"

def main() -> None:
    cp = subprocess.run(
        ["python3", str(REQ), "aos router 比較して整理したい"],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 0, cp.stdout + "\n" + cp.stderr

    out = json.loads(cp.stdout)
    assert out["ok"] is True
    assert out["mode"] == "router"
    assert out["status"] == "completed"
    assert out["selected_skill"] in ("research", "decision")
    assert isinstance(out.get("runner_result"), dict)
    assert out["runner_result"]["ok"] is True
    assert out["runner_result"]["status"] == "completed"
    assert out["runner_result"]["selected_skill"] == out["selected_skill"]
    assert isinstance(out.get("task_result"), dict)
    assert "summary" in out["task_result"]
    assert "findings" in out["task_result"]

    task_path = Path(out["task_path"])
    assert task_path.exists()
    task = json.loads(task_path.read_text(encoding="utf-8"))
    assert task["status"] == "completed"
    assert task["selected_skill"] == out["selected_skill"]
    assert isinstance(task.get("result"), dict)

    print("PASS: Step75 router autorun OK")

if __name__ == "__main__":
    main()
