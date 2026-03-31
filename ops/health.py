"""Health - システムヘルス監視の統合モジュール

統合元:
- health_store.py
- health_snapshot.py
- health_evaluator.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


TASK_STATES = ("queued", "running", "awaiting_approval", "completed", "failed")


# =============================================================================
# Store Layer (from health_store.py)
# =============================================================================

def _health_dir(state_root: Path) -> Path:
    return state_root / "health"


def ensure_health_dir(state_root: Path) -> Path:
    p = _health_dir(state_root)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _history_path(state_root: Path) -> Path:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return _health_dir(state_root) / f"history-{day}.jsonl"


def _latest_path(state_root: Path) -> Path:
    return _health_dir(state_root) / "latest.json"


def write_latest_health(state_root: Path, payload: Dict[str, Any]) -> Path:
    ensure_health_dir(state_root)
    path = _latest_path(state_root)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def append_health_history(state_root: Path, payload: Dict[str, Any]) -> Path:
    ensure_health_dir(state_root)
    path = _history_path(state_root)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


# =============================================================================
# Snapshot Layer (from health_snapshot.py)
# =============================================================================

@dataclass(frozen=True)
class SessionSizeEntry:
    basename: str
    bytes: int


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def count_task_files(tasks_root: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for state in TASK_STATES:
        p = tasks_root / state
        if not p.exists() or not p.is_dir():
            counts[state] = 0
            continue
        counts[state] = sum(1 for x in p.iterdir() if x.is_file())
    return counts


def normalize_session_sizes(raw: Optional[Iterable[Dict[str, Any]]]) -> List[SessionSizeEntry]:
    items: List[SessionSizeEntry] = []
    for row in raw or []:
        basename = str(row.get("basename") or "").strip()
        size = row.get("bytes", 0)
        if not basename:
            continue
        try:
            size_int = int(size)
        except (TypeError, ValueError):
            size_int = 0
        if size_int < 0:
            size_int = 0
        items.append(SessionSizeEntry(basename=basename, bytes=size_int))
    items.sort(key=lambda x: x.bytes, reverse=True)
    return items


def build_health_snapshot(
    *,
    tasks_root: Path,
    session_sizes: Optional[Iterable[Dict[str, Any]]] = None,
    gateway_status: Optional[Dict[str, Any]] = None,
    recent_log_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    task_counts = count_task_files(tasks_root)
    sessions = normalize_session_sizes(session_sizes)

    return {
        "timestamp": utc_now_iso(),
        "gateway": {
            "status": gateway_status or {},
            "recent_logs": recent_log_summary or {},
        },
        "tasks": {
            "counts": task_counts,
            "total": sum(task_counts.values()),
        },
        "sessions": {
            "count": len(sessions),
            "largest_bytes": sessions[0].bytes if sessions else 0,
            "top": [
                {"basename": x.basename, "bytes": x.bytes}
                for x in sessions[:5]
            ],
        },
    }


# =============================================================================
# Evaluator Layer (from health_evaluator.py)
# =============================================================================

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
