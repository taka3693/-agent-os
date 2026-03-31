from __future__ import annotations

from pathlib import Path

from ops.approval_queue_formatter import format_pending_approvals
from ops.approval_queue_reader import list_pending_approvals


def render_pending_approvals(state_root: Path, limit: int | None = None) -> str:
    rows = list_pending_approvals(state_root, limit=limit)
    return format_pending_approvals(rows)
