from tools.run_execution_adapter import map_task_to_action_type
from __future__ import annotations
from execution.execution_store import audit, claim_is_stale, create_claim, ledger_append, now_ts, queue_items, remove_claim, rewrite_queue
from execution.self_operation_executor import execute_self_operation
from typing import Dict, Any, Tuple, Literal, Optional
from pathlib import Path
import json

# === PRE-EXECUTION GUARD (Phase 1) ===

DANGEROUS_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/root/.ssh",
    "~/.ssh",
    "/boot",
    "/proc",
    "/sys",
]

def pre_execution_guard(action_type: str, payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    try:
        if action_type == "write":
            path = payload.get("path", "")
            for dangerous in DANGEROUS_PATHS:
                if path.startswith(dangerous) or path == dangerous:
                    return "blocked", {
                        "reason": "dangerous_path",
                        "detail": f"Write to {path} is not allowed"
                    }
        return "allow", {}
    except Exception as e:
        return "guard_error", {"error": str(e)}


# === RESULT CLASSIFIER (Phase 3.5) ===

MAX_RETRY_COUNT = 3
ResultClass = Literal["success", "blocked", "permanent", "retryable", "needs_human", "permanent_unknown"]

KNOWN_ERRORS = [
    "unsupported_action",
    "source_missing",
    "permission_denied",
    "invalid_payload",
]

def classify_result(result: Dict[str, Any]) -> ResultClass:
    if result.get("ok"):
        return "success"
    if result.get("status") == "blocked":
        return "blocked"
    if result.get("status") == "guard_error":
        return "permanent"
    
    error_type = result.get("error_type", "")
    error = result.get("error", "")
    
    if error_type == "permanent":
        return "permanent"
    if error_type in ("transient", "timeout", "network"):
        return "retryable"
    
    # error_type が空でも error 文字列から retryable を判定
    error_lower = error.lower()
    for keyword in ("timeout", "network", "connection"):
        if keyword in error_lower:
            return "retryable"
    
    for known in KNOWN_ERRORS:
        if known in error_lower:
            return "permanent"
    
    # Unknown errors are not retryable
    if error_type == "unknown" or not error_type:
        return "permanent_unknown"
    
    return "needs_human"


# === LEARNING INSIGHTS (Phase 4) ===

INSIGHTS_DIR = Path.home() / ".openclaw" / "state" / "agentos"
INSIGHTS_FILE = INSIGHTS_DIR / "learning_insights.jsonl"

def _ensure_insights_dir():
    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)

