from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import json


def _resolve_base_dir(base_dir):
    if base_dir:
        return Path(base_dir)

    import tools.run_agent_os_request as mod
    return Path(mod.__file__).resolve().parents[1]


def _audit_store_path(base_dir=None) -> Path:
    root = _resolve_base_dir(base_dir)
    p = root / "state" / "audit" / "policy_review_audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_latest_policy_review_audit(*, base_dir=None) -> Dict[str, Any]:
    path = _audit_store_path(base_dir=base_dir)
    if not path.exists():
        return {}

    lines = [x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not lines:
        return {}

    try:
        row = json.loads(lines[-1])
    except Exception:
        return {}

    return row if isinstance(row, dict) else {}


def append_policy_review_audit(
    *,
    action: str,
    updated: Dict[str, Any],
    reviewer: str | None = None,
    base_dir=None,
) -> Dict[str, Any]:
    path = _audit_store_path(base_dir=base_dir)

    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "policy_review_audit",
        "action": action,
        "reviewer": reviewer or "unknown",
        "failure_type": updated.get("failure_type"),
        "suggested_action": updated.get("suggested_action"),
        "status": updated.get("status"),
        "reason": updated.get("reason"),
        "reviewer_note": updated.get("reviewer_note"),
        "reviewed_at": updated.get("reviewed_at"),
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return {
        "ok": True,
        "path": str(path),
        "event": event,
    }
