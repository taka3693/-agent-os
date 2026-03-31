from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ops.approval_decision_apply import apply_approval_decision
from ops.approval_decision_reader import list_approval_decisions
from ops.approval_queue_reader import list_pending_approvals


def apply_approval_decision_payload(
    state_root: Path,
    *,
    timestamp: str,
    fingerprint: str,
    decision: str,
    reason: Optional[str] = None,
    source: str = "manual_review",
    pending_limit: int | None = None,
    decision_limit: int | None = None,
) -> Dict[str, Any]:
    result = apply_approval_decision(
        state_root,
        timestamp=timestamp,
        fingerprint=fingerprint,
        decision=decision,
        reason=reason,
        source=source,
    )
    if not result["ok"]:
        return result

    pending_items = list_pending_approvals(state_root, limit=pending_limit)
    decision_items = list_approval_decisions(state_root, limit=decision_limit)
    return {
        **result,
        "pending_count": len(pending_items),
        "pending_items": pending_items,
        "decision_count": len(decision_items),
        "decision_items": decision_items,
    }
