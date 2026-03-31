from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


AUTO_ALLOWED = "auto_allowed"
APPROVAL_REQUIRED = "approval_required"
FORBIDDEN = "forbidden"


def build_action_queue(
    actions: Optional[Iterable[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    queue: Dict[str, List[Dict[str, Any]]] = {
        AUTO_ALLOWED: [],
        APPROVAL_REQUIRED: [],
        FORBIDDEN: [],
    }

    for row in actions or []:
        item = dict(row)
        policy = str(item.get("policy") or "").strip()

        if policy == AUTO_ALLOWED:
            queue[AUTO_ALLOWED].append(item)
        elif policy == APPROVAL_REQUIRED:
            queue[APPROVAL_REQUIRED].append(item)
        else:
            queue[FORBIDDEN].append(item)

    return queue
