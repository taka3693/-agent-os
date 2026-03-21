from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ops.approval_facade import apply_approval, get_approval_status


def run_approval_ops(
    *,
    state_root: Path,
    mode: str,
    timestamp: Optional[str] = None,
    fingerprint: Optional[str] = None,
    decision: Optional[str] = None,
    reason: Optional[str] = None,
    pending_limit: int | None = None,
    decision_limit: int | None = None,
) -> Dict[str, Any]:
    if mode == "status":
        out = get_approval_status(
            state_root,
            pending_limit=pending_limit,
            decision_limit=decision_limit,
        )
        out["reply_text"] = out["text"]
        return out

    if mode == "apply":
        if timestamp is None or fingerprint is None or decision is None:
            return {
                "ok": False,
                "mode": "decision",
                "status": "invalid_args",
                "reply_text": "approval apply: invalid_args",
            }
        out = apply_approval(
            state_root,
            timestamp=timestamp,
            fingerprint=fingerprint,
            decision=decision,
            reason=reason,
        )
        out["reply_text"] = out["text"]
        return out

    return {
        "ok": False,
        "status": "invalid_mode",
        "mode": mode,
        "reply_text": f"approval: invalid_mode ({mode})",
    }
