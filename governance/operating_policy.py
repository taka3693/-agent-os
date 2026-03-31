#!/usr/bin/env python3
"""
Governance / Operating Policy Layer

This module provides explicit governance for whether requested actions are
allowed under conservative human-gated operation.

Key principles:
- NO automatic apply
- NO automatic rollback
- NO automatic commit
- NO automatic promotion execution
- Manual approvals required for all risky actions
- Conservative denial for ambiguous states
- Append-only state design

Action types governed:
- APPLY: Execute a patch apply
- PROMOTE: Promote a proposal after successful verification
- REVERT: Execute a rollback
- COMMIT: Commit changes to repository

Governance decisions:
- ALLOWED: Action is permitted (still requires manual trigger)
- DENIED: Action is not permitted
- MANUAL_APPROVAL_REQUIRED: Action requires explicit human approval
- INELIGIBLE_EXPIRED: Entity is expired
- INELIGIBLE_INCOMPLETE: Entity verification is incomplete
- INELIGIBLE_AMBIGUOUS: State is ambiguous, deny conservatively
"""

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from tools.apply_lifecycle import (
    load_apply_plans,
    get_latest_apply_state,
    load_post_apply_verification_results,
)
from policy.improvement_policy import (
    get_policy_decision_status,
    load_policy_decisions,
)

# State directory
STATE_DIR = PROJECT_ROOT / "state"

# Action types
ACTION_APPLY = "APPLY"
ACTION_PROMOTE = "PROMOTE"
ACTION_REVERT = "REVERT"
ACTION_COMMIT = "COMMIT"

VALID_ACTIONS = {ACTION_APPLY, ACTION_PROMOTE, ACTION_REVERT, ACTION_COMMIT}

# Governance decision outcomes
DECISION_ALLOWED = "ALLOWED"
DECISION_DENIED = "DENIED"
DECISION_MANUAL_APPROVAL_REQUIRED = "MANUAL_APPROVAL_REQUIRED"
DECISION_INELIGIBLE_EXPIRED = "INELIGIBLE_EXPIRED"
DECISION_INELIGIBLE_INCOMPLETE = "INELIGIBLE_INCOMPLETE"
DECISION_INELIGIBLE_AMBIGUOUS = "INELIGIBLE_AMBIGUOUS"

VALID_DECISIONS = {
    DECISION_ALLOWED,
    DECISION_DENIED,
    DECISION_MANUAL_APPROVAL_REQUIRED,
    DECISION_INELIGIBLE_EXPIRED,
    DECISION_INELIGIBLE_INCOMPLETE,
    DECISION_INELIGIBLE_AMBIGUOUS,
}

# Actions that ALWAYS require manual approval
MANUAL_APPROVAL_REQUIRED_ACTIONS = {
    ACTION_APPLY,
    ACTION_PROMOTE,
    ACTION_REVERT,
    ACTION_COMMIT,
}

# Default expiry time for apply plans (in seconds)
DEFAULT_EXPIRY_SECONDS = 24 * 60 * 60  # 24 hours


