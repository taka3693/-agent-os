from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


TASK_STATES = ("queued", "running", "awaiting_approval", "completed", "failed")


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
