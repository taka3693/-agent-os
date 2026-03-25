#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runner.run_task_once import apply_light_check_answer, read_json, write_json


def main() -> int:
    if len(sys.argv) < 3:
        print(json.dumps({
            "ok": False,
            "error": "usage: apply_light_check_answer.py <task_path> <answer>"
        }, ensure_ascii=False, indent=2))
        return 1

    task_path = Path(sys.argv[1])
    if not task_path.is_absolute():
        task_path = (PROJECT_ROOT / task_path).resolve()

    if not task_path.exists():
        print(json.dumps({
            "ok": False,
            "error": f"task not found: {task_path}"
        }, ensure_ascii=False, indent=2))
        return 1

    answer = sys.argv[2]
    task = read_json(task_path)
    updated = apply_light_check_answer(task, answer)
    write_json(task_path, updated)

    print(json.dumps({
        "ok": True,
        "task_path": str(task_path),
        "status": updated.get("status"),
        "completed_light_checks": updated.get("completed_light_checks", []),
        "light_check_answer": updated.get("light_check_answer"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
