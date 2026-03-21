#!/usr/bin/env python3
"""
Post-Apply Verification Policy Layer

This module provides conservative post-apply verification for successfully
applied patches. It runs verification checks and records structured results
before the apply lifecycle can be considered safely advanced.

Key principles:
- Patch apply success is NOT equivalent to safe completion
- Verification is SEPARATE from patch execution
- NO automatic rollback
- NO automatic promotion
- NO automatic commit
- Append-only state design
- Conservative verification checks

Verification flow:
1. Load pending verification entry
2. Run conservative verification checks
3. Record structured verification evidence
4. Mark verification passed or failed
5. Record apply_state_transition appropriately
"""

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from execution.guard import check_syntax, check_critical_files
from tools.apply_lifecycle import (
    load_post_apply_verification_results,
    complete_post_apply_verification,
    record_apply_state_transition,
    load_apply_state_transitions,
    get_latest_apply_state,
)


def _run_targeted_pytest(
    changed_files: List[Path],
    project_root: Path,
    timeout: int = 60,
) -> Tuple[bool, Optional[str], List[str]]:
    """Run targeted pytest for changed files.
    
    Args:
        changed_files: List of changed Python files
        project_root: Project root directory
        timeout: Timeout in seconds
        
    Returns:
        Tuple of (passed, error_message, evidence_refs)
    """
    if not changed_files:
        return True, None, []
    
    # Find test files for changed modules
    tests_dir = project_root / "tests"
    if not tests_dir.exists():
        return True, "no_tests_directory", []
    
    test_targets = []
    for f in changed_files:
        if not f.suffix == ".py":
            continue
        stem = f.stem
        candidates = [
            tests_dir / f"test_{stem}.py",
            tests_dir / f"{stem}_test.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                test_targets.append(candidate)
    
    if not test_targets:
        # No tests found, that's OK for verification
        return True, None, []
    
    # Run pytest on found targets
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest"] + [str(t) for t in test_targets] + ["-x", "-q", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=timeout,
        )
        
        evidence_refs = [f"pytest_exit_code:{result.returncode}"]
        
        if result.returncode == 0:
            return True, None, evidence_refs
        else:
            # Extract failure summary
            error_msg = result.stdout[:500] if result.stdout else "pytest failed"
            return False, error_msg, evidence_refs
            
    except subprocess.TimeoutExpired:
        return False, "pytest_timeout", []
    except Exception as e:
        return False, f"pytest_error: {e}", []


def _run_verification_checks(
    apply_plan_id: str,
    changed_files: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
) -> Tuple[bool, List[str], List[str], str]:
    """Run all verification checks for an apply plan.
    
    Args:
        apply_plan_id: Apply plan ID
        changed_files: List of changed file paths
        project_root: Project root directory
        
    Returns:
        Tuple of (passed, failure_codes, evidence_refs, summary)
    """
    if project_root is None:
        project_root = PROJECT_ROOT
    
    if changed_files is None:
        changed_files = []
    
    failure_codes = []
    evidence_refs = []
    summary_parts = []
    
    # Convert to Path objects
    file_paths = [Path(f) for f in changed_files if f]
    
    # 1. Syntax check
    syntax_passed, syntax_error = check_syntax(file_paths)
    if not syntax_passed:
        failure_codes.append("SYNTAX_ERROR")
        evidence_refs.append(f"syntax_check:failed:{syntax_error}")
        summary_parts.append(f"Syntax check failed: {syntax_error}")
    else:
        evidence_refs.append("syntax_check:passed")
        summary_parts.append("Syntax check passed")
    
    # 2. Critical files check
    critical_passed, critical_file = check_critical_files(changed_files)
    if not critical_passed:
        failure_codes.append("CRITICAL_FILE_MODIFIED")
        evidence_refs.append(f"critical_file:{critical_file}")
        summary_parts.append(f"Critical file modified: {critical_file}")
    else:
        evidence_refs.append("critical_file_check:passed")
        summary_parts.append("Critical file check passed")
    
    # 3. Targeted pytest (if Python files changed)
    py_files = [f for f in file_paths if f.suffix == ".py"]
    if py_files and syntax_passed:  # Only run pytest if syntax passed
        pytest_passed, pytest_error, pytest_refs = _run_targeted_pytest(py_files, project_root)
        evidence_refs.extend(pytest_refs)
        
        if not pytest_passed:
            failure_codes.append("PYTEST_FAILED")
            summary_parts.append(f"Pytest failed: {pytest_error}")
        else:
            summary_parts.append("Pytest passed")
    
    # Determine overall result
    passed = len(failure_codes) == 0
    summary = " | ".join(summary_parts) if summary_parts else "Verification completed"
    
    return passed, failure_codes, evidence_refs, summary


