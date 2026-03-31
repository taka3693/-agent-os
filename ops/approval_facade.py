"""Approval Facade - 承認システムの公開API

統合元:
- 旧 approval_facade.py
- approval_ops_api.py
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ops.approval_decision import apply_approval_decision_view
from ops.approval_queue import render_pending_approvals
from ops.approval_status import render_approval_status


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
