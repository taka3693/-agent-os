#!/usr/bin/env python3
"""Step102: Policy-Driven Routing Refinement

Rule-based policy layer that adjusts routing decisions based on:
- Task input complexity
- Task memory (summary, decisions)
- Failure / partial history (metrics)
- Budget remaining
- Orchestration eligibility

This module does NOT replace the existing router — it post-processes
the route result produced by build_route_result().
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .constants import ROUTER_MAX_CHAIN

# ---------------------------------------------------------------------------
# Complexity heuristic
# ---------------------------------------------------------------------------

# Simple tasks: short text, single concern
_SIMPLE_CHAR_THRESHOLD = 80
# Complex tasks: long text OR multi-keyword
_COMPLEX_CHAR_THRESHOLD = 300

# Skills that indicate complexity when chained
_COMPLEX_SKILLS = {"critique", "decision", "experiment"}


def estimate_complexity(text: str, skill_chain: List[str]) -> str:
    """Classify task complexity as 'simple', 'moderate', or 'complex'.

    Args:
        text: Input query text
        skill_chain: Skills detected by the classifier

    Returns:
        One of 'simple', 'moderate', 'complex'
    """
    text_len = len(text or "")
    chain_len = len(skill_chain)
    has_complex_skill = bool(set(skill_chain) & _COMPLEX_SKILLS)

    if text_len <= _SIMPLE_CHAR_THRESHOLD and chain_len <= 1:
        return "simple"
    if text_len >= _COMPLEX_CHAR_THRESHOLD or chain_len >= 3:
        return "complex"
    if has_complex_skill and chain_len >= 2:
        return "complex"
    return "moderate"


# ---------------------------------------------------------------------------
# Failure avoidance
# ---------------------------------------------------------------------------

def get_failed_skills(metrics: Dict[str, Any], events: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count per-skill failures from event history.

    Returns:
        Dict mapping skill name to failure count
    """
    counts: Dict[str, int] = {}
    for evt in events:
        if evt.get("event_type") in ("worker_complete", "step_error") and \
           evt.get("status_after") in ("failed", "error"):
            # Try to extract skill from subtask_id or step_id
            sid = evt.get("subtask_id") or evt.get("step_id") or ""
            # Convention: subtask_id contains skill in some form
            # But we can also use a broader heuristic
            # For now, count any failure
            counts[sid] = counts.get(sid, 0) + 1
    return counts


def filter_failed_chains(
    skill_chain: List[str],
    failure_history: Dict[str, int],
    threshold: int = 3,
) -> List[str]:
    """Remove skills from the chain that have failed >= threshold times.

    Always keeps at least one skill (falls back to 'research').

    Args:
        skill_chain: Original skill chain
        failure_history: {skill_name: failure_count}
        threshold: Failure count above which a skill is demoted

    Returns:
        Filtered skill chain
    """
    filtered = [s for s in skill_chain if failure_history.get(s, 0) < threshold]
    if not filtered:
        filtered = ["research"]
    return filtered


# ---------------------------------------------------------------------------
# Partial-run reinforcement
# ---------------------------------------------------------------------------

def reinforce_for_partials(
    skill_chain: List[str],
    partial_runs: int,
    threshold: int = 2,
) -> List[str]:
    """When partial runs are high, add critique or decision for reinforcement.

    Args:
        skill_chain: Current chain
        partial_runs: Number of partial runs recorded
        threshold: Partials above which reinforcement kicks in

    Returns:
        Potentially augmented skill chain
    """
    if partial_runs < threshold:
        return skill_chain

    chain = list(skill_chain)

    # Add critique if not present
    if "critique" not in chain and len(chain) < ROUTER_MAX_CHAIN:
        chain.append("critique")

    # Add decision if not present and still room
    if "decision" not in chain and len(chain) < ROUTER_MAX_CHAIN:
        chain.append("decision")

    return chain[:ROUTER_MAX_CHAIN]


# ---------------------------------------------------------------------------
# Orchestration eligibility
# ---------------------------------------------------------------------------

