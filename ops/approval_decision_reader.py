from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ops.approval_decision_store import approval_decision_log_path


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
