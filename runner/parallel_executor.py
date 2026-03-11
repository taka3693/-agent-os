#!/usr/bin/env python3
"""Step97: Parallel Executor

Provides limited parallel execution for independent substeps:
- Detects parallel-safe substeps (no depends_on)
- Executes independent substeps in parallel
- Merges results using state_merge helper
- Respects max_parallel_workers limit
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.state_merge import (
    merge_task_states,
    bump_revision,
    _now_iso,
    _atomic_write_json,
)


# Default parallelism limit
DEFAULT_MAX_PARALLEL_WORKERS = 2


def effective_max_workers(
    scheduler_max_concurrent: int,
    current_running: int,
    max_parallel_workers: int = DEFAULT_MAX_PARALLEL_WORKERS,
) -> int:
    """Compute the effective worker count respecting the scheduler global limit.

    The parallel executor must not spawn more workers than the remaining
    global concurrency budget.  This function composes the two limits so
    the system never exceeds scheduler_max_concurrent tasks overall.

    Args:
        scheduler_max_concurrent: Global max_concurrent_tasks from scheduler
        current_running: Number of tasks already in 'running' status
        max_parallel_workers: Per-pipeline max workers

    Returns:
        Effective max workers (>= 1 when there is budget, 0 when exhausted)
    """
    remaining = max(0, scheduler_max_concurrent - current_running)
    return min(max_parallel_workers, remaining)


def analyze_step_dependencies(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze step dependencies and determine execution order.

    Args:
        steps: List of step definitions

    Returns:
        Dict with:
        - parallel_groups: List of step groups (each group can run in parallel)
        - serial_steps: List of steps that must run serially
    """
    if not steps:
        return {"parallel_groups": [], "serial_steps": []}

    # Build dependency graph
    step_ids = set()
    for i, step in enumerate(steps):
        step_id = step.get("step_id", f"step_{i}")
        step_ids.add(step_id)

    # Find steps without dependencies (parallel-safe)
    parallel_safe = []
    serial_required = []

    for i, step in enumerate(steps):
        step_id = step.get("step_id", f"step_{i}")
        depends_on = step.get("depends_on")

        if not depends_on:
            # No dependencies - can potentially run in parallel
            parallel_safe.append({
                "step_index": i,
                "step_id": step_id,
                "step": step,
            })
        else:
            # Has dependencies - must run serially
            serial_required.append({
                "step_index": i,
                "step_id": step_id,
                "step": step,
                "depends_on": depends_on,
            })

    # Group parallel-safe steps (limited by max workers)
    parallel_groups = []
    if parallel_safe:
        parallel_groups.append(parallel_safe)

    return {
        "parallel_groups": parallel_groups,
        "serial_steps": serial_required,
    }


def is_parallel_safe(step: Dict[str, Any]) -> bool:
    """Check if a step can be executed in parallel.

    Args:
        step: Step definition

    Returns:
        True if step is parallel-safe
    """
    return not step.get("depends_on")


def execute_step_with_context(
    step: Dict[str, Any],
    task: Dict[str, Any],
    step_fn: Callable,
    step_index: int,
) -> Dict[str, Any]:
    """Execute a single step with task context.

    Args:
        step: Step definition
        task: Current task state
        step_fn: Step execution function
        step_index: Step index

    Returns:
        Step result dict
    """
    started_at = _now_iso()
    start_time = time.time()

    step_result = {
        "step_index": step_index,
        "step_id": step.get("step_id", f"step_{step_index}"),
        "skill": step.get("skill", "unknown"),
        "status": "ok",
        "started_at": started_at,
        "finished_at": None,
        "duration_ms": None,
        "output": {},
        "error_type": None,
        "error_message": None,
        "thread_id": threading.current_thread().name,
    }

    try:
        output = step_fn(task, step)
        if not isinstance(output, dict):
            output = {"raw": output}
        step_result["output"] = output
        step_result["status"] = "ok"
    except Exception as e:
        step_result["status"] = "error"
        step_result["error_type"] = type(e).__name__
        step_result["error_message"] = str(e)

    finished_at = _now_iso()
    step_result["finished_at"] = finished_at
    step_result["duration_ms"] = int((time.time() - start_time) * 1000)

    return step_result


