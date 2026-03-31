from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from ops.action_fingerprint import build_action_fingerprint
from ops.cooldown_policy import should_emit_by_cooldown
from ops.cooldown_store import get_last_emitted_at


def filter_actions_by_cooldown(
    *,
    state_root,
    actions: Optional[Iterable[Dict[str, Any]]],
    now_iso: str,
    cooldown_seconds: int,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for row in actions or []:
        item = dict(row)
        key = build_action_fingerprint(item)
        last_emitted_at = get_last_emitted_at(state_root, key)

        if should_emit_by_cooldown(
            now_iso=now_iso,
            last_emitted_at=last_emitted_at,
            cooldown_seconds=cooldown_seconds,
        ):
            item["fingerprint"] = key
            out.append(item)

    return out
