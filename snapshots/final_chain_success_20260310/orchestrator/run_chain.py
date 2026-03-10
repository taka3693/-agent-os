#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List


BASE_DIR = Path(__file__).resolve().parent.parent
RUNNER = BASE_DIR / "runner" / "run_research_task.py"


def python_cmd() -> str:
    if sys.executable:
        return sys.executable
    found = shutil.which("python3") or shutil.which("python")
    if found:
        return found
    return "/usr/bin/python3"


def child_env() -> Dict[str, str]:
    env = os.environ.copy()
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(BASE_DIR) if not prev else f"{str(BASE_DIR)}:{prev}"
    return env


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def run_one(task_path: Path) -> Dict[str, Any]:
    proc = subprocess.run(
        [python_cmd(), str(RUNNER), str(task_path)],
        cwd=str(BASE_DIR),
        env=child_env(),
        capture_output=True,
        text=True,
    )

    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    if proc.returncode != 0:
        raise RuntimeError(f"runner failed for {task_path}")

    return load_json(task_path)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_chain.py /path/to/task.json", file=sys.stderr)
        return 2

    current = Path(sys.argv[1]).resolve()
    if not current.exists():
        print(f"task file not found: {current}", file=sys.stderr)
        return 2

    visited: List[str] = []
    steps = 0
    max_steps = 10

    while True:
        steps += 1
        if steps > max_steps:
            raise RuntimeError(f"max_steps exceeded: {max_steps}")

        obj = run_one(current)
        visited.append(str(current))

        next_task_path = obj.get("next_task_path")
        if not next_task_path:
            print(json.dumps({
                "ok": True,
                "final_task_path": str(current),
                "steps": steps,
                "visited": visited,
                "status": obj.get("status"),
                "selected_skill": obj.get("selected_skill"),
            }, ensure_ascii=False))
            return 0

        current = Path(next_task_path).resolve()
        if str(current) in visited:
            raise RuntimeError(f"cycle detected: {current}")


if __name__ == "__main__":
    raise SystemExit(main())
