#!/usr/bin/env python3
"""
Improvement Policy Engine

This module provides conservative policy evaluation for apply outcomes.
It records what the system should do next, WITHOUT executing any unsafe automation.

Key principles:
- NO automatic apply
- NO automatic rollback
- NO automatic commit
- NO automatic proposal promotion execution
- All risky actions remain manual
- Append-only state design
- Conservative policy decisions

Policy decision outcomes:
- PROMOTE_ELIGIBLE: Safe to promote (requires manual trigger)
- HOLD_REVIEW: Needs human review before any action
- REJECT: Should be rejected
- REVERT_CANDIDATE_RECOMMENDED: Rollback recommended (requires manual trigger)

Decision flow:
1. Read apply/patch/verification results
2. Evaluate outcome conservatively
3. Record structured policy decision
4. Optionally create revert candidate record
5. Do NOT execute any automated actions
"""

import json
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
    load_apply_state_transitions,
    get_latest_apply_state,
    load_post_apply_verification_results,
)

# State directory
STATE_DIR = PROJECT_ROOT / "state"

# Decision types
DECISION_PROMOTE_ELIGIBLE = "PROMOTE_ELIGIBLE"
DECISION_HOLD_REVIEW = "HOLD_REVIEW"
DECISION_REJECT = "REJECT"
DECISION_REVERT_CANDIDATE_RECOMMENDED = "REVERT_CANDIDATE_RECOMMENDED"

VALID_DECISIONS = {
    DECISION_PROMOTE_ELIGIBLE,
    DECISION_HOLD_REVIEW,
    DECISION_REJECT,
    DECISION_REVERT_CANDIDATE_RECOMMENDED,
}


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


def _get_verification_result(apply_plan_id: str) -> Optional[Dict[str, Any]]:
    """Get the latest verification result for an apply plan."""
    verifications = load_post_apply_verification_results()
    
    # Find the latest verification for this apply plan
    latest = None
    for v in verifications:
        if v.get("apply_plan_id") == apply_plan_id:
            latest = v
    
    return latest


def _determine_decision(
    verification_result: Optional[Dict[str, Any]],
    apply_state: Optional[Dict[str, Any]],
) -> str:
    """Determine policy decision based on verification and apply state.
    
    Conservative logic:
    - verification passed + sufficient evidence -> PROMOTE_ELIGIBLE
    - verification failed -> REJECT or REVERT_CANDIDATE_RECOMMENDED
    - missing/incomplete verification -> HOLD_REVIEW
    - ambiguous state -> HOLD_REVIEW
    
    Args:
        verification_result: Latest verification result
        apply_state: Latest apply state transition
        
    Returns:
        Decision type string
    """
    if not verification_result:
        # No verification found
        return DECISION_HOLD_REVIEW
    
    result = verification_result.get("result", "")
    
    # Check if verification passed
    if result == "passed":
        # Check for evidence
        evidence_refs = verification_result.get("evidence_refs", [])
        if evidence_refs and len(evidence_refs) >= 1:
            return DECISION_PROMOTE_ELIGIBLE
        else:
            # Passed but no evidence - conservative hold
            return DECISION_HOLD_REVIEW
    
    # Check if verification failed
    if result == "failed":
        # Check apply state for patch attempt status
        if apply_state:
            event = apply_state.get("event", "")
            # If patch was applied successfully but verification failed
            if event in ("post_apply_verification_failed", "patch_attempt_succeeded"):
                return DECISION_REVERT_CANDIDATE_RECOMMENDED
        
        # Default to reject
        return DECISION_REJECT
    
    # Unknown state - conservative hold
    return DECISION_HOLD_REVIEW


