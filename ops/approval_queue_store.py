from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Set


def approval_queue_path(state_root: Path) -> Path:
    return state_root / "approval_queue.jsonl"


def load_existing_approval_fingerprints(state_root: Path) -> Set[str]:
    path = approval_queue_path(state_root)
    if not path.exists():
        return set()

    out: Set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        fp = payload.get("fingerprint")
        if isinstance(fp, str) and fp:
            out.add(fp)
    return out


def append_approval_queue_entry(
    state_root: Path,
    *,
    timestamp: str,
    fingerprint: str,
    action: str,
    args: Dict[str, Any],
    policy: str,
    reason: str,
    source: Optional[str] = None,
) -> Optional[Path]:
    existing = load_existing_approval_fingerprints(state_root)
    if fingerprint in existing:
        return None

    path = approval_queue_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": timestamp,
        "fingerprint": fingerprint,
        "action": action,
        "args": args,
        "policy": policy,
        "reason": reason,
        "source": source,
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return path
