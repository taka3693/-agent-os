"""Approval Queue - 承認待ちキューの全操作を統合

統合元:
- approval_queue_store.py
- approval_queue_reader.py
- approval_queue_mutation.py
- approval_queue_formatter.py
- approval_queue_view.py
- approval_queue_api.py
- approval_queue_service.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# =============================================================================
# Store Layer
# =============================================================================

def approval_queue_path(state_root: Path) -> Path:
    return state_root / "approval_queue.jsonl"


def load_existing_approval_fingerprints(state_root: Path) -> Set[str]:
    path = approval_queue_path(state_root)
    if not path.exists():
        return set()

    out: Set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        fp = payload.get("fingerprint")
        if isinstance(fp, str) and fp:
            out.add(fp)
    return out


def append_approval_queue_entry(
    state_root: Path,
    *,
    timestamp: str,
    fingerprint: str,
    action: str,
    args: Dict[str, Any],
    policy: str,
    reason: str,
    source: Optional[str] = None,
) -> Optional[Path]:
    existing = load_existing_approval_fingerprints(state_root)
    if fingerprint in existing:
        return None

    path = approval_queue_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": timestamp,
        "fingerprint": fingerprint,
        "action": action,
        "args": args,
        "policy": policy,
        "reason": reason,
        "source": source,
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return path


# =============================================================================
# Reader Layer
# =============================================================================

def load_approval_queue(state_root: Path) -> List[Dict[str, Any]]:
    path = approval_queue_path(state_root)
    if not path.exists():
        return []

    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


def list_pending_approvals(state_root: Path, limit: int | None = None) -> List[Dict[str, Any]]:
    rows = load_approval_queue(state_root)
    rows = sorted(rows, key=lambda x: x.get("timestamp", ""), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return rows


def find_pending_approval_by_fingerprint(
    state_root: Path,
    fingerprint: str,
) -> Dict[str, Any] | None:
    for row in load_approval_queue(state_root):
        if row.get("fingerprint") == fingerprint:
            return row
    return None


# =============================================================================
# Mutation Layer
# =============================================================================

def remove_pending_approval_by_fingerprint(
    state_root: Path,
    fingerprint: str,
) -> Dict[str, Any]:
    path = approval_queue_path(state_root)
    if not path.exists():
        return {"ok": False, "removed": False, "count": 0}

    rows = []
    removed = False

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not removed and row.get("fingerprint") == fingerprint:
            removed = True
            continue
        rows.append(row)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {"ok": True, "removed": removed, "count": len(rows)}


# =============================================================================
# Formatter Layer
# =============================================================================

def format_pending_approvals(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "承認待ち: 0件"

    lines = [f"承認待ち: {len(rows)}件"]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"{i}. {row.get('action', '-')}"
            f" | fp={row.get('fingerprint', '-')}"
            f" | source={row.get('source', '-')}"
        )
    return "\n".join(lines)


# =============================================================================
# View / Service / API Layer
# =============================================================================

def render_pending_approvals(state_root: Path, limit: int | None = None) -> str:
    rows = list_pending_approvals(state_root, limit=limit)
    return format_pending_approvals(rows)


def get_pending_approvals_view(state_root: Path, limit: int | None = None) -> Dict[str, Any]:
    rows = list_pending_approvals(state_root, limit=limit)
    return {
        "count": len(rows),
        "rows": rows,
        "text": format_pending_approvals(rows),
    }


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