def execute_parallel_steps(
    task: Dict[str, Any],
    steps: List[Dict[str, Any]],
    step_fn: Callable,
    max_workers: int = DEFAULT_MAX_PARALLEL_WORKERS,
) -> Dict[str, Any]:
    """Execute parallel-safe steps concurrently.

    Args:
        task: Current task state
        steps: List of parallel-safe steps (with step_index and step_id)
        step_fn: Step execution function
        max_workers: Maximum parallel workers

    Returns:
        Updated task with step results
    """
    if not steps:
        return task

    task = dict(task)
    task["step_results"] = list(task.get("step_results", []))

    results = []
    errors = []

    # Execute in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for step_info in steps:
            # Handle both dict format and StepInfo objects
            if isinstance(step_info, dict):
                step_index = step_info.get("step_index", 0)
                step = step_info.get("step", step_info)
                step_id = step_info.get("step_id", step.get("step_id", f"step_{step_index}"))
            else:
                step_index = getattr(step_info, "step_index", 0)
                step = getattr(step_info, "step", step_info)
                step_id = getattr(step_info, "step_id", f"step_{step_index}")

            future = executor.submit(
                execute_step_with_context,
                step,
                task,
                step_fn,
                step_index,
            )
            futures[future] = {
                "step_index": step_index,
                "step_id": step_id,
            }

        # Collect results as they complete
        for future in as_completed(futures):
            step_info = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                # Handle unexpected errors
                error_result = {
                    "step_index": step_info["step_index"],
                    "step_id": step_info["step_id"],
                    "status": "error",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
                results.append(error_result)
                errors.append(error_result)

    # Sort results by step_index
    results.sort(key=lambda r: r.get("step_index", 0))

    # Append results to task
    for result in results:
        task["step_results"].append(result)

    return task


def run_parallel_pipeline(
    task: Dict[str, Any],
    steps: List[Dict[str, Any]],
    step_fn: Callable,
    max_parallel_workers: int = DEFAULT_MAX_PARALLEL_WORKERS,
    task_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run a pipeline with parallel execution for independent steps.

    Args:
        task: Initial task state
        steps: List of step definitions
        step_fn: Step execution function
        max_parallel_workers: Maximum parallel workers
        task_path: Optional path to save task state

    Returns:
        Final task state
    """
    if not steps:
        return task

    task = dict(task)
    task["step_results"] = list(task.get("step_results", []))

    # Analyze dependencies
    analysis = analyze_step_dependencies(steps)
    parallel_groups = analysis["parallel_groups"]
    serial_steps = analysis["serial_steps"]

    # Execute parallel groups first
    for group in parallel_groups:
        task = execute_parallel_steps(
            task,
            group,
            step_fn,
            max_parallel_workers,
        )

        # Save intermediate state if path provided
        if task_path:
            task = bump_revision(task)
            _atomic_write_json(task_path, task)

    # Execute serial steps
    for step_info in serial_steps:
        step_index = step_info["step_index"]
        step = step_info["step"]

        result = execute_step_with_context(step, task, step_fn, step_index)
        task["step_results"].append(result)

        # Check for errors
        if result.get("status") == "error":
            continue_on_error = step.get("continue_on_error", False)
            if not continue_on_error:
                # Stop on error
                break

        # Save intermediate state
        if task_path:
            task = bump_revision(task)
            _atomic_write_json(task_path, task)

    # Determine final status
    has_errors = any(
        r.get("status") == "error"
        for r in task.get("step_results", [])
    )
    all_completed = len(task["step_results"]) >= len(steps)

    if has_errors:
        if all_completed:
            task["status"] = "partial"
        else:
            task["status"] = "failed"
    elif all_completed:
        task["status"] = "completed"

    task["finished_at"] = _now_iso()
    task = bump_revision(task)

    if task_path:
        _atomic_write_json(task_path, task)

    return task
