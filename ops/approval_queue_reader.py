from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ops.approval_queue_store import approval_queue_path


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
