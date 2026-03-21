#!/usr/bin/env python3
"""
Apply Lifecycle Separation Layer

This module provides apply lifecycle management functions.

Key principle: Proposal lifecycle and apply lifecycle are SEPARATE.
- Proposals track intent and approval
- Apply lifecycle tracks execution and verification
"""

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# State directory
BASE_DIR = Path(__file__).resolve().parents[1] / "state"


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
    """Load all records from a JSONL file, skipping corrupted lines."""
    if not path.exists():
        return []
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return records


# --- Apply Plans ---

def create_apply_plan(
    proposal_id: str,
    approved_by: str,
    patch_artifact_ref: str = "",
    expected_verifications: Optional[List[str]] = None,
    safety_constraints_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create an apply plan (frozen execution intent)."""
    import hashlib
    
    apply_plans_path = BASE_DIR / "apply_plans.jsonl"
    
    idempotency_key = str(uuid.uuid4())
    apply_plan_id = hashlib.md5(idempotency_key.encode()).hexdigest()[:16]
    
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    
    record = {
        "apply_plan_id": apply_plan_id,
        "proposal_id": proposal_id,
        "approved_by": approved_by,
        "approved_at": now,
        "patch_artifact_ref": patch_artifact_ref,
        "expected_verifications": expected_verifications or [],
        "safety_constraints_snapshot": safety_constraints_snapshot or {},
        "idempotency_key": idempotency_key,
        "eligibility_expires_at": "",
        "created_at": now,
    }
    
    _append_jsonl_record(record, apply_plans_path)
    record_apply_state_transition(apply_plan_id, "apply_plan_created", actor=approved_by)
    
    return record


def load_apply_plans(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all apply plans."""
    if path is None:
        path = BASE_DIR / "apply_plans.jsonl"
    return _load_jsonl_records(path)


# --- Apply State Transitions ---

def record_apply_state_transition(
    apply_plan_id: str,
    event: str,
    actor: str = "",
    reason: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Record an apply state transition event."""
    transitions_path = BASE_DIR / "apply_state_transitions.jsonl"
    
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    
    record = {
        "apply_plan_id": apply_plan_id,
        "event": event,
        "at": now,
        "actor": actor,
        "reason": reason,
    }
    
    if metadata:
        record["metadata"] = metadata
    
    return _append_jsonl_record(record, transitions_path)


def load_apply_state_transitions(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all apply state transitions."""
    if path is None:
        path = BASE_DIR / "apply_state_transitions.jsonl"
    return _load_jsonl_records(path)


def get_latest_apply_state(apply_plan_id: str) -> Optional[Dict[str, Any]]:
    """Get the latest state transition for an apply plan."""
    transitions = load_apply_state_transitions()
    matching = [t for t in transitions if t.get("apply_plan_id") == apply_plan_id]
    if not matching:
        return None
    return matching[-1]


# --- Execution Leases ---

def acquire_execution_lease(
    apply_plan_id: str,
    acquired_by: str,
    lease_scope: str = "patch_execution",
    expires_in_seconds: int = 3600,
) -> Dict[str, Any]:
    """Acquire an execution lease for an apply plan."""
    leases_path = BASE_DIR / "execution_leases.jsonl"
    
    active = find_active_lease_for_plan(apply_plan_id, leases_path)
    if active:
        return {
            "status": "blocked",
            "reason": f"existing_lease: {active.get('lease_id', 'unknown')}",
            "existing_lease": active,
        }
    
    now = time.time()
    expires_at = datetime.fromtimestamp(now + expires_in_seconds).strftime("%Y-%m-%dT%H:%M:%S%z")
    acquired_at = datetime.fromtimestamp(now).strftime("%Y-%m-%dT%H:%M:%S%z")
    
    lease_id = str(uuid.uuid4())[:16]
    
    record = {
        "lease_id": lease_id,
        "apply_plan_id": apply_plan_id,
        "acquired_at": acquired_at,
        "acquired_by": acquired_by,
        "lease_scope": lease_scope,
        "expires_at": expires_at,
        "status": "active",
    }
    
    _append_jsonl_record(record, leases_path)
    record_apply_state_transition(apply_plan_id, "execution_lease_acquired", actor=acquired_by)
    
    return record


def find_active_lease_for_plan(apply_plan_id: str, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Find an active lease for an apply plan."""
    if path is None:
        path = BASE_DIR / "execution_leases.jsonl"
    
    leases = _load_jsonl_records(path)
    now = time.time()
    
    for lease in leases:
        if lease.get("apply_plan_id") != apply_plan_id:
            continue
        if lease.get("status") != "active":
            continue
        
        expires_at = lease.get("expires_at", "")
        if expires_at:
            try:
                expires_ts = datetime.fromisoformat(expires_at.replace("+0900", "+09:00")).timestamp()
                if expires_ts < now:
                    continue
            except Exception:
                pass
        
        return lease
    
    return None


def load_execution_leases(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all execution leases."""
    if path is None:
        path = BASE_DIR / "execution_leases.jsonl"
    return _load_jsonl_records(path)


# --- Post-Apply Verification ---

def create_post_apply_verification(
    apply_plan_id: str,
    patch_attempt_id: str,
    verification_steps: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a post-apply verification task."""
    verifications_path = BASE_DIR / "post_apply_verification_results.jsonl"
    
    verification_id = str(uuid.uuid4())[:16]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    
    record = {
        "verification_id": verification_id,
        "apply_plan_id": apply_plan_id,
        "patch_attempt_id": patch_attempt_id,
        "started_at": now,
        "finished_at": "",
        "verification_steps": verification_steps or [],
        "result": "pending",
        "failure_codes": [],
        "summary": "",
        "evidence_refs": [],
    }
    
    _append_jsonl_record(record, verifications_path)
    record_apply_state_transition(apply_plan_id, "post_apply_verification_started", actor="verification_system")
    
    return record


def complete_post_apply_verification(
    verification_id: str,
    result: str,
    summary: str = "",
    failure_codes: Optional[List[str]] = None,
    evidence_refs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Complete a post-apply verification task."""
    verifications_path = BASE_DIR / "post_apply_verification_results.jsonl"
    
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    
    verifications = load_post_apply_verification_results()
    target = None
    for v in verifications:
        if v.get("verification_id") == verification_id:
            target = v
            break
    
    if not target:
        return {
            "verification_id": verification_id,
            "result": "error",
            "error": "verification_not_found",
        }
    
    record = {
        **target,
        "finished_at": now,
        "result": result,
        "summary": summary[:500] if summary else "",
        "failure_codes": failure_codes or [],
        "evidence_refs": evidence_refs or [],
    }
    
    _append_jsonl_record(record, verifications_path)
    
    event = "post_apply_verification_passed" if result == "passed" else "post_apply_verification_failed"
    record_apply_state_transition(
        target["apply_plan_id"],
        event,
        actor="verification_system",
        reason=summary[:200] if summary else "",
    )
    
    return record


def load_post_apply_verification_results(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all post-apply verification results."""
    if path is None:
        path = BASE_DIR / "post_apply_verification_results.jsonl"
    return _load_jsonl_records(path)


# --- Extended Patch Attempts ---

def create_extended_patch_attempt(
    apply_plan_id: str,
    execution_lease_id: str,
    executor_identity: str,
    patch_artifact_ref: str = "",
) -> Dict[str, Any]:
    """Create an extended patch attempt record."""
    attempts_path = BASE_DIR / "patch_attempt_results.jsonl"
    
    patch_attempt_id = str(uuid.uuid4())[:16]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    
    record = {
        "patch_attempt_id": patch_attempt_id,
        "apply_plan_id": apply_plan_id,
        "execution_lease_id": execution_lease_id,
        "started_at": now,
        "finished_at": "",
        "executor_identity": executor_identity,
        "patch_artifact_ref": patch_artifact_ref,
        "precondition_check_result": "",
        "execution_result": "pending",
        "failure_code": "",
        "failure_detail": "",
        "diff_summary": "",
        "produced_artifact_refs": [],
    }
    
    _append_jsonl_record(record, attempts_path)
    record_apply_state_transition(apply_plan_id, "patch_attempt_started", actor=executor_identity)
    
    return record


def complete_extended_patch_attempt(
    patch_attempt_id: str,
    execution_result: str,
    failure_code: str = "",
    failure_detail: str = "",
    diff_summary: str = "",
    produced_artifact_refs: Optional[List[str]] = None,
    precondition_check_result: str = "",
) -> Dict[str, Any]:
    """Complete an extended patch attempt record."""
    attempts_path = BASE_DIR / "patch_attempt_results.jsonl"
    
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    
    attempts = _load_jsonl_records(attempts_path)
    target = None
    for a in attempts:
        if a.get("patch_attempt_id") == patch_attempt_id:
            target = a
            break
    
    if not target:
        return {
            "patch_attempt_id": patch_attempt_id,
            "execution_result": "error",
            "error": "attempt_not_found",
        }
    
    record = {
        **target,
        "finished_at": now,
        "precondition_check_result": precondition_check_result,
        "execution_result": execution_result,
        "failure_code": failure_code,
        "failure_detail": failure_detail[:500] if failure_detail else "",
        "diff_summary": diff_summary[:200] if diff_summary else "",
        "produced_artifact_refs": produced_artifact_refs or [],
    }
    
    _append_jsonl_record(record, attempts_path)
    
    event = "patch_attempt_succeeded" if execution_result == "succeeded" else "patch_attempt_failed"
    record_apply_state_transition(
        target["apply_plan_id"],
        event,
        actor=target.get("executor_identity", "unknown"),
        reason=failure_code if failure_code else "",
    )
    
    return record
