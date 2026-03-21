#!/usr/bin/env python3
"""Unified task factory for skill-based tasks.

Provides a single source of truth for creating queued tasks
that run through run_research_task.py and similar runners.

This factory is used for:
- research, decision, critique, retrospective skills
- follow-up task creation in chained execution

NOT used for:
- execution tasks (use bridge/route_to_task.py instead)
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from router.model_policy import resolve_model_for_skill


def utc_now() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_task_id(prefix: str = "task") -> str:
    """Generate a unique task ID.

    Format: {prefix}-YYYYMMDD-HHMMSS-ffffff-XXXXXX
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    rnd = secrets.token_hex(3)
    return f"{prefix}-{ts}-{rnd}"


def create_skill_task(
    skill: str,
    query: str,
    *,
    source: str = "agent_os",
    chain_count: int = 0,
    parent_task_id: Optional[str] = None,
    task_id: Optional[str] = None,
    route_reason: Optional[str] = None,
    allowed_skills: Optional[list] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a queued task dict for skill-based execution.

    Args:
        skill: The skill to execute (research, decision, critique, retrospective)
        query: The input query text
        source: Origin of the task (default: "agent_os")
        chain_count: Chain depth for follow-up tasks (default: 0)
        parent_task_id: Parent task ID for follow-up tasks (default: None)
        task_id: Custom task ID (default: auto-generated)
        route_reason: Reason for routing (default: None)
        allowed_skills: List of allowed skills (default: [skill])
        extra_fields: Additional fields to merge into task (default: None)
            These fields will NOT overwrite core fields if keys conflict.

    Returns:
        Task dict with standardized schema for run_research_task.py
    """
    ts = utc_now()
    actual_task_id = task_id or make_task_id()
    actual_allowed = allowed_skills if allowed_skills is not None else [skill]

    task: Dict[str, Any] = {
        "task_id": actual_task_id,
        "created_at": ts,
        "updated_at": ts,
        "selected_skill": skill,
        "input_text": query,
        "run_input": {"query": query},
        "status": "queued",
        "chain_count": chain_count,
        "model": resolve_model_for_skill(skill),
        "parent_task_id": parent_task_id,
        "source": source,
        "result": None,
        "error": None,
    }

    # Optional fields
    if route_reason is not None:
        task["route_reason"] = route_reason

    if actual_allowed != [skill]:
        task["allowed_skills"] = actual_allowed

    # Merge extra fields (do not overwrite core fields)
    if extra_fields:
        for key, value in extra_fields.items():
            if key not in task:
                task[key] = value

    return task


def create_followup_task(
    parent_task: Dict[str, Any],
    next_skill: str,
    query: str,
) -> Dict[str, Any]:
    """Create a follow-up task from a parent task.

    Convenience wrapper for create_skill_task() that extracts
    parent context automatically.

    Args:
        parent_task: The parent task dict
        next_skill: The skill for the follow-up task
        query: The query for the follow-up task

    Returns:
        Follow-up task dict with parent linkage
    """
    parent_id = parent_task.get("task_id") or parent_task.get("id")
    chain_count = int(parent_task.get("chain_count", 0)) + 1
    source = parent_task.get("source", "agent_os")

    task = create_skill_task(
        skill=next_skill,
        query=query,
        source=source,
        chain_count=chain_count,
        parent_task_id=parent_id,
    )

    # Add route_reason indicating chain origin
    task["route_reason"] = f"chained_from:{parent_id}"

    # Always include allowed_skills for schema compatibility with legacy code
    task["allowed_skills"] = [next_skill]

    return task
