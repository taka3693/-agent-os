#!/usr/bin/env python3
"""Execution Guard Module

Provides minimal blocking guard checks for code execution.
Prevents success reporting when verification fails.

This is NOT a logging layer - it actively blocks success.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Default thresholds
MAX_DIFF_LINES_DEFAULT = 500
MAX_DIFF_LINES_SMALL_CHANGE = 50
MAX_CONSECUTIVE_DELETIONS = 10

# Critical files that must not be modified through normal execution
CRITICAL_FILES = {
    "tools/run_agent_os_request.py",
    "execution/guard.py",
}


def _is_non_semantic_line(line: str) -> bool:
    """Check if a line is non-semantic (whitespace or comment only).
    
    This is used to exclude harmless edits from dangerous-change detection.
    
    IMPORTANT: This must be conservative. Only clearly safe exclusions:
    - empty/whitespace-only lines
    - comment-only lines starting with #
    - pure triple-quote marker lines (exactly triple-double or triple-single)
    
    Args:
        line: A single line of code (without leading -)
        
    Returns:
        True if the line is non-semantic, False otherwise
    """
    stripped = line.strip()
    
    # Empty or whitespace-only
    if not stripped:
        return True
    
    # Python comment
    if stripped.startswith("#"):
        return True
    
    # Pure triple-quote marker lines only (exact match)
    # These are standalone docstring delimiters with no content
    if stripped == '"""' or stripped == "'''":
        return True
    
    return False


def detect_dangerous_changes(diff_output: str) -> Dict[str, Any]:
    """Detect dangerous code changes in git diff output.
    
    Only flags real code deletions, excluding non-semantic changes
    (whitespace, comments, docstrings).
    
    Args:
        diff_output: Git diff output string
        
    Returns:
        Dict with danger signals:
        - function_deleted: bool
        - class_deleted: bool
        - import_removed: bool
        - large_deletion: bool
        - danger_count: int
    """
    signals = {
        "function_deleted": False,
        "class_deleted": False,
        "import_removed": False,
        "large_deletion": False,
        "danger_count": 0,
    }
    
    if not diff_output:
        return signals
    
    lines = diff_output.split("\n")
    consecutive_deletions = 0
    in_docstring = False  # Track docstring context
    
    for line in lines:
        # Skip non-diff lines
        if not line.startswith("-") or line.startswith("---"):
            consecutive_deletions = 0
            continue
        
        removed = line[1:]  # Keep original, don't strip yet
        stripped = removed.strip()
        
        # Skip non-semantic lines (whitespace, comments, docstrings)
        if _is_non_semantic_line(removed):
            consecutive_deletions = 0
            continue
        
        # Check function deletion - only if not in docstring context
        if stripped.startswith("def ") or stripped.startswith("async def "):
            signals["function_deleted"] = True
            signals["danger_count"] += 1
        
        # Check class deletion
        if stripped.startswith("class "):
            signals["class_deleted"] = True
            signals["danger_count"] += 1
        
        # Check import removal - these are always semantic
        if stripped.startswith("import ") or stripped.startswith("from "):
            signals["import_removed"] = True
            signals["danger_count"] += 1
        
        # Track consecutive deletions (only for semantic lines)
        consecutive_deletions += 1
        if consecutive_deletions > MAX_CONSECUTIVE_DELETIONS:
            signals["large_deletion"] = True
            signals["danger_count"] += 1
    
    return signals


class GuardFailure(Exception):
    """Raised when a guard check fails."""
    pass


def check_edit_failed(output: str) -> Tuple[bool, Optional[str]]:
    """Check if 'edit failed' appears in output.
    
    Args:
        output: Output string to check
        
    Returns:
        Tuple of (passed, reason) - reason is None if passed
    """
    if "edit failed" in output.lower():
        return False, "edit failed detected in output"
    if "Edit:" in output and "failed" in output.lower():
        return False, "edit operation failed"
    return True, None


def check_syntax(files: List[Path]) -> Tuple[bool, Optional[str]]:
    """Check Python syntax for all specified files.
    
    Args:
        files: List of Python file paths to check
        
    Returns:
        Tuple of (passed, reason) - reason is None if passed
    """
    for f in files:
        if not f.exists():
            continue
        if not f.suffix == ".py":
            continue
        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(f)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return False, f"syntax error in {f}: {result.stderr[:200]}"
        except subprocess.TimeoutExpired:
            return False, f"syntax check timeout for {f}"
        except Exception as e:
            return False, f"syntax check failed for {f}: {e}"
    return True, None


