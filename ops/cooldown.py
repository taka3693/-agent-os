"""Cooldown - アクション発行間隔制御の統合モジュール

統合元:
- cooldown_store.py
- cooldown_policy.py
- cooldown_filter.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ops.action_fingerprint import build_action_fingerprint


# =============================================================================
# Store Layer (from cooldown_store.py)
# =============================================================================

def _cooldown_path(state_root: Path) -> Path:
    return state_root / "ops_cooldowns.json"


def load_cooldowns(state_root: Path) -> Dict[str, Any]:
    path = _cooldown_path(state_root)
    if not path.exists():
        return {"items": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"items": {}}
    if not isinstance(data, dict):
        return {"items": {}}
    items = data.get("items")
    if not isinstance(items, dict):
        return {"items": {}}
    return {"items": items}


def save_cooldowns(state_root: Path, payload: Dict[str, Any]) -> Path:
    state_root.mkdir(parents=True, exist_ok=True)
    path = _cooldown_path(state_root)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def get_last_emitted_at(state_root: Path, key: str) -> Optional[str]:
    data = load_cooldowns(state_root)
    item = data.get("items", {}).get(key)
    if not isinstance(item, dict):
        return None
    value = item.get("last_emitted_at")
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def mark_emitted(state_root: Path, key: str, emitted_at: str) -> Path:
    data = load_cooldowns(state_root)
    items = data.setdefault("items", {})
    items[key] = {"last_emitted_at": emitted_at}
    return save_cooldowns(state_root, data)


# =============================================================================
# Policy Layer (from cooldown_policy.py)
# =============================================================================

def _parse_iso_utc(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def should_emit_by_cooldown(
    *,
    now_iso: str,
    last_emitted_at: str | None,
    cooldown_seconds: int,
) -> bool:
    if cooldown_seconds <= 0:
        return True
    if not last_emitted_at:
        return True
    now_dt = _parse_iso_utc(now_iso)
    last_dt = _parse_iso_utc(last_emitted_at)
    if now_dt is None or last_dt is None:
        return True
    elapsed = (now_dt - last_dt).total_seconds()
    return elapsed >= cooldown_seconds


# =============================================================================
# Filter Layer (from cooldown_filter.py)
# =============================================================================

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
