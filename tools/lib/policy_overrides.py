from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import json

from tools.lib.policy_review_queue import load_policy_suggestions


def _resolve_base_dir(base_dir):
    if base_dir:
        return Path(base_dir)

    import tools.run_agent_os_request as mod
    return Path(mod.__file__).resolve().parents[1]


def _override_store_path(base_dir=None) -> Path:
    root = _resolve_base_dir(base_dir)
    p = root / "state" / "policy_overrides.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def build_policy_overrides(*, base_dir=None) -> Dict[str, Any]:
    rows = load_policy_suggestions(base_dir=base_dir)

    overrides: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overrides": {},
        "sources": [],
    }

    for row in rows:
        if str(row.get("status") or "") != "approved":
            continue

        ftype = str(row.get("failure_type") or "")
        suggested_action = str(row.get("suggested_action") or "")
        reason = str(row.get("reason") or "")

        if not ftype or not suggested_action:
            continue

        if suggested_action == "manual_review_bias":
            strategy = "manual_review"
        elif suggested_action == "tighten_auto_heal_scope":
            strategy = "retry_or_skip"
        elif suggested_action == "backoff_retry_bias":
            strategy = "backoff_retry"
        else:
            continue

        overrides["overrides"][ftype] = strategy
        overrides["sources"].append({
            "failure_type": ftype,
            "suggested_action": suggested_action,
            "reason": reason,
            "reviewed_at": row.get("reviewed_at"),
        })

    return overrides


def write_policy_overrides(*, base_dir=None) -> Dict[str, Any]:
    data = build_policy_overrides(base_dir=base_dir)
    path = _override_store_path(base_dir=base_dir)

    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
        if not isinstance(existing, dict):
            existing = {}

    new_overrides = data.get("overrides", {})
    if not isinstance(new_overrides, dict):
        new_overrides = {}

    existing_overrides = existing.get("overrides", {})
    if not isinstance(existing_overrides, dict):
        existing_overrides = {}

    # 保守的挙動:
    # 新規生成結果が空で、既存overrideが非空なら既存を保持する
    if not new_overrides and existing_overrides:
        data = existing

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "count": len((data.get("overrides", {}) if isinstance(data, dict) else {})),
    }


def load_policy_overrides(*, base_dir=None) -> Dict[str, Any]:
    path = _override_store_path(base_dir=base_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