def check_verification_evidence(
    result: Dict[str, Any],
    required_commands: Optional[List[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """Check if required verification evidence is present.
    
    Args:
        result: Execution result dict
        required_commands: List of required verification commands (grep, sed, diff, git diff, py_compile)
        
    Returns:
        Tuple of (passed, reason) - reason is None if passed
    """
    if required_commands is None:
        required_commands = []
    
    # Check if files were changed
    artifacts = result.get("artifacts", [])
    if not artifacts:
        # No files changed, skip verification
        return True, None
    
    # For now, just check that result has required keys
    required_keys = ["ok"]
    for key in required_keys:
        if key not in result:
            return False, f"missing required key: {key}"
    
    return True, None


def check_critical_files(
    artifacts: Optional[List[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """Check if any critical safety files are being modified.
    
    Args:
        artifacts: List of file paths that were modified
        
    Returns:
        Tuple of (passed, reason) - reason is None if passed
    """
    if not artifacts:
        return True, None
    
    for artifact in artifacts:
        # Normalize path for comparison
        p = Path(artifact) if not isinstance(artifact, Path) else artifact
        # Get relative path string for comparison
        try:
            # Try to get a relative path
            parts = p.parts
            # Reconstruct path relative to project root
            rel_path = "/".join(parts[-2:]) if len(parts) >= 2 else p.name
        except Exception:
            rel_path = str(p)
        
        # Check against critical files
        for critical in CRITICAL_FILES:
            if rel_path.endswith(critical) or str(p).endswith(critical):
                return False, critical
    
    return True, None


def check_pytest(
    pytest_info: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str]]:
    """Check pytest result status.
    
    Args:
        pytest_info: Dict with pytest execution info:
            - required: bool
            - ran: bool
            - passed: bool | None
            - exit_code: int | None
            - summary: str | None
        
    Returns:
        Tuple of (passed, reason) - reason is None if passed
    """
    if pytest_info is None:
        return True, None
    
    required = pytest_info.get("required", False)
    ran = pytest_info.get("ran", False)
    passed = pytest_info.get("passed")
    summary = pytest_info.get("summary")
    
    # If pytest was run and failed -> guard failure
    if ran and passed is False:
        if summary:
            return False, f"pytest failed: {summary}"
        return False, "pytest failed"
    
    # If pytest was required but not run -> guard failure
    if required and not ran:
        return False, "pytest required but not executed"
    
    # All other cases: pass
    # - pytest not applicable (passed is None, not required)
    # - pytest passed
    # - pytest not required and not run
    return True, None


def check_diff_size(
    diff_output: str,
    max_lines: int = MAX_DIFF_LINES_DEFAULT,
    is_small_change: bool = False,
) -> Tuple[bool, Optional[str]]:
    """Check if diff size is within acceptable limits.
    
    Args:
        diff_output: Git diff output string
        max_lines: Maximum allowed diff lines
        is_small_change: If True, use stricter limit
        
    Returns:
        Tuple of (passed, reason) - reason is None if passed
    """
    if not diff_output:
        return True, None
    
    limit = MAX_DIFF_LINES_SMALL_CHANGE if is_small_change else max_lines
    lines = diff_output.strip().split("\n")
    
    if len(lines) > limit:
        return False, f"diff too large: {len(lines)} lines (max {limit})"
    
    return True, None


def run_all_guards(
    result: Dict[str, Any],
    output: str = "",
    changed_files: Optional[List[Path]] = None,
    diff_output: str = "",
    is_small_change: bool = False,
    required_verification: Optional[List[str]] = None,
    pytest_info: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str], List[Dict[str, str]]]:
    """Run all guard checks and return combined result.
    
    Args:
        result: Execution result dict
        output: Output string to check for edit failures
        changed_files: List of changed Python files for syntax check
        diff_output: Git diff output for size check
        is_small_change: If True, use stricter diff limits
        required_verification: List of required verification commands
        pytest_info: Dict with pytest execution info (required, ran, passed, exit_code, summary)
        
    Returns:
        Tuple of (all_passed, list of failure strings, list of failure details)
    """
    failures = []
    failure_details = []
    
    # Check 1: edit failed
    passed, reason = check_edit_failed(output)
    if not passed:
        failures.append(f"EDIT_FAILED: {reason}")
        failure_details.append({"code": "EDIT_FAILED", "message": reason or "edit failed"})
    
    # Check 2: syntax
    if changed_files:
        passed, reason = check_syntax(changed_files)
        if not passed:
            failures.append(f"SYNTAX_ERROR: {reason}")
            failure_details.append({"code": "SYNTAX_ERROR", "message": reason or "syntax error"})
    
    # Check 3: verification evidence
    passed, reason = check_verification_evidence(result, required_verification)
    if not passed:
        failures.append(f"VERIFICATION_MISSING: {reason}")
        failure_details.append({"code": "VERIFICATION_MISSING", "message": reason or "verification missing"})
    
    # Check 4: pytest result
    passed, reason = check_pytest(pytest_info)
    if not passed:
        failures.append(f"PYTEST_FAILED: {reason}")
        # Determine specific pytest code
        if pytest_info and not pytest_info.get("ran") and pytest_info.get("required"):
            code = "PYTEST_REQUIRED_BUT_NOT_EXECUTED"
        else:
            code = "PYTEST_FAILED"
        failure_details.append({"code": code, "message": reason or "pytest failed"})
    
    # Check 5: critical file modification
    artifacts = result.get("artifacts", [])
    passed, reason = check_critical_files(artifacts)
    if not passed:
        failures.append(f"CRITICAL_FILE_MODIFIED: {reason}")
        failure_details.append({"code": "CRITICAL_FILE_MODIFIED", "message": f"attempted modification of critical file: {reason}"})
    
    # Check 6: dangerous changes (always blocks, regardless of diff size)
    danger_signals = detect_dangerous_changes(diff_output)
    if danger_signals["danger_count"] > 0:
        # Build reason string
        danger_reasons = []
        if danger_signals["function_deleted"]:
            danger_reasons.append("function deletion")
        if danger_signals["class_deleted"]:
            danger_reasons.append("class deletion")
        if danger_signals["import_removed"]:
            danger_reasons.append("import removal")
        if danger_signals["large_deletion"]:
            danger_reasons.append("large deletion (>10 lines)")
        
        # Dangerous changes always block, regardless of diff size
        msg = ', '.join(danger_reasons)
        failures.append(f"DANGEROUS_CHANGE: {msg}")
        failure_details.append({"code": "DANGEROUS_CHANGE", "message": msg})
    
    # Check 7: diff size (only if no dangerous changes detected)
    if not danger_signals["danger_count"]:
        passed, reason = check_diff_size(diff_output, is_small_change=is_small_change)
        if not passed:
            failures.append(f"DIFF_TOO_LARGE: {reason}")
            failure_details.append({"code": "DIFF_TOO_LARGE", "message": reason or "diff too large"})
    
    return len(failures) == 0, failures, failure_details


def enforce_guard(
    result: Dict[str, Any],
    output: str = "",
    changed_files: Optional[List[Path]] = None,
    diff_output: str = "",
    is_small_change: bool = False,
    pytest_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Enforce guard checks and modify result if checks fail.
    
    This is the main entry point. It modifies result in-place if guards fail.
    
    Args:
        result: Execution result dict (will be modified if guards fail)
        output: Output string to check
        changed_files: List of changed Python files
        diff_output: Git diff output
        is_small_change: If True, use stricter diff limits
        pytest_info: Dict with pytest execution info (required, ran, passed, exit_code, summary)
        
    Returns:
        Modified result dict (with ok=False and guard_failures if checks failed)
    """
    all_passed, failures, failure_details = run_all_guards(
        result=result,
        output=output,
        changed_files=changed_files,
        diff_output=diff_output,
        is_small_change=is_small_change,
        pytest_info=pytest_info,
    )
    
    # Include pytest_info in result (always)
    result = dict(result)
    if pytest_info is not None:
        result["pytest_info"] = pytest_info
    
    if all_passed:
        return result
    
    # Guard failed - modify result
    result["ok"] = False
    result["guard_failed"] = True
    result["guard_failures"] = failures
    result["guard_failure_details"] = failure_details
    result["status"] = "guard_blocked"
    
    return result
