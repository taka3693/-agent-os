#!/usr/bin/env python3
"""
spawn_with_miso — Launch subagents with MISO visibility

Combines sessions_spawn with MISO mission control:
1. Create MISO mission (INIT message)
2. Spawn subagent(s) with label
3. Track completion via subagent events
4. Update MISO on state changes
"""

from __future__ import annotations
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from miso.bridge import (
    start_mission,
    update_mission,
    request_approval,
    complete_mission,
    fail_mission,
    _load_mission,
    _save_mission,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def generate_mission_id() -> str:
    """Generate unique mission ID"""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"mission-{ts}-{uuid.uuid4().hex[:6]}"


class MisoSpawner:
    """
    Orchestrates subagent spawning with MISO visibility.
    
    Usage:
        spawner = MisoSpawner(
            chat_id="6474742983",
            mission_name="PR review",
            goal="Review and approve PR #123",
        )
        spawner.add_agent("reviewer", "Review code changes")
        spawner.add_agent("security", "Check for security issues")
        result = spawner.start()
    """
    
    def __init__(
        self,
        chat_id: str,
        mission_name: str,
        goal: str,
        mission_id: Optional[str] = None,
    ):
        self.chat_id = chat_id
        self.mission_name = mission_name
        self.goal = goal
        self.mission_id = mission_id or generate_mission_id()
        self.agents: List[Dict[str, Any]] = []
        self._started = False
        self._message_id: Optional[str] = None
    
    def add_agent(
        self,
        name: str,
        task: str,
        display_label: Optional[str] = None,
    ) -> "MisoSpawner":
        """Add an agent to the mission"""
        self.agents.append({
            "name": name,
            "label": name,  # Used for sessions_spawn label
            "display_label": display_label or name,
            "task": task,
            "status": "INIT",
        })
        return self
    
    def start(self) -> Dict[str, Any]:
        """
        Start the mission:
        1. Send MISO INIT message
        2. Return mission info for subsequent spawns
        
        Note: Actual sessions_spawn calls should be done by the caller
        since we don't have direct access to the OpenClaw runtime here.
        """
        if self._started:
            return {"ok": False, "error": "mission already started"}
        
        if not self.agents:
            return {"ok": False, "error": "no agents added"}
        
        result = start_mission(
            mission_id=self.mission_id,
            mission_name=self.mission_name,
            goal=self.goal,
            chat_id=self.chat_id,
            agents=self.agents,
        )
        
        if result.get("ok"):
            self._started = True
            self._message_id = result.get("message_id")
        
        return {
            **result,
            "mission_id": self.mission_id,
            "agents": [
                {
                    "name": a["name"],
                    "label": a["label"],
                    "task": a["task"],
                }
                for a in self.agents
            ],
        }
    
    def attach_agent(
        self,
        label: str,
        session_id: Optional[str] = None,
        detail: str = "準備完了",
    ) -> Dict[str, Any]:
        """
        Mark an agent as attached/running.
        Call this after sessions_spawn returns.
        """
        mission = _load_mission(self.mission_id)
        if not mission:
            return {"ok": False, "error": "mission not found"}
        
        # Update agent status
        for agent in mission.get("agents", []):
            if agent.get("label") == label or agent.get("name") == label:
                agent["status"] = "RUNNING"
                agent["detail"] = detail
                if session_id:
                    agent["session_id"] = session_id
                break
        
        # Check if all agents are running
        all_running = all(
            a.get("status") in ("RUNNING", "COMPLETE")
            for a in mission.get("agents", [])
        )
        
        new_state = "RUNNING" if all_running else "PARTIAL"
        
        return update_mission(
            mission_id=self.mission_id,
            state=new_state,
            agents=mission.get("agents", []),
            next_action="処理中",
        )
    
    def complete_agent(
        self,
        label: str,
        summary: str = "",
    ) -> Dict[str, Any]:
        """
        Mark an agent as complete.
        Call this when subagent completion is detected.
        """
        mission = _load_mission(self.mission_id)
        if not mission:
            return {"ok": False, "error": "mission not found"}
        
        # Update agent status
        for agent in mission.get("agents", []):
            if agent.get("label") == label or agent.get("name") == label:
                agent["status"] = "COMPLETE"
                agent["detail"] = summary or "完了"
                break
        
        # Check overall progress
        agents = mission.get("agents", [])
        done_count = sum(1 for a in agents if a.get("status") == "COMPLETE")
        total = len(agents)
        
        if done_count == total:
            new_state = "COMPLETE"
            next_action = "全エージェント完了"
        else:
            new_state = "PARTIAL"
            next_action = f"{done_count}/{total} 完了"
        
        return update_mission(
            mission_id=self.mission_id,
            state=new_state,
            agents=agents,
            next_action=next_action,
        )
    
    def fail_agent(
        self,
        label: str,
        error: str,
    ) -> Dict[str, Any]:
        """
        Mark an agent as failed.
        """
        mission = _load_mission(self.mission_id)
        if not mission:
            return {"ok": False, "error": "mission not found"}
        
        for agent in mission.get("agents", []):
            if agent.get("label") == label or agent.get("name") == label:
                agent["status"] = "ERROR"
                agent["detail"] = error
                break
        
        return fail_mission(
            mission_id=self.mission_id,
            error=f"{label}: {error}",
            allow_retry=True,
        )
    
    def request_approval_for_task(
        self,
        task_id: str,
        target: str,
        handler: str,
        reason: str,
    ) -> Dict[str, Any]:
        """
        Transition mission to AWAITING_APPROVAL for a task.
        """
        return request_approval(
            mission_id=self.mission_id,
            task_id=task_id,
            target=target,
            handler=handler,
            reason=reason,
        )


def spawn_single_with_miso(
    chat_id: str,
    task: str,
    agent_name: str = "worker",
    mission_name: Optional[str] = None,
    goal: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function for single-agent spawn with MISO.
    
    Returns mission info. Caller should use the label for sessions_spawn.
    """
    spawner = MisoSpawner(
        chat_id=chat_id,
        mission_name=mission_name or f"{agent_name} task",
        goal=goal or task[:50],
    )
    spawner.add_agent(agent_name, task)
    return spawner.start()


if __name__ == "__main__":
    # Test usage
    import argparse
    parser = argparse.ArgumentParser(description="Spawn with MISO")
    parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    parser.add_argument("--mission", required=True, help="Mission name")
    parser.add_argument("--goal", required=True, help="Mission goal")
    parser.add_argument("--agent", action="append", nargs=2, metavar=("NAME", "TASK"), help="Agent name and task")
    args = parser.parse_args()
    
    spawner = MisoSpawner(
        chat_id=args.chat_id,
        mission_name=args.mission,
        goal=args.goal,
    )
    
    for name, task in (args.agent or []):
        spawner.add_agent(name, task)
    
    result = spawner.start()
    print(json.dumps(result, ensure_ascii=False, indent=2))
