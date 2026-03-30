#!/usr/bin/env python3
"""Light check policy module.

Provides lightweight policy evaluation for task execution.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parents[1]
POLICY_LOG = BASE_DIR / "state" / "policy_checks.jsonl"


def evaluate_light_check(
    text: str,
    recent_actions: list | None = None,
    task_id: str = "",
    completed_topic_keys: list | None = None,
) -> Dict[str, Any]:
    """Evaluate a task against light check policies.
    
    Args:
        text: The query/command text to evaluate
        recent_actions: List of recent actions for context
        task_id: Task identifier
        completed_topic_keys: List of completed topic keys
        
    Returns:
        Dict with 'allowed' (bool) and 'reason' (str)
    """
    if recent_actions is None:
        recent_actions = []
    if completed_topic_keys is None:
        completed_topic_keys = []
    
    # Blocked commands
    blocked_keywords = ["rm ", "delete ", "drop ", "truncate "]
    text_lower = text.lower()
    
    for kw in blocked_keywords:
        if kw in text_lower:
            return {
                "allowed": False,
                "reason": f"blocked_keyword:{kw.strip()}",
            }
    
    # All checks passed
    return {
        "allowed": True,
        "reason": "passed",
    }


def record_light_check(task: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Record a policy check result to the log.
    
    Args:
        task: The task that was checked
        result: The evaluation result from evaluate_light_check
    """
    import json
    from datetime import datetime, timezone
    
    POLICY_LOG.parent.mkdir(parents=True, exist_ok=True)
    
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task.get("task_id"),
        "selected_skill": task.get("selected_skill"),
        "allowed": result.get("allowed"),
        "reason": result.get("reason"),
    }
    
    with POLICY_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
