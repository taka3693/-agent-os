#!/usr/bin/env python3
"""
Controlled Patch Executor

This module provides controlled patch execution for apply plans.

Key principles:
- NO automatic execution - all operations require manual trigger
- Execution lease required - prevents duplicate/conconcurrent execution
- Precondition checks - working tree clean, repository HEAD match, patch artifact exists
- Append-only state - all records are append-only
- Reuse apply lifecycle layer - delegates to apply lifecycle functions

Executor flow:
1. acquire_execution_lease (from apply lifecycle)
2. run_precondition_checks
3. record patch_attempt_started
4. execute_patch_application
5. record patch_attempt_result
6. create post_apply_verification

Safety guarantees:
- No automatic apply
- No automatic rollback
- No automatic promotion
- All mutations are require execution lease
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import from apply lifecycle layer
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.apply_lifecycle import (
    create_apply_plan,
    load_apply_plans,
    acquire_execution_lease,
    find_active_lease_for_plan,
    create_extended_patch_attempt,
    complete_extended_patch_attempt,
    load_post_apply_verification_results,
    create_post_apply_verification,
    complete_post_apply_verification,
    record_apply_state_transition,
)

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = PROJECT_ROOT / "state"


def _run_git_command(args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    """Run a git command and return output."""
    result = subprocess.run(
        args,
        cwd=cwd or PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return result


def _check_working_tree_clean(cwd: Optional[Path] = None) -> Dict[str, Any]:
    """Check if working tree is clean.
    
    Returns:
        Dict with 'clean' bool and 'detail' if dirty
    """
    result = _run_git_command(["git", "status", "--porcelain"], cwd=cwd)
    if result.returncode != 0:
        return {"clean": False, "detail": f"git_status_failed: {result.stderr}"}
    
    if result.stdout.strip():
        return {"clean": False, "detail": f"dirty_working_tree: {result.stdout.strip()[:200]}"}
    
    return {"clean": True}


def _check_head_match(expected_head: Optional[str], cwd: Optional[Path] = None) -> Dict[str, Any]:
    """Check if current HEAD matches expected HEAD.
    
    Args:
        expected_head: Expected HEAD SHA (optional)
        cwd: Working directory
        
    Returns:
        Dict with 'match' bool and 'detail' if mismatch
    """
    if not expected_head:
        return {"match": True, "note": "no_expected_head_specified"}
    
    result = _run_git_command(["git", "rev-parse", "HEAD"], cwd=cwd)
    if result.returncode != 0:
        return {"match": False, "detail": f"git_rev_parse_failed: {result.stderr}"}
    
    current_head = result.stdout.strip()
    if current_head != expected_head:
        return {"match": False, "detail": f"head_mismatch: expected={expected_head[:12]}, actual={current_head[:12]}"}
    
    return {"match": True, "current_head": current_head}


def _run_safety_checks(
    patch_path: Optional[Path],
    expected_head: Optional[str] = None,
    cwd: Optional[Path] = None
) -> Dict[str, Any]:
    """Run safety checks on patch.
    
    Checks:
    - Working tree is clean
    - HEAD matches expected (if specified)
    - Syntax check (if Python file)
    - Patch artifact exists
    
    Returns:
        Dict with check results
    """
    results = {
        "passed": True,
        "checks": {},
    }
    
    # Working tree clean check
    tree_check = _check_working_tree_clean(cwd)
    if not tree_check.get("clean", False):
        results["passed"] = False
        results["checks"]["working_tree"] = tree_check.get("detail", "dirty")
    
    # HEAD match check
    head_check = _check_head_match(expected_head, cwd)
    if not head_check.get("match", False):
        results["passed"] = False
        results["checks"]["head_match"] = head_check.get("detail", "mismatch")
    
    # Syntax check for Python files
    if patch_path and str(patch_path).endswith(".py"):
        syntax_result = subprocess.run(
            ["python3", "-m", "py_compile", str(patch_path)],
            cwd=cwd or PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if syntax_result.returncode != 0:
            results["passed"] = False
            results["checks"]["syntax"] = syntax_result.stderr[:500]
    
    # Patch artifact existence
    if patch_path and not Path(patch_path).exists():
        results["passed"] = False
        results["checks"]["patch_exists"] = f"Patch file does not exist: {patch_path}"
    
    return results


def execute_apply_plan(
    apply_plan_id: str,
    patch_path: Optional[Path] = None,
    executor_identity: str = "manual",
    skip_lease: bool = False,
) -> Dict[str, Any]:
    """Execute an apply plan.
    
    This is the main entry point for controlled patch execution.
    
    Flow:
    1. Acquire execution lease (fails if duplicate)
    2. Run precondition checks
    3. Record patch_attempt_started
    4. Execute patch application
    5. Record patch_attempt_result
    6. Create post_apply_verification
    
    Args:
        apply_plan_id: Apply plan ID
        patch_path: Path to patch file
        executor_identity: Who is executing
        skip_lease: Skip lease acquisition (for testing)
        
    Returns:
        Execution result dict
    """
    result = {
        "apply_plan_id": apply_plan_id,
        "status": "pending",
        "lease_acquired": False,
        "preconditions_passed": False,
        "patch_applied": False,
        "verification_created": False,
        "errors": [],
    }
    
    # Load apply plan
    plans = load_apply_plans()
    plan = None
    for p in plans:
        if p.get("apply_plan_id") == apply_plan_id:
            plan = p
            break
    
    if not plan:
        result["status"] = "failed"
        result["errors"].append("apply_plan_not_found")
        return result
    
    # Step 1: Acquire execution lease
    if not skip_lease:
        lease = acquire_execution_lease(
            apply_plan_id=apply_plan_id,
            acquired_by=executor_identity,
            lease_scope="patch_execution",
            expires_in_seconds=3600,
        )
        
        if lease.get("status") == "blocked":
            result["status"] = "blocked"
            result["errors"].append(f"lease_blocked: {lease.get('reason', 'unknown')}")
            return result
        
        result["lease_id"] = lease.get("lease_id", "")
        result["lease_acquired"] = True
    
    # Step 2: Run precondition checks (with expected_head from plan)
    expected_head = plan.get("expected_head")
    preconditions = _run_safety_checks(patch_path, expected_head=expected_head)
    result["preconditions"] = preconditions
    
    if not preconditions.get("passed", True):
        result["status"] = "failed"
        result["errors"].append("preconditions_failed")
        return result
    
    result["preconditions_passed"] = True
    
    # Step 3: Record patch attempt started
    attempt = create_extended_patch_attempt(
        apply_plan_id=apply_plan_id,
        execution_lease_id=result.get("lease_id", ""),
        executor_identity=executor_identity,
        patch_artifact_ref=str(patch_path) if patch_path else "",
    )
    result["patch_attempt_id"] = attempt.get("patch_attempt_id", "")
    
    # Step 4: Execute real patch application
    patch_result = _apply_patch(patch_path)
    result["patch_result"] = patch_result
    
    if not patch_result.get("success", False):
        # Record failure
        complete_extended_patch_attempt(
            patch_attempt_id=result["patch_attempt_id"],
            execution_result="failed",
            failure_code=patch_result.get("error", "unknown"),
            failure_detail=patch_result.get("detail", ""),
        )
        result["status"] = "failed"
        result["errors"].append(f"patch_failed: {patch_result.get('error', 'unknown')}")
        return result
    
    # Step 5: Record success
    complete_extended_patch_attempt(
        patch_attempt_id=result["patch_attempt_id"],
        execution_result="succeeded",
        diff_summary=patch_result.get("diff_summary", ""),
        produced_artifact_refs=patch_result.get("artifacts", []),
    )
    result["patch_applied"] = True
    
    # Step 6: Create post_apply_verification
    verification = create_post_apply_verification(
        apply_plan_id=apply_plan_id,
        patch_attempt_id=result["patch_attempt_id"],
        verification_steps=plan.get("expected_verifications", []),
    )
    result["verification_id"] = verification.get("verification_id", "")
    result["verification_created"] = True
    result["status"] = "completed"
    
    return result


def _apply_patch(patch_path: Optional[Path], cwd: Optional[Path] = None) -> Dict[str, Any]:
    """Apply a patch using git apply.
    
    This performs real patch application with safety checks.
    
    Args:
        patch_path: Path to patch file
        cwd: Working directory
        
    Returns:
        Dict with success status and details
    """
    if not patch_path:
        return {
            "success": False,
            "error": "no_patch_path",
            "detail": "No patch path provided",
        }
    
    if not Path(patch_path).exists():
        return {
            "success": False,
            "error": "patch_not_found",
            "detail": f"Patch file does not exist: {patch_path}",
        }
    
    # Run git apply with --check first (dry run)
    check_result = _run_git_command(
        ["git", "apply", "--check", str(patch_path)],
        cwd=cwd or PROJECT_ROOT,
    )
    
    if check_result.returncode != 0:
        return {
            "success": False,
            "error": "patch_check_failed",
            "detail": check_result.stderr[:500] if check_result.stderr else "unknown error",
        }
    
    # Apply the patch for real
    apply_result = _run_git_command(
        ["git", "apply", str(patch_path)],
        cwd=cwd or PROJECT_ROOT,
    )
    
    if apply_result.returncode != 0:
        return {
            "success": False,
            "error": "patch_apply_failed",
            "detail": apply_result.stderr[:500] if apply_result.stderr else "unknown error",
        }
    
    # Get diff summary
    diff_result = _run_git_command(
        ["git", "diff", "--stat", "HEAD"],
        cwd=cwd or PROJECT_ROOT,
    )
    
    diff_summary = "patch applied"
    if diff_result.returncode == 0 and diff_result.stdout.strip():
        # Extract first line of diff stat
        lines = diff_result.stdout.strip().split("\n")
        if lines:
            diff_summary = lines[-1][:100]  # Last line has summary
    
    return {
        "success": True,
        "diff_summary": diff_summary,
        "artifacts": [],
        "note": "real_patch_applied",
    }
