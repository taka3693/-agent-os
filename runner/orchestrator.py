#!/usr/bin/env python3
"""Step99/100: Multi-Agent Orchestrator with Budget Control

Provides coordinator + limited workers orchestration:
- Coordinator decomposes a task into bounded subtasks
- Workers execute only their assigned subtask
- Coordinator merges worker results into final output
- Enforces max_workers_per_task and max_orchestration_depth
- Step100: budget guardrails (subtask count, worker runs, retries, duration)
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.state_merge import (
    merge_task_states,
    bump_revision,
    _now_iso,
    _now_utc,
    _atomic_write_json,
)
from runner.task_events import (
    ensure_observability,
    record_event,
    increment_metric,
)

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
DEFAULT_MAX_WORKERS_PER_TASK = 3
MAX_ORCHESTRATION_DEPTH = 1  # no nested orchestration
MAX_SUBTASKS = 5  # hard ceiling on decomposition


# ---------------------------------------------------------------------------
# Budget defaults
# ---------------------------------------------------------------------------
DEFAULT_BUDGET_MAX_SUBTASKS = 5
DEFAULT_BUDGET_MAX_WORKER_RUNS = 10
DEFAULT_BUDGET_MAX_RETRIES_TOTAL = 6
DEFAULT_BUDGET_MAX_DURATION_SECONDS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
ROLE_COORDINATOR = "coordinator"
ROLE_WORKER = "worker"


# ---------------------------------------------------------------------------
# Budget helpers
# ---------------------------------------------------------------------------

def init_budget(
    max_subtasks: int = DEFAULT_BUDGET_MAX_SUBTASKS,
    max_worker_runs: int = DEFAULT_BUDGET_MAX_WORKER_RUNS,
    max_retries_total: int = DEFAULT_BUDGET_MAX_RETRIES_TOTAL,
    max_duration_seconds: int = DEFAULT_BUDGET_MAX_DURATION_SECONDS,
) -> Dict[str, Any]:
    """Create a fresh budget dict."""
    return {
        "max_subtasks": max_subtasks,
        "max_worker_runs": max_worker_runs,
        "max_retries_total": max_retries_total,
        "max_duration_seconds": max_duration_seconds,
        "spent_subtasks": 0,
        "spent_worker_runs": 0,
        "spent_retries_total": 0,
        "started_budget_at": None,
        "limit_reached_reason": None,
    }


def _ensure_budget(task: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure task has a budget section with defaults."""
    task = dict(task)
    if "budget" not in task or not isinstance(task.get("budget"), dict):
        task["budget"] = init_budget()
    else:
        defaults = init_budget()
        for key, value in defaults.items():
            if key not in task["budget"]:
                task["budget"][key] = value
    return task


def _budget_start_clock(task: Dict[str, Any]) -> Dict[str, Any]:
    """Start the duration clock if not already started."""
    task = dict(task)
    task["budget"] = dict(task.get("budget", {}))
    if not task["budget"].get("started_budget_at"):
        task["budget"]["started_budget_at"] = _now_iso()
    return task


def _check_budget_subtasks(budget: Dict[str, Any], needed: int) -> Optional[str]:
    """Return reason string if subtask budget would be exceeded, else None."""
    spent = budget.get("spent_subtasks", 0)
    limit = budget.get("max_subtasks", DEFAULT_BUDGET_MAX_SUBTASKS)
    if spent + needed > limit:
        return f"max_subtasks exceeded: spent={spent} + needed={needed} > limit={limit}"
    return None


def _check_budget_worker_runs(budget: Dict[str, Any], needed: int = 1) -> Optional[str]:
    spent = budget.get("spent_worker_runs", 0)
    limit = budget.get("max_worker_runs", DEFAULT_BUDGET_MAX_WORKER_RUNS)
    if spent + needed > limit:
        return f"max_worker_runs exceeded: spent={spent} + needed={needed} > limit={limit}"
    return None


def _check_budget_retries(budget: Dict[str, Any], needed: int = 1) -> Optional[str]:
    spent = budget.get("spent_retries_total", 0)
    limit = budget.get("max_retries_total", DEFAULT_BUDGET_MAX_RETRIES_TOTAL)
    if spent + needed > limit:
        return f"max_retries_total exceeded: spent={spent} + needed={needed} > limit={limit}"
    return None


