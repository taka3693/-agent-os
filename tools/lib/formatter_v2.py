from __future__ import annotations

from datetime import datetime
from typing import Any, Dict


def build_task_id(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"task-{now.strftime('%Y%m%d%H%M%S')}"


def format_router_result(
    selected_skill: str = "decision",
    status: str = "completed",
    task_id: str | None = None,
) -> str:
    task_id = task_id or build_task_id()
    return (
        "router 受付完了\n"
        f"skill: {selected_skill}\n"
        f"status: {status}\n"
        f"task: {task_id}\n"
        f"bridge: selected_skill={selected_skill} status={status}"
    )


def format_router_result_from_payload(payload: Dict[str, Any]) -> str:
    return format_router_result(
        selected_skill=str(payload.get("selected_skill") or payload.get("skill") or "decision"),
        status=str(payload.get("status") or "completed"),
        task_id=str(payload.get("task_id") or build_task_id()),
    )


def render_router_summary(payload: Dict[str, Any]) -> str:
    return format_router_result_from_payload(payload)
