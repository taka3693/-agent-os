"""Approval Decision - 承認決定の全操作を統合

統合元:
- approval_decision_store.py
- approval_decision_reader.py
- approval_decision_formatter.py
- approval_decision_view.py
- approval_decision_api.py
- approval_decision_apply.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ops.approval_queue import (
    find_pending_approval_by_fingerprint,
    list_pending_approvals,
    remove_pending_approval_by_fingerprint,
)
from ops.approval_validation import validate_approval_decision_input


def approval_decision_log_path(state_root: Path) -> Path:
    return state_root / "approval_decisions.jsonl"


def append_approval_decision(
    state_root: Path,
    *,
    timestamp: str,
    fingerprint: str,
    decision: str,
    action: str,
    args: Dict[str, Any],
    reason: Optional[str] = None,
    source: Optional[str] = None,
) -> Path:
    path = approval_decision_log_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": timestamp,
        "fingerprint": fingerprint,
        "decision": decision,
        "action": action,
        "args": args,
        "reason": reason,
        "source": source,
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return path


def load_approval_decisions(state_root: Path) -> List[Dict[str, Any]]:
    path = approval_decision_log_path(state_root)
    if not path.exists():
        return []

    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


def list_approval_decisions(
    state_root: Path,
    limit: int | None = None,
) -> List[Dict[str, Any]]:
    rows = load_approval_decisions(state_root)
    rows = sorted(rows, key=lambda x: x.get("timestamp", ""), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return rows


def format_approval_decisions(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "承認決定履歴: 0件"

    lines = [f"承認決定履歴: {len(rows)}件"]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"{i}. {row.get('decision', '-')}"
            f" | action={row.get('action', '-')}"
            f" | fp={row.get('fingerprint', '-')}"
        )
    return "\n".join(lines)


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