def _append_jsonl_record(record: Dict[str, Any], path: Path) -> bool:
    """Append a record to a JSONL file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _load_jsonl_records(path: Path) -> List[Dict[str, Any]]:
    """Load all records from a JSONL file."""
    if not path.exists():
        return []
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except Exception:
        pass
    return records


def _is_apply_plan_expired(apply_plan: Dict[str, Any]) -> bool:
    """Check if an apply plan is expired.
    
    Args:
        apply_plan: Apply plan record
        
    Returns:
        True if expired
    """
    # Check explicit expiry
    expires_at = apply_plan.get("eligibility_expires_at", "")
    if expires_at:
        try:
            expires_ts = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
            if time.time() > expires_ts:
                return True
        except Exception:
            pass
    
    # Check created_at with default expiry
    created_at = apply_plan.get("created_at", "")
    if created_at:
        try:
            created_ts = datetime.fromisoformat(created_at.replace("+0900", "+09:00")).timestamp()
            if time.time() > created_ts + DEFAULT_EXPIRY_SECONDS:
                return True
        except Exception:
            pass
    
    return False


def _get_verification_status(apply_plan_id: str) -> Optional[Dict[str, Any]]:
    """Get the latest verification status for an apply plan."""
    verifications = load_post_apply_verification_results()
    
    latest = None
    for v in verifications:
        if v.get("apply_plan_id") == apply_plan_id:
            latest = v
    
    return latest


def _is_verification_complete(verification: Optional[Dict[str, Any]]) -> bool:
    """Check if verification is complete (not pending).
    
    Args:
        verification: Verification record
        
    Returns:
        True if complete
    """
    if not verification:
        return False
    
    result = verification.get("result", "")
    return result in ("passed", "failed")


def evaluate_action_eligibility(
    action_type: str,
    entity_id: str,
    additional_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate whether an action is allowed.
    
    This is the main entry point for governance evaluation.
    
    IMPORTANT: This function only evaluates and records a decision.
    It does NOT execute any action.
    
    Args:
        action_type: Type of action (APPLY, PROMOTE, REVERT, COMMIT)
        entity_id: Entity ID (e.g., apply_plan_id, proposal_id)
        additional_context: Optional additional context
        
    Returns:
        Governance decision record
    """
    decision_id = str(uuid.uuid4())[:16]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    
    result = {
        "decision_id": decision_id,
        "action_type": action_type,
        "entity_id": entity_id,
        "decision": DECISION_DENIED,
        "reason": "",
        "manual_approval_required": False,
        "entity_status": {},
        "created_at": now,
        "additional_context": additional_context or {},
    }
    
    # Validate action type
    if action_type not in VALID_ACTIONS:
        result["decision"] = DECISION_DENIED
        result["reason"] = f"invalid_action_type: {action_type}"
        return result
    
    # ALL risky actions require manual approval
    if action_type in MANUAL_APPROVAL_REQUIRED_ACTIONS:
        result["manual_approval_required"] = True
    
    # Load apply plan if applicable (find the latest record)
    apply_plan = None
    if action_type in (ACTION_APPLY, ACTION_PROMOTE, ACTION_REVERT):
        plans = load_apply_plans()
        # Find the latest record for this apply_plan_id
        for p in reversed(plans):
            if p.get("apply_plan_id") == entity_id:
                apply_plan = p
                break
        
        if not apply_plan:
            result["decision"] = DECISION_DENIED
            result["reason"] = "apply_plan_not_found"
            return result
        
        result["entity_status"]["apply_plan_exists"] = True
        
        # Check expiry
        if _is_apply_plan_expired(apply_plan):
            result["decision"] = DECISION_INELIGIBLE_EXPIRED
            result["reason"] = "apply_plan_expired"
            return result
        
        result["entity_status"]["expired"] = False
        
        # Get verification status
        verification = _get_verification_status(entity_id)
        if verification:
            result["entity_status"]["verification_result"] = verification.get("result")
        
        # Check verification completeness for PROMOTE
        if action_type == ACTION_PROMOTE:
            if not _is_verification_complete(verification):
                result["decision"] = DECISION_INELIGIBLE_INCOMPLETE
                result["reason"] = "verification_incomplete"
                return result
            
            if verification.get("result") != "passed":
                result["decision"] = DECISION_DENIED
                result["reason"] = "verification_failed"
                return result
            
            # Check policy decision
            decisions = load_policy_decisions()
            latest_policy = None
            for d in decisions:
                if d.get("apply_plan_id") == entity_id:
                    latest_policy = d
            
            if latest_policy:
                result["entity_status"]["policy_decision"] = latest_policy.get("decision")
                
                # Even if PROMOTE_ELIGIBLE, still require manual approval
                if latest_policy.get("decision") != "PROMOTE_ELIGIBLE":
                    result["decision"] = DECISION_DENIED
                    result["reason"] = "policy_decision_not_promote_eligible"
                    return result
        
        # Check for REVERT
        if action_type == ACTION_REVERT:
            # Revert requires verification failure or explicit policy recommendation
            if verification and verification.get("result") == "passed":
                result["decision"] = DECISION_DENIED
                result["reason"] = "verification_passed_revert_not_warranted"
                return result
        
        # For APPLY, check if already applied
        latest_state = get_latest_apply_state(entity_id)
        if latest_state:
            result["entity_status"]["latest_apply_event"] = latest_state.get("event")
            
            if action_type == ACTION_APPLY:
                event = latest_state.get("event", "")
                if event in ("patch_attempt_succeeded", "apply_closed"):
                    result["decision"] = DECISION_DENIED
                    result["reason"] = "already_applied"
                    return result
    
    # All checks passed - action is allowed BUT requires manual approval
    result["decision"] = DECISION_MANUAL_APPROVAL_REQUIRED
    result["reason"] = "manual_approval_required_for_risky_action"
    
    # Record governance decision
    decisions_path = STATE_DIR / "governance_decisions.jsonl"
    _append_jsonl_record(result, decisions_path)
    
    return result


