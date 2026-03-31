from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ops.approval_queue_service import get_pending_approvals_view


def get_pending_approvals_payload(
    state_root: Path,
    limit: int | None = None,
) -> Dict[str, Any]:
    view = get_pending_approvals_view(state_root, limit=limit)
    return {
        "ok": True,
        "count": view["count"],
        "items": view["rows"],
        "text": view["text"],
    }