def should_orchestrate(
    complexity: str,
    budget: Dict[str, Any],
    metrics: Dict[str, Any],
) -> bool:
    """Decide whether orchestration is appropriate.

    Rules:
    - Simple tasks: never orchestrate
    - Complex tasks with sufficient budget: eligible
    - High failure count: suppress orchestration

    Args:
        complexity: 'simple', 'moderate', or 'complex'
        budget: Budget dict from task
        metrics: Metrics dict from task

    Returns:
        True if orchestration is recommended
    """
    if complexity == "simple":
        return False

    # Check budget remaining
    max_subtasks = budget.get("max_subtasks", 5)
    spent_subtasks = budget.get("spent_subtasks", 0)
    if max_subtasks - spent_subtasks < 2:
        return False  # not enough budget

    max_worker_runs = budget.get("max_worker_runs", 10)
    spent_worker_runs = budget.get("spent_worker_runs", 0)
    if max_worker_runs - spent_worker_runs < 2:
        return False

    # High failure → suppress
    budget_limit_hits = metrics.get("budget_limit_hits", 0)
    failed_steps = metrics.get("failed_steps", 0)
    if budget_limit_hits >= 2 or failed_steps >= 5:
        return False

    if complexity == "complex":
        return True

    # Moderate: only if chain is multi-skill
    return False


# ---------------------------------------------------------------------------
# Budget-aware chain trimming
# ---------------------------------------------------------------------------

def trim_chain_for_budget(
    skill_chain: List[str],
    budget: Dict[str, Any],
) -> List[str]:
    """Shorten chain when budget is low.

    If remaining worker budget is <= 2, keep only the primary skill.

    Args:
        skill_chain: Current chain
        budget: Budget dict

    Returns:
        Potentially shortened chain
    """
    max_runs = budget.get("max_worker_runs", 10)
    spent_runs = budget.get("spent_worker_runs", 0)
    remaining = max_runs - spent_runs

    if remaining <= 2 and len(skill_chain) > 1:
        return skill_chain[:1]
    return skill_chain


# ---------------------------------------------------------------------------
# Top-level policy application
# ---------------------------------------------------------------------------

def apply_routing_policy(
    route_result: Dict[str, Any],
    text: str,
    task_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply policy adjustments to a route result.

    Args:
        route_result: Output from build_route_result()
        text: Original query text
        task_context: Optional dict with keys:
            - memory: task memory dict
            - metrics: task metrics dict
            - events: task events list
            - budget: task budget dict
            - failure_history: {skill: count}

    Returns:
        Adjusted route result (new dict, original not mutated)
    """
    result = dict(route_result)
    ctx = task_context or {}

    skill_chain = list(result.get("selected_skills", [result.get("selected_skill", "research")]))
    metrics = ctx.get("metrics", {})
    budget = ctx.get("budget", {})
    events = ctx.get("events", [])
    failure_history = ctx.get("failure_history", {})

    # 1. Estimate complexity
    complexity = estimate_complexity(text, skill_chain)

    # 2. Filter chains with high failure
    if failure_history:
        skill_chain = filter_failed_chains(skill_chain, failure_history)

    # 3. Reinforce for partials
    partial_runs = metrics.get("partial_runs", 0)
    skill_chain = reinforce_for_partials(skill_chain, partial_runs)

    # 4. Trim for budget
    if budget:
        skill_chain = trim_chain_for_budget(skill_chain, budget)

    # 5. Orchestration eligibility
    orchestrate = should_orchestrate(complexity, budget, metrics)

    # Update result
    result["selected_skill"] = skill_chain[0] if skill_chain else "research"
    result["selected_skills"] = skill_chain
    result["pipeline"]["skill_chain"] = skill_chain
    result["pipeline"]["chain_length"] = len(skill_chain)

    # Add policy metadata
    result["routing_policy"] = {
        "complexity": complexity,
        "orchestration_eligible": orchestrate,
        "chain_adjusted": skill_chain != route_result.get("selected_skills"),
        "adjustments_applied": [],
    }

    if failure_history:
        result["routing_policy"]["adjustments_applied"].append("failure_avoidance")
    if partial_runs >= 2:
        result["routing_policy"]["adjustments_applied"].append("partial_reinforcement")
    if budget and budget.get("max_worker_runs", 10) - budget.get("spent_worker_runs", 0) <= 2:
        result["routing_policy"]["adjustments_applied"].append("budget_trim")
    if orchestrate:
        result["routing_policy"]["adjustments_applied"].append("orchestration_eligible")

    return result
