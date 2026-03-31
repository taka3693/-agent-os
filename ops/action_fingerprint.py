from __future__ import annotations

from typing import Any, Dict


def build_action_fingerprint(item: Dict[str, Any]) -> str:
    action = str(item.get("action") or "").strip()

    if action == "session.archive":
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        target = str(args.get("target_basename") or "").strip()
        if target:
            return f"{action}:{target}"

    return action or "unknown"