def _load_insights() -> Dict[str, Dict[str, Any]]:
    _ensure_insights_dir()
    if not INSIGHTS_FILE.exists():
        return {}
    insights = {}
    try:
        with open(INSIGHTS_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    key = f"{entry['type']}:{entry['pattern_key']}"
                    insights[key] = entry
    except:
        pass
    return insights

def _save_insights(insights: Dict[str, Dict[str, Any]]) -> None:
    _ensure_insights_dir()
    with open(INSIGHTS_FILE, "w") as f:
        for entry in insights.values():
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def _normalize_error(error: str) -> str:
    """Extract key part of error message."""
    for pattern in KNOWN_ERRORS:
        if pattern in error:
            return pattern
    return error[:50] if error else "unknown"

def generate_pattern_key(action_type: str, error_type: Optional[str], error: Optional[str]) -> str:
    """Generate pattern key for learning."""
    normalized = _normalize_error(error) if error else ""
    return f"{action_type}:{error_type or 'none'}:{normalized}"

def is_known_failure_pattern(action_type: str, error_type: Optional[str], error: Optional[str]) -> bool:
    """Check if this failure pattern has been seen 2+ times."""
    insights = _load_insights()
    pattern_key = generate_pattern_key(action_type, error_type, error)
    key = f"failure_pattern:{pattern_key}"
    if key in insights:
        return insights[key].get("count", 0) >= 2
    return False

def is_known_permanent_failure(action_type: str) -> bool:
    """Check if this action_type has 2+ permanent failures (skip threshold)."""
    insights = _load_insights()
    for key, entry in insights.items():
        if key.startswith("failure_pattern:") and entry.get("action_type") == action_type:
            if entry.get("count", 0) >= 2:
                return True
    return False

def update_insight(insight_type: str, pattern_key: str, data: Dict[str, Any]) -> None:
    """Update or create an insight entry."""
    # Skip test actions
    if "test." in pattern_key:
        return
    
    insights = _load_insights()
    key = f"{insight_type}:{pattern_key}"
    ts = now_ts()
    
    if key in insights:
        insights[key]["count"] += 1
        insights[key]["last_seen"] = ts
    else:
        insights[key] = {
            "type": insight_type,
            "pattern_key": pattern_key,
            "count": 1,
            "first_seen": ts,
            "last_seen": ts,
            **data
        }
    
    _save_insights(insights)


def run_execution_worker(worker_id: str = "worker-1") -> Dict[str, Any]:
    rows = queue_items()

    recovered = 0
    for row in rows:
        status = row.get("status")
        execution_id = row.get("execution_id")
        if status in ("claimed", "running") and execution_id and claim_is_stale(execution_id):
            prev_status = status
            remove_claim(execution_id)
            row["status"] = "queued"
            recovered += 1
            ledger_append({
                "ts": now_ts(),
                "execution_id": execution_id,
                "idempotency_key": row.get("idempotency_key"),
                "fingerprint": row.get("fingerprint"),
                "action_type": row.get("action_type"),
                "status": "recovered_stale_claim",
                "previous_status": prev_status,
            })
            audit("execution_recovered_stale_claim", execution_id=execution_id, fingerprint=row.get("fingerprint"), previous_status=prev_status)

    if recovered:
        rewrite_queue(rows)

    idx = None
    target = None

    for i, row in enumerate(rows):
        if row.get("status") == "queued":
            idx = i
            target = row
            break

    if target is None:
        return {"ok": True, "message": "no_queued_items"}

    execution_id = target["execution_id"]
    attempt = target.get("attempt", 0)
    action_type = target["action_type"]

    # === PRE-EXECUTION GUARD CHECK (Phase 1) ===
    guard_status, guard_info = pre_execution_guard(action_type, target["payload"])
    
    if guard_status == "blocked":
        del rows[idx]
        rewrite_queue(rows)
        ledger_append({
            "ts": now_ts(),
            "execution_id": execution_id,
            "idempotency_key": target["idempotency_key"],
            "fingerprint": target["fingerprint"],
            "action_type": action_type,
            "status": "blocked",
            "error_type": "governance_blocked",
            "error": guard_info.get("reason"),
            "blocked_reason": guard_info.get("reason"),
            "blocked_detail": guard_info.get("detail"),
        })
        # Learning: blocked pattern
        pattern_key = f"{action_type}:{guard_info.get('reason')}"
        update_insight("blocked_pattern", pattern_key, {
            "action_type": action_type,
            "blocked_reason": guard_info.get("reason"),
        })
        audit("execution_blocked", execution_id=execution_id, fingerprint=target["fingerprint"], reason=guard_info.get("reason"))
        return {"ok": False, "execution_id": execution_id, "status": "blocked", "reason": guard_info.get("reason"), "class": "blocked"}
    
    if guard_status == "guard_error":
        del rows[idx]
        rewrite_queue(rows)
        ledger_append({
            "ts": now_ts(),
            "execution_id": execution_id,
            "idempotency_key": target["idempotency_key"],
            "fingerprint": target["fingerprint"],
            "action_type": action_type,
            "status": "guard_error",
            "error": guard_info.get("error"),
        })
        audit("execution_guard_error", execution_id=execution_id, fingerprint=target["fingerprint"], error=guard_info.get("error"))
        return {"ok": False, "execution_id": execution_id, "status": "guard_error", "error": guard_info.get("error"), "class": "permanent"}
    
    # guard_status == "allow" → proceed
    
    if not create_claim(execution_id):
        return {"ok": False, "message": "claim_failed", "execution_id": execution_id}

    try:
        rows[idx]["status"] = "claimed"
        rewrite_queue(rows)
        ledger_append({
            "ts": now_ts(),
            "execution_id": execution_id,
            "idempotency_key": target["idempotency_key"],
            "fingerprint": target["fingerprint"],
            "action_type": action_type,
            "status": "claimed",
            "claimed_by": worker_id,
            "attempt": attempt + 1,
        })
        audit("execution_claimed", execution_id=execution_id, fingerprint=target["fingerprint"])

        rows[idx]["status"] = "running"
        rewrite_queue(rows)
        ledger_append({
            "ts": now_ts(),
            "execution_id": execution_id,
            "idempotency_key": target["idempotency_key"],
            "fingerprint": target["fingerprint"],
            "action_type": action_type,
            "status": "running",
            "claimed_by": worker_id,
            "attempt": attempt + 1,
        })
        audit("execution_started", execution_id=execution_id, fingerprint=target["fingerprint"])

        # Execute (pass attempt to payload for attempt-aware actions)
        exec_payload = dict(target["payload"])

# FORCE inject task into payload
if "task" not in exec_payload:
    exec_payload["task"] = str(target)

        exec_payload["_worker_attempt"] = attempt
        

# FORCE task extraction
task_text = (
    exec_payload.get("task")
    or exec_payload.get("text")
    or exec_payload.get("instruction")
    or str(exec_payload)
)
action_type = map_task_to_action_type(task_text)

action_type = map_task_to_action_type(exec_payload.get("task") or exec_payload.get("text") or "")
res = execute_self_operation(action_type, exec_payload)

        
        # === RESULT CLASSIFICATION (Phase 3.5) ===
        result_class = classify_result(res)
        error_type = res.get("error_type")
        error = res.get("error")
        
        if result_class == "success":
            ledger_append({
                "ts": now_ts(),
                "execution_id": execution_id,
                "idempotency_key": target["idempotency_key"],
                "fingerprint": target["fingerprint"],
                "status": "succeeded",
                "claimed_by": worker_id,
                "attempt": attempt + 1,
                "action_type": action_type,
                "result": res.get("result", {}),
                "idempotent_reuse": res.get("idempotent_reuse", False),
            })
            del rows[idx]
            rewrite_queue(rows)
            # Learning: retry success
            if attempt > 0:
                update_insight("retry_success", action_type, {
                    "action_type": action_type,
                    "attempts": attempt + 1,
                })
            audit("execution_succeeded", execution_id=execution_id, fingerprint=target["fingerprint"])
            return {"ok": True, "execution_id": execution_id, "result": res, "class": "success"}

        # Failed - check if retryable
        # Disable retry shortening for known patterns (false positive prevention)
        # Always use MAX_RETRY_COUNT to allow success on 3rd attempt
        # Failed - check if retryable (learning-aware)
        if is_known_failure_pattern(action_type, error_type, error):
            max_retry = 1
        else:
            max_retry = MAX_RETRY_COUNT
        
        if result_class == "retryable" and attempt + 1 < max_retry:
            rows[idx]["status"] = "queued"
            rows[idx]["attempt"] = attempt + 1
            rewrite_queue(rows)
            ledger_append({
                "ts": now_ts(),
                "execution_id": execution_id,
                "idempotency_key": target["idempotency_key"],
                "fingerprint": target["fingerprint"],
                "action_type": action_type,
                "status": "retry_scheduled",
                "claimed_by": worker_id,
                "attempt": attempt + 1,
                "error_type": error_type,
                "error": error,
                "next_attempt": attempt + 2,
            })
            audit("execution_retry_scheduled", execution_id=execution_id, fingerprint=target["fingerprint"], attempt=attempt + 1)
            return {"ok": False, "execution_id": execution_id, "status": "retry_scheduled", "attempt": attempt + 1, "class": "retryable"}
        
        # Permanent failure or max retries reached
        final_status = "failed" if result_class in ("permanent", "needs_human") else "failed_max_retries"
        del rows[idx]
        rewrite_queue(rows)
        ledger_append({
            "ts": now_ts(),
            "execution_id": execution_id,
            "idempotency_key": target["idempotency_key"],
            "fingerprint": target["fingerprint"],
              "action_type": action_type,
            "status": final_status,
            "claimed_by": worker_id,
            "attempt": attempt + 1,
            "error_type": error_type,
            "error": error,
            "result_class": result_class,
        })
        # Learning: permanent failure only (not needs_human)
        if result_class == "permanent":
            # Check if this is a known failure pattern (pattern_key level)
            if is_known_failure_pattern(action_type, error_type, error):
                ledger_append({
                    "ts": now_ts(),
                    "execution_id": execution_id,
                    "idempotency_key": target["idempotency_key"],
                    "fingerprint": target["fingerprint"],
                    "status": "known_failure_pattern_warning",
                    "action_type": action_type,
                    "error_type": error_type,
                    "error": error,
                })
                audit("execution_known_failure_pattern_warning", execution_id=execution_id, fingerprint=target["fingerprint"], action_type=action_type, error=error)
            
            pattern_key = generate_pattern_key(action_type, error_type, error)
            update_insight("failure_pattern", pattern_key, {
                "action_type": action_type,
                "error_type": error_type,
                "normalized_error": _normalize_error(error),
            })
        audit("execution_failed", execution_id=execution_id, fingerprint=target["fingerprint"], error=error, result_class=result_class)
        return {"ok": False, "execution_id": execution_id, "status": final_status, "error": error, "class": result_class}

    finally:
        remove_claim(execution_id)