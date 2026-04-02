#!/usr/bin/env python3
"""MISO-integrated orchestrator wrapper

Wraps run_orchestration to automatically send MISO status updates.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.orchestrator import run_orchestration, ROLE_COORDINATOR
from miso.bridge import (
    start_mission,
    update_mission,
    complete_mission,
    fail_mission,
    request_approval,
)

# Default MISO chat_id (Telegram) - can be overridden
DEFAULT_MISO_CHAT_ID = "6474742983"


def run_orchestration_with_miso(
    task: Dict[str, Any],
    decompose_fn: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
    worker_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    merge_fn: Optional[Callable[[Dict[str, Any], List[Dict[str, Any]]], Dict[str, Any]]] = None,
    max_workers_per_task: int = 3,
    max_orchestration_depth: int = 1,
    task_path: Optional[Path] = None,
    budget: Optional[Dict[str, Any]] = None,
    miso_enabled: bool = True,
    miso_chat_id: str = DEFAULT_MISO_CHAT_ID,
) -> Dict[str, Any]:
    """
    Run orchestration with MISO mission control visibility.
    
    Args:
        task: The parent task
        decompose_fn: Coordinator decomposition function
        worker_fn: Worker execution function (wrapped to report progress)
        merge_fn: Optional result merge function
        max_workers_per_task: Max concurrent workers
        max_orchestration_depth: Recursion depth limit
        task_path: Optional path to persist state
        budget: Optional budget overrides
        miso_enabled: Whether to send MISO updates
        miso_chat_id: Telegram chat ID for MISO
        
    Returns:
        Final task state with miso_mission_id
    """
    task_name = task.get("name", task.get("task_id", "unknown"))
    goal = task.get("goal", task.get("description", task_name))
    
    mission_id = None
    
    # --- MISO: Start mission ---
    if miso_enabled:
        try:
            result = start_mission(
                chat_id=miso_chat_id,
                mission_name=task_name,
                goal=goal,
                agents=[],  # Will be populated after decomposition
            )
            mission_id = result.get("mission_id")
            task["miso_mission_id"] = mission_id
        except Exception as e:
            # Don't fail task if MISO fails
            task.setdefault("warnings", []).append(f"MISO start failed: {e}")
    
    # --- Wrap worker_fn to report progress ---
    completed_count = [0]  # Use list for closure mutation
    total_count = [0]
    
    def worker_with_miso(subtask: Dict[str, Any]) -> Dict[str, Any]:
        result = worker_fn(subtask)
        completed_count[0] += 1
        
        if miso_enabled and mission_id:
            try:
                agents_status = []
                for i in range(total_count[0]):
                    if i < completed_count[0]:
                        agents_status.append({
                            "label": f"worker-{i+1}",
                            "status": "✓ done" if i < completed_count[0] - 1 else result.get("status", "done"),
                        })
                    else:
                        agents_status.append({
                            "label": f"worker-{i+1}",
                            "status": "pending",
                        })
                
                update_mission(
                    mission_id=mission_id,
                    state="PARTIAL" if completed_count[0] < total_count[0] else "RUNNING",
                    agents=agents_status,
                    next_action=f"Completed {completed_count[0]}/{total_count[0]} workers",
                )
            except Exception:
                pass  # Silent fail for MISO updates
        
        return result
    
    # --- Wrap decompose_fn to capture subtask count ---
    def decompose_with_count(t: Dict[str, Any]) -> List[Dict[str, Any]]:
        subtasks = decompose_fn(t)
        total_count[0] = len(subtasks)
        
        if miso_enabled and mission_id and subtasks:
            try:
                agents = [{"label": f"worker-{i+1}", "status": "pending"} for i in range(len(subtasks))]
                update_mission(
                    mission_id=mission_id,
                    state="RUNNING",
                    agents=agents,
                    next_action=f"Executing {len(subtasks)} subtasks",
                )
            except Exception:
                pass
        
        return subtasks
    
    # --- Run orchestration ---
    try:
        result = run_orchestration(
            task=task,
            decompose_fn=decompose_with_count,
            worker_fn=worker_with_miso,
            merge_fn=merge_fn,
            max_workers_per_task=max_workers_per_task,
            max_orchestration_depth=max_orchestration_depth,
            task_path=task_path,
            budget=budget,
        )
        
        # --- MISO: Complete or fail ---
        if miso_enabled and mission_id:
            final_status = result.get("status", "unknown")
            try:
                if final_status == "completed":
                    complete_mission(
                        mission_id=mission_id,
                        summary=f"Task completed: {task_name}",
                        artifacts=result.get("orchestration_result", {}).get("merged_output", []),
                    )
                elif final_status in ("failed", "error"):
                    fail_mission(
                        mission_id=mission_id,
                        error=result.get("error", "Unknown error"),
                    )
                elif final_status == "partial":
                    update_mission(
                        mission_id=mission_id,
                        state="PARTIAL",
                        next_action="Some workers failed, review needed",
                    )
            except Exception as e:
                result.setdefault("warnings", []).append(f"MISO complete failed: {e}")
        
        return result
        
    except Exception as e:
        # --- MISO: Error ---
        if miso_enabled and mission_id:
            try:
                fail_mission(mission_id=mission_id, error=str(e))
            except Exception:
                pass
        raise


# Convenience function for simple tasks
def run_task_with_miso_report(
    task_name: str,
    goal: str,
    execute_fn: Callable[[], Dict[str, Any]],
    chat_id: str = DEFAULT_MISO_CHAT_ID,
) -> Dict[str, Any]:
    """
    Simple wrapper for single-step tasks with MISO reporting.
    
    Usage:
        result = run_task_with_miso_report(
            task_name="Fix bug #123",
            goal="Resolve the timeout issue",
            execute_fn=lambda: do_work(),
        )
    """
    mission_id = None
    
    try:
        # Start
        result = start_mission(
            chat_id=chat_id,
            mission_name=task_name,
            goal=goal,
            agents=[{"label": "executor", "status": "starting"}],
        )
        mission_id = result.get("mission_id")
        
        # Update to running
        update_mission(
            mission_id=mission_id,
            state="RUNNING",
            agents=[{"label": "executor", "status": "executing..."}],
        )
        
        # Execute
        exec_result = execute_fn()
        
        # Complete
        complete_mission(
            mission_id=mission_id,
            summary=exec_result.get("summary", "Task completed"),
            artifacts=exec_result.get("artifacts", []),
        )
        
        return {"ok": True, "mission_id": mission_id, "result": exec_result}
        
    except Exception as e:
        if mission_id:
            try:
                fail_mission(mission_id=mission_id, error=str(e))
            except Exception:
                pass
        return {"ok": False, "mission_id": mission_id, "error": str(e)}
