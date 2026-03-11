#!/usr/bin/env python3
"""Step96: Parallel-Safe State Merge

Provides merge capabilities for concurrent task state updates:
- Revision-based conflict detection
- Append-safe step_results merging
- Memory merging with union semantics
- Status transition priority
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    """Return current timestamp in ISO 8601 format."""
    return _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


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


# Status transition priority (higher = more important)
# failed > partial > completed > running > queued > pending
STATUS_PRIORITY = {
    "failed": 100,
    "partial": 80,
    "completed": 60,
    "running": 40,
    "queued": 20,
    "pending": 10,
}


def get_status_priority(status: str) -> int:
    """Get priority for a status value."""
    return STATUS_PRIORITY.get(status, 0)


def resolve_status_conflict(statuses: List[str]) -> str:
    """Resolve conflicting statuses by priority.

    Args:
        statuses: List of status values

    Returns:
        Highest priority status
    """
    if not statuses:
        return "pending"

    # Get unique statuses with their priorities
    unique = set(statuses)
    if len(unique) == 1:
        return statuses[0]

    # Return highest priority
    return max(unique, key=get_status_priority)


def _ensure_revision(task: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure task has revision field."""
    task = dict(task)
    if "revision" not in task:
        task["revision"] = 1
    return task


def bump_revision(task: Dict[str, Any]) -> Dict[str, Any]:
    """Increment task revision.

    Args:
        task: Task to update

    Returns:
        Task with incremented revision
    """
    task = _ensure_revision(task)
    task["revision"] = task.get("revision", 1) + 1
    return task


def check_revision_conflict(base: Dict[str, Any], current: Dict[str, Any]) -> bool:
    """Check if there's a revision conflict.

    Args:
        base: Base revision task
        current: Current task state

    Returns:
        True if there's a conflict
    """
    base_rev = base.get("revision", 1)
    current_rev = current.get("revision", 1)
    return current_rev > base_rev


# =============================================================================
# Step Results Merging
# =============================================================================

