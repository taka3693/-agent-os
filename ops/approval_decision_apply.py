from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ops.approval_decision_store import append_approval_decision
from ops.approval_queue_mutation import remove_pending_approval_by_fingerprint
from ops.approval_queue_reader import find_pending_approval_by_fingerprint
from ops.approval_validation import validate_approval_decision_input


def apply_approval_decision(
    state_root: Path,
    *,
    timestamp: str,
    fingerprint: str,
    decision: str,
    reason: Optional[str] = None,
    source: str = "manual_review",
) -> Dict[str, Any]:
    valid = validate_approval_decision_input(
        fingerprint=fingerprint,
        decision=decision,
    )
    if not valid["ok"]:
        return {
            "ok": False,
            "status": valid["status"],
            "fingerprint": fingerprint,
            "decision": decision,
        }

    row = find_pending_approval_by_fingerprint(state_root, fingerprint)
    if row is None:
        return {"ok": False, "status": "not_found", "fingerprint": fingerprint}

    append_approval_decision(
        state_root,
        timestamp=timestamp,
        fingerprint=fingerprint,
        decision=decision,
        action=row["action"],
        args=row.get("args", {}),
        reason=reason,
        source=source,
    )

    removal = remove_pending_approval_by_fingerprint(state_root, fingerprint)
    return {
        "ok": True,
        "status": "applied",
        "fingerprint": fingerprint,
        "decision": decision,
        "removed": removal["removed"],
    }
