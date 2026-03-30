from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

StepFn = Callable[[Dict[str, Any]], Dict[str, Any]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _init_task_state(
    *,
    task_id: str,
    query: str,
    selected_skill: str,
    skill_chain: List[str],
    source: str = "cli",
) -> Dict[str, Any]:
    now = _now_iso()
    return {
        "task_id": task_id,
        "query": query,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "selected_skill": selected_skill,
        "skill_chain": skill_chain,
        "step_results": [],
        "execution": {
            "current_step_index": 0
        },
        "source": source,
    }


def _execute_single_step(
    *,
    task: Dict[str, Any],
    step_index: int,
    skill: str,
    step_fn: StepFn,
    continue_on_error: bool,
) -> Dict[str, Any]:

    start = _now_iso()
    ok = True
    err = None
    result = {}

    try:
        result = step_fn(task)
    except Exception as e:
        ok = False
        err = str(e)

    end = _now_iso()

    step_result = {
        "step": skill,
        "start_time": start,
        "end_time": end,
        "ok": ok,
        "error": err,
        "result": result,
    }

    task["step_results"].append(step_result)
    task["execution"]["current_step_index"] = step_index + 1
    task["updated_at"] = end

    if not ok and not continue_on_error:
        task["status"] = "failed"

    return task


def run_pipeline_executor(
    *,
    task_id: str,
    query: str,
    skill_chain: List[str],
    step_fns: List[StepFn],
    tasks_dir: Path,
    selected_skill: str = "unknown",
    source: str = "cli",
    continue_on_error_chain: List[bool] | None = None,
) -> Dict[str, Any]:

    task = _init_task_state(
        task_id=task_id,
        query=query,
        selected_skill=selected_skill,
        skill_chain=skill_chain,
        source=source,
    )

    if continue_on_error_chain is None:
        continue_on_error_chain = [False] * len(step_fns)

    for i, fn in enumerate(step_fns):
        skill = skill_chain[i]
        task = _execute_single_step(
            task=task,
            step_index=i,
            skill=skill,
            step_fn=fn,
            continue_on_error=continue_on_error_chain[i],
        )
        if task["status"] == "failed":
            break

    results = task["step_results"]

    if results and all(r["ok"] for r in results):
        task["status"] = "completed"
    elif any(r["ok"] for r in results):
        task["status"] = "partial"
    else:
        task["status"] = "failed"

    task["updated_at"] = _now_iso()

    _atomic_write_json(tasks_dir / f"{task_id}.json", task)

    return task