def _check_budget_duration(budget: Dict[str, Any]) -> Optional[str]:
    started = budget.get("started_budget_at")
    if not started:
        return None
    limit = budget.get("max_duration_seconds", DEFAULT_BUDGET_MAX_DURATION_SECONDS)
    try:
        started_dt = datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return None
    elapsed = (_now_utc() - started_dt).total_seconds()
    if elapsed > limit:
        return f"max_duration_seconds exceeded: elapsed={elapsed:.1f}s > limit={limit}s"
    return None


def _set_limit_reached(task: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Record why budget was exhausted and set status."""
    task = dict(task)
    old_status = task.get("status")
    task["budget"] = dict(task.get("budget", {}))
    task["budget"]["limit_reached_reason"] = reason
    task["status"] = "failed"
    task["finished_at"] = _now_iso()
    task = record_event(
        task, "budget_limit",
        status_before=old_status, status_after="failed",
        reason=reason, source="orchestrator",
    )
    task = increment_metric(task, "budget_limit_hits")
    return task


# ---------------------------------------------------------------------------
# Subtask schema
# ---------------------------------------------------------------------------

def create_subtask(
    subtask_id: str,
    parent_task_id: str,
    query: str,
    skill: str,
    subtask_index: int,
) -> Dict[str, Any]:
    """Create a subtask dict assigned to a worker."""
    return {
        "subtask_id": subtask_id,
        "parent_task_id": parent_task_id,
        "subtask_index": subtask_index,
        "role": ROLE_WORKER,
        "status": "queued",
        "query": query,
        "skill": skill,
        "created_at": _now_iso(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Coordinator: decompose
# ---------------------------------------------------------------------------

def decompose_task(
    task: Dict[str, Any],
    decompose_fn: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
    max_subtasks: int = MAX_SUBTASKS,
) -> List[Dict[str, Any]]:
    """Coordinator decomposes a task into subtasks.

    Args:
        task: Parent task
        decompose_fn: User-supplied function (task -> list of dicts)
        max_subtasks: Hard ceiling

    Returns:
        List of subtask dicts (capped at max_subtasks)
    """
    task_id = task.get("task_id", "unknown")
    raw_specs = decompose_fn(task)

    if not isinstance(raw_specs, list):
        raw_specs = []

    specs = raw_specs[:max_subtasks]

    subtasks: List[Dict[str, Any]] = []
    for i, spec in enumerate(specs):
        if not isinstance(spec, dict):
            continue
        subtask_id = f"{task_id}-sub-{i}"
        subtasks.append(
            create_subtask(
                subtask_id=subtask_id,
                parent_task_id=task_id,
                query=spec.get("query", ""),
                skill=spec.get("skill", "research"),
                subtask_index=i,
            )
        )

    return subtasks


# ---------------------------------------------------------------------------
# Worker: execute a single subtask
# ---------------------------------------------------------------------------

def execute_subtask(
    subtask: Dict[str, Any],
    worker_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    """Worker executes its assigned subtask."""
    subtask = dict(subtask)
    subtask["started_at"] = _now_iso()

    try:
        result = worker_fn(subtask)
        if not isinstance(result, dict):
            result = {"raw": result}
        subtask["result"] = result
        subtask["status"] = "completed"
    except Exception as e:
        subtask["status"] = "failed"
        subtask["error"] = f"{type(e).__name__}: {e}"

    subtask["finished_at"] = _now_iso()
    return subtask


# ---------------------------------------------------------------------------
# Coordinator: merge results
# ---------------------------------------------------------------------------

def merge_subtask_results(
    task: Dict[str, Any],
    subtasks: List[Dict[str, Any]],
    merge_fn: Optional[Callable[[Dict[str, Any], List[Dict[str, Any]]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Coordinator merges worker results into the parent task."""
    task = dict(task)

    completed = [s for s in subtasks if s.get("status") == "completed"]
    failed = [s for s in subtasks if s.get("status") == "failed"]
    total = len(subtasks)

    if merge_fn:
        merged = merge_fn(task, subtasks)
        if isinstance(merged, dict):
            task["orchestration_result"] = merged
    else:
        task["orchestration_result"] = {
            "subtask_results": [
                {
                    "subtask_id": s.get("subtask_id"),
                    "status": s.get("status"),
                    "result": s.get("result"),
                    "error": s.get("error"),
                }
                for s in subtasks
            ],
        }

    # Determine parent status
    if len(failed) == total:
        task["status"] = "failed"
    elif failed:
        task["status"] = "partial"
    elif len(completed) == total:
        task["status"] = "completed"
    else:
        task["status"] = "partial"

    task["finished_at"] = _now_iso()

    orch = task.setdefault("orchestration", {})
    orch["role"] = ROLE_COORDINATOR
    orch["subtask_count"] = total
    orch["completed_count"] = len(completed)
    orch["failed_count"] = len(failed)
    orch["subtask_ids"] = [s.get("subtask_id") for s in subtasks]

    return task


# ---------------------------------------------------------------------------
# Full orchestration pipeline
# ---------------------------------------------------------------------------

def run_orchestration(
    task: Dict[str, Any],
    decompose_fn: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
    worker_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    merge_fn: Optional[Callable[[Dict[str, Any], List[Dict[str, Any]]], Dict[str, Any]]] = None,
    max_workers_per_task: int = DEFAULT_MAX_WORKERS_PER_TASK,
    max_orchestration_depth: int = MAX_ORCHESTRATION_DEPTH,
    task_path: Optional[Path] = None,
    budget: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run coordinator → workers → merge pipeline.

    Args:
        task: The parent task
        decompose_fn: Coordinator decomposition function
        worker_fn: Worker execution function
        merge_fn: Optional result merge function
        max_workers_per_task: Max concurrent workers
        max_orchestration_depth: Recursion depth limit
        task_path: Optional path to persist state
        budget: Optional budget overrides dict

    Returns:
        Final task state
    """
    task = dict(task)

    # --- Observability setup ---
    task = ensure_observability(task)

    # --- Budget setup ---
    task = _ensure_budget(task)
    if budget and isinstance(budget, dict):
        for k, v in budget.items():
            task["budget"][k] = v
    task = _budget_start_clock(task)

    # Check depth limit
    orch = task.get("orchestration", {})
    current_depth = orch.get("depth", 0)
    if current_depth >= max_orchestration_depth:
        task["status"] = "failed"
        task["error"] = (
            f"orchestration depth {current_depth} exceeds max {max_orchestration_depth}"
        )
        task["finished_at"] = _now_iso()
        return task

    # Check duration budget before starting
    reason = _check_budget_duration(task["budget"])
    if reason:
        return _set_limit_reached(task, reason)

    # Mark as coordinator
    task.setdefault("orchestration", {})
    task["orchestration"]["role"] = ROLE_COORDINATOR
    task["orchestration"]["depth"] = current_depth
    old_status = task.get("status")
    task["status"] = "running"
    task["started_at"] = _now_iso()
    task = record_event(
        task, "orchestration_start",
        status_before=old_status, status_after="running",
        source="orchestrator",
    )
    task = increment_metric(task, "orchestration_runs")

    if task_path:
        _atomic_write_json(task_path, task)

    # Phase 1: Decompose (respecting budget)
    budget_subtask_limit = task["budget"].get("max_subtasks", DEFAULT_BUDGET_MAX_SUBTASKS)
    already_spent = task["budget"].get("spent_subtasks", 0)
    remaining_subtask_budget = max(0, budget_subtask_limit - already_spent)

    effective_max_subtasks = min(MAX_SUBTASKS, remaining_subtask_budget)

    reason = _check_budget_subtasks(task["budget"], 1)
    if reason and remaining_subtask_budget == 0:
        return _set_limit_reached(task, reason)

    subtasks = decompose_task(task, decompose_fn, max_subtasks=effective_max_subtasks)

    # Re-check: actual count against budget
    if subtasks:
        reason = _check_budget_subtasks(task["budget"], len(subtasks))
        if reason:
            return _set_limit_reached(task, reason)
        task["budget"]["spent_subtasks"] = already_spent + len(subtasks)

    if not subtasks:
        task["status"] = "completed"
        task["orchestration_result"] = {"subtask_results": []}
        task["orchestration"]["subtask_count"] = 0
        task["finished_at"] = _now_iso()
        if task_path:
            _atomic_write_json(task_path, task)
        return task

    # Phase 2: Execute workers (parallel, capped)
    effective_workers = min(max_workers_per_task, len(subtasks))
    completed_subtasks: List[Dict[str, Any]] = []

    # Check worker runs budget
    reason = _check_budget_worker_runs(task["budget"], len(subtasks))
    if reason:
        return _set_limit_reached(task, reason)

    # Check duration before launching workers
    reason = _check_budget_duration(task["budget"])
    if reason:
        return _set_limit_reached(task, reason)

    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        futures = {
            executor.submit(execute_subtask, st, worker_fn): st
            for st in subtasks
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                completed_subtasks.append(result)
            except Exception as e:
                original = futures[future]
                original = dict(original)
                original["status"] = "failed"
                original["error"] = f"ThreadError: {e}"
                original["finished_at"] = _now_iso()
                completed_subtasks.append(original)

    # Update spent worker runs
    task["budget"]["spent_worker_runs"] = (
        task["budget"].get("spent_worker_runs", 0) + len(completed_subtasks)
    )
    task = increment_metric(task, "worker_runs", len(completed_subtasks))

    # Count retries (failed subtasks)
    failed_count = sum(1 for s in completed_subtasks if s.get("status") == "failed")
    task["budget"]["spent_retries_total"] = (
        task["budget"].get("spent_retries_total", 0) + failed_count
    )

    # Record per-worker events and failed_steps metric
    for st in completed_subtasks:
        task = record_event(
            task, "worker_complete",
            subtask_id=st.get("subtask_id"),
            status_after=st.get("status"),
            source="orchestrator",
        )
        if st.get("status") == "failed":
            task = increment_metric(task, "failed_steps")

    # Sort by subtask_index for deterministic merge
    completed_subtasks.sort(key=lambda s: s.get("subtask_index", 0))

    # Phase 3: Merge
    pre_merge_status = task.get("status")
    task = merge_subtask_results(task, completed_subtasks, merge_fn)

    # Record status change
    if task.get("status") != pre_merge_status:
        task = record_event(
            task, "status_change",
            status_before=pre_merge_status,
            status_after=task.get("status"),
            source="orchestrator",
        )
    if task.get("status") == "partial":
        task = increment_metric(task, "partial_runs")

    # total_steps
    task = increment_metric(
        task, "total_steps",
        len(completed_subtasks) - len(completed_subtasks),  # reset-safe: set below
    )
    from runner.task_events import set_metric
    task = set_metric(task, "total_steps", len(completed_subtasks))

    # Check if duration exceeded after execution
    reason = _check_budget_duration(task["budget"])
    if reason:
        task["budget"]["limit_reached_reason"] = reason
        # Don't override status if already set by merge — just record

    # Preserve memory
    if "memory" not in task:
        task["memory"] = {
            "summary": "",
            "decisions": [],
            "open_questions": [],
            "next_actions": [],
        }

    task = bump_revision(task)

    if task_path:
        _atomic_write_json(task_path, task)

    return task


# ---------------------------------------------------------------------------
# High-level: single-skill execution with automatic chain
# ---------------------------------------------------------------------------

def run_skill_with_chain(
    task: Dict[str, Any],
    task_path: Optional[Path] = None,
    budget: Optional[Dict[str, Any]] = None,
    max_chain: int = 3,
) -> Dict[str, Any]:
    """Execute a skill and automatically chain to next skills."""
    from runner.run_research_task import (
        determine_next_skill,
        build_next_query,
        run_selected_skill,
        MAX_CHAIN_COUNT,
    )
    
    task = dict(task)
    task = _ensure_budget(task)
    if budget and isinstance(budget, dict):
        for k, v in budget.items():
            task["budget"][k] = v

    chain_count = 0
    _max_chain = max_chain if max_chain else MAX_CHAIN_COUNT

    while chain_count <= _max_chain:
        skill = task.get("selected_skill", "research")
        query = task.get("query") or task.get("input_text", "")

        def _decompose(_t: Dict[str, Any], _q: str = query, _s: str = skill) -> List[Dict[str, Any]]:
            return [{"query": _q, "skill": _s}]

        def _worker(subtask: Dict[str, Any]) -> Dict[str, Any]:
            return run_selected_skill(subtask["skill"], subtask["query"])

        task = run_orchestration(
            task=task,
            decompose_fn=_decompose,
            worker_fn=_worker,
            task_path=task_path,
            budget=task.get("budget"),
        )

        orch = task.get("orchestration_result", {})
        sub_results = orch.get("subtask_results", [])
        result = sub_results[0].get("result", {}) if sub_results else {}

        next_skill = determine_next_skill(skill, result)
        if next_skill is None:
            break

        chain_count += 1
        next_query = build_next_query(skill, task, result)

        task.setdefault("chain_history", []).append({
            "skill": skill,
            "chain_index": chain_count - 1,
        })

        task["selected_skill"] = next_skill
        task["query"] = next_query
        task["status"] = "queued"

    task["chain_count"] = chain_count
    return task
