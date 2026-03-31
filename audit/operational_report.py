#!/usr/bin/env python3
"""
Audit / Operational Reporting Layer

This module provides conservative operational summaries and audit reports
by reconstructing current status from append-only state files.

Key principles:
- READ-ONLY: Never mutates any state
- NO automation
- NO scheduling
- Reconstructs status from append-only records
- Conservative identification of pending/failed/stale items

Reporting capabilities:
- Apply plan operational status
- Operational summary across all queues/states
- Pending manual actions
- Failed/denied/stale entities
- Revert recommendations

State files used (all read-only):
- state/apply_plans.jsonl
- state/apply_state_transitions.jsonl
- state/post_apply_verification_results.jsonl
- state/policy_decisions.jsonl
- state/revert_candidates.jsonl
- state/governance_decisions.jsonl
- state/proposal_queue.jsonl
- state/proposal_state_transitions.jsonl
- state/simulation_results.jsonl
"""

import json
from datetime import datetime, timezone
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
    load_execution_leases,
    load_post_apply_verification_results,
)
from policy.improvement_policy import (
    load_policy_decisions,
    load_revert_candidates,
    get_pending_revert_candidates,
)
from governance.operating_policy import (
    load_governance_decisions,
)

# State directory
STATE_DIR = PROJECT_ROOT / "state"

# Staleness threshold (in seconds)
STALE_THRESHOLD_SECONDS = 24 * 60 * 60  # 24 hours


def _load_jsonl_records(path: Path) -> List[Dict[str, Any]]:
    """Load all records from a JSONL file (read-only)."""
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


def _find_latest_record(records: List[Dict[str, Any]], key: str, value: str) -> Optional[Dict[str, Any]]:
    """Find the latest record matching a key-value pair."""
    for record in reversed(records):
        if record.get(key) == value:
            return record
    return None


def _is_stale(timestamp_str: str, threshold_seconds: int = STALE_THRESHOLD_SECONDS) -> bool:
    """Check if a timestamp is stale.
    
    Args:
        timestamp_str: ISO format timestamp string
        threshold_seconds: Staleness threshold in seconds
        
    Returns:
        True if stale
    """
    if not timestamp_str:
        return False
    
    try:
        # Handle various timestamp formats
        ts = timestamp_str.replace("Z", "+00:00").replace("+0900", "+09:00")
        created_ts = datetime.fromisoformat(ts).timestamp()
        now_ts = datetime.now(timezone.utc).timestamp()
        return (now_ts - created_ts) > threshold_seconds
    except Exception:
        return False


def get_apply_plan_operational_status(apply_plan_id: str) -> Dict[str, Any]:
    """Reconstruct the current operational status for an apply plan.
    
    This function READS from multiple append-only state files to reconstruct
    the current status. It does NOT mutate any state.
    
    Args:
        apply_plan_id: Apply plan ID
        
    Returns:
        Reconstructed operational status dict
    """
    status = {
        "apply_plan_id": apply_plan_id,
        "apply_plan_exists": False,
        "latest_apply_state": None,
        "latest_patch_attempt_status": None,
        "latest_verification_status": None,
        "latest_policy_decision": None,
        "latest_governance_decision": None,
        "next_manual_action": None,
        "stale_or_blocked_reason": None,
        "evidence_refs": [],
        "is_stale": False,
    }
    
    # Load apply plan
    apply_plans = load_apply_plans()
    apply_plan = _find_latest_record(apply_plans, "apply_plan_id", apply_plan_id)
    
    if not apply_plan:
        status["stale_or_blocked_reason"] = "apply_plan_not_found"
        return status
    
    status["apply_plan_exists"] = True
    status["created_at"] = apply_plan.get("created_at", "")
    
    # Check staleness
    if _is_stale(apply_plan.get("created_at", "")):
        status["is_stale"] = True
        status["stale_or_blocked_reason"] = "apply_plan_stale"
    
    # Get latest apply state
    latest_state = get_latest_apply_state(apply_plan_id)
    if latest_state:
        status["latest_apply_state"] = latest_state.get("event")
    
    # Get patch attempt status by looking at all state transitions
    transitions = load_apply_state_transitions()
    patch_events = []
    for t in transitions:
        if t.get("apply_plan_id") == apply_plan_id:
            event = t.get("event", "")
            if event.startswith("patch_attempt_"):
                patch_events.append(event)
    
    # Determine patch attempt status from events
    if "patch_attempt_succeeded" in patch_events:
        status["latest_patch_attempt_status"] = "succeeded"
    elif "patch_attempt_failed" in patch_events:
        status["latest_patch_attempt_status"] = "failed"
    elif "patch_attempt_started" in patch_events:
        status["latest_patch_attempt_status"] = "started"
    
    # Get latest verification status
    verifications = load_post_apply_verification_results()
    latest_verification = _find_latest_record(verifications, "apply_plan_id", apply_plan_id)
    
    if latest_verification:
        status["latest_verification_status"] = latest_verification.get("result")
        status["evidence_refs"] = latest_verification.get("evidence_refs", [])
        
        if latest_verification.get("result") == "failed":
            if not status["stale_or_blocked_reason"]:
                status["stale_or_blocked_reason"] = "verification_failed"
    
    # Get latest policy decision
    policy_decisions = load_policy_decisions()
    latest_policy = _find_latest_record(policy_decisions, "apply_plan_id", apply_plan_id)
    
    if latest_policy:
        status["latest_policy_decision"] = latest_policy.get("decision")
    
    # Get latest governance decision
    governance_decisions = load_governance_decisions()
    latest_governance = _find_latest_record(governance_decisions, "entity_id", apply_plan_id)
    
    if latest_governance:
        status["latest_governance_decision"] = latest_governance.get("decision")
    
    # Determine next manual action
    status["next_manual_action"] = _determine_next_manual_action(status)
    
    return status


