from __future__ import annotations

from typing import Any, Dict, Optional


AUTO_ALLOWED = "auto_allowed"
APPROVAL_REQUIRED = "approval_required"
FORBIDDEN = "forbidden"


def classify_action_policy(
    action: str,
    args: Optional[Dict[str, Any]] = None,
) -> str:
    _ = args or {}

    if action in {
        "service.status_openclaw_gateway",
        "service.logs_openclaw_gateway_recent",
        "config.read_openclaw_json",
        "session.list_jsonl_sizes",
        "git.status_repo",
    }:
        return AUTO_ALLOWED

    if action == "session.archive":
        return APPROVAL_REQUIRED

    if action == "service.restart_openclaw_gateway":
        return APPROVAL_REQUIRED

    return FORBIDDEN


def decide_recommended_action(
    item: Dict[str, Any],
) -> Dict[str, Any]:
    action = str(item.get("action") or "").strip()
    args = item.get("args") if isinstance(item.get("args"), dict) else {}
    policy = classify_action_policy(action, args)

    out = dict(item)
    out["policy"] = policy
    return out
