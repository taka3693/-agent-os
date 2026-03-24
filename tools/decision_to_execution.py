#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state" / "decision_runs"
LOG_FILE = STATE_DIR / "decision_runs.jsonl"

def generate_decision_id() -> str:
    return f"dec-{uuid.uuid4().hex[:12]}"

def run_auto_task(query: str) -> dict:
    cp = subprocess.run(
        ["python3", str(ROOT / "tools" / "entrypoint.py"), "auto_task", query],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
    )
    stdout = (cp.stdout or "").strip()
    if not stdout:
        return {"ok": False, "error": "empty_auto_task_stdout"}
    return json.loads(stdout)

def run_execution(query: str) -> dict:
    cp = subprocess.run(
        ["python3", str(ROOT / "skills" / "execution" / "execution_impl.py"), query],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
    )
    stdout = (cp.stdout or "").strip()
    if not stdout:
        return {"ok": False, "error": "empty_execution_stdout"}
    return json.loads(stdout)

def append_log(record: dict) -> str:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return str(LOG_FILE)

def main() -> int:
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print(json.dumps({"ok": False, "error": "missing_query"}, ensure_ascii=False, indent=2))
        return 1

    decision_id = generate_decision_id()
    decision_out = run_auto_task(query)
    
    if not decision_out.get("ok"):
        out = {
            "ok": False,
            "decision_id": decision_id,
            "stage": "decision",
            "decision_out": decision_out,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    task_result = decision_out.get("task_result") or {}
    decision = task_result.get("decision") or {}

    conclusion = str(decision.get("conclusion") or "").strip()
    next_actions = decision.get("next_actions") or []

    execution_query_parts = []
    if conclusion:
        execution_query_parts.append(conclusion)
    if next_actions:
        execution_query_parts.append(" / ".join(str(x) for x in next_actions[:3]))
    if not execution_query_parts:
        execution_query_parts.append(query)

    execution_query = "。".join(execution_query_parts)
    execution_out = run_execution(execution_query)

    ts = datetime.now().isoformat(timespec="seconds")
    task_id = ((decision_out.get("router") or {}).get("task_id")
               or (decision_out.get("router_result") or {}).get("task_id")
               or decision_out.get("task_id"))
    
    record = {
        "timestamp": ts,
        "decision_id": decision_id,
        "task_id": task_id,
        "input_query": query,
        "original_query": decision_out.get("original_query"),
        "history_augmented_query": decision_out.get("history_augmented_query"),
        "history_used_count": decision_out.get("history_used_count"),
        "history_context": decision_out.get("history_context"),
        "decision_skill": decision_out.get("selected_skill"),
        "route_reason": ((decision_out.get("router") or {}).get("route_reason")
                         or (decision_out.get("router_result") or {}).get("route_reason")),
        "conclusion": decision.get("conclusion"),
        "winner": decision.get("winner"),
        "deprioritized": decision.get("deprioritized"),
        "next_actions": decision.get("next_actions"),
        "axes": task_result.get("axes"),
        "scores": task_result.get("scores"),
        "decision_reason_structured": task_result.get("decision_reason_structured"),
        "execution_summary": execution_out.get("summary"),
        "execution_steps": execution_out.get("steps"),
        "execution_status": "success" if execution_out.get("ok") else "failed",
        "ok": bool(decision_out.get("ok")) and bool(execution_out.get("ok")),
    }
    log_path = append_log(record)

    out = {
        "ok": bool(decision_out.get("ok")) and bool(execution_out.get("ok")),
        "decision_id": decision_id,
        "task_id": task_id,
        "input_query": query,
        "decision_out": decision_out,
        "execution_out": execution_out,
        "log_path": log_path,
        "logged_at": ts,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1

if __name__ == "__main__":
    raise SystemExit(main())
