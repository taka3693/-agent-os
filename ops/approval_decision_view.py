from __future__ import annotations

from pathlib import Path
from typing import Optional

from ops.approval_decision_api import apply_approval_decision_payload


def apply_approval_decision_view(
    state_root: Path,
    *,
    timestamp: str,
    fingerprint: str,
    decision: str,
    reason: Optional[str] = None,
    source: str = "manual_review",
) -> dict:
    out = apply_approval_decision_payload(
        state_root,
        timestamp=timestamp,
        fingerprint=fingerprint,
        decision=decision,
        reason=reason,
        source=source,
    )
    if not out["ok"]:
        out["text"] = f"承認決定失敗: status={out['status']} fp={fingerprint}"
        return out

    out["text"] = (
        f"承認決定: {decision}\n"
        f"fingerprint: {fingerprint}\n"
        f"pending_count: {out['pending_count']}\n"
        f"decision_count: {out['decision_count']}"
    )
    return out