def run_post_apply_verification(
    verification_id: str,
    changed_files: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run post-apply verification for a specific verification entry.
    
    This is the main entry point for post-apply verification.
    
    Args:
        verification_id: Verification ID to run
        changed_files: Optional list of changed file paths
        project_root: Optional project root directory
        
    Returns:
        Verification result dict
    """
    result = {
        "verification_id": verification_id,
        "status": "pending",
        "result": "pending",
        "passed": False,
        "failure_codes": [],
        "evidence_refs": [],
        "summary": "",
    }
    
    # Load verification entry - find the latest record
    verifications = load_post_apply_verification_results()
    latest = None
    for v in verifications:
        if v.get("verification_id") == verification_id:
            latest = v  # Keep the last one (most recent)
    
    if not latest:
        result["status"] = "error"
        result["summary"] = "verification_not_found"
        return result
    
    # Check if already completed (latest record has result != pending)
    if latest.get("result") not in ("pending", None, ""):
        result["status"] = "already_completed"
        result["summary"] = f"verification already completed: {latest.get('result')}"
        result["result"] = latest.get("result")
        result["passed"] = latest.get("result") == "passed"
        result["failure_codes"] = latest.get("failure_codes", [])
        result["evidence_refs"] = latest.get("evidence_refs", [])
        return result
    
    apply_plan_id = latest.get("apply_plan_id", "")
    
    # Run verification checks
    passed, failure_codes, evidence_refs, summary = _run_verification_checks(
        apply_plan_id=apply_plan_id,
        changed_files=changed_files,
        project_root=project_root,
    )
    
    result["result"] = "passed" if passed else "failed"
    result["passed"] = passed
    result["failure_codes"] = failure_codes
    result["evidence_refs"] = evidence_refs
    result["summary"] = summary
    
    # Complete the verification
    complete_result = complete_post_apply_verification(
        verification_id=verification_id,
        result="passed" if passed else "failed",
        summary=summary,
        failure_codes=failure_codes,
        evidence_refs=evidence_refs,
    )
    
    result["status"] = "completed"
    result["completed_verification"] = complete_result
    
    # Record apply_closed only if verification passed
    # This is the safe closure point - verification passed means apply is complete
    if passed:
        record_apply_state_transition(
            apply_plan_id=apply_plan_id,
            event="apply_closed",
            actor="verification_system",
            reason="verification_passed",
            metadata={
                "verification_id": verification_id,
                "evidence_refs": evidence_refs[:5],  # Limit metadata size
            },
        )
    
    return result


def get_verification_status(verification_id: str) -> Optional[Dict[str, Any]]:
    """Get the current status of a verification entry.
    
    Args:
        verification_id: Verification ID
        
    Returns:
        Verification status dict or None if not found
    """
    verifications = load_post_apply_verification_results()
    
    # Find the latest record for this verification_id
    latest = None
    for v in verifications:
        if v.get("verification_id") == verification_id:
            latest = v
    
    if not latest:
        return None
    
    # Get apply state
    apply_plan_id = latest.get("apply_plan_id", "")
    latest_state = get_latest_apply_state(apply_plan_id)
    
    return {
        "verification_id": verification_id,
        "apply_plan_id": apply_plan_id,
        "result": latest.get("result", "pending"),
        "summary": latest.get("summary", ""),
        "failure_codes": latest.get("failure_codes", []),
        "latest_apply_state": latest_state.get("event") if latest_state else None,
    }
