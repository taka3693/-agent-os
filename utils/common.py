#!/usr/bin/env python3
"""Common Utilities Module

Provides shared utility functions used across AgentOS:
- Timestamp helpers (_now_utc, _now_iso)
- Atomic JSON file operations
- Path helpers
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


# =============================================================================
# Timestamp Helpers
# =============================================================================

def now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def now_iso() -> str:
    """Return current timestamp in ISO 8601 format (UTC)."""
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_timestamp(ts: str | None) -> datetime | None:
    """Parse ISO 8601 timestamp to datetime.
    
    Args:
        ts: ISO 8601 timestamp string (e.g., "2026-03-13T12:34:56Z")
        
    Returns:
        datetime object with UTC timezone, or None if invalid
    """
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def seconds_since(ts: str | None) -> float | None:
    """Return seconds elapsed since timestamp.
    
    Args:
        ts: ISO 8601 timestamp string
        
    Returns:
        Seconds elapsed, or None if invalid
    """
    dt = parse_iso_timestamp(ts)
    if dt is None:
        return None
    return (now_utc() - dt).total_seconds()


# =============================================================================
# Atomic File Operations
# =============================================================================

def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Atomically write JSON to avoid partial writes.
    
    Writes to a temporary file first, then renames to target path.
    This ensures no partial/corrupted files on crash.
    
    Args:
        path: Target file path
        data: Dictionary to write as JSON
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def read_json_if_exists(path: Path) -> Dict[str, Any] | None:
    """Read JSON file if it exists.
    
    Args:
        path: Path to JSON file
        
    Returns:
        Parsed JSON dict, or None if not found/invalid
    """
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# =============================================================================
# Backward Compatibility Aliases
# =============================================================================

# These aliases allow existing code to import from utils.common
# while gradually migrating to the new naming convention.
_now_utc = now_utc
_now_iso = now_iso
_atomic_write_json = atomic_write_json
