"""
Agent-OS Executor - 契約完全準拠版
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _init_task_state(
    query: str,
    selected_skill: str,
    skill_chain: Optional[List[str]] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    now = _now_iso()
    return {
        "task_id": task_id or str(uuid.uuid4()),
        "query": query,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "selected_skill": selected_skill,
        "skill_chain": skill_chain if skill_chain is not None else [],
        "step_results": [],
        "execution": {
            "current_step_index": 0,
        },
    }


def _execute_single_step(
    task: Dict[str, Any],
    step_fn: Callable[[], Dict[str, Any]],
    step_name: str,
) -> Dict[str, Any]:
    start_time = _now_iso()
    step_result: Dict[str, Any] = {
        "step": step_name,
        "start_time": start_time,
        "end_time": None,
        "ok": False,
        "error": None,
        "output": None,
    }

    try:
        output = step_fn()
        step_result["ok"] = True
        step_result["output"] = output
    except Exception as e:
        step_result["ok"] = False
        step_result["error"] = str(e)

    step_result["end_time"] = _now_iso()
    task["step_results"].append(step_result)
    task["execution"]["current_step_index"] += 1
    task["updated_at"] = _now_iso()

    return step_result


def _determine_status(task: Dict[str, Any], continue_on_error: bool) -> str:
    results = task.get("step_results", [])
    if not results:
        return "pending"

    ok_count = sum(1 for r in results if r.get("ok"))
    total = len(results)

    if ok_count == total:
        return "completed"
    elif ok_count == 0:
        return "failed"
    else:
        return "partial"


def _save_task_atomic(task: Dict[str, Any], tasks_dir: str) -> str:
    tasks_path = Path(tasks_dir)
    tasks_path.mkdir(parents=True, exist_ok=True)

    task_id = task["task_id"]
    target_file = tasks_path / f"{task_id}.json"
    temp_file = tasks_path / f".{task_id}.tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)

    temp_file.rename(target_file)
    return str(target_file)


def run_pipeline_executor(
    query: str,
    selected_skill: str,
    step_fns: List[Callable[[], Dict[str, Any]]],
    step_names: Optional[List[str]] = None,
    skill_chain: Optional[List[str]] = None,
    tasks_dir: str = "./tasks",
    continue_on_error: bool = False,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    task = _init_task_state(
        query=query,
        selected_skill=selected_skill,
        skill_chain=skill_chain,
        task_id=task_id,
    )

    if step_names is None:
        step_names = [f"step_{i}" for i in range(len(step_fns))]

    for i, step_fn in enumerate(step_fns):
        step_name = step_names[i] if i < len(step_names) else f"step_{i}"
        result = _execute_single_step(task, step_fn, step_name)

        if not result["ok"] and not continue_on_error:
            break

    task["status"] = _determine_status(task, continue_on_error)
    task["updated_at"] = _now_iso()
    _save_task_atomic(task, tasks_dir)

    return task


__all__ = [
    "_now_iso",
    "_init_task_state",
    "_execute_single_step",
    "run_pipeline_executor",
]
