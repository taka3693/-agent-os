#!/usr/bin/env python3
"""Step94/95: Task Memory

Provides structured working memory for tasks:
- Summary of execution progress
- Decisions made during execution
- Open questions to resolve
- Next actions to take
- Memory size limits to prevent bloat
- Compaction and retrieval policies
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    """Return current timestamp in ISO 8601 format."""
    return _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Atomically write JSON to avoid partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as tmp:
        tmp.write(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _load_task(path: Path) -> Dict[str, Any]:
    """Load task JSON with error handling."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# Memory size limits
MAX_SUMMARY_LENGTH = 500
MAX_DECISIONS = 10
MAX_OPEN_QUESTIONS = 10
MAX_NEXT_ACTIONS = 10
MEMORY_VERSION = 2


def _init_memory() -> Dict[str, Any]:
    """Initialize empty memory section."""
    return {
        "summary": "",
        "decisions": [],
        "open_questions": [],
        "next_actions": [],
        "updated_at": _now_iso(),
        "version": MEMORY_VERSION,
        "compacted_at": None,
        "compaction_count": 0,
    }


def _ensure_memory(task: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure task has memory section with defaults."""
    task = dict(task)
    if "memory" not in task or not isinstance(task.get("memory"), dict):
        task["memory"] = _init_memory()
    else:
        defaults = _init_memory()
        for key, value in defaults.items():
            if key not in task["memory"]:
                task["memory"][key] = value
    return task


def _truncate_summary(summary: str, max_length: int = MAX_SUMMARY_LENGTH) -> str:
    """Truncate summary to max length."""
    if not summary:
        return ""
    if len(summary) <= max_length:
        return summary
    return summary[:max_length - 3] + "..."


def _dedupe_and_limit(items: List[str], max_items: int = 10) -> List[str]:
    """Deduplicate and limit list items."""
    if not items:
        return []

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for item in items:
        if isinstance(item, str) and item not in seen:
            seen.add(item)
            unique.append(item)

    # Limit to max_items
    return unique[:max_items]


def update_memory(
    task: Dict[str, Any],
    summary: str | None = None,
    decisions: List[str] | None = None,
    open_questions: List[str] | None = None,
    next_actions: List[str] | None = None,
    append: bool = True,
) -> Dict[str, Any]:
    """Update task memory with new information.

    Args:
        task: Task to update
        summary: New summary text (appended if append=True)
        decisions: New decisions (appended if append=True)
        open_questions: New questions (appended if append=True)
        next_actions: New actions (appended if append=True)
        append: If True, append to existing; if False, replace

    Returns:
        Updated task with memory
    """
    task = _ensure_memory(task)
    task["memory"] = dict(task["memory"])

    now = _now_iso()
    task["memory"]["updated_at"] = now
    task["memory"]["version"] = MEMORY_VERSION

    # Update summary
    if summary is not None:
        if append and task["memory"]["summary"]:
            # Append with separator
            new_summary = task["memory"]["summary"] + " | " + summary
        else:
            new_summary = summary
        task["memory"]["summary"] = _truncate_summary(new_summary)

    # Update decisions
    if decisions is not None:
        if append:
            existing = task["memory"].get("decisions", [])
            new_decisions = existing + list(decisions)
        else:
            new_decisions = list(decisions)
        task["memory"]["decisions"] = _dedupe_and_limit(new_decisions, MAX_DECISIONS)

    # Update open_questions
    if open_questions is not None:
        if append:
            existing = task["memory"].get("open_questions", [])
            new_questions = existing + list(open_questions)
        else:
            new_questions = list(open_questions)
        task["memory"]["open_questions"] = _dedupe_and_limit(new_questions, MAX_OPEN_QUESTIONS)

    # Update next_actions
    if next_actions is not None:
        if append:
            existing = task["memory"].get("next_actions", [])
            new_actions = existing + list(next_actions)
        else:
            new_actions = list(next_actions)
        task["memory"]["next_actions"] = _dedupe_and_limit(new_actions, MAX_NEXT_ACTIONS)

    return task


def extract_memory_from_step_result(step_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract memory updates from a step result.

    Args:
        step_result: Step execution result

    Returns:
        Dict with memory fields to update
    """
    output = step_result.get("output", {})
    if not isinstance(output, dict):
        output = {}

    memory_update = {}

    # Extract summary from output
    if "summary" in output:
        memory_update["summary"] = output["summary"]
    elif "result" in output and isinstance(output["result"], dict):
        if "summary" in output["result"]:
            memory_update["summary"] = output["result"]["summary"]

    # Extract decisions
    if "decisions" in output:
        memory_update["decisions"] = output["decisions"]
    elif "result" in output and isinstance(output["result"], dict):
        if "decisions" in output["result"]:
            memory_update["decisions"] = output["result"]["decisions"]

    # Extract open_questions
    if "open_questions" in output:
        memory_update["open_questions"] = output["open_questions"]
    elif "questions" in output:
        memory_update["open_questions"] = output["questions"]
    elif "result" in output and isinstance(output["result"], dict):
        if "open_questions" in output["result"]:
            memory_update["open_questions"] = output["result"]["open_questions"]

    # Extract next_actions
    if "next_actions" in output:
        memory_update["next_actions"] = output["next_actions"]
    elif "actions" in output:
        memory_update["next_actions"] = output["actions"]
    elif "result" in output and isinstance(output["result"], dict):
        if "next_actions" in output["result"]:
            memory_update["next_actions"] = output["result"]["next_actions"]

    return memory_update


def update_memory_from_step(
    task: Dict[str, Any],
    step_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Update task memory from a step execution result.

    Args:
        task: Task to update
        step_result: Step execution result

    Returns:
        Updated task with memory
    """
    memory_update = extract_memory_from_step_result(step_result)

    if not memory_update:
        # Just update timestamp
        task = _ensure_memory(task)
        task["memory"]["updated_at"] = _now_iso()
        return task

    return update_memory(task, **memory_update, append=True)


def preserve_memory_on_recovery(task: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure memory is preserved during recovery.

    Args:
        task: Task being recovered

    Returns:
        Task with memory preserved
    """
    task = _ensure_memory(task)

    # Run compaction first
    task = compact_memory(task)

    # Add recovery note to memory
    recovery_note = f"Recovered at {_now_iso()}"
    existing_summary = task["memory"].get("summary", "")
    if existing_summary:
        task["memory"]["summary"] = _truncate_summary(
            existing_summary + " | " + recovery_note
        )
    else:
        task["memory"]["summary"] = recovery_note

    task["memory"]["updated_at"] = _now_iso()

    return task


# =============================================================================
# Step95: Memory Compaction and Retrieval Policy
# =============================================================================

# Retrieval policy: which memory fields each skill should reference
RETRIEVAL_POLICY = {
    "decision": ["summary", "decisions", "open_questions"],
    "critique": ["summary", "open_questions", "next_actions"],
    "execution": ["summary", "decisions", "next_actions"],
    "retrospective": ["summary", "decisions", "open_questions", "next_actions"],
    "research": ["summary", "decisions", "open_questions"],
    "experiment": ["summary", "decisions", "next_actions"],
}


def get_retrieval_policy(skill: str) -> List[str]:
    """Get memory fields to retrieve for a given skill.

    Args:
        skill: Skill name

    Returns:
        List of memory field names to retrieve
    """
    return RETRIEVAL_POLICY.get(skill, ["summary"])


def retrieve_memory_for_skill(task: Dict[str, Any], skill: str) -> Dict[str, Any]:
    """Retrieve memory fields relevant to a skill.

    Args:
        task: Task with memory
        skill: Skill name

    Returns:
        Dict with relevant memory fields
    """
    task = _ensure_memory(task)
    fields = get_retrieval_policy(skill)

    result = {}
    for field in fields:
        if field in task["memory"]:
            result[field] = task["memory"][field]

    return result


def mark_question_solved(question: str) -> str:
    """Mark a question as solved (prefix with [SOLVED]).

    Args:
        question: Question text

    Returns:
        Marked question
    """
    if question.startswith("[SOLVED]"):
        return question
    return f"[SOLVED] {question}"


def mark_action_completed(action: str) -> str:
    """Mark an action as completed (prefix with [DONE]).

    Args:
        action: Action text

    Returns:
        Marked action
    """
    if action.startswith("[DONE]"):
        return action
    return f"[DONE] {action}"


def _is_solved(question: str) -> bool:
    """Check if question is marked as solved."""
    return question.startswith("[SOLVED]")


def _is_completed(action: str) -> bool:
    """Check if action is marked as completed."""
    return action.startswith("[DONE]")


def _merge_conflicting_decisions(decisions: List[str]) -> List[str]:
    """Merge conflicting or duplicate decisions.

    Detects patterns like:
    - Exact duplicates
    - "Use X" and "Use Y" -> "Use X or Y (reconsidered)"
    - Negation patterns

    Args:
        decisions: List of decisions

    Returns:
        Merged decisions
    """
    if not decisions:
        return []

    # Simple dedupe first
    seen = set()
    unique = []
    for d in decisions:
        if isinstance(d, str) and d not in seen:
            seen.add(d)
            unique.append(d)

    # Detect and merge simple conflicts (same prefix, different values)
    # For now, just return deduped list
    # Future: could detect "Use A" vs "Use B" patterns
    return unique[:MAX_DECISIONS]


def compact_memory(task: Dict[str, Any]) -> Dict[str, Any]:
    """Compact memory by removing stale entries.

    - Remove solved open_questions
    - Remove completed next_actions
    - Merge conflicting/duplicate decisions
    - Resummarize if needed

    Args:
        task: Task to compact

    Returns:
        Task with compacted memory
    """
    task = _ensure_memory(task)
    task["memory"] = dict(task["memory"])

    now = _now_iso()

    # Remove solved questions
    questions = task["memory"].get("open_questions", [])
    unsolved = [q for q in questions if not _is_solved(q)]
    task["memory"]["open_questions"] = unsolved[:MAX_OPEN_QUESTIONS]

    # Remove completed actions
    actions = task["memory"].get("next_actions", [])
    pending = [a for a in actions if not _is_completed(a)]
    task["memory"]["next_actions"] = pending[:MAX_NEXT_ACTIONS]

    # Merge conflicting decisions
    decisions = task["memory"].get("decisions", [])
    task["memory"]["decisions"] = _merge_conflicting_decisions(decisions)

    # Truncate summary if needed
    summary = task["memory"].get("summary", "")
    task["memory"]["summary"] = _truncate_summary(summary)

    # Update compaction metadata
    task["memory"]["compacted_at"] = now
    task["memory"]["compaction_count"] = task["memory"].get("compaction_count", 0) + 1
    task["memory"]["updated_at"] = now

    return task


def compact_memory_on_resume(task: Dict[str, Any]) -> Dict[str, Any]:
    """Compact memory when resuming a task.

    Args:
        task: Task being resumed

    Returns:
        Task with compacted memory
    """
    return compact_memory(task)


def solve_question(task: Dict[str, Any], question_index: int) -> Dict[str, Any]:
    """Mark a specific question as solved.

    Args:
        task: Task with memory
        question_index: 0-based index of question to solve

    Returns:
        Updated task
    """
    task = _ensure_memory(task)
    task["memory"] = dict(task["memory"])

    questions = task["memory"].get("open_questions", [])
    if 0 <= question_index < len(questions):
        questions[question_index] = mark_question_solved(questions[question_index])
        task["memory"]["open_questions"] = questions
        task["memory"]["updated_at"] = _now_iso()

    return task


def complete_action(task: Dict[str, Any], action_index: int) -> Dict[str, Any]:
    """Mark a specific action as completed.

    Args:
        task: Task with memory
        action_index: 0-based index of action to complete

    Returns:
        Updated task
    """
    task = _ensure_memory(task)
    task["memory"] = dict(task["memory"])

    actions = task["memory"].get("next_actions", [])
    if 0 <= action_index < len(actions):
        actions[action_index] = mark_action_completed(actions[action_index])
        task["memory"]["next_actions"] = actions
        task["memory"]["updated_at"] = _now_iso()

    return task


def get_memory_summary(task: Dict[str, Any]) -> str:
    """Get human-readable memory summary.

    Args:
        task: Task with memory

    Returns:
        Formatted memory summary
    """
    task = _ensure_memory(task)
    memory = task["memory"]

    lines = []

    if memory.get("summary"):
        lines.append(f"要約: {memory['summary']}")

    decisions = memory.get("decisions", [])
    if decisions:
        lines.append(f"決定事項 ({len(decisions)}件):")
        for i, d in enumerate(decisions[:3], 1):
            lines.append(f"  {i}. {d}")
        if len(decisions) > 3:
            lines.append(f"  ... 他{len(decisions) - 3}件")

    questions = memory.get("open_questions", [])
    if questions:
        lines.append(f"未解決 ({len(questions)}件):")
        for i, q in enumerate(questions[:3], 1):
            lines.append(f"  {i}. {q}")

    actions = memory.get("next_actions", [])
    if actions:
        lines.append(f"次のアクション ({len(actions)}件):")
        for i, a in enumerate(actions[:3], 1):
            lines.append(f"  {i}. {a}")

    if not lines:
        return "メモリなし"

    return "\n".join(lines)
