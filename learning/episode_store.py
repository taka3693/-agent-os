#!/usr/bin/env python3
"""
Learning Episode Store

This module captures completed improvement episodes and stores them
for learning and pattern detection.

Key principles:
- READ-ONLY access to existing state files
- Append-only learning state
- NO direct repository mutation
- NO automatic execution

Episode capture aggregates cross-layer information:
- Apply lifecycle state
- Verification results
- Policy decisions
- Governance decisions
"""

import json
import uuid
from datetime import datetime, timezone
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
    load_apply_state_transitions,
)
from policy.improvement_policy import load_policy_decisions, load_revert_candidates
from governance.operating_policy import load_governance_decisions

# State directory
STATE_DIR = PROJECT_ROOT / "state"


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


def _derive_patch_type(patch_artifact_ref: str) -> str:
    """Derive patch type from artifact reference.
    
    Returns a conservative classification.
    """
    if not patch_artifact_ref:
        return "unknown"
    
    ref_lower = patch_artifact_ref.lower()
    
    if ".py" in ref_lower:
        return "python_code"
    elif ".js" in ref_lower or ".ts" in ref_lower:
        return "javascript_code"
    elif ".md" in ref_lower:
        return "documentation"
    elif ".json" in ref_lower or ".yaml" in ref_lower or ".yml" in ref_lower:
        return "configuration"
    elif ".sh" in ref_lower:
        return "shell_script"
    else:
        return "other"


def _derive_target_area(file_refs: List[str]) -> str:
    """Derive target area from file references.
    
    Returns a conservative area classification.
    """
    if not file_refs:
        return "unknown"
    
    areas = set()
    for ref in file_refs:
        ref_lower = ref.lower()
        if "execution/" in ref_lower or "executor" in ref_lower:
            areas.add("execution")
        elif "guard" in ref_lower:
            areas.add("safety")
        elif "verification" in ref_lower or "verify" in ref_lower:
            areas.add("verification")
        elif "policy" in ref_lower:
            areas.add("policy")
        elif "governance" in ref_lower:
            areas.add("governance")
        elif "scheduler" in ref_lower:
            areas.add("scheduler")
        elif "audit" in ref_lower or "report" in ref_lower:
            areas.add("reporting")
        elif "tools/" in ref_lower:
            areas.add("tools")
        elif "tests/" in ref_lower:
            areas.add("testing")
        elif "docs/" in ref_lower:
            areas.add("documentation")
    
    if not areas:
        return "other"
    elif len(areas) == 1:
        return list(areas)[0]
    else:
        return "multiple"


def _derive_time_to_close(apply_plan_id: str) -> Optional[int]:
    """Derive time to close in minutes from apply state transitions.
    
    Returns None if not closable or data incomplete.
    """
    transitions = load_apply_state_transitions()
    
    created_at = None
    closed_at = None
    
    for t in transitions:
        if t.get("apply_plan_id") != apply_plan_id:
            continue
        
        event = t.get("event", "")
        at = t.get("at", "")
        
        if event == "apply_plan_created" and not created_at:
            created_at = at
        elif event in ("apply_closed", "post_apply_verification_passed") and not closed_at:
            closed_at = at
    
    if not created_at or not closed_at:
        return None
    
    try:
        # Parse ISO format timestamps
        created_ts = datetime.fromisoformat(created_at.replace("Z", "+00:00").replace("+0900", "+09:00"))
        closed_ts = datetime.fromisoformat(closed_at.replace("Z", "+00:00").replace("+0900", "+09:00"))
        
        # Calculate minutes
        delta = (closed_ts - created_ts).total_seconds() / 60
        return int(delta)
    except Exception:
        return None


def _find_revert_candidate(apply_plan_id: str) -> Optional[Dict[str, Any]]:
    """Find revert candidate for an apply plan."""
    candidates = load_revert_candidates()
    for c in candidates:
        if c.get("apply_plan_id") == apply_plan_id:
            return c
    return None


