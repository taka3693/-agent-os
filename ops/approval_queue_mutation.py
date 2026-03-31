from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ops.approval_queue_store import approval_queue_path


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
