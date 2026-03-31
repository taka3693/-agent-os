"""Retry State - リトライ状態の一元管理

3箇所に分散していたリトライ管理を統合:
- orchestrator.py: spent_retries_total (ワーカー失敗)
- task_scheduler.py: schedule.retry_count (再スケジュール)  
- task_recovery.py: recovery.recovery_count (復旧)
"""
from __future__ import annotations

from typing import Any, Dict


def _init_retry_state() -> Dict[str, Any]:
    """Initialize unified retry state."""
    return {
        "worker_retries": 0,      # ワーカー実行失敗
        "schedule_retries": 0,    # 再スケジュール
        "recovery_retries": 0,    # 復旧
        "total_retries": 0,       # 合計
        "max_total_retries": 10,  # 合計上限
        "last_retry_reason": None,
        "last_retry_at": None,
    }


def ensure_retry_state(task: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure task has unified retry_state section."""
    task = dict(task)
    if "retry_state" not in task or not isinstance(task.get("retry_state"), dict):
        task["retry_state"] = _init_retry_state()
    else:
        defaults = _init_retry_state()
        for key, value in defaults.items():
            if key not in task["retry_state"]:
                task["retry_state"][key] = value
    return task


def can_retry(task: Dict[str, Any]) -> bool:
    """Check if task can be retried based on unified state."""
    task = ensure_retry_state(task)
    state = task["retry_state"]
    return state["total_retries"] < state["max_total_retries"]


def increment_retry(
    task: Dict[str, Any],
    *,
    category: str,  # "worker" | "schedule" | "recovery"
    reason: str | None = None,
    timestamp: str | None = None,
) -> Dict[str, Any]:
    """Increment retry count for specific category and update total."""
    from datetime import datetime, timezone
    
    task = ensure_retry_state(task)
    state = task["retry_state"]
    
    # カテゴリ別カウント
    key = f"{category}_retries"
    if key in state:
        state[key] = state.get(key, 0) + 1
    
    # 合計更新
    state["total_retries"] = (
        state.get("worker_retries", 0) +
        state.get("schedule_retries", 0) +
        state.get("recovery_retries", 0)
    )
    
    state["last_retry_reason"] = reason
    state["last_retry_at"] = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    return task


def get_retry_summary(task: Dict[str, Any]) -> Dict[str, Any]:
    """Get summary of retry state for logging/display."""
    task = ensure_retry_state(task)
    state = task["retry_state"]
    return {
        "worker": state.get("worker_retries", 0),
        "schedule": state.get("schedule_retries", 0),
        "recovery": state.get("recovery_retries", 0),
        "total": state.get("total_retries", 0),
        "max": state.get("max_total_retries", 10),
        "can_retry": can_retry(task),
    }


def sync_from_legacy(task: Dict[str, Any]) -> Dict[str, Any]:
    """Sync retry_state from legacy fields (migration helper)."""
    task = ensure_retry_state(task)
    state = task["retry_state"]
    
    # orchestrator.py の spent_retries_total
    if "budget" in task and "spent_retries_total" in task["budget"]:
        state["worker_retries"] = task["budget"]["spent_retries_total"]
    
    # task_scheduler.py の schedule.retry_count
    if "schedule" in task and "retry_count" in task["schedule"]:
        state["schedule_retries"] = task["schedule"]["retry_count"]
    
    # task_recovery.py の recovery.recovery_count
    if "recovery" in task and "recovery_count" in task["recovery"]:
        state["recovery_retries"] = task["recovery"]["recovery_count"]
    
    # 合計再計算
    state["total_retries"] = (
        state.get("worker_retries", 0) +
        state.get("schedule_retries", 0) +
        state.get("recovery_retries", 0)
    )
    
    return task


def sync_to_legacy(task: Dict[str, Any]) -> Dict[str, Any]:
    """Sync retry_state back to legacy fields (backward compat)."""
    task = ensure_retry_state(task)
    state = task["retry_state"]
    
    # orchestrator.py
    if "budget" not in task:
        task["budget"] = {}
    task["budget"]["spent_retries_total"] = state.get("worker_retries", 0)
    
    # task_scheduler.py
    if "schedule" not in task:
        task["schedule"] = {}
    task["schedule"]["retry_count"] = state.get("schedule_retries", 0)
    
    # task_recovery.py
    if "recovery" not in task:
        task["recovery"] = {}
    task["recovery"]["recovery_count"] = state.get("recovery_retries", 0)
    
    return task
