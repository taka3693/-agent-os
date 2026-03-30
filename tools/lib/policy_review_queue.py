from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import json


def _resolve_base_dir(base_dir):
    if base_dir:
        return Path(base_dir)

    import tools.run_agent_os_request as mod
    return Path(mod.__file__).resolve().parents[1]


def _suggestion_store_path(base_dir=None) -> Path:
    root = _resolve_base_dir(base_dir)
    return root / "state" / "policy_suggestions" / "policy_suggestions.jsonl"


def load_policy_suggestions(*, base_dir=None) -> List[Dict[str, Any]]:
    path = _suggestion_store_path(base_dir=base_dir)
    if not path.exists():
        return []

    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def list_pending_policy_suggestions(*, base_dir=None) -> List[Dict[str, Any]]:
    rows = load_policy_suggestions(base_dir=base_dir)
    return [x for x in rows if str(x.get("status") or "") == "pending_review"]


def _rewrite_policy_suggestions(rows: List[Dict[str, Any]], *, base_dir=None) -> Dict[str, Any]:
    path = _suggestion_store_path(base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"ok": True, "path": str(path), "count": len(rows)}


def mark_policy_suggestion_status(
    *,
    index: int,
    status: str,
    reviewer_note: str | None = None,
    base_dir=None,
) -> Dict[str, Any]:
    if status not in {"approved", "rejected"}:
        raise ValueError("status must be approved or rejected")

    rows = load_policy_suggestions(base_dir=base_dir)
    pending_positions = [i for i, row in enumerate(rows) if str(row.get("status") or "") == "pending_review"]

    if index < 0 or index >= len(pending_positions):
        raise IndexError("pending suggestion index out of range")

    row_index = pending_positions[index]
    row = dict(rows[row_index])
    row["status"] = status
    row["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if reviewer_note:
        row["reviewer_note"] = str(reviewer_note)

    rows[row_index] = row
    write_res = _rewrite_policy_suggestions(rows, base_dir=base_dir)

    return {
        "ok": True,
        "updated": row,
        "path": write_res["path"],
    }