def merge_step_results(
    base: List[Dict[str, Any]],
    ours: List[Dict[str, Any]],
    theirs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge step_results from concurrent updates.

    Strategy: Union by step_index, preserving both results.

    Args:
        base: Original step_results
        ours: Our updates
        theirs: Their updates

    Returns:
        Merged step_results
    """
    # Build index map
    by_index: Dict[int, Dict[str, Any]] = {}

    # Add base results
    for step in base:
        if isinstance(step, dict):
            idx = step.get("step_index")
            if isinstance(idx, int):
                by_index[idx] = step

    # Add our results (overwrite base)
    for step in ours:
        if isinstance(step, dict):
            idx = step.get("step_index")
            if isinstance(idx, int):
                by_index[idx] = step

    # Add their results (overwrite ours if newer)
    for step in theirs:
        if isinstance(step, dict):
            idx = step.get("step_index")
            if isinstance(idx, int):
                existing = by_index.get(idx)
                if existing:
                    # Compare timestamps
                    existing_time = existing.get("finished_at", "")
                    new_time = step.get("finished_at", "")
                    if new_time > existing_time:
                        by_index[idx] = step
                else:
                    by_index[idx] = step

    # Sort by step_index
    sorted_results = [by_index[i] for i in sorted(by_index.keys())]
    return sorted_results


# =============================================================================
# Memory Merging
# =============================================================================

def merge_memory(
    base: Dict[str, Any],
    ours: Dict[str, Any],
    theirs: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge memory from concurrent updates.

    Strategy:
    - summary: use most recent by updated_at
    - decisions: union and dedupe
    - open_questions: union and dedupe
    - next_actions: union and dedupe

    Args:
        base: Original memory
        ours: Our updates
        theirs: Their updates

    Returns:
        Merged memory
    """
    result = dict(base)

    # Merge summary: use most recent
    ours_time = ours.get("updated_at", "")
    theirs_time = theirs.get("updated_at", "")

    if theirs_time > ours_time:
        result["summary"] = theirs.get("summary", ours.get("summary", ""))
    else:
        result["summary"] = ours.get("summary", theirs.get("summary", ""))

    # Merge decisions: union
    all_decisions = []
    for mem in [base, ours, theirs]:
        decisions = mem.get("decisions", [])
        if isinstance(decisions, list):
            all_decisions.extend(decisions)

    seen = set()
    unique_decisions = []
    for d in all_decisions:
        if isinstance(d, str) and d not in seen:
            seen.add(d)
            unique_decisions.append(d)
    result["decisions"] = unique_decisions[:10]  # Limit

    # Merge open_questions: union
    all_questions = []
    for mem in [base, ours, theirs]:
        questions = mem.get("open_questions", [])
        if isinstance(questions, list):
            all_questions.extend(questions)

    seen = set()
    unique_questions = []
    for q in all_questions:
        if isinstance(q, str) and q not in seen:
            seen.add(q)
            unique_questions.append(q)
    result["open_questions"] = unique_questions[:10]  # Limit

    # Merge next_actions: union
    all_actions = []
    for mem in [base, ours, theirs]:
        actions = mem.get("next_actions", [])
        if isinstance(actions, list):
            all_actions.extend(actions)

    seen = set()
    unique_actions = []
    for a in all_actions:
        if isinstance(a, str) and a not in seen:
            seen.add(a)
            unique_actions.append(a)
    result["next_actions"] = unique_actions[:10]  # Limit

    # Update metadata
    result["updated_at"] = _now_iso()
    if theirs_time > ours_time:
        result["version"] = theirs.get("version", ours.get("version", 1))
    else:
        result["version"] = ours.get("version", theirs.get("version", 1))

    return result


# =============================================================================
# Schedule Merging
# =============================================================================

def merge_schedule(
    base: Dict[str, Any],
    ours: Dict[str, Any],
    theirs: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge schedule from concurrent updates.

    Strategy:
    - Use highest retry_count
    - Use earliest next_retry_at
    - Clear lock if either side cleared it

    Args:
        base: Original schedule
        ours: Our updates
        theirs: Their updates

    Returns:
        Merged schedule
    """
    result = dict(base)

    # Use highest retry_count
    ours_count = ours.get("retry_count", 0)
    theirs_count = theirs.get("retry_count", 0)
    result["retry_count"] = max(ours_count, theirs_count)

    # Use earliest next_retry_at
    ours_retry = ours.get("next_retry_at")
    theirs_retry = theirs.get("next_retry_at")

    if ours_retry and theirs_retry:
        result["next_retry_at"] = min(ours_retry, theirs_retry)
    elif ours_retry:
        result["next_retry_at"] = ours_retry
    elif theirs_retry:
        result["next_retry_at"] = theirs_retry

    # Clear lock if either side cleared it
    ours_locked = ours.get("locked_by")
    theirs_locked = theirs.get("locked_by")

    if not ours_locked or not theirs_locked:
        # If either side cleared the lock, keep it cleared
        result["locked_by"] = None
        result["locked_at"] = None
    else:
        result["locked_by"] = theirs_locked
        result["locked_at"] = theirs.get("locked_at")

    return result


# =============================================================================
# Recovery Merging
# =============================================================================

def merge_recovery(
    base: Dict[str, Any],
    ours: Dict[str, Any],
    theirs: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge recovery from concurrent updates.

    Strategy:
    - Use highest recovery_count
    - Use most recent recovered_at

    Args:
        base: Original recovery
        ours: Our updates
        theirs: Their updates

    Returns:
        Merged recovery
    """
    result = dict(base)

    # Use highest recovery_count
    ours_count = ours.get("recovery_count", 0)
    theirs_count = theirs.get("recovery_count", 0)
    result["recovery_count"] = max(ours_count, theirs_count)

    # Use most recent recovered_at
    ours_time = ours.get("recovered_at", "")
    theirs_time = theirs.get("recovered_at", "")

    if theirs_time > ours_time:
        result["recovered_at"] = theirs_time
        result["last_recovery_reason"] = theirs.get("last_recovery_reason")
    elif ours_time:
        result["recovered_at"] = ours_time
        result["last_recovery_reason"] = ours.get("last_recovery_reason")

    return result


# =============================================================================
# Full Task Merge
# =============================================================================

def merge_task_states(
    base: Dict[str, Any],
    ours: Dict[str, Any],
    theirs: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge two concurrent updates to a task.

    Args:
        base: Original task state
        ours: Our updates
        theirs: Their updates

    Returns:
        Merged task state
    """
    result = dict(base)

    # Resolve status conflict
    statuses = [
        base.get("status", "pending"),
        ours.get("status", "pending"),
        theirs.get("status", "pending"),
    ]
    result["status"] = resolve_status_conflict(statuses)

    # Merge step_results
    base_steps = base.get("step_results", [])
    ours_steps = ours.get("step_results", [])
    theirs_steps = theirs.get("step_results", [])
    result["step_results"] = merge_step_results(base_steps, ours_steps, theirs_steps)

    # Merge memory
    base_mem = base.get("memory", {})
    ours_mem = ours.get("memory", {})
    theirs_mem = theirs.get("memory", {})
    result["memory"] = merge_memory(base_mem, ours_mem, theirs_mem)

    # Merge schedule
    base_sched = base.get("schedule", {})
    ours_sched = ours.get("schedule", {})
    theirs_sched = theirs.get("schedule", {})
    result["schedule"] = merge_schedule(base_sched, ours_sched, theirs_sched)

    # Merge recovery
    base_rec = base.get("recovery", {})
    ours_rec = ours.get("recovery", {})
    theirs_rec = theirs.get("recovery", {})
    result["recovery"] = merge_recovery(base_rec, ours_rec, theirs_rec)

    # Merge execution
    ours_exec = ours.get("execution", {})
    theirs_exec = theirs.get("execution", {})

    # Use highest current_step_index
    ours_idx = ours_exec.get("current_step_index", 0)
    theirs_idx = theirs_exec.get("current_step_index", 0)
    result["execution"] = dict(base.get("execution", {}))
    result["execution"]["current_step_index"] = max(ours_idx, theirs_idx)
    result["execution"]["completed_steps"] = len([
        s for s in result["step_results"]
        if isinstance(s, dict) and s.get("status") == "ok"
    ])

    # Bump revision
    result["revision"] = max(
        base.get("revision", 1),
        ours.get("revision", 1),
        theirs.get("revision", 1),
    ) + 1

    # Update timestamps
    result["updated_at"] = _now_iso()

    return result


def safe_update_task(
    task_path: Path,
    update_fn,
    *args,
    **kwargs,
) -> Tuple[Dict[str, Any], bool]:
    """Safely update a task with conflict handling.

    Reads current state, applies update, handles conflicts.

    Args:
        task_path: Path to task JSON
        update_fn: Function to apply (receives task, returns updated task)
        *args, **kwargs: Additional arguments for update_fn

    Returns:
        Tuple of (updated_task, success)
    """
    # Load current state
    current = _load_task(task_path)
    if not current:
        return {}, False

    base_revision = current.get("revision", 1)

    # Apply update
    try:
        updated = update_fn(current, *args, **kwargs)
    except Exception:
        return current, False

    # Ensure revision is bumped
    updated = _ensure_revision(updated)
    if updated.get("revision", 1) <= base_revision:
        updated["revision"] = base_revision + 1

    # Write atomically
    _atomic_write_json(task_path, updated)

    return updated, True
