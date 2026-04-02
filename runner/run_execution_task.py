#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skills.execution import run_execution

TASKS_DIR = PROJECT_ROOT / "state" / "tasks"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_plan(task: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        task.get("input", {}).get("plan") if isinstance(task.get("input"), dict) else None,
        task.get("plan"),
        task.get("payload", {}).get("plan") if isinstance(task.get("payload"), dict) else None,
    ]
    for x in candidates:
        if isinstance(x, dict) and "steps" in x:
            return x
    raise ValueError("execution plan not found in task.input.plan / task.plan / task.payload.plan")


def parse_runtime_error_payload(exc: Exception) -> Dict[str, Any] | None:
    msg = str(exc)
    try:
        obj = json.loads(msg)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def run_task(task_path: Path) -> Dict[str, Any]:
    task = load_json(task_path)
    task_id = task.get("id") or task_path.stem

    task["status"] = "running"
    task["started_at"] = utc_now()
    save_json(task_path, task)

    try:
        plan = extract_plan(task)
        result = run_execution(plan=plan, task_id=task_id)

        task["status"] = "completed"
        task["completed_at"] = utc_now()
        task["result"] = result
        task["error"] = None
        task["artifacts"] = result.get("artifact_paths", [])
        task["run_log_path"] = result.get("run_log_path")
        task["operation_count"] = result.get("operation_count", 0)

        save_json(task_path, task)
        return task

    except Exception as e:
        payload = parse_runtime_error_payload(e)

        task["status"] = "failed"
        task["completed_at"] = utc_now()

        if payload is not None:
            task["result"] = payload
            task["error"] = payload.get("error", f"{type(e).__name__}: {e}")
            task["artifacts"] = payload.get("artifact_paths", [])
            task["run_log_path"] = payload.get("run_log_path")
            task["operation_count"] = payload.get("operation_count", 0)
        else:
            task["result"] = None
            task["error"] = f"{type(e).__name__}: {e}"
            task["artifacts"] = []
            task["run_log_path"] = None
            task["operation_count"] = 0

        save_json(task_path, task)
        return task


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_execution_task.py /home/milky/agent-os/state/tasks/task-xxxx.json", file=sys.stderr)
        return 2

    task_path = Path(sys.argv[1]).resolve()
    if not task_path.exists():
        print(f"task not found: {task_path}", file=sys.stderr)
        return 2

    task = run_task(task_path)
    print(json.dumps({
        "id": task.get("id", task_path.stem),
        "status": task.get("status"),
        "error": task.get("error"),
        "run_log_path": task.get("run_log_path"),
        "operation_count": task.get("operation_count"),
        "artifacts": task.get("artifacts", []),
    }, ensure_ascii=False, indent=2))
    return 0 if task.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# MISO-integrated version
# ---------------------------------------------------------------------------
def run_task_with_miso(
    task_path: Path,
    miso_enabled: bool = True,
    miso_chat_id: str = "6474742983",
) -> Dict[str, Any]:
    """
    Run task with MISO mission control reporting.
    
    Same as run_task() but sends status updates to Telegram via MISO.
    """
    from miso.bridge import (
        start_mission,
        update_mission,
        complete_mission,
        fail_mission,
    )
    
    task = load_json(task_path)
    task_id = task.get("id") or task_path.stem
    task_name = task.get("name", task_id)
    goal = task.get("goal", task.get("description", task_name))
    
    mission_id = None
    
    # --- MISO: Start mission ---
    if miso_enabled:
        try:
            result = start_mission(
                chat_id=miso_chat_id,
                mission_name=task_name,
                goal=goal,
                agents=[{"label": "executor", "status": "starting"}],
            )
            mission_id = result.get("mission_id")
            task["miso_mission_id"] = mission_id
        except Exception as e:
            task.setdefault("warnings", []).append(f"MISO start failed: {e}")
    
    task["status"] = "running"
    task["started_at"] = utc_now()
    save_json(task_path, task)
    
    # --- MISO: Running ---
    if miso_enabled and mission_id:
        try:
            update_mission(
                mission_id=mission_id,
                state="RUNNING",
                agents=[{"label": "executor", "status": "executing..."}],
                next_action="Processing task",
            )
        except Exception:
            pass
    
    try:
        plan = extract_plan(task)
        result = run_execution(plan=plan, task_id=task_id)
        
        task["status"] = "completed"
        task["completed_at"] = utc_now()
        task["result"] = result
        task["error"] = None
        task["artifacts"] = result.get("artifact_paths", [])
        task["run_log_path"] = result.get("run_log_path")
        task["operation_count"] = result.get("operation_count", 0)
        save_json(task_path, task)
        
        # --- MISO: Complete ---
        if miso_enabled and mission_id:
            try:
                complete_mission(
                    mission_id=mission_id,
                    summary=f"Task {task_name} completed",
                    artifacts=task.get("artifacts", []),
                )
            except Exception as e:
                task.setdefault("warnings", []).append(f"MISO complete failed: {e}")
        
        return task
        
    except Exception as e:
        payload = parse_runtime_error_payload(e)
        task["status"] = "failed"
        task["completed_at"] = utc_now()
        if payload is not None:
            task["result"] = payload
            task["error"] = payload.get("message") or str(e)
        else:
            task["result"] = None
            task["error"] = str(e)
        save_json(task_path, task)
        
        # --- MISO: Error ---
        if miso_enabled and mission_id:
            try:
                fail_mission(mission_id=mission_id, error=task["error"])
            except Exception:
                pass
        
        return task