def _determine_next_manual_action(status: Dict[str, Any]) -> Optional[str]:
    """Determine the next manual action required for an apply plan.
    
    Args:
        status: Reconstructed status dict
        
    Returns:
        Next manual action string or None
    """
    if not status.get("apply_plan_exists"):
        return None
    
    if status.get("is_stale"):
        return "REVIEW_STALE_PLAN"
    
    latest_state = status.get("latest_apply_state")
    verification_status = status.get("latest_verification_status")
    policy_decision = status.get("latest_policy_decision")
    governance_decision = status.get("latest_governance_decision")
    
    # No apply state yet
    if not latest_state or latest_state == "apply_plan_created":
        return "APPROVE_AND_EXECUTE_APPLY"
    
    # Patch attempted but no verification
    if latest_state in ("patch_attempt_succeeded", "patch_attempt_failed"):
        if not verification_status or verification_status == "pending":
            return "RUN_POST_APPLY_VERIFICATION"
    
    # Verification passed, awaiting policy evaluation
    if verification_status == "passed":
        if not policy_decision:
            return "EVALUATE_POLICY"
        
        if policy_decision == "PROMOTE_ELIGIBLE":
            if governance_decision == "MANUAL_APPROVAL_REQUIRED":
                return "MANUAL_APPROVE_PROMOTE"
            elif governance_decision == "ALLOWED":
                return "EXECUTE_PROMOTE"
    
    # Verification failed
    if verification_status == "failed":
        if not policy_decision:
            return "EVALUATE_POLICY"
        
        if policy_decision == "REVERT_CANDIDATE_RECOMMENDED":
            if governance_decision == "MANUAL_APPROVAL_REQUIRED":
                return "MANUAL_APPROVE_REVERT"
    
    # Default: review needed
    return "MANUAL_REVIEW"


def build_operational_summary() -> Dict[str, Any]:
    """Build an operational summary across all queues/states.
    
    This function READS from multiple append-only state files.
    It does NOT mutate any state.
    
    Returns:
        Operational summary dict with counts and lists
    """
    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ok",
        "pending_manual_review": [],
        "pending_apply_actions": [],
        "pending_verifications": [],
        "failed_verifications": [],
        "revert_candidates_pending": [],
        "governance_denied_items": [],
        "stale_items": [],
        "counts": {
            "apply_plans": 0,
            "pending_manual_review": 0,
            "pending_apply_actions": 0,
            "pending_verifications": 0,
            "failed_verifications": 0,
            "revert_candidates_pending": 0,
            "governance_denied_items": 0,
            "stale_items": 0,
        },
    }
    
    # Load all state
    apply_plans = load_apply_plans()
    summary["counts"]["apply_plans"] = len(apply_plans)
    
    verifications = load_post_apply_verification_results()
    policy_decisions = load_policy_decisions()
    revert_candidates = load_revert_candidates()
    governance_decisions = load_governance_decisions()
    
    # Find pending verifications
    for v in verifications:
        if v.get("result") == "pending":
            summary["pending_verifications"].append({
                "verification_id": v.get("verification_id"),
                "apply_plan_id": v.get("apply_plan_id"),
            })
    summary["counts"]["pending_verifications"] = len(summary["pending_verifications"])
    
    # Find failed verifications
    for v in verifications:
        if v.get("result") == "failed":
            summary["failed_verifications"].append({
                "verification_id": v.get("verification_id"),
                "apply_plan_id": v.get("apply_plan_id"),
                "failure_codes": v.get("failure_codes", []),
            })
    summary["counts"]["failed_verifications"] = len(summary["failed_verifications"])
    
    # Find pending revert candidates
    pending_reverts = get_pending_revert_candidates()
    for c in pending_reverts:
        summary["revert_candidates_pending"].append({
            "candidate_id": c.get("candidate_id"),
            "apply_plan_id": c.get("apply_plan_id"),
            "reason": c.get("reason"),
        })
    summary["counts"]["revert_candidates_pending"] = len(summary["revert_candidates_pending"])
    
    # Find governance denied items
    for g in governance_decisions:
        if g.get("decision") in ("DENIED", "INELIGIBLE_EXPIRED", "INELIGIBLE_INCOMPLETE", "INELIGIBLE_AMBIGUOUS"):
            summary["governance_denied_items"].append({
                "decision_id": g.get("decision_id"),
                "action_type": g.get("action_type"),
                "entity_id": g.get("entity_id"),
                "decision": g.get("decision"),
                "reason": g.get("reason"),
            })
    summary["counts"]["governance_denied_items"] = len(summary["governance_denied_items"])
    
    # Find stale items and pending manual actions
    for plan in apply_plans:
        apply_plan_id = plan.get("apply_plan_id")
        status = get_apply_plan_operational_status(apply_plan_id)
        
        if status.get("is_stale"):
            summary["stale_items"].append({
                "apply_plan_id": apply_plan_id,
                "reason": status.get("stale_or_blocked_reason"),
            })
        
        next_action = status.get("next_manual_action")
        if next_action and next_action not in (None, "MANUAL_REVIEW"):
            if "APPROVE" in next_action or "EXECUTE" in next_action:
                summary["pending_apply_actions"].append({
                    "apply_plan_id": apply_plan_id,
                    "action": next_action,
                })
        elif next_action == "MANUAL_REVIEW":
            summary["pending_manual_review"].append({
                "apply_plan_id": apply_plan_id,
                "reason": status.get("stale_or_blocked_reason"),
            })
    
    summary["counts"]["stale_items"] = len(summary["stale_items"])
    summary["counts"]["pending_apply_actions"] = len(summary["pending_apply_actions"])
    summary["counts"]["pending_manual_review"] = len(summary["pending_manual_review"])
    
    return summary


