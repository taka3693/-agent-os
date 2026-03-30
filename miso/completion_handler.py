#!/usr/bin/env python3
"""
MISO Completion Handler

Parses OpenClaw's [Internal task completion event] messages
and updates MISO missions accordingly.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from miso.bridge import (
    _load_mission,
    update_mission,
    complete_mission,
    fail_mission,
    MISO_STATE_DIR,
)


# Pattern to match OpenClaw's internal completion event
COMPLETION_EVENT_PATTERN = re.compile(
    r'\[Internal task completion event\].*?'
    r'session_key:\s*(\S+).*?'
    r'task:\s*(.+?)(?:\n|$).*?'
    r'status:\s*(\S+)',
    re.DOTALL | re.IGNORECASE
)

# Alternative pattern for "A subagent task X just completed/failed"
SIMPLE_COMPLETION_PATTERN = re.compile(
    r'(?:A )?subagent (?:task )?["\']?(\S+?)["\']? just (completed|failed)',
    re.IGNORECASE
)


def parse_completion_event(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse an OpenClaw completion event message.
    
    Returns:
        {
            "session_key": "...",
            "task_label": "...",
            "status": "completed" | "failed" | "error",
        }
        or None if no completion event found
    """
    # Try detailed pattern first
    match = COMPLETION_EVENT_PATTERN.search(text)
    if match:
        session_key = match.group(1).strip()
        task_label = match.group(2).strip()
        status_raw = match.group(3).strip().lower()
        
        # Normalize status
        if status_raw in ("completed", "success", "done"):
            status = "completed"
        elif status_raw in ("failed", "error", "failure"):
            status = "failed"
        else:
            status = status_raw
        
        return {
            "session_key": session_key,
            "task_label": task_label,
            "status": status,
        }
    
    # Try simple pattern
    simple_match = SIMPLE_COMPLETION_PATTERN.search(text)
    if simple_match:
        task_label = simple_match.group(1).strip()
        outcome = simple_match.group(2).strip().lower()
        
        return {
            "session_key": None,
            "task_label": task_label,
            "status": "completed" if outcome == "completed" else "failed",
        }
    
    return None


def find_mission_by_agent_label(label: str) -> Optional[str]:
    """
    Find mission ID by agent label.
    
    Searches all mission state files for an agent with matching label.
    """
    if not MISO_STATE_DIR.exists():
        return None
    
    for state_file in MISO_STATE_DIR.glob("*.json"):
        try:
            mission = _load_mission(state_file.stem)
            for agent in mission.get("agents", []):
                if agent.get("label") == label or agent.get("name") == label:
                    return mission.get("mission_id")
        except Exception:
            continue
    
    return None


def handle_completion_event(text: str) -> Dict[str, Any]:
    """
    Handle a completion event message.
    
    1. Parse the event
    2. Find the corresponding mission
    3. Update MISO state
    
    Returns:
        {
            "handled": bool,
            "mission_id": str or None,
            "agent_label": str or None,
            "status": str or None,
            "error": str or None,
        }
    """
    parsed = parse_completion_event(text)
    if not parsed:
        return {"handled": False, "error": "no completion event found"}
    
    task_label = parsed["task_label"]
    status = parsed["status"]
    
    # Find mission by agent label
    mission_id = find_mission_by_agent_label(task_label)
    if not mission_id:
        return {
            "handled": False,
            "agent_label": task_label,
            "status": status,
            "error": f"no mission found for agent label: {task_label}",
        }
    
    # Load mission and update agent
    mission = _load_mission(mission_id)
    if not mission:
        return {
            "handled": False,
            "mission_id": mission_id,
            "error": "mission not found",
        }
    
    # Update agent status
    for agent in mission.get("agents", []):
        if agent.get("label") == task_label or agent.get("name") == task_label:
            agent["status"] = "COMPLETE" if status == "completed" else "ERROR"
            agent["detail"] = "完了" if status == "completed" else "失敗"
            break
    
    # Calculate overall mission state
    agents = mission.get("agents", [])
    done_count = sum(1 for a in agents if a.get("status") == "COMPLETE")
    error_count = sum(1 for a in agents if a.get("status") == "ERROR")
    total = len(agents)
    
    if error_count > 0:
        new_state = "ERROR"
        next_action = f"エラー発生: {task_label}"
    elif done_count == total:
        new_state = "COMPLETE"
        next_action = "全エージェント完了"
    else:
        new_state = "PARTIAL"
        next_action = f"{done_count}/{total} 完了"
    
    # Update mission
    result = update_mission(
        mission_id=mission_id,
        state=new_state,
        agents=agents,
        next_action=next_action,
    )
    
    return {
        "handled": True,
        "mission_id": mission_id,
        "agent_label": task_label,
        "status": status,
        "new_state": new_state,
        "update_result": result,
    }


if __name__ == "__main__":
    import json
    
    # Test with sample completion events
    test_messages = [
        """[Internal task completion event]
source: subagent
session_key: agent:worker:task-123
task: researcher
status: completed

Result:
<<<BEGIN_UNTRUSTED_CHILD_RESULT>>>
Analysis complete.
<<<END_UNTRUSTED_CHILD_RESULT>>>""",
        
        "A subagent task 'writer' just completed",
        
        "subagent reviewer just failed",
        
        "Hello world",  # Should not match
    ]
    
    for msg in test_messages:
        print(f"=== Input ===\n{msg[:50]}...")
        result = parse_completion_event(msg)
        print(f"=== Parsed ===\n{json.dumps(result, ensure_ascii=False, indent=2)}\n")
