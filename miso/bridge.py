"""MISO bridge — connects agent-os tasks to Telegram Mission Control"""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from miso.formatter import (
    format_mission_message,
    format_approval_message,
    get_reaction_for_state,
    STATE_LABELS,
)
from miso.telegram_hooks import (
    send_message,
    edit_message,
    react_to_message,
    make_approval_buttons,
    make_retry_buttons,
)
from runner.run_route_task import apply_approval_decision

# Mission state storage
MISO_STATE_DIR = PROJECT_ROOT / "state" / "miso"
MISO_STATE_DIR.mkdir(parents=True, exist_ok=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_mission(mission_id: str) -> Dict[str, Any]:
    path = MISO_STATE_DIR / f"{mission_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_mission(mission_id: str, data: Dict[str, Any]) -> None:
    path = MISO_STATE_DIR / f"{mission_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def start_mission(
    mission_id: str,
    mission_name: str,
    goal: str,
    chat_id: str,
    agents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Start a new MISO mission.
    
    1. Send INIT message to Telegram
    2. Add 🔥 reaction
    3. Save mission state with message_id
    
    Returns: {"ok": True, "message_id": "...", "mission_id": "..."}
    """
    # Format initial message
    message = format_mission_message(
        mission_name=mission_name,
        goal=goal,
        agents=[{"name": a.get("name", f"担当{i+1}"), "status": "INIT"} for i, a in enumerate(agents)],
        state="INIT",
        elapsed="0m",
        next_action="エージェント起動中",
    )
    
    # Send message
    result = send_message(chat_id=chat_id, message=message)
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "send failed")}
    
    message_id = result.get("message_id")
    if not message_id:
        return {"ok": False, "error": "no message_id returned"}
    
    # Add reaction
    react_to_message(chat_id=chat_id, message_id=message_id, emoji="🔥")
    
    # Save mission state
    mission_state = {
        "mission_id": mission_id,
        "mission_name": mission_name,
        "goal": goal,
        "chat_id": chat_id,
        "message_id": message_id,
        "state": "INIT",
        "agents": [{"name": a.get("name", f"担当{i+1}"), "status": "INIT", "label": a.get("label")} for i, a in enumerate(agents)],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    _save_mission(mission_id, mission_state)
    
    return {"ok": True, "message_id": message_id, "mission_id": mission_id}


def update_mission(
    mission_id: str,
    state: Optional[str] = None,
    agents: Optional[List[Dict[str, Any]]] = None,
    next_action: Optional[str] = None,
    elapsed: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update an existing mission.
    
    1. Load mission state
    2. Update fields
    3. Edit Telegram message
    4. Update reaction if state changed
    """
    mission = _load_mission(mission_id)
    if not mission:
        return {"ok": False, "error": "mission not found"}
    
    # Update fields
    old_state = mission.get("state")
    if state:
        mission["state"] = state
    if agents:
        mission["agents"] = agents
    if next_action:
        mission["next_action"] = next_action
    if elapsed:
        mission["elapsed"] = elapsed
    mission["updated_at"] = utc_now()
    
    # Calculate elapsed if not provided
    if not elapsed:
        created = datetime.fromisoformat(mission["created_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        minutes = int((now - created).total_seconds() / 60)
        elapsed = f"{minutes}m"
    
    # Format updated message
    message = format_mission_message(
        mission_name=mission["mission_name"],
        goal=mission["goal"],
        agents=mission.get("agents", []),
        state=mission.get("state", "RUNNING"),
        elapsed=elapsed,
        next_action=mission.get("next_action", ""),
    )
    
    # Edit message
    chat_id = mission["chat_id"]
    message_id = mission["message_id"]
    result = edit_message(chat_id=chat_id, message_id=message_id, message=message)
    
    # Update reaction if state changed
    new_state = mission.get("state")
    if old_state != new_state:
        new_reaction = get_reaction_for_state(new_state)
        react_to_message(chat_id=chat_id, message_id=message_id, emoji=new_reaction)
    
    # Save state
    _save_mission(mission_id, mission)
    
    return {"ok": True, "mission_id": mission_id, "state": new_state}


def request_approval(
    mission_id: str,
    task_id: str,
    target: str,
    handler: str,
    reason: str,
) -> Dict[str, Any]:
    """
    Transition mission to AWAITING_APPROVAL state with inline buttons.
    """
    mission = _load_mission(mission_id)
    if not mission:
        return {"ok": False, "error": "mission not found"}
    
    mission["state"] = "AWAITING_APPROVAL"
    mission["pending_approval"] = {
        "task_id": task_id,
        "target": target,
        "handler": handler,
        "reason": reason,
    }
    mission["updated_at"] = utc_now()
    
    # Format approval message
    message = format_approval_message(
        task_id=task_id,
        target=target,
        handler=handler,
        reason=reason,
    )
    
    # Edit message with approval buttons
    chat_id = mission["chat_id"]
    message_id = mission["message_id"]
    buttons = make_approval_buttons(task_id)
    
    result = edit_message(
        chat_id=chat_id,
        message_id=message_id,
        message=message,
        buttons=buttons,
    )
    
    # Update reaction to 👀
    react_to_message(chat_id=chat_id, message_id=message_id, emoji="👀")
    
    # Save state
    _save_mission(mission_id, mission)
    
    return {"ok": True, "mission_id": mission_id, "state": "AWAITING_APPROVAL"}


def handle_approval_callback(
    callback_data: str,
    mission_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Handle inline button callback for approval.
    
    callback_data format: "miso:approve:<task_id>" or "miso:reject:<task_id>"
    
    1. Parse callback_data
    2. Find task path
    3. Apply approval decision
    4. Update MISO message
    """
    parts = callback_data.split(":")
    if len(parts) != 3 or parts[0] != "miso":
        return {"ok": False, "error": "invalid callback format"}
    
    action = parts[1]  # approve or reject
    task_id = parts[2]
    
    if action not in {"approve", "reject"}:
        return {"ok": False, "error": f"unknown action: {action}"}
    
    # Find task path
    tasks_dir = PROJECT_ROOT / "state" / "tasks"
    task_path = tasks_dir / f"{task_id}.json"
    
    if not task_path.exists():
        return {"ok": False, "error": f"task not found: {task_id}"}
    
    # Apply approval decision
    try:
        result = apply_approval_decision(task_path, action)
    except Exception as e:
        return {"ok": False, "error": f"approval failed: {e}"}
    
    # Find mission by task_id if not provided
    if not mission_id:
        for miso_file in MISO_STATE_DIR.glob("*.json"):
            m = json.loads(miso_file.read_text(encoding="utf-8"))
            pending = m.get("pending_approval", {})
            if pending.get("task_id") == task_id:
                mission_id = m.get("mission_id")
                break
    
    # Update MISO if mission found
    if mission_id:
        new_state = "COMPLETE" if action == "approve" else "ERROR"
        next_action = "承認済み、実行へ移行" if action == "approve" else "却下済み、停止"
        update_mission(
            mission_id=mission_id,
            state=new_state,
            next_action=next_action,
        )
    
    return {
        "ok": True,
        "action": action,
        "task_id": task_id,
        "approval_state": result.get("approval_state"),
        "route_result": result.get("route_result"),
    }


def complete_mission(
    mission_id: str,
    summary: str = "",
    artifacts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Mark mission as COMPLETE.
    """
    return update_mission(
        mission_id=mission_id,
        state="COMPLETE",
        next_action=summary or "完了",
    )


def fail_mission(
    mission_id: str,
    error: str,
    allow_retry: bool = True,
) -> Dict[str, Any]:
    """
    Mark mission as ERROR with optional retry button.
    """
    mission = _load_mission(mission_id)
    if not mission:
        return {"ok": False, "error": "mission not found"}
    
    mission["state"] = "ERROR"
    mission["error"] = error
    mission["updated_at"] = utc_now()
    
    # Format error message
    message = format_mission_message(
        mission_name=mission["mission_name"],
        goal=mission["goal"],
        agents=mission.get("agents", []),
        state="ERROR",
        next_action=f"エラー: {error}",
    )
    
    chat_id = mission["chat_id"]
    message_id = mission["message_id"]
    
    # Add retry buttons if allowed
    buttons = make_retry_buttons(mission_id) if allow_retry else None
    
    edit_message(
        chat_id=chat_id,
        message_id=message_id,
        message=message,
        buttons=buttons,
    )
    
    # Update reaction to ❌
    react_to_message(chat_id=chat_id, message_id=message_id, emoji="❌")
    
    _save_mission(mission_id, mission)
    
    return {"ok": True, "mission_id": mission_id, "state": "ERROR"}
