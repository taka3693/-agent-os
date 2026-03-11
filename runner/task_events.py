#!/usr/bin/env python3
"""Step101: Task Events & Metrics

Lightweight observability layer that records structured events
and aggregated metrics inside the task state dict.

- Events are appended to task["events"] (capped list)
- Metrics are maintained in task["metrics"] (counter dict)
- No external dependencies — pure in-process bookkeeping
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Event constants
# ---------------------------------------------------------------------------
MAX_EVENTS = 50  # ring-buffer cap per task


# ---------------------------------------------------------------------------
# Init helpers
# ---------------------------------------------------------------------------

def init_metrics() -> Dict[str, int]:
    """Return a zero-valued metrics dict."""
    return {
        "total_steps": 0,
        "failed_steps": 0,
        "partial_runs": 0,
        "recovery_count": 0,
        "retry_count": 0,
        "orchestration_runs": 0,
        "worker_runs": 0,
        "budget_limit_hits": 0,
        "total_duration_ms": 0,
    }


def _ensure_events(task: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure task has an events list."""
    task = dict(task)
    if "events" not in task or not isinstance(task.get("events"), list):
        task["events"] = []
    return task


def _ensure_metrics(task: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure task has a metrics dict with all keys."""
    task = dict(task)
    if "metrics" not in task or not isinstance(task.get("metrics"), dict):
        task["metrics"] = init_metrics()
    else:
        defaults = init_metrics()
        for key, value in defaults.items():
            if key not in task["metrics"]:
                task["metrics"][key] = value
    return task


def ensure_observability(task: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure task has both events and metrics sections."""
    task = _ensure_events(task)
    task = _ensure_metrics(task)
    return task


# ---------------------------------------------------------------------------
# Record an event
# ---------------------------------------------------------------------------

def record_event(
    task: Dict[str, Any],
    event_type: str,
    *,
    step_id: Optional[str] = None,
    subtask_id: Optional[str] = None,
    status_before: Optional[str] = None,
    status_after: Optional[str] = None,
    reason: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Append a structured event to task["events"].

    Args:
        task: Task dict (mutated in-place for efficiency, but also returned)
        event_type: e.g. "status_change", "step_error", "recovery",
                    "budget_limit", "orchestration_start", "worker_complete"
        step_id: Optional step identifier
        subtask_id: Optional subtask identifier
        status_before: Status before the event
        status_after: Status after the event
        reason: Human-readable reason
        source: Component that emitted the event

    Returns:
        task (same reference, updated)
    """
    task = _ensure_events(task)
    event: Dict[str, Any] = {
        "event_type": event_type,
        "timestamp": _now_iso(),
        "task_id": task.get("task_id"),
    }
    if step_id is not None:
        event["step_id"] = step_id
    if subtask_id is not None:
        event["subtask_id"] = subtask_id
    if status_before is not None:
        event["status_before"] = status_before
    if status_after is not None:
        event["status_after"] = status_after
    if reason is not None:
        event["reason"] = reason
    if source is not None:
        event["source"] = source

    task["events"].append(event)

    # Cap
    if len(task["events"]) > MAX_EVENTS:
        task["events"] = task["events"][-MAX_EVENTS:]

    return task


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def increment_metric(
    task: Dict[str, Any],
    key: str,
    amount: int = 1,
) -> Dict[str, Any]:
    """Increment a single metric counter."""
    task = _ensure_metrics(task)
    task["metrics"][key] = task["metrics"].get(key, 0) + amount
    return task


def set_metric(
    task: Dict[str, Any],
    key: str,
    value: int,
) -> Dict[str, Any]:
    """Set a metric to an absolute value."""
    task = _ensure_metrics(task)
    task["metrics"][key] = value
    return task


def get_metric(task: Dict[str, Any], key: str) -> int:
    """Read a metric value (0 if missing)."""
    return task.get("metrics", {}).get(key, 0)


def get_events(task: Dict[str, Any], event_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return events, optionally filtered by type."""
    events = task.get("events", [])
    if event_type:
        return [e for e in events if e.get("event_type") == event_type]
    return list(events)


# ---------------------------------------------------------------------------
# Convenience: compute metrics from task state
# ---------------------------------------------------------------------------

def compute_metrics_from_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute metrics from current task state (idempotent snapshot).

    This reads step_results, orchestration, budget, recovery, etc. and
    produces a metrics dict.  It does NOT mutate the task.
    """
    m = init_metrics()

    # Steps
    step_results = task.get("step_results", [])
    m["total_steps"] = len(step_results)
    m["failed_steps"] = sum(
        1 for s in step_results
        if isinstance(s, dict) and s.get("status") in ("error", "failed")
    )

    # Recovery
    recovery = task.get("recovery", {})
    m["recovery_count"] = recovery.get("recovery_count", 0)

    # Retries
    schedule = task.get("schedule", {})
    m["retry_count"] = schedule.get("retry_count", 0)

    # Orchestration
    orch = task.get("orchestration", {})
    if orch.get("role") == "coordinator":
        m["orchestration_runs"] = 1
    m["worker_runs"] = orch.get("subtask_count", 0)

    # Budget
    budget = task.get("budget", {})
    if budget.get("limit_reached_reason"):
        m["budget_limit_hits"] = 1

    # Partial runs
    status = task.get("status")
    if status == "partial":
        m["partial_runs"] = 1

    # Duration
    started = task.get("started_at", "")
    finished = task.get("finished_at", "")
    if started and finished:
        try:
            from datetime import datetime as _dt
            s = _dt.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            f = _dt.strptime(finished, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            m["total_duration_ms"] = max(0, int((f - s).total_seconds() * 1000))
        except (ValueError, TypeError):
            pass

    return m