def record_episode_from_apply_plan(apply_plan_id: str) -> Dict[str, Any]:
    """Record a learning episode from an apply plan.
    
    This function READS from existing state files and aggregates
    cross-layer information into a single episode record.
    
    It does NOT mutate any existing state.
    
    Args:
        apply_plan_id: Apply plan ID to capture
        
    Returns:
        Episode record dict
    """
    episode_id = str(uuid.uuid4())[:16]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    episode = {
        "episode_id": episode_id,
        "apply_plan_id": apply_plan_id,
        "patch_attempt_id": None,
        "verification_id": None,
        "policy_decision_id": None,
        "governance_decision_id": None,
        "patch_type": "unknown",
        "target_area": "unknown",
        "verification_outcome": None,
        "policy_outcome": None,
        "governance_outcome": None,
        "final_operator_action": None,
        "revert_candidate_created": False,
        "failure_codes": [],
        "time_to_close_minutes": None,
        "stale_flag": False,
        "evidence_refs": [],
        "created_at": now,
    }
    
    # Load apply plan
    apply_plans = load_apply_plans()
    apply_plan = None
    for p in reversed(apply_plans):  # Get latest
        if p.get("apply_plan_id") == apply_plan_id:
            apply_plan = p
            break
    
    if not apply_plan:
        episode["error"] = "apply_plan_not_found"
        return episode
    
    # Derive patch type and target area
    patch_ref = apply_plan.get("patch_artifact_ref", "")
    episode["patch_type"] = _derive_patch_type(patch_ref)
    
    # Collect all file references for target area
    file_refs = []
    if patch_ref:
        file_refs.append(patch_ref)
    episode["target_area"] = _derive_target_area(file_refs)
    
    # Get latest apply state
    latest_state = get_latest_apply_state(apply_plan_id)
    if latest_state:
        event = latest_state.get("event", "")
        
        # Derive final operator action
        if event == "apply_closed":
            episode["final_operator_action"] = "closed"
        elif event == "patch_attempt_failed":
            episode["final_operator_action"] = "patch_failed"
        elif event == "post_apply_verification_failed":
            episode["final_operator_action"] = "verification_failed"
        elif event in ("apply_plan_created", "execution_lease_acquired"):
            episode["final_operator_action"] = "in_progress"
    
    # Get verification results
    verifications = load_post_apply_verification_results()
    for v in reversed(verifications):
        if v.get("apply_plan_id") == apply_plan_id:
            episode["verification_id"] = v.get("verification_id")
            episode["verification_outcome"] = v.get("result")
            episode["failure_codes"] = v.get("failure_codes", [])
            episode["evidence_refs"] = v.get("evidence_refs", [])
            break
    
    # Get policy decision
    policy_decisions = load_policy_decisions()
    for p in reversed(policy_decisions):
        if p.get("apply_plan_id") == apply_plan_id:
            episode["policy_decision_id"] = p.get("decision_id")
            episode["policy_outcome"] = p.get("decision")
            break
    
    # Get governance decision
    governance_decisions = load_governance_decisions()
    for g in reversed(governance_decisions):
        if g.get("entity_id") == apply_plan_id:
            episode["governance_decision_id"] = g.get("decision_id")
            episode["governance_outcome"] = g.get("decision")
            break
    
    # Check for revert candidate
    revert_candidate = _find_revert_candidate(apply_plan_id)
    if revert_candidate:
        episode["revert_candidate_created"] = True
    
    # Derive time to close
    episode["time_to_close_minutes"] = _derive_time_to_close(apply_plan_id)
    
    # Check stale flag (created > 24h ago and not closed)
    created_at = apply_plan.get("created_at", "")
    if created_at:
        try:
            created_ts = datetime.fromisoformat(created_at.replace("Z", "+00:00").replace("+0900", "+09:00")).timestamp()
            now_ts = datetime.now(timezone.utc).timestamp()
            if (now_ts - created_ts) > 24 * 60 * 60:  # 24 hours
                if episode["final_operator_action"] != "closed":
                    episode["stale_flag"] = True
        except Exception:
            pass
    
    # Store episode
    episodes_path = STATE_DIR / "learning_episodes.jsonl"
    _append_jsonl_record(episode, episodes_path)
    
    return episode


def load_learning_episodes(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all learning episodes.
    
    Args:
        path: Optional path to episodes file
        
    Returns:
        List of episode records
    """
    if path is None:
        path = STATE_DIR / "learning_episodes.jsonl"
    return _load_jsonl_records(path)


def get_episode_by_id(episode_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific episode by ID.
    
    Args:
        episode_id: Episode ID
        
    Returns:
        Episode record or None
    """
    episodes = load_learning_episodes()
    for e in episodes:
        if e.get("episode_id") == episode_id:
            return e
    return None


def get_episodes_by_apply_plan(apply_plan_id: str) -> List[Dict[str, Any]]:
    """Get all episodes for an apply plan.
    
    Args:
        apply_plan_id: Apply plan ID
        
    Returns:
        List of episode records
    """
    episodes = load_learning_episodes()
    return [e for e in episodes if e.get("apply_plan_id") == apply_plan_id]