def record_governance_decision(
    action_type: str,
    entity_id: str,
    decision: str,
    reason: str,
    approver: str = "",
    additional_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record a governance decision (e.g., after manual approval).
    
    Args:
        action_type: Type of action
        entity_id: Entity ID
        decision: Decision outcome
        reason: Reason for decision
        approver: Who made the decision
        additional_context: Optional additional context
        
    Returns:
        Governance decision record
    """
    decision_id = str(uuid.uuid4())[:16]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    
    record = {
        "decision_id": decision_id,
        "action_type": action_type,
        "entity_id": entity_id,
        "decision": decision,
        "reason": reason,
        "approver": approver,
        "created_at": now,
        "additional_context": additional_context or {},
    }
    
    decisions_path = STATE_DIR / "governance_decisions.jsonl"
    _append_jsonl_record(record, decisions_path)
    
    return record


def get_action_eligibility_status(decision_id: str) -> Optional[Dict[str, Any]]:
    """Get the status of a governance decision.
    
    Args:
        decision_id: Decision ID
        
    Returns:
        Decision record or None if not found
    """
    decisions_path = STATE_DIR / "governance_decisions.jsonl"
    decisions = _load_jsonl_records(decisions_path)
    
    latest = None
    for d in decisions:
        if d.get("decision_id") == decision_id:
            latest = d
    
    return latest


def load_governance_decisions(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all governance decisions.
    
    Args:
        path: Optional path to decisions file
        
    Returns:
        List of decision records
    """
    if path is None:
        path = STATE_DIR / "governance_decisions.jsonl"
    return _load_jsonl_records(path)


def check_manual_approval_granted(
    action_type: str,
    entity_id: str,
) -> bool:
    """Check if manual approval has been granted for an action.
    
    Args:
        action_type: Type of action
        entity_id: Entity ID
        
    Returns:
        True if approval granted
    """
    decisions = load_governance_decisions()
    
    for d in decisions:
        if (d.get("action_type") == action_type and 
            d.get("entity_id") == entity_id and
            d.get("decision") == DECISION_ALLOWED and
            d.get("approver")):
            return True
    
    return False


def is_action_allowed(
    action_type: str,
    entity_id: str,
) -> Dict[str, Any]:
    """Check if an action is allowed (combines eligibility + approval check).
    
    Args:
        action_type: Type of action
        entity_id: Entity ID
        
    Returns:
        Dict with 'allowed' bool and 'reason' string
    """
    # First check eligibility
    eligibility = evaluate_action_eligibility(action_type, entity_id)
    
    if eligibility["decision"] == DECISION_DENIED:
        return {"allowed": False, "reason": eligibility["reason"]}
    
    if eligibility["decision"] in (DECISION_INELIGIBLE_EXPIRED, 
                                    DECISION_INELIGIBLE_INCOMPLETE,
                                    DECISION_INELIGIBLE_AMBIGUOUS):
        return {"allowed": False, "reason": eligibility["reason"]}
    
    # Check if manual approval has been granted
    if eligibility["manual_approval_required"]:
        if not check_manual_approval_granted(action_type, entity_id):
            return {"allowed": False, "reason": "manual_approval_not_granted"}
    
    return {"allowed": True, "reason": "eligible_and_approved"}