def build_apply_plan_audit_report(apply_plan_id: str) -> Dict[str, Any]:
    """Build a detailed audit report for an apply plan.
    
    This function READS from multiple append-only state files.
    It does NOT mutate any state.
    
    Args:
        apply_plan_id: Apply plan ID
        
    Returns:
        Detailed audit report dict
    """
    report = {
        "apply_plan_id": apply_plan_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "operational_status": get_apply_plan_operational_status(apply_plan_id),
        "apply_state_history": [],
        "verification_history": [],
        "policy_decision_history": [],
        "governance_decision_history": [],
    }
    
    # Get apply state history
    transitions = load_apply_state_transitions()
    for t in transitions:
        if t.get("apply_plan_id") == apply_plan_id:
            report["apply_state_history"].append({
                "event": t.get("event"),
                "at": t.get("at"),
                "actor": t.get("actor"),
                "reason": t.get("reason"),
            })
    
    # Get verification history
    verifications = load_post_apply_verification_results()
    for v in verifications:
        if v.get("apply_plan_id") == apply_plan_id:
            report["verification_history"].append({
                "verification_id": v.get("verification_id"),
                "result": v.get("result"),
                "started_at": v.get("started_at"),
                "finished_at": v.get("finished_at"),
                "summary": v.get("summary"),
                "failure_codes": v.get("failure_codes", []),
                "evidence_refs": v.get("evidence_refs", []),
            })
    
    # Get policy decision history
    policy_decisions = load_policy_decisions()
    for p in policy_decisions:
        if p.get("apply_plan_id") == apply_plan_id:
            report["policy_decision_history"].append({
                "decision_id": p.get("decision_id"),
                "decision": p.get("decision"),
                "reason": p.get("reason"),
                "created_at": p.get("created_at"),
                "evidence_refs": p.get("evidence_refs", []),
            })
    
    # Get governance decision history
    governance_decisions = load_governance_decisions()
    for g in governance_decisions:
        if g.get("entity_id") == apply_plan_id:
            report["governance_decision_history"].append({
                "decision_id": g.get("decision_id"),
                "action_type": g.get("action_type"),
                "decision": g.get("decision"),
                "reason": g.get("reason"),
                "approver": g.get("approver"),
                "created_at": g.get("created_at"),
            })
    
    return report


def list_all_apply_plans_status() -> List[Dict[str, Any]]:
    """List operational status for all apply plans.
    
    This function READS from state files.
    It does NOT mutate any state.
    
    Returns:
        List of operational status dicts
    """
    apply_plans = load_apply_plans()
    statuses = []
    
    seen_ids = set()
    for plan in reversed(apply_plans):
        apply_plan_id = plan.get("apply_plan_id")
        if apply_plan_id not in seen_ids:
            seen_ids.add(apply_plan_id)
            status = get_apply_plan_operational_status(apply_plan_id)
            statuses.append(status)
    
    return statuses
