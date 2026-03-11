#!/usr/bin/env python3
"""Step93: Task Recovery

Provides recovery capabilities for stuck tasks:
- Detect stale running tasks (heartbeat timeout)
- Detect expired locked tasks
- Resume-able tasks -> queued or partial
- Non-resume-able tasks -> failed
- Track recovery count and reasons
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
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


def _seconds_since(ts: str | None) -> float | None:
    """Return seconds elapsed since timestamp, or None if invalid."""
    dt = _parse_iso(ts)
    if dt is None:
        return None
    return (_now_utc() - dt).total_seconds()


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


def _init_recovery() -> Dict[str, Any]:
    """Initialize empty recovery section."""
    return {
        "stale_after_seconds": 300,  # 5 minutes
        "detected_at": None,
        "recovered_at": None,
        "recovery_count": 0,
        "last_recovery_reason": None,
        "max_recoveries": 3,
    }


def _ensure_recovery(task: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure task has recovery section with defaults."""
    task = dict(task)
    if "recovery" not in task or not isinstance(task.get("recovery"), dict):
        task["recovery"] = _init_recovery()
    else:
        defaults = _init_recovery()
        for key, value in defaults.items():
            if key not in task["recovery"]:
                task["recovery"][key] = value
    return task


def _ensure_execution_heartbeat(task: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure execution section has last_heartbeat_at."""
    task = dict(task)
    if "execution" not in task or not isinstance(task.get("execution"), dict):
        task["execution"] = {
            "current_step_index": 0,
            "completed_steps": 0,
            "resume_count": 0,
        }
    if "last_heartbeat_at" not in task["execution"]:
        task["execution"]["last_heartbeat_at"] = task.get("started_at")
    return task


def _is_stale_running(task: Dict[str, Any]) -> bool:
    """Check if running task is stale (no heartbeat for stale_after_seconds)."""
    if task.get("status") != "running":
        return False

    task = _ensure_recovery(task)
    task = _ensure_execution_heartbeat(task)

    stale_after = task["recovery"].get("stale_after_seconds", 300)
    last_heartbeat = task["execution"].get("last_heartbeat_at")

    if not last_heartbeat:
        # No heartbeat ever, use started_at
        last_heartbeat = task.get("started_at")

    if not last_heartbeat:
        return True  # No timing info, consider stale

    seconds = _seconds_since(last_heartbeat)
    if seconds is None:
        return True

    return seconds > stale_after


def _is_expired_lock(task: Dict[str, Any]) -> bool:
    """Check if task has expired lock (lock older than 5 minutes)."""
    schedule = task.get("schedule", {})
    locked_at = schedule.get("locked_at")

    if not locked_at:
        return False

    seconds = _seconds_since(locked_at)
    if seconds is None:
        return False

    return seconds > 300  # 5 minutes


def _can_recover(task: Dict[str, Any]) -> bool:
    """Check if task can be recovered (under max_recoveries)."""
    task = _ensure_recovery(task)
    recovery_count = task["recovery"].get("recovery_count", 0)
    max_recoveries = task["recovery"].get("max_recoveries", 3)
    return recovery_count < max_recoveries


def _is_resume_able(task: Dict[str, Any]) -> bool:
    """Check if task can be resumed (has partial progress)."""
    step_results = task.get("step_results", [])
    if not step_results:
        return False

    # Check if there's any successful step
    has_success = any(
        isinstance(r, dict) and r.get("status") == "ok"
        for r in step_results
    )

    return has_success


def _recover_task(
    task: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    """Recover a task and update its state.

    Args:
        task: Task to recover
        reason: Recovery reason

    Returns:
        Updated task with recovery applied
    """
    task = _ensure_recovery(task)
    task = _ensure_execution_heartbeat(task)

    now = _now_iso()

    # Update recovery metadata
    task["recovery"]["detected_at"] = now
    task["recovery"]["recovered_at"] = now
    task["recovery"]["recovery_count"] = task["recovery"].get("recovery_count", 0) + 1
    task["recovery"]["last_recovery_reason"] = reason

    # Clear lock
    if "schedule" in task:
        task["schedule"]["locked_by"] = None
        task["schedule"]["locked_at"] = None

    # Determine new status
    if _is_resume_able(task):
        # Has partial progress -> partial
        task["status"] = "partial"
    else:
        # No progress -> queued for retry
        task["status"] = "queued"

    # Reset execution state for resume
    task["execution"]["current_step_index"] = len([
        r for r in task.get("step_results", [])
        if isinstance(r, dict) and r.get("status") == "ok"
    ])

    return task


def _fail_task(task: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Mark task as failed with reason.

    Args:
        task: Task to fail
        reason: Failure reason

    Returns:
        Updated task with failed status
    """
    task = dict(task)
    task["status"] = "failed"
    task["finished_at"] = _now_iso()

    if "recovery" not in task:
        task["recovery"] = _init_recovery()
    task["recovery"]["last_recovery_reason"] = reason

    # Clear lock
    if "schedule" in task:
        task["schedule"]["locked_by"] = None
        task["schedule"]["locked_at"] = None

    return task


def find_stale_tasks(tasks_dir: Path) -> List[Dict[str, Any]]:
    """Find tasks that are stale and need recovery.

    Criteria:
    - status is "running" with stale heartbeat
    - OR has expired lock

    Args:
        tasks_dir: Directory containing task JSON files

    Returns:
        List of stale tasks
    """
    if not tasks_dir.exists():
        return []

    stale = []

    for task_file in sorted(tasks_dir.glob("task-*.json")):
        task = _load_task(task_file)
        if not task:
            continue

        # Check for stale running
        if _is_stale_running(task):
            stale.append({
                "task": task,
                "reason": "stale_heartbeat",
                "task_path": task_file,
            })
            continue

        # Check for expired lock
        if _is_expired_lock(task):
            stale.append({
                "task": task,
                "reason": "expired_lock",
                "task_path": task_file,
            })

    return stale


def run_recovery_cycle(
    tasks_dir: Path,
    max_recoveries: int = 10,
) -> Dict[str, Any]:
    """Run one recovery cycle.

    Args:
        tasks_dir: Directory containing task JSON files
        max_recoveries: Maximum number of tasks to recover in one cycle

    Returns:
        Summary of what was recovered
    """
    summary = {
        "found": 0,
        "recovered": 0,
        "failed": 0,
        "skipped": 0,
        "tasks": [],
    }

    stale_tasks = find_stale_tasks(tasks_dir)
    summary["found"] = len(stale_tasks)

    for entry in stale_tasks[:max_recoveries]:
        task = entry["task"]
        reason = entry["reason"]
        task_path = entry["task_path"]
        task_id = task.get("task_id", "unknown")

        # Check recovery limit
        if not _can_recover(task):
            # Mark as failed
            task = _fail_task(task, f"recovery_limit_exceeded:{reason}")
            _atomic_write_json(task_path, task)

            summary["failed"] += 1
            summary["tasks"].append({
                "task_id": task_id,
                "action": "failed",
                "reason": f"recovery_limit_exceeded:{reason}",
            })
            continue

        # Recover task
        task = _recover_task(task, reason)
        _atomic_write_json(task_path, task)

        summary["recovered"] += 1
        summary["tasks"].append({
            "task_id": task_id,
            "action": "recovered",
            "reason": reason,
            "new_status": task["status"],
        })

    return summary


def update_heartbeat(task: Dict[str, Any]) -> Dict[str, Any]:
    """Update task heartbeat timestamp.

    Call this periodically during long-running tasks.

    Args:
        task: Task to update

    Returns:
        Updated task with fresh heartbeat
    """
    task = dict(task)
    if "execution" not in task:
        task["execution"] = {}
    task["execution"]["last_heartbeat_at"] = _now_iso()
    return task
