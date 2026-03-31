#!/usr/bin/env python3
"""Prompt Template Loader

Provides centralized prompt template loading for Agent-OS.
Ensures consistent agent behavior across all skills and runners.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

# Default paths
CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_PROMPT_PATH = CONFIG_DIR / "agent_prompt.md"


def load_prompt_template(path: Optional[Path] = None) -> str:
    """Load a prompt template from file.
    
    Args:
        path: Optional custom path. Defaults to config/agent_prompt.md
        
    Returns:
        Prompt template content as string
        
    Raises:
        FileNotFoundError: If prompt file doesn't exist
    """
    prompt_path = path or DEFAULT_PROMPT_PATH
    
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")
    
    return prompt_path.read_text(encoding="utf-8")


def get_agent_prompt() -> str:
    """Get the default agent prompt template.
    
    Returns:
        Default agent prompt content
    """
    try:
        return load_prompt_template()
    except FileNotFoundError:
        # Fallback to inline prompt if file is missing
        return _get_fallback_prompt()


def _get_fallback_prompt() -> str:
    """Return a minimal fallback prompt if file is missing."""
    return """
You are an autonomous agent operating inside Agent-OS.

Language policy:
- Accept user requests in Japanese or English.
- When handling technical operations, prefer English internally if it improves accuracy.
- Always provide final explanations, summaries, and reports in Japanese.

Behavior policy:
- Be precise, concise, and execution-oriented.
- Inspect before modifying.
- Prefer minimal safe changes.

When reporting findings, use this structure when appropriate:

1. 概要
2. 技術分析
3. 問題点
4. 改善提案
""".strip()


def format_report(
    overview: str,
    technical_analysis: str = "",
    issues: str = "",
    improvements: str = "",
) -> str:
    """Format a standard report in Japanese.
    
    Args:
        overview: Task summary (概要)
        technical_analysis: Technical findings (技術分析)
        issues: Problems identified (問題点)
        improvements: Actionable recommendations (改善提案)
        
    Returns:
        Formatted report string
    """
    sections = [
        ("## 1. 概要", overview),
        ("## 2. 技術分析", technical_analysis),
        ("## 3. 問題点", issues),
        ("## 4. 改善提案", improvements),
    ]
    
    parts = []
    for header, content in sections:
        if content:
            parts.append(f"{header}\n\n{content}")
    
    return "\n\n".join(parts)


# Module-level cache for loaded prompt
_cached_prompt: Optional[str] = None


def get_cached_prompt() -> str:
    """Get cached agent prompt, loading if necessary.
    
    Returns:
        Agent prompt content (cached)
    """
    global _cached_prompt
    if _cached_prompt is None:
        _cached_prompt = get_agent_prompt()
    return _cached_prompt


def clear_cache() -> None:
    """Clear the cached prompt (useful for development/testing)."""
    global _cached_prompt
    _cached_prompt = None
