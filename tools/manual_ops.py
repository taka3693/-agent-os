#!/usr/bin/env python3
"""
Manual Ops Surface

This module provides a minimal, safe, operator-facing command surface
for human operators to interact with Agent-OS layers.

Key principles:
- NO scheduler
- NO automatic apply
- NO automatic rollback
- NO automatic commit
- NO automatic promotion
- All risky actions require governance/manual approval checks
- Reuses existing layers (audit, governance, policy, verification, executor)
- Provides clear operator-facing summaries/messages

Operator commands:
- show_operational_summary() - View system-wide status
- show_apply_plan_status(apply_plan_id) - View single apply plan
- run_manual_verification(verification_id) - Trigger verification
- evaluate_manual_policy(apply_plan_id) - Trigger policy evaluation
- evaluate_manual_governance(action_type, entity_id) - Check governance
- run_manual_apply(apply_plan_id) - Execute apply (if governance allows)
- list_pending_revert_candidates() - List revert candidates
- grant_manual_approval(action_type, entity_id) - Grant manual approval
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from audit.operational_report import (
    get_apply_plan_operational_status,
    build_operational_summary,
    build_apply_plan_audit_report,
    list_all_apply_plans_status,
)
from verification.post_apply_verifier import (
    run_post_apply_verification,
    get_verification_status,
)
from policy.improvement_policy import (
    evaluate_apply_outcome,
    get_policy_decision_status,
    get_pending_revert_candidates,
)
from governance.operating_policy import (
    evaluate_action_eligibility,
    record_governance_decision,
    is_action_allowed,
    check_manual_approval_granted,
    ACTION_APPLY,
    ACTION_PROMOTE,
    ACTION_REVERT,
    DECISION_ALLOWED,
    DECISION_MANUAL_APPROVAL_REQUIRED,
    DECISION_DENIED,
)
from execution.controlled_patch_executor import execute_apply_plan
from tools.apply_lifecycle import (
    load_apply_plans,
    get_latest_apply_state,
    load_post_apply_verification_results,
)


# =============================================================================
# Status Views (READ-ONLY)
# =============================================================================

def show_operational_summary() -> Dict[str, Any]:
    """Show operational summary across all queues/states.
    
    This is a READ-ONLY operation.
    
    Returns:
        Operational summary dict
    """
    summary = build_operational_summary()
    
    # Format for operator display
    result = {
        "command": "show_operational_summary",
        "generated_at": summary.get("generated_at"),
        "counts": summary.get("counts", {}),
        "pending_manual_review": summary.get("pending_manual_review", [])[:10],
        "pending_apply_actions": summary.get("pending_apply_actions", [])[:10],
        "pending_verifications": summary.get("pending_verifications", [])[:10],
        "failed_verifications": summary.get("failed_verifications", [])[:10],
        "revert_candidates_pending": summary.get("revert_candidates_pending", [])[:10],
        "governance_denied_items": summary.get("governance_denied_items", [])[:10],
        "stale_items": summary.get("stale_items", [])[:10],
        "status": "ok",
    }
    
    return result


def show_apply_plan_status(apply_plan_id: str) -> Dict[str, Any]:
    """Show status for a single apply plan.
    
    This is a READ-ONLY operation.
    
    Args:
        apply_plan_id: Apply plan ID
        
    Returns:
        Apply plan status dict
    """
    status = get_apply_plan_operational_status(apply_plan_id)
    
    result = {
        "command": "show_apply_plan_status",
        "apply_plan_id": apply_plan_id,
        "status": "ok",
        **status,
    }
    
    return result


def show_apply_plan_audit_report(apply_plan_id: str) -> Dict[str, Any]:
    """Show detailed audit report for an apply plan.
    
    This is a READ-ONLY operation.
    
    Args:
        apply_plan_id: Apply plan ID
        
    Returns:
        Detailed audit report dict
    """
    report = build_apply_plan_audit_report(apply_plan_id)
    
    result = {
        "command": "show_apply_plan_audit_report",
        **report,
    }
    
    return result


def list_all_apply_plans() -> Dict[str, Any]:
    """List all apply plans with their status.
    
    This is a READ-ONLY operation.
    
    Returns:
        Dict with list of apply plan statuses
    """
    statuses = list_all_apply_plans_status()
    
    result = {
        "command": "list_all_apply_plans",
        "count": len(statuses),
        "apply_plans": statuses,
        "status": "ok",
    }
    
    return result


# =============================================================================
# Manual Actions (require governance checks)
# =============================================================================

def run_manual_verification(
    verification_id: str,
    changed_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run post-apply verification manually.
    
    This triggers verification but does NOT bypass any safety checks.
    
    Args:
        verification_id: Verification ID to run
        changed_files: Optional list of changed files
        
    Returns:
        Verification result dict
    """
    result = {
        "command": "run_manual_verification",
        "verification_id": verification_id,
        "status": "pending",
    }
    
    # Run verification (it has its own safety checks)
    verification_result = run_post_apply_verification(
        verification_id=verification_id,
        changed_files=changed_files,
    )
    
    result["verification_result"] = verification_result.get("result")
    result["status"] = verification_result.get("status", "unknown")
    result["passed"] = verification_result.get("passed", False)
    result["failure_codes"] = verification_result.get("failure_codes", [])
    result["evidence_refs"] = verification_result.get("evidence_refs", [])
    
    return result


