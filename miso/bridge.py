"""MISO bridge — connects agent-os tasks to Telegram Mission Control"""

from __future__ import annotations
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
LOG_DIR = PROJECT_ROOT / "miso" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"bridge_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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


# Cost tracking
def log_mission_cost(
    mission_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> Dict[str, Any]:
    """Log mission cost (imported dynamically to avoid circular import)"""
    try:
        from miso.cost_tracker import calculate_cost, log_cost
        cost = calculate_cost(model, input_tokens, output_tokens)
        return log_cost(model, input_tokens, output_tokens, mission_id, cost)
    except Exception:
        return {"ok": False, "error": "cost tracking failed"}

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
        agents=[{"name": (a if isinstance(a, str) else a.get("name", f"担当{i+1}")), "status": "INIT"} for i, a in enumerate(agents)],
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
        "agents": [{"name": (a if isinstance(a, str) else a.get("name", f"担当{i+1}")), "status": "INIT", "label": (None if isinstance(a, str) else a.get("label"))} for i, a in enumerate(agents)],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    _save_mission(mission_id, mission_state)

    # Log mission start for cost tracking (0 tokens initially)
    log_mission_cost(mission_id, "unknown", 0, 0)

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


def update_agent_status(
    mission_id: str,
    agent_name: str,
    status: str,
    detail: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update status of a specific agent in a mission.

    Args:
        mission_id: Mission identifier
        agent_name: Name of the agent to update
        status: New status (INIT, RUNNING, DONE, ERROR, BLOCKED)
        detail: Optional detail message for the agent

    Returns:
        Dict with ok, mission_id, and updated agents list
    """
    mission = _load_mission(mission_id)
    if not mission:
        return {"ok": False, "error": "mission not found"}

    agents = mission.get("agents", [])
    agent_found = False

    # Find and update the agent
    for agent in agents:
        if agent.get("name") == agent_name:
            agent["status"] = status
            if detail is not None:
                agent["detail"] = detail
            agent_found = True
            logger.info(f"Updated agent {agent_name} status to {status}")
            break

    if not agent_found:
        logger.warning(f"Agent {agent_name} not found in mission {mission_id}")
        return {"ok": False, "error": f"agent not found: {agent_name}"}

    # Update mission with new agent states
    result = update_mission(
        mission_id=mission_id,
        agents=agents,
    )

    return {
        "ok": True,
        "mission_id": mission_id,
        "agent_name": agent_name,
        "status": status,
        "agents": agents,
    }


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
    model: str = "unknown",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> Dict[str, Any]:
    """
    Mark mission as COMPLETE.
    """
    # Load mission first to get chat_id for context check
    mission = _load_mission(mission_id)

    # Log cost if tokens are provided
    if input_tokens > 0 or output_tokens > 0:
        log_mission_cost(mission_id, model, input_tokens, output_tokens)

    # Update agent statuses
    agents = None
    if mission:
        agents = mission.get("agents", [])
        for a in agents:
            a["status"] = "COMPLETE"
            a["detail"] = "完了"

    # Update mission
    result = update_mission(
        mission_id=mission_id,
        state="COMPLETE",
        agents=agents,
        next_action=summary or "完了",
    )

    # Check context health after mission completion (if chat_id is available)
    if mission and mission.get("chat_id"):
        try:
            from miso.context_manager import send_context_warning

            # Use a default session_id for context tracking
            session_id = mission.get("session_id", "main")
            send_context_warning(session_id, mission["chat_id"])
        except Exception:
            # Context check is optional, don't fail if it errors
            pass

    return result


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


# === CLI Entry Point ===
def main():

    import argparse

    parser = argparse.ArgumentParser(description="MISO Bridge CLI")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # start_mission command
    start_parser = subparsers.add_parser("start_mission", help="Start a new mission")
    start_parser.add_argument("--mission-id", "--mission_id", required=True, dest="mission_id", help="Mission ID")
    start_parser.add_argument("--mission-name", "--mission_name", required=True, dest="mission_name", help="Mission name")
    start_parser.add_argument("--goal", required=True, help="Mission goal")
    start_parser.add_argument("--chat-id", "--chat_id", required=True, dest="chat_id", help="Telegram chat ID")
    start_parser.add_argument("--agents", required=True, help="Agents JSON string")

    # complete_mission command
    complete_parser = subparsers.add_parser("complete_mission", help="Complete a mission")
    complete_parser.add_argument("--mission-id", "--mission_id", required=True, dest="mission_id", help="Mission ID")
    complete_parser.add_argument("--summary", default="", help="Mission summary")
    complete_parser.add_argument("--model", default="unknown", help="Model used")
    complete_parser.add_argument("--input", type=int, default=0, help="Input tokens")
    complete_parser.add_argument("--output", type=int, default=0, help="Output tokens")

    # fail_mission command
    fail_parser = subparsers.add_parser("fail_mission", help="Fail a mission")
    fail_parser.add_argument("--mission-id", "--mission_id", required=True, dest="mission_id", help="Mission ID")
    fail_parser.add_argument("--error", required=True, help="Error message")

    args = parser.parse_args()

    result = {}

    if args.command == "start_mission":
        agents = json.loads(args.agents)
        result = start_mission(
            args.mission_id,
            args.mission_name,
            args.goal,
            args.chat_id,
            agents,
        )
    elif args.command == "complete_mission":
        result = complete_mission(
            args.mission_id,
            args.summary,
            model=args.model,
            input_tokens=args.input,
            output_tokens=args.output,
        )
    elif args.command == "fail_mission":
        result = fail_mission(args.mission_id, args.error)

    # Output result as JSON
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
