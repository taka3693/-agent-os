from __future__ import annotations

from pathlib import Path
from typing import Optional

from ops.approval_decision_view import apply_approval_decision_view
from ops.approval_queue_view import render_pending_approvals


def get_pending_approvals_text(state_root: Path, limit: int | None = None) -> dict:
    text = render_pending_approvals(state_root, limit=limit)
    return {"ok": True, "mode": "list", "text": text}


def apply_pending_approval_text(
    state_root: Path,
    *,
    timestamp: str,
    fingerprint: str,
    decision: str,
    reason: Optional[str] = None,
    source: str = "manual_review",
) -> dict:
    out = apply_approval_decision_view(
        state_root,
        timestamp=timestamp,
        fingerprint=fingerprint,
        decision=decision,
        reason=reason,
        source=source,
    )
    return {"mode": "decision", **out}
