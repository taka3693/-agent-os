from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _health_dir(state_root: Path) -> Path:
    return state_root / "health"


def ensure_health_dir(state_root: Path) -> Path:
    p = _health_dir(state_root)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _history_path(state_root: Path) -> Path:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return _health_dir(state_root) / f"history-{day}.jsonl"


def _latest_path(state_root: Path) -> Path:
    return _health_dir(state_root) / "latest.json"


def write_latest_health(state_root: Path, payload: Dict[str, Any]) -> Path:
    ensure_health_dir(state_root)
    path = _latest_path(state_root)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def append_health_history(state_root: Path, payload: Dict[str, Any]) -> Path:
    ensure_health_dir(state_root)
    path = _history_path(state_root)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path
