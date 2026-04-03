#!/usr/bin/env python3
"""Centralized model resolution for agent-os skills.

Two-stage resolution: skill → role → model
- AgentOS defines skill → role mapping
- OpenClaw config defines role → model mapping (source of truth)

This module loads OpenClaw configuration and resolves models accordingly.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# OpenClaw config path
# ---------------------------------------------------------------------------

OPENCLAW_CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"


# ---------------------------------------------------------------------------
# Skill → Role mapping (AgentOS domain)
# ---------------------------------------------------------------------------

_SKILL_ROLE_MAP: Dict[str, str] = {
    "research": "primary",
    "decision": "primary",
    "execution": "subagent",
    "critique": "reviewer",
    "retrospective": "deep_reviewer",
}

_DEFAULT_ROLE = "primary"


# ---------------------------------------------------------------------------
# Fallback models (when OpenClaw config is unavailable)
# ---------------------------------------------------------------------------

_FALLBACK_MODEL_FOR_ROLE: Dict[str, str] = {
    "primary": "zai/glm-4.7",
    "subagent": "openrouter/moonshotai/kimi-k2.5",
    "reviewer": "anthropic/claude-opus-4-5",
    "deep_reviewer": "anthropic/claude-opus-4-5",
}

_DEFAULT_MODEL = "zai/glm-4.7"


# ---------------------------------------------------------------------------
# OpenClaw config loading
# ---------------------------------------------------------------------------

_cached_roles: Optional[Dict[str, str]] = None


def _clear_cache() -> None:
    """Clear cached roles (for testing)."""
    global _cached_roles
    _cached_roles = None


def load_openclaw_roles() -> Dict[str, str]:
    """Load role → model mapping from OpenClaw config.

    Resolution order:
    1. agents.defaults.roles.<role> (primary source)
    2. Legacy fallbacks:
       - primary → agents.defaults.model.primary
       - subagent → agents.defaults.subagents.model
    3. Hardcoded fallback

    Returns:
        Dict mapping role name to model identifier
    """
    global _cached_roles
    if _cached_roles is not None:
        return _cached_roles

    roles: Dict[str, str] = {}

    # Try to load OpenClaw config
    try:
        if OPENCLAW_CONFIG_PATH.exists():
            config = json.loads(OPENCLAW_CONFIG_PATH.read_text())
            defaults = config.get("agents", {}).get("defaults", {})

            # Primary source: agents.defaults.roles
            explicit_roles = defaults.get("roles", {})
            if isinstance(explicit_roles, dict):
                for role, model in explicit_roles.items():
                    if isinstance(model, str) and model.strip():
                        roles[role] = model.strip()

            # Legacy fallback: primary → model.primary
            if "primary" not in roles:
                primary = defaults.get("model", {}).get("primary")
                if isinstance(primary, str) and primary.strip():
                    roles["primary"] = primary.strip()

            # Legacy fallback: subagent → subagents.model
            if "subagent" not in roles:
                subagent_model = defaults.get("subagents", {}).get("model")
                if isinstance(subagent_model, str) and subagent_model.strip():
                    roles["subagent"] = subagent_model.strip()

    except (json.JSONDecodeError, OSError):
        pass

    # Hardcoded fallback for missing roles
    for role, model in _FALLBACK_MODEL_FOR_ROLE.items():
        if role not in roles:
            roles[role] = model

    _cached_roles = roles
    return roles


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_role_for_skill(skill: Optional[str]) -> str:
    """Resolve the role for a given skill.

    Args:
        skill: Skill name (e.g., "research", "execution")
               None or unknown skills return default role.

    Returns:
        Role name (e.g., "primary", "reviewer")
    """
    if not skill:
        return _DEFAULT_ROLE
    return _SKILL_ROLE_MAP.get(skill.strip().lower(), _DEFAULT_ROLE)


def resolve_model_for_skill(skill: Optional[str]) -> str:
    """Resolve the model to use for a given skill.

    Two-stage resolution: skill → role → model

    Args:
        skill: Skill name (e.g., "research", "decision")
               None or unknown skills fall back to default.

    Returns:
        Model identifier string (e.g., "zai/glm-5")
    """
    role = resolve_role_for_skill(skill)
    roles = load_openclaw_roles()
    return roles.get(role, _DEFAULT_MODEL)


def resolve_model_for_role(role: str) -> str:
    """Resolve the model for a given role.

    Args:
        role: Role name (e.g., "primary", "reviewer")

    Returns:
        Model identifier string
    """
    roles = load_openclaw_roles()
    return roles.get(role, _DEFAULT_MODEL)


def get_default_model() -> str:
    """Return the default model identifier."""
    return _DEFAULT_MODEL


def list_skill_role_mappings() -> Dict[str, str]:
    """Return a copy of the skill→role mapping (for inspection/testing)."""
    return dict(_SKILL_ROLE_MAP)


def list_role_model_mappings() -> Dict[str, str]:
    """Return the current role→model mapping (for inspection/testing)."""
    return load_openclaw_roles()
