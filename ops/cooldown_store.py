from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


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
