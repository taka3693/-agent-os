#!/usr/bin/env python3
"""Update execution result status."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state" / "execution_runs"
LOG_FILE = STATE_DIR / "execution_runs.jsonl"

def update_execution_result(
    task_id: str,
    status: str,
    output: str = "",
    decision_id: str = None,
) -> dict:
    """Log status update for a task."""
    if not task_id:
        return {"ok": False, "error": "missing_task_id"}
    
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    
    ts = datetime.now().isoformat(timespec="seconds")
    
    record = {
        "logged_at": ts,
        "action": "status_update",
        "task_id": task_id,
        "decision_id": decision_id,
        "status": status,
        "output": output[:1000] if output else "",
    }
    
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    return {"ok": True, "task_id": task_id, "status": status, "logged_at": ts}