def evaluate_manual_policy(apply_plan_id: str) -> Dict[str, Any]:
    """Evaluate policy for an apply plan manually.
    
    This triggers policy evaluation but does NOT bypass any safety checks.
    
    Args:
        apply_plan_id: Apply plan ID
        
    Returns:
        Policy evaluation result dict
    """
    result = {
        "command": "evaluate_manual_policy",
        "apply_plan_id": apply_plan_id,
        "status": "pending",
    }
    
    # Run policy evaluation
    policy_result = evaluate_apply_outcome(apply_plan_id)
    
    result["policy_decision"] = policy_result.get("decision")
    result["reason"] = policy_result.get("reason")
    result["decision_id"] = policy_result.get("decision_id")
    result["executed"] = policy_result.get("executed", False)
    result["status"] = "ok"
    
    # Note: Policy evaluation does NOT execute any actions
    result["note"] = "Policy evaluation recorded only. No automatic execution."
    
    return result


def evaluate_manual_governance(
    action_type: str,
    entity_id: str,
) -> Dict[str, Any]:
    """Evaluate governance eligibility for an action manually.
    
    This checks whether an action is allowed under governance rules.
    It does NOT bypass any safety checks.
    
    Args:
        action_type: Type of action (APPLY, PROMOTE, REVERT, COMMIT)
        entity_id: Entity ID (e.g., apply_plan_id)
        
    Returns:
        Governance evaluation result dict
    """
    result = {
        "command": "evaluate_manual_governance",
        "action_type": action_type,
        "entity_id": entity_id,
        "status": "pending",
    }
    
    # Evaluate governance eligibility
    eligibility = evaluate_action_eligibility(action_type, entity_id)
    
    result["decision"] = eligibility.get("decision")
    result["reason"] = eligibility.get("reason")
    result["manual_approval_required"] = eligibility.get("manual_approval_required", False)
    result["decision_id"] = eligibility.get("decision_id")
    result["status"] = "ok"
    
    # Check if action is allowed
    allowed = is_action_allowed(action_type, entity_id)
    result["is_allowed"] = allowed.get("allowed", False)
    result["allowed_reason"] = allowed.get("reason")
    
    if not result["is_allowed"]:
        result["note"] = f"Action {action_type} is NOT allowed. Reason: {allowed.get('reason')}"
    else:
        result["note"] = f"Action {action_type} is allowed and ready for execution."
    
    return result


def run_manual_apply(
    apply_plan_id: str,
    patch_path: Optional[str] = None,
    executor_identity: str = "manual_operator",
) -> Dict[str, Any]:
    """Run apply execution manually.
    
    IMPORTANT: This action is BLOCKED unless governance allows it.
    It does NOT bypass any safety checks.
    
    Args:
        apply_plan_id: Apply plan ID
        patch_path: Optional path to patch file
        executor_identity: Identity of executor
        
    Returns:
        Apply execution result dict
    """
    result = {
        "command": "run_manual_apply",
        "apply_plan_id": apply_plan_id,
        "status": "pending",
    }
    
    # Check if apply is allowed by governance
    allowed = is_action_allowed(ACTION_APPLY, apply_plan_id)
    
    if not allowed.get("allowed", False):
        result["status"] = "blocked"
        result["reason"] = f"Governance denied: {allowed.get('reason')}"
        result["note"] = "Apply execution requires governance approval. Use evaluate_manual_governance to check eligibility, then grant_manual_approval if appropriate."
        return result
    
    # Execute apply (it has its own safety checks)
    patch_path_obj = Path(patch_path) if patch_path else None
    apply_result = execute_apply_plan(
        apply_plan_id=apply_plan_id,
        patch_path=patch_path_obj,
        executor_identity=executor_identity,
    )
    
    result["apply_result"] = apply_result.get("status")
    result["patch_applied"] = apply_result.get("patch_applied", False)
    result["verification_created"] = apply_result.get("verification_created", False)
    result["status"] = apply_result.get("status", "unknown")
    
    if apply_result.get("errors"):
        result["errors"] = apply_result.get("errors")
    
    return result


