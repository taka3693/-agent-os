#!/usr/bin/env python3
"""Step92: Task Scheduler

Provides minimal scheduling capabilities for task execution:
- Scan state/tasks/*.json for executable tasks
- Respect run_at / next_retry_at timing
- Prevent double execution of running tasks
- Handle retry policies with max_retries
- Simple lock mechanism to prevent duplicate scheduler runs
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    """Return current timestamp in ISO 8601 format."""
    return _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse ISO 8601 timestamp to datetime."""
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _is_future(ts: str | None) -> bool:
    """Check if timestamp is in the future."""
    if not ts:
        return False
    dt = _parse_iso(ts)
    if dt is None:
        return False
    return dt > _now_utc()


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Atomically write JSON to avoid partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as tmp:
        tmp.write(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _load_task(path: Path) -> Dict[str, Any]:
    """Load task JSON with error handling."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _init_schedule() -> Dict[str, Any]:
    """Initialize empty schedule section."""
    return {
        "run_at": None,
        "retry_count": 0,
        "max_retries": 3,
        "last_attempt_at": None,
        "next_retry_at": None,
        "locked_by": None,
        "locked_at": None,
    }


def _ensure_schedule(task: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure task has schedule section with defaults."""
    task = dict(task)
    if "schedule" not in task or not isinstance(task.get("schedule"), dict):
        task["schedule"] = _init_schedule()
    else:
        # Fill in missing fields with defaults
        defaults = _init_schedule()
        for key, value in defaults.items():
            if key not in task["schedule"]:
                task["schedule"][key] = value
    return task


def _is_task_locked(task: Dict[str, Any]) -> bool:
    """Check if task is currently locked."""
    schedule = task.get("schedule", {})
    locked_by = schedule.get("locked_by")
    locked_at = schedule.get("locked_at")

    if not locked_by or not locked_at:
        return False

    # Lock expires after 5 minutes
    locked_dt = _parse_iso(locked_at)
    if locked_dt is None:
        return False

    elapsed = (_now_utc() - locked_dt).total_seconds()
    if elapsed > 300:  # 5 minutes
        return False

    return True


def _acquire_lock(task: Dict[str, Any], lock_id: str) -> Dict[str, Any]:
    """Acquire lock on task."""
    task = dict(task)
    task["schedule"] = dict(task.get("schedule", {}))
    task["schedule"]["locked_by"] = lock_id
    task["schedule"]["locked_at"] = _now_iso()
    return task


def _release_lock(task: Dict[str, Any]) -> Dict[str, Any]:
    """Release lock on task."""
    task = dict(task)
    task["schedule"] = dict(task.get("schedule", {}))
    task["schedule"]["locked_by"] = None
    task["schedule"]["locked_at"] = None
    return task


def _can_retry(task: Dict[str, Any]) -> bool:
    """Check if task can be retried."""
    schedule = task.get("schedule", {})
    retry_count = schedule.get("retry_count", 0)
    max_retries = schedule.get("max_retries", 3)
    return retry_count < max_retries


def _increment_retry(task: Dict[str, Any]) -> Dict[str, Any]:
    """Increment retry count and set next_retry_at."""
    task = dict(task)
    task["schedule"] = dict(task.get("schedule", {}))

    retry_count = task["schedule"].get("retry_count", 0)
    task["schedule"]["retry_count"] = retry_count + 1
    task["schedule"]["last_attempt_at"] = _now_iso()

    # Exponential backoff: 1min, 2min, 4min
    delay_minutes = 2 ** (retry_count)
    next_retry = _now_utc().replace(tzinfo=None) + __import__("datetime").timedelta(minutes=delay_minutes)
    task["schedule"]["next_retry_at"] = next_retry.strftime("%Y-%m-%dT%H:%M:%SZ")

    return task


# ---------------------------------------------------------------------------
# Step98: Priority & fairness helpers
# ---------------------------------------------------------------------------

# Fixed priority order: queued > partial > failed (retry) > recovery
_STATUS_EXEC_PRIORITY: Dict[str, int] = {
    "queued": 0,
    "partial": 1,
    "failed": 2,
}

# Starvation threshold – tasks waiting longer than this (seconds) get boosted
_STARVATION_THRESHOLD_SECONDS: int = 300  # 5 minutes

# Default global concurrency limit
DEFAULT_MAX_CONCURRENT_TASKS: int = 4


def _task_sort_key(task: Dict[str, Any]) -> tuple:
    """Return a sort key implementing priority + starvation.

    Sorting is ascending, so *lower* values run first.

    Key structure: (starvation_boost, status_priority, created_ts)
      - starvation_boost: 0 if starving (old), 1 otherwise → starving wins
      - status_priority : queued(0) < partial(1) < failed(2)
      - created_ts      : older tasks first within same priority
    """
    status = task.get("status", "queued")
    priority = _STATUS_EXEC_PRIORITY.get(status, 9)

    # Starvation detection
    created_at = task.get("created_at") or ""
    created_dt = _parse_iso(created_at)
    starving = 1  # default: not starving
    if created_dt:
        age = (_now_utc() - created_dt).total_seconds()
        if age >= _STARVATION_THRESHOLD_SECONDS:
            starving = 0  # boost

    return (starving, priority, created_at)


def _interleave_by_skill(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Round-robin interleave tasks across skill chains for fairness.

    Tasks that share the same first-skill are spread out so no single
    skill dominates the head of the queue.

    Pre-condition: *tasks* is already sorted by _task_sort_key (priority).
    """
    from collections import OrderedDict

    buckets: OrderedDict[str, List[Dict[str, Any]]] = OrderedDict()
    for t in tasks:
        skill_chain = (t.get("plan") or {}).get("skill_chain") or []
        key = skill_chain[0] if skill_chain else ""
        buckets.setdefault(key, []).append(t)

    result: List[Dict[str, Any]] = []
    while buckets:
        empty_keys = []
        for key in list(buckets.keys()):
            lst = buckets[key]
            result.append(lst.pop(0))
            if not lst:
                empty_keys.append(key)
        for key in empty_keys:
            del buckets[key]
    return result


def _count_running_tasks(tasks_dir: Path) -> int:
    """Count tasks currently in 'running' status."""
    count = 0
    if not tasks_dir.exists():
        return count
    for task_file in tasks_dir.glob("task-*.json"):
        task = _load_task(task_file)
        if task.get("status") == "running":
            count += 1
    return count


def find_executable_tasks(
    tasks_dir: Path,
    lock_id: str | None = None,
    max_concurrent_tasks: int = DEFAULT_MAX_CONCURRENT_TASKS,
) -> List[Dict[str, Any]]:
    """Find tasks that are ready for execution.

    Criteria:
    - status is "queued" or ("failed"/"partial" with retries remaining)
    - run_at is None or in the past
    - next_retry_at is None or in the past
    - not currently running
    - not locked (or lock expired)
    - total running + to-be-returned does not exceed max_concurrent_tasks

    Tasks are returned sorted by priority / fairness / starvation.

    Args:
        tasks_dir: Directory containing task JSON files
        lock_id: Optional lock ID to use for locking tasks
        max_concurrent_tasks: Global concurrency ceiling

    Returns:
        List of tasks ready for execution (with lock acquired)
    """
    if not tasks_dir.exists():
        return []

    # How many slots are free?
    running_count = _count_running_tasks(tasks_dir)
    available_slots = max(0, max_concurrent_tasks - running_count)
    if available_slots == 0:
        return []

    candidates: List[Dict[str, Any]] = []

    for task_file in sorted(tasks_dir.glob("task-*.json")):
        task = _load_task(task_file)
        if not task:
            continue

        task = _ensure_schedule(task)
        status = task.get("status", "")

        # Skip completed tasks
        if status == "completed":
            continue

        # Skip running tasks (prevent double execution)
        if status == "running":
            continue

        # Check if task is locked
        if _is_task_locked(task):
            continue

        # Check run_at timing
        run_at = task["schedule"].get("run_at")
        if run_at and _is_future(run_at):
            continue

        # Handle queued tasks
        if status == "queued":
            candidates.append((task, task_file))
            continue

        # Handle failed/partial tasks with retry
        if status in ("failed", "partial"):
            if not _can_retry(task):
                continue

            # Check next_retry_at timing
            next_retry_at = task["schedule"].get("next_retry_at")
            if next_retry_at and _is_future(next_retry_at):
                continue

            candidates.append((task, task_file))

    # Sort by priority / starvation, then interleave for fairness
    candidates.sort(key=lambda pair: _task_sort_key(pair[0]))
    sorted_tasks = [pair[0] for pair in candidates]
    file_map = {id(pair[0]): pair[1] for pair in candidates}

    interleaved = _interleave_by_skill(sorted_tasks)
    # Rebuild (task, file) pairs after interleaving
    candidates = [(t, file_map[id(t)]) for t in interleaved]

    # Enforce global concurrency limit
    executable: List[Dict[str, Any]] = []
    for task, task_file in candidates[:available_slots]:
        if lock_id:
            task = _acquire_lock(task, lock_id)
            _atomic_write_json(task_file, task)
        executable.append(task)

    return executable


def run_scheduler_cycle(
    tasks_dir: Path,
    executor_fn,  # Callable[[Dict], Dict] - executes task, returns updated task
    lock_id: str | None = None,
    max_tasks: int = 10,
    max_concurrent_tasks: int = DEFAULT_MAX_CONCURRENT_TASKS,
) -> Dict[str, Any]:
    """Run one scheduler cycle.

    Args:
        tasks_dir: Directory containing task JSON files
        executor_fn: Function to execute a task (receives task, returns updated task)
        lock_id: Optional lock ID for preventing duplicate scheduler runs
        max_tasks: Maximum number of tasks to process in one cycle
        max_concurrent_tasks: Global concurrency ceiling

    Returns:
        Summary of what was processed
    """
    if lock_id is None:
        lock_id = f"scheduler-{os.getpid()}-{int(time.time())}"

    summary = {
        "lock_id": lock_id,
        "found": 0,
        "executed": 0,
        "skipped": 0,
        "errors": 0,
        "tasks": [],
    }

    tasks = find_executable_tasks(
        tasks_dir,
        lock_id=lock_id,
        max_concurrent_tasks=max_concurrent_tasks,
    )
    summary["found"] = len(tasks)

    for task in tasks[:max_tasks]:
        task_id = task.get("task_id", "unknown")
        task_path = tasks_dir / f"{task_id}.json"

        try:
            # Update retry count if this is a retry
            if task.get("status") in ("failed", "partial"):
                task = _increment_retry(task)

            # Execute task
            updated_task = executor_fn(task)

            # Release lock
            updated_task = _release_lock(updated_task)

            # Save updated task
            _atomic_write_json(task_path, updated_task)

            summary["executed"] += 1
            summary["tasks"].append({
                "task_id": task_id,
                "status": updated_task.get("status"),
                "success": True,
            })

        except Exception as e:
            summary["errors"] += 1
            summary["tasks"].append({
                "task_id": task_id,
                "error": str(e),
                "success": False,
            })

            # Release lock on error
            try:
                task = _release_lock(task)
                task["status"] = "failed"
                _atomic_write_json(task_path, task)
            except Exception:
                pass

    return summary


def create_scheduled_task(
    task_id: str,
    query: str,
    skill_chain: List[str],
    run_at: str | None = None,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Create a new scheduled task with proper schema.

    Args:
        task_id: Unique task identifier
        query: User query text
        skill_chain: List of skills to execute
        run_at: Optional ISO timestamp for scheduled execution
        max_retries: Maximum retry count

    Returns:
        Task dict with proper schema
    """
    now = _now_iso()
    return {
        "task_id": task_id,
        "status": "queued",
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "request": {
            "source": "scheduler",
            "text": query,
        },
        "plan": {
            "selected_skill": skill_chain[0] if skill_chain else "research",
            "skill_chain": skill_chain,
        },
        "execution": {
            "current_step_index": 0,
            "completed_steps": 0,
            "resume_count": 0,
        },
        "step_results": [],
        "schedule": {
            "run_at": run_at,
            "retry_count": 0,
            "max_retries": max_retries,
            "last_attempt_at": None,
            "next_retry_at": None,
            "locked_by": None,
            "locked_at": None,
        },
    }
