from __future__ import annotations

from pathlib import Path
from typing import Optional

from ops.approval_decision_view import apply_approval_decision_view
from ops.approval_status_view import render_approval_status


def get_approval_status(
    state_root: Path,
    *,
    pending_limit: int | None = None,
    decision_limit: int | None = None,
) -> dict:
    return {
        "ok": True,
        "mode": "status",
        **render_approval_status(
            state_root,
            pending_limit=pending_limit,
            decision_limit=decision_limit,
        ),
    }


def apply_approval(
    state_root: Path,
    *,
    timestamp: str,
    fingerprint: str,
    decision: str,
    reason: Optional[str] = None,
    source: str = "manual_review",
) -> dict:
    return {
        "mode": "decision",
        **apply_approval_decision_view(
            state_root,
            timestamp=timestamp,
            fingerprint=fingerprint,
            decision=decision,
            reason=reason,
            source=source,
        ),
    }