def grant_manual_approval(
    action_type: str,
    entity_id: str,
    approver: str = "manual_operator",
    reason: str = "operator approved",
) -> Dict[str, Any]:
    """Grant manual approval for an action.
    
    This records a governance decision that grants approval.
    It does NOT execute the action.
    
    Args:
        action_type: Type of action
        entity_id: Entity ID
        approver: Who is granting approval
        reason: Reason for approval
        
    Returns:
        Approval result dict
    """
    result = {
        "command": "grant_manual_approval",
        "action_type": action_type,
        "entity_id": entity_id,
        "approver": approver,
        "status": "pending",
    }
    
    # First check eligibility
    eligibility = evaluate_action_eligibility(action_type, entity_id)
    
    if eligibility.get("decision") == DECISION_DENIED:
        result["status"] = "blocked"
        result["reason"] = f"Action is fundamentally denied: {eligibility.get('reason')}"
        return result
    
    # Record the approval
    approval_record = record_governance_decision(
        action_type=action_type,
        entity_id=entity_id,
        decision=DECISION_ALLOWED,
        reason=reason,
        approver=approver,
    )
    
    result["status"] = "approved"
    result["decision_id"] = approval_record.get("decision_id")
    result["note"] = f"Approval granted. Action {action_type} can now be executed if other conditions are met."
    
    return result


# =============================================================================
# List Operations (READ-ONLY)
# =============================================================================

def list_pending_revert_candidates() -> Dict[str, Any]:
    """List all pending revert candidates.
    
    This is a READ-ONLY operation.
    
    Returns:
        Dict with list of pending revert candidates
    """
    candidates = get_pending_revert_candidates()
    
    result = {
        "command": "list_pending_revert_candidates",
        "count": len(candidates),
        "candidates": candidates,
        "status": "ok",
    }
    
    return result


def list_pending_verifications() -> Dict[str, Any]:
    """List all pending verifications.
    
    This is a READ-ONLY operation.
    
    Returns:
        Dict with list of pending verifications
    """
    verifications = load_post_apply_verification_results()
    
    pending = []
    for v in verifications:
        if v.get("result") == "pending":
            pending.append({
                "verification_id": v.get("verification_id"),
                "apply_plan_id": v.get("apply_plan_id"),
                "started_at": v.get("started_at"),
            })
    
    result = {
        "command": "list_pending_verifications",
        "count": len(pending),
        "verifications": pending,
        "status": "ok",
    }
    
    return result


# =============================================================================
# Utility Functions
# =============================================================================

def format_summary_for_display(summary: Dict[str, Any]) -> str:
    """Format operational summary for display.
    
    Args:
        summary: Operational summary dict
        
    Returns:
        Formatted string
    """
    lines = []
    lines.append("=" * 60)
    lines.append("OPERATIONAL SUMMARY")
    lines.append(f"Generated: {summary.get('generated_at', 'unknown')}")
    lines.append("")
    
    counts = summary.get("counts", {})
    lines.append("COUNTS:")
    for key, value in counts.items():
        lines.append(f"  {key}: {value}")
    
    lines.append("")
    
    if summary.get("failed_verifications"):
        lines.append("FAILED VERIFICATIONS:")
        for v in summary["failed_verifications"][:5]:
            lines.append(f"  - {v.get('apply_plan_id')}: {v.get('failure_codes', [])}")
    
    if summary.get("revert_candidates_pending"):
        lines.append("REVERT CANDIDATES PENDING:")
        for c in summary["revert_candidates_pending"][:5]:
            lines.append(f"  - {c.get('apply_plan_id')}: {c.get('reason')}")
    
    if summary.get("stale_items"):
        lines.append("STALE ITEMS:")
        for s in summary["stale_items"][:5]:
            lines.append(f"  - {s.get('apply_plan_id')}: {s.get('reason')}")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


def format_status_for_display(status: Dict[str, Any]) -> str:
    """Format apply plan status for display.
    
    Args:
        status: Apply plan status dict
        
    Returns:
        Formatted string
    """
    lines = []
    lines.append("=" * 60)
    lines.append(f"APPLY PLAN STATUS: {status.get('apply_plan_id', 'unknown')}")
    lines.append("")
    
    lines.append(f"  Exists: {status.get('apply_plan_exists', False)}")
    lines.append(f"  Latest State: {status.get('latest_apply_state', 'none')}")
    lines.append(f"  Patch Status: {status.get('latest_patch_attempt_status', 'none')}")
    lines.append(f"  Verification: {status.get('latest_verification_status', 'none')}")
    lines.append(f"  Policy: {status.get('latest_policy_decision', 'none')}")
    lines.append(f"  Governance: {status.get('latest_governance_decision', 'none')}")
    lines.append(f"  Next Action: {status.get('next_manual_action', 'none')}")
    lines.append(f"  Is Stale: {status.get('is_stale', False)}")
    
    if status.get("stale_or_blocked_reason"):
        lines.append(f"  Blocked Reason: {status.get('stale_or_blocked_reason')}")
    
    if status.get("evidence_refs"):
        lines.append("  Evidence:")
        for ref in status["evidence_refs"][:5]:
            lines.append(f"    - {ref}")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)
