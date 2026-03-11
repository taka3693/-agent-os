#!/usr/bin/env python3
"""Step103: Cost-Aware Execution Policy

Selects an execution policy tier (cheap / balanced / thorough) based on
complexity, failure history, partial history, budget remaining, and metrics.

The selected policy controls:
- allow_orchestration: whether orchestration is permitted
- allow_parallel: whether parallel execution is permitted
- max_chain_override: max skill chain length (None = use router default)
- retry_override: max retries for this execution (None = use scheduler default)
- fail_fast: stop on first error (True) vs continue_on_error (False)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Policy tiers
# ---------------------------------------------------------------------------
POLICY_CHEAP = "cheap"
POLICY_BALANCED = "balanced"
POLICY_THOROUGH = "thorough"

VALID_POLICIES = (POLICY_CHEAP, POLICY_BALANCED, POLICY_THOROUGH)


# ---------------------------------------------------------------------------
# Policy definitions
# ---------------------------------------------------------------------------

_POLICY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    POLICY_CHEAP: {
        "allow_orchestration": False,
        "allow_parallel": False,
        "max_chain_override": 1,
        "retry_override": 1,
        "fail_fast": True,
        "continue_on_error": False,
    },
    POLICY_BALANCED: {
        "allow_orchestration": False,
        "allow_parallel": True,
        "max_chain_override": 2,
        "retry_override": 2,
        "fail_fast": False,
        "continue_on_error": False,
    },
    POLICY_THOROUGH: {
        "allow_orchestration": True,
        "allow_parallel": True,
        "max_chain_override": None,  # use router default
        "retry_override": 3,
        "fail_fast": False,
        "continue_on_error": True,
    },
}


def get_policy_defaults(tier: str) -> Dict[str, Any]:
    """Return a copy of the defaults for the given tier."""
    if tier not in _POLICY_DEFAULTS:
        tier = POLICY_BALANCED
    return dict(_POLICY_DEFAULTS[tier])


# ---------------------------------------------------------------------------
# Tier selection logic
# ---------------------------------------------------------------------------

def select_policy_tier(
    complexity: str,
    budget: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    failure_history: Optional[Dict[str, int]] = None,
) -> str:
    """Select execution policy tier based on context.

    Rules (evaluated in order; first match wins):
    1. Low budget remaining → cheap
    2. High failure history → cheap (suppress expensive retries)
    3. Complex task + healthy budget + low failures → thorough
    4. Otherwise → balanced

    Args:
        complexity: 'simple', 'moderate', or 'complex'
        budget: Task budget dict
        metrics: Task metrics dict
        failure_history: {skill: failure_count}

    Returns:
        One of 'cheap', 'balanced', 'thorough'
    """
    budget = budget or {}
    metrics = metrics or {}
    failure_history = failure_history or {}

    # 1. Low budget → cheap
    max_runs = budget.get("max_worker_runs", 10)
    spent_runs = budget.get("spent_worker_runs", 0)
    remaining_runs = max_runs - spent_runs

    max_subtasks = budget.get("max_subtasks", 5)
    spent_subtasks = budget.get("spent_subtasks", 0)
    remaining_subtasks = max_subtasks - spent_subtasks

    budget_limit_hits = metrics.get("budget_limit_hits", 0)

    if remaining_runs <= 2 or remaining_subtasks <= 1 or budget_limit_hits >= 2:
        return POLICY_CHEAP

    # 2. High failure history → cheap
    total_failures = sum(failure_history.values())
    failed_steps = metrics.get("failed_steps", 0)
    if total_failures >= 5 or failed_steps >= 5:
        return POLICY_CHEAP

    # 3. Complex + healthy budget + low failures → thorough
    if (
        complexity == "complex"
        and remaining_runs >= 5
        and remaining_subtasks >= 3
        and total_failures < 3
        and failed_steps < 3
    ):
        return POLICY_THOROUGH

    # 4. Default
    return POLICY_BALANCED


# ---------------------------------------------------------------------------
# Policy builder
# ---------------------------------------------------------------------------

def build_execution_policy(
    tier: str,
    complexity: str,
    partial_runs: int = 0,
    allow_critique_boost: bool = True,
) -> Dict[str, Any]:
    """Build the full execution policy dict for the given tier.

    Post-processes the default settings based on runtime context.

    Args:
        tier: Policy tier ('cheap', 'balanced', 'thorough')
        complexity: Complexity estimate
        partial_runs: Number of partial runs observed
        allow_critique_boost: Whether to allow critique/decision addition

    Returns:
        Execution policy dict
    """
    policy = get_policy_defaults(tier)
    policy["tier"] = tier
    policy["complexity"] = complexity

    # Thorough: allow critique/decision reinforcement on partials
    if tier == POLICY_THOROUGH and allow_critique_boost and partial_runs >= 2:
        policy["critique_boost"] = True
        policy["decision_boost"] = True
    else:
        policy["critique_boost"] = False
        policy["decision_boost"] = False

    # Simple tasks never get orchestration regardless of tier
    if complexity == "simple":
        policy["allow_orchestration"] = False
        policy["allow_parallel"] = False

    return policy


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def apply_execution_policy(
    route_result: Dict[str, Any],
    text: str,
    task_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Derive and attach an execution policy to a route result.

    Args:
        route_result: Output from build_route_result() or apply_routing_policy()
        text: Original query text
        task_context: Optional dict with keys:
            - complexity: pre-computed complexity (or derived from routing_policy)
            - budget: task budget dict
            - metrics: task metrics dict
            - failure_history: {skill: count}

    Returns:
        route_result extended with 'execution_policy' key
    """
    result = dict(route_result)
    ctx = task_context or {}

    # Derive complexity from routing_policy if available
    routing_pol = result.get("routing_policy", {})
    complexity = ctx.get("complexity") or routing_pol.get("complexity", "moderate")

    budget = ctx.get("budget", {})
    metrics = ctx.get("metrics", {})
    failure_history = ctx.get("failure_history", {})
    partial_runs = metrics.get("partial_runs", 0)

    # Select tier
    tier = select_policy_tier(
        complexity=complexity,
        budget=budget,
        metrics=metrics,
        failure_history=failure_history,
    )

    # Build policy
    policy = build_execution_policy(
        tier=tier,
        complexity=complexity,
        partial_runs=partial_runs,
    )

    # Apply max_chain_override to skill chain if set
    override = policy.get("max_chain_override")
    if override is not None:
        current_chain = result.get("selected_skills", [])
        trimmed = current_chain[:override]
        if trimmed:
            result["selected_skills"] = trimmed
            result["selected_skill"] = trimmed[0]
            if "pipeline" in result:
                result["pipeline"] = dict(result["pipeline"])
                result["pipeline"]["skill_chain"] = trimmed
                result["pipeline"]["chain_length"] = len(trimmed)

    result["execution_policy"] = policy
    return result
