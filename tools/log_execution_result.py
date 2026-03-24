#!/usr/bin/env python3
"""Log execution results to execution_runs.jsonl"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state" / "execution_runs"
LOG_FILE = STATE_DIR / "execution_runs.jsonl"

def append_execution_result(
    action_or_record,
    query: str = None,
    result: dict = None,
    decision_id: str = None,
    task_id: str = None,
) -> dict:
    """Append execution result to log file.
    
    Supports two calling conventions:
    1. append_execution_result(record_dict) - single dict with all fields
    2. append_execution_result(action, query, result, ...) - separate args
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    
    # Handle single dict argument
    if isinstance(action_or_record, dict) and query is None:
        record = action_or_record.copy()
        record["logged_at"] = ts
    else:
        # Handle separate arguments
        action = action_or_record
        record = {
            "logged_at": ts,
            "action": action,
            "query": query[:500] if query else "",
            "decision_id": decision_id or (result.get("decision_id") if result else None),
            "task_id": task_id or (result.get("task_id") if result else None),
            "result_flag": "success" if (result and result.get("ok")) else "failed",
            "decision_conclusion": None,
            "decision_winner": None,
            "execution_summary": None,
            "execution_steps": None,
        }
        
        if result:
            # Extract decision info
            decision_out = result.get("decision_out") or result.get("result", {}).get("decision_out") or {}
            task_result = decision_out.get("task_result") or {}
            decision = task_result.get("decision") or {}
            
            record["decision_conclusion"] = decision.get("conclusion")
            record["decision_winner"] = decision.get("winner")
            record["decision_deprioritized"] = decision.get("deprioritized")
            
            # Extract execution info
            execution_out = result.get("execution_out") or result.get("result", {}).get("execution_out") or {}
            record["execution_summary"] = execution_out.get("summary")
            record["execution_steps"] = execution_out.get("steps")
            record["execution_notes"] = execution_out.get("notes")
    
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    return {"ok": True, "log_path": str(LOG_FILE), "logged_at": ts}
