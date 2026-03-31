from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def approval_decision_log_path(state_root: Path) -> Path:
    return state_root / "approval_decisions.jsonl"


def append_approval_decision(
    state_root: Path,
    *,
    timestamp: str,
    fingerprint: str,
    decision: str,
    action: str,
    args: Dict[str, Any],
    reason: Optional[str] = None,
    source: Optional[str] = None,
) -> Path:
    path = approval_decision_log_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": timestamp,
        "fingerprint": fingerprint,
        "decision": decision,
        "action": action,
        "args": args,
        "reason": reason,
        "source": source,
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return path
