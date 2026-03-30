from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict


RATE_STATE_PATH = Path("state/policy/rate_limits.json")


def _utcnow() -> datetime:
    return datetime.utcnow()


def _load_state(path: Path = RATE_STATE_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: Dict[str, Any], path: Path = RATE_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def check_and_consume(
    bucket: str,
    *,
    limit: int,
    window_seconds: int,
    path: Path = RATE_STATE_PATH,
) -> Dict[str, Any]:
    state = _load_state(path)
    now = _utcnow()

    bucket_state = state.get(bucket) or {"events": []}
    events = []
    cutoff = now - timedelta(seconds=window_seconds)

    for item in bucket_state.get("events", []):
        try:
            ts = datetime.fromisoformat(str(item))
            if ts >= cutoff:
                events.append(ts.isoformat())
        except Exception:
            continue

    allowed = len(events) < limit
    if allowed:
        events.append(now.isoformat())

    bucket_state["events"] = events
    state[bucket] = bucket_state
    _save_state(state, path)

    return {
        "ok": allowed,
        "bucket": bucket,
        "limit": limit,
        "window_seconds": window_seconds,
        "used": len(events),
        "remaining": max(0, limit - len(events)),
    }