def evaluate_apply_outcome(
    apply_plan_id: str,
    additional_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate apply outcome and record policy decision.
    
    This is the main entry point for policy evaluation.
    
    IMPORTANT: This function only RECORDS a decision.
    It does NOT execute rollback, promotion, or any other action.
    
    Args:
        apply_plan_id: Apply plan ID to evaluate
        additional_context: Optional additional context for decision
        
    Returns:
        Policy decision record
    """
    decision_id = str(uuid.uuid4())[:16]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    
    result = {
        "decision_id": decision_id,
        "apply_plan_id": apply_plan_id,
        "decision": DECISION_HOLD_REVIEW,
        "reason": "",
        "verification_result": None,
        "apply_state": None,
        "evidence_refs": [],
        "created_at": now,
        "executed": False,  # Always False - decisions are not auto-executed
        "additional_context": additional_context or {},
    }
    
    # Load apply plan
    plans = load_apply_plans()
    plan = None
    for p in plans:
        if p.get("apply_plan_id") == apply_plan_id:
            plan = p
            break
    
    if not plan:
        result["decision"] = DECISION_REJECT
        result["reason"] = "apply_plan_not_found"
        return result
    
    # Get latest apply state
    apply_state = get_latest_apply_state(apply_plan_id)
    result["apply_state"] = apply_state.get("event") if apply_state else None
    
    # Get verification result
    verification_result = _get_verification_result(apply_plan_id)
    if verification_result:
        result["verification_result"] = verification_result.get("result")
        result["evidence_refs"] = verification_result.get("evidence_refs", [])
    
    # Determine decision
    decision = _determine_decision(verification_result, apply_state)
    result["decision"] = decision
    
    # Set reason based on decision
    if decision == DECISION_PROMOTE_ELIGIBLE:
        result["reason"] = "verification_passed_with_evidence"
    elif decision == DECISION_REJECT:
        result["reason"] = "verification_failed"
    elif decision == DECISION_REVERT_CANDIDATE_RECOMMENDED:
        result["reason"] = "verification_failed_patch_applied"
        # Create revert candidate record
        create_revert_candidate(
            apply_plan_id=apply_plan_id,
            decision_id=decision_id,
            reason="verification_failed_rollback_recommended",
        )
    else:
        result["reason"] = "insufficient_evidence_or_incomplete_verification"
    
    # Record decision
    decisions_path = STATE_DIR / "policy_decisions.jsonl"
    _append_jsonl_record(result, decisions_path)
    
    return result


def create_revert_candidate(
    apply_plan_id: str,
    decision_id: str,
    reason: str = "",
) -> Dict[str, Any]:
    """Create a revert candidate record.
    
    IMPORTANT: This only RECORDS a revert candidate.
    It does NOT execute rollback.
    
    Args:
        apply_plan_id: Apply plan ID
        decision_id: Associated policy decision ID
        reason: Reason for revert recommendation
        
    Returns:
        Revert candidate record
    """
    candidate_id = str(uuid.uuid4())[:16]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    
    record = {
        "candidate_id": candidate_id,
        "apply_plan_id": apply_plan_id,
        "decision_id": decision_id,
        "reason": reason,
        "status": "pending",  # pending, executed, dismissed
        "created_at": now,
        "executed_at": "",
        "executed_by": "",
    }
    
    candidates_path = STATE_DIR / "revert_candidates.jsonl"
    _append_jsonl_record(record, candidates_path)
    
    return record


def get_policy_decision_status(decision_id: str) -> Optional[Dict[str, Any]]:
    """Get the current status of a policy decision.
    
    Args:
        decision_id: Decision ID
        
    Returns:
        Decision status dict or None if not found
    """
    decisions_path = STATE_DIR / "policy_decisions.jsonl"
    decisions = _load_jsonl_records(decisions_path)
    
    # Find the latest record for this decision
    latest = None
    for d in decisions:
        if d.get("decision_id") == decision_id:
            latest = d
    
    return latest


def load_policy_decisions(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all policy decisions.
    
    Args:
        path: Optional path to decisions file
        
    Returns:
        List of decision records
    """
    if path is None:
        path = STATE_DIR / "policy_decisions.jsonl"
    return _load_jsonl_records(path)


def load_revert_candidates(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all revert candidates.
    
    Args:
        path: Optional path to candidates file
        
    Returns:
        List of candidate records
    """
    if path is None:
        path = STATE_DIR / "revert_candidates.jsonl"
    return _load_jsonl_records(path)


def get_pending_revert_candidates() -> List[Dict[str, Any]]:
    """Get all pending revert candidates.
    
    Returns:
        List of pending candidate records
    """
    candidates = load_revert_candidates()
    return [c for c in candidates if c.get("status") == "pending"]
