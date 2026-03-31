from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ops.approval_queue_formatter import format_pending_approvals
from ops.approval_queue_reader import list_pending_approvals


def get_pending_approvals_view(state_root: Path, limit: int | None = None) -> Dict[str, Any]:
    rows = list_pending_approvals(state_root, limit=limit)
    return {
        "count": len(rows),
        "rows": rows,
        "text": format_pending_approvals(rows),
    }
