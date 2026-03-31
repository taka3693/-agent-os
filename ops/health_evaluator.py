from __future__ import annotations

from typing import Any, Dict, List


def _safe_int(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return max(n, 0)


def evaluate_health_snapshot(
    snapshot: Dict[str, Any],
    *,
    session_warn_bytes: int = 5_000_000,
    failed_task_warn_count: int = 3,
    awaiting_approval_warn_count: int = 3,
) -> Dict[str, Any]:
    tasks = snapshot.get("tasks", {})
    task_counts = tasks.get("counts", {}) or {}
    sessions = snapshot.get("sessions", {}) or {}

    failed_count = _safe_int(task_counts.get("failed", 0))
    awaiting_count = _safe_int(task_counts.get("awaiting_approval", 0))
    largest_bytes = _safe_int(sessions.get("largest_bytes", 0))
    top_sessions = sessions.get("top", []) or []

    signals: List[str] = []
    risks: List[Dict[str, Any]] = []
    recommended_actions: List[Dict[str, Any]] = []

    health_score = 100

    if largest_bytes >= session_warn_bytes:
        signals.append("session_context_growth_detected")
        health_score -= 20

        target_basename = None
        if top_sessions and isinstance(top_sessions[0], dict):
            target_basename = top_sessions[0].get("basename")

        risks.append(
            {
                "code": "session_oversize",
                "level": "medium",
                "target": target_basename,
                "details": {
                    "largest_bytes": largest_bytes,
                    "threshold": session_warn_bytes,
                },
            }
        )

        if target_basename:
            recommended_actions.append(
                {
                    "action": "session.archive",
                    "args": {"target_basename": target_basename},
                    "reason": "largest session exceeds warning threshold",
                }
            )

    if failed_count >= failed_task_warn_count:
        signals.append("failed_tasks_accumulating")
        health_score -= 25

        risks.append(
            {
                "code": "failed_tasks_backlog",
                "level": "medium",
                "target": "tasks.failed",
                "details": {
                    "count": failed_count,
                    "threshold": failed_task_warn_count,
                },
            }
        )

    if awaiting_count >= awaiting_approval_warn_count:
        signals.append("approval_queue_backlog")
        health_score -= 15

        risks.append(
            {
                "code": "approval_backlog",
                "level": "low",
                "target": "tasks.awaiting_approval",
                "details": {
                    "count": awaiting_count,
                    "threshold": awaiting_approval_warn_count,
                },
            }
        )

    if not signals:
        signals.append("healthy")

    if health_score < 0:
        health_score = 0

    return {
        "health_score": health_score,
        "signals": signals,
        "risks": risks,
        "recommended_actions": recommended_actions,
    }
