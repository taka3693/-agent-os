#!/usr/bin/env python3
"""Workspace Operations Module

Provides file system operations within the AgentOS workspace:
- Path resolution and validation
- Directory listing and tree
- File preview
- Directory creation
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

# Default limits
READ_PREVIEW_LIMIT = 300
LS_LIMIT = 50
TREE_LIMIT = 80
TREE_MAX_DEPTH = 3


def resolve_workspace_path(
    rel_path: str | None,
    workspace_root: Path,
) -> Path | None:
    """Resolve a relative path within the workspace.

    Args:
        rel_path: Relative path string (or None for workspace root)
        workspace_root: Root directory of the workspace

    Returns:
        Resolved absolute path, or None if path escapes workspace
    """
    raw = (rel_path or ".").strip()
    p = (workspace_root / raw).resolve()
    root = workspace_root.resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p


def read_preview_from_workspace(
    rel_path: str | None,
    workspace_root: Path,
    limit: int = READ_PREVIEW_LIMIT,
) -> str | None:
    """Read a file preview from the workspace.

    Args:
        rel_path: Relative path to the file
        workspace_root: Root directory of the workspace
        limit: Maximum characters to read

    Returns:
        File content (truncated if needed), or None if not readable
    """
    p = resolve_workspace_path(rel_path, workspace_root)
    if p is None or not p.exists() or not p.is_file():
        return None

    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return None

    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def list_dir(
    rel_path: str | None,
    workspace_root: Path,
    ls_limit: int = LS_LIMIT,
) -> str:
    """List directory contents.

    Args:
        rel_path: Relative path to the directory
        workspace_root: Root directory of the workspace
        ls_limit: Maximum items to display

    Returns:
        Formatted directory listing
    """
    p = resolve_workspace_path(rel_path, workspace_root)
    if p is None:
        return "一覧失敗\n原因: path escapes workspace"

    if not p.exists():
        return f"一覧失敗\n原因: not found: {rel_path or '.'}"

    if not p.is_dir():
        return f"一覧失敗\n原因: not a directory: {rel_path or '.'}"

    items = []
    for child in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if child.name.startswith("."):
            continue
        mark = "/" if child.is_dir() else ""
        items.append(child.name + mark)

    shown = items[:ls_limit]
    omitted = max(0, len(items) - len(shown))
    lines = [
        "一覧結果",
        f"対象: {(rel_path or '.').strip() or '.'}",
        f"表示上限: {ls_limit}件",
    ]
    if shown:
        lines.extend(f"- {x}" for x in shown)
        if omitted:
            lines.append(f"... ほか {omitted} 件")
    else:
        lines.append("(empty)")
    return "\n".join(lines)


def build_tree_lines(
    root: Path,
    depth: int,
    max_depth: int,
    out: List[str],
    tree_limit: int = TREE_LIMIT,
) -> None:
    """Recursively build tree lines.

    Args:
        root: Current directory
        depth: Current depth
        max_depth: Maximum depth to traverse
        out: Output list to append lines to
        tree_limit: Maximum lines to output
    """
    if depth > max_depth or len(out) >= tree_limit:
        return

    children = [
        c for c in sorted(root.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        if not c.name.startswith(".")
    ]

    for child in children:
        if len(out) >= tree_limit:
            return
        indent = "  " * depth
        suffix = "/" if child.is_dir() else ""
        out.append(f"{indent}- {child.name}{suffix}")
        if child.is_dir():
            build_tree_lines(child, depth + 1, max_depth, out, tree_limit)


def tree_dir(
    rel_path: str | None,
    workspace_root: Path,
    tree_limit: int = TREE_LIMIT,
    tree_max_depth: int = TREE_MAX_DEPTH,
) -> str:
    """Generate a tree view of a directory.

    Args:
        rel_path: Relative path to the directory
        workspace_root: Root directory of the workspace
        tree_limit: Maximum lines to output
        tree_max_depth: Maximum depth to traverse

    Returns:
        Formatted tree view
    """
    p = resolve_workspace_path(rel_path, workspace_root)
    if p is None:
        return "ツリー失敗\n原因: path escapes workspace"

    if not p.exists():
        return f"ツリー失敗\n原因: not found: {rel_path or '.'}"

    if not p.is_dir():
        return f"ツリー失敗\n原因: not a directory: {rel_path or '.'}"

    out: List[str] = []
    build_tree_lines(p, 0, tree_max_depth, out, tree_limit)

    lines = [
        "ツリー結果",
        f"対象: {(rel_path or '.').strip() or '.'}",
        f"表示上限: {tree_limit}件 / 深さ: {tree_max_depth}",
    ]
    if out:
        lines.extend(out[:tree_limit])
    else:
        lines.append("(empty)")
    if len(out) >= tree_limit:
        lines.append("... (truncated)")
    return "\n".join(lines)


def mkdir_dir(
    rel_path: str | None,
    workspace_root: Path,
) -> str:
    """Create a directory in the workspace.

    Args:
        rel_path: Relative path for the new directory
        workspace_root: Root directory of the workspace

    Returns:
        Result message
    """
    raw = (rel_path or "").strip()
    if not raw:
        return "ディレクトリ作成失敗\n原因: path is empty"

    p = resolve_workspace_path(raw, workspace_root)
    if p is None:
        return "ディレクトリ作成失敗\n原因: path escapes workspace"

    if p.exists() and p.is_file():
        return f"ディレクトリ作成失敗\n原因: file exists: {raw}"

    p.mkdir(parents=True, exist_ok=True)
    return "\n".join([
        "ディレクトリ作成完了",
        f"対象: {raw}",
    ])


def simplify_error(error: str | None) -> str:
    """Simplify an error message by removing common prefixes.

    Args:
        error: Original error message

    Returns:
        Simplified error message
    """
    s = (error or "").strip()
    if not s:
        return "unknown error"

    prefixes = [
        "PlanValidationError:",
        "ValueError:",
        "RuntimeError:",
        "FileNotFoundError:",
        "FileExistsError:",
    ]
    for prefix in prefixes:
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
            break
    return s or "unknown error"
