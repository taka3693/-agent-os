from __future__ import annotations

from pathlib import Path

from ops.approval_decision_formatter import format_approval_decisions
from ops.approval_decision_reader import list_approval_decisions
from ops.approval_queue_formatter import format_pending_approvals
from ops.approval_queue_reader import list_pending_approvals


def render_approval_status(
    state_root: Path,
    *,
    pending_limit: int | None = None,
    decision_limit: int | None = None,
) -> dict:
    pending_rows = list_pending_approvals(state_root, limit=pending_limit)
    decision_rows = list_approval_decisions(state_root, limit=decision_limit)

    pending_text = format_pending_approvals(pending_rows)
    decision_text = format_approval_decisions(decision_rows)

    return {
        "ok": True,
        "pending_count": len(pending_rows),
        "decision_count": len(decision_rows),
        "pending_text": pending_text,
        "decision_text": decision_text,
        "text": pending_text + "\n---\n" + decision_text,
    }
