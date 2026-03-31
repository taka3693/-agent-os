#!/usr/bin/env python3
"""
Learning Outcome Classifier

This module classifies learning episodes into a conservative taxonomy.

Key principles:
- READ-ONLY classification
- NO automatic execution
- NO policy/governance modification
- Conservative taxonomy only

Outcome taxonomy:
- success_clean: Verification passed, policy approved, governance allowed
- success_high_friction: Success but required multiple attempts or approvals
- blocked_by_governance: Governance denied action
- failed_verification: Verification failed
- rejected_low_confidence: Policy rejected with low confidence
- stale_abandoned: Plan became stale before completion
- revert_recommended: Revert candidate was created

NOTE: Classification is stored in learning_episodes.jsonl, not a separate file.
This follows the conservative design principle of minimizing state files.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from learning.episode_store import (
    load_learning_episodes,
    get_episode_by_id,
    _append_jsonl_record,
)

# State directory
STATE_DIR = PROJECT_ROOT / "state"

# Outcome taxonomy
OUTCOME_SUCCESS_CLEAN = "success_clean"
OUTCOME_SUCCESS_HIGH_FRICTION = "success_high_friction"
OUTCOME_BLOCKED_BY_GOVERNANCE = "blocked_by_governance"
OUTCOME_FAILED_VERIFICATION = "failed_verification"
OUTCOME_REJECTED_LOW_CONFIDENCE = "rejected_low_confidence"
OUTCOME_STALE_ABANDONED = "stale_abandoned"
OUTCOME_REVERT_RECOMMENDED = "revert_recommended"

VALID_OUTCOMES = {
    OUTCOME_SUCCESS_CLEAN,
    OUTCOME_SUCCESS_HIGH_FRICTION,
    OUTCOME_BLOCKED_BY_GOVERNANCE,
    OUTCOME_FAILED_VERIFICATION,
    OUTCOME_REJECTED_LOW_CONFIDENCE,
    OUTCOME_STALE_ABANDONED,
    OUTCOME_REVERT_RECOMMENDED,
}


def classify_episode_outcome(episode_id: str) -> Dict[str, Any]:
    """Classify an episode's outcome.
    
    This function READS from episode data and classifies
    into a conservative taxonomy.
    
    The classification is appended as a new record to learning_episodes.jsonl
    with the same episode_id but updated classification fields.
    
    Args:
        episode_id: Episode ID to classify
        
    Returns:
        Classification result dict
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    result = {
        "episode_id": episode_id,
        "outcome": None,
        "classification_reason": "",
        "classification_confidence": "low",
        "classification_factors": [],
        "classified_at": now,
    }
    
    # Load episode
    episode = get_episode_by_id(episode_id)
    
    if not episode:
        result["error"] = "episode_not_found"
        return result
    
    # Extract factors
    verification_outcome = episode.get("verification_outcome")
    policy_outcome = episode.get("policy_outcome")
    governance_outcome = episode.get("governance_outcome")
    revert_candidate_created = episode.get("revert_candidate_created", False)
    stale_flag = episode.get("stale_flag", False)
    failure_codes = episode.get("failure_codes", [])
    
    factors = []
    
    # Classification logic (conservative)
    
    # Check stale first
    if stale_flag:
        result["outcome"] = OUTCOME_STALE_ABANDONED
        result["classification_reason"] = "Episode became stale before completion"
        factors.append("stale_flag")
    
    # Check revert recommended
    elif revert_candidate_created:
        result["outcome"] = OUTCOME_REVERT_RECOMMENDED
        result["classification_reason"] = "Revert candidate was created"
        factors.append("revert_candidate_created")
        if failure_codes:
            factors.append(f"failure_codes:{','.join(failure_codes[:3])}")
    
    # Check governance blocked
    elif governance_outcome in ("DENIED", "INELIGIBLE_EXPIRED", "INELIGIBLE_INCOMPLETE", "INELIGIBLE_AMBIGUOUS"):
        result["outcome"] = OUTCOME_BLOCKED_BY_GOVERNANCE
        result["classification_reason"] = f"Governance outcome: {governance_outcome}"
        factors.append(f"governance:{governance_outcome}")
    
    # Check verification failed
    elif verification_outcome == "failed":
        result["outcome"] = OUTCOME_FAILED_VERIFICATION
        result["classification_reason"] = "Verification failed"
        factors.append("verification:failed")
        if failure_codes:
            factors.append(f"failure_codes:{','.join(failure_codes[:3])}")
    
    # Check policy rejected
    elif policy_outcome in ("REJECT", "HOLD_REVIEW"):
        result["outcome"] = OUTCOME_REJECTED_LOW_CONFIDENCE
        result["classification_reason"] = f"Policy outcome: {policy_outcome}"
        factors.append(f"policy:{policy_outcome}")
    
    # Check success
    elif verification_outcome == "passed" and policy_outcome == "PROMOTE_ELIGIBLE":
        # Check if high friction
        time_to_close = episode.get("time_to_close_minutes")
        if time_to_close and time_to_close > 60:  # More than 1 hour
            result["outcome"] = OUTCOME_SUCCESS_HIGH_FRICTION
            result["classification_reason"] = f"Success but took {time_to_close} minutes"
            factors.append("high_friction")
            factors.append(f"time_to_close:{time_to_close}")
        else:
            result["outcome"] = OUTCOME_SUCCESS_CLEAN
            result["classification_reason"] = "Clean success"
            factors.append("clean_success")
    
    # Default: low confidence classification
    else:
        result["outcome"] = OUTCOME_REJECTED_LOW_CONFIDENCE
        result["classification_reason"] = "Unable to classify with high confidence"
        factors.append("default_classification")
    
    result["classification_factors"] = factors
    
    # Store classification as a new episode record (append-only)
    # This preserves the original episode and adds classification
    classified_episode = dict(episode)  # Copy original
    classified_episode.update({
        "outcome": result["outcome"],
        "classification_reason": result["classification_reason"],
        "classification_confidence": result["classification_confidence"],
        "classification_factors": result["classification_factors"],
        "classified_at": now,
    })
    
    episodes_path = STATE_DIR / "learning_episodes.jsonl"
    _append_jsonl_record(classified_episode, episodes_path)
    
    return result


def get_latest_classification(episode_id: str) -> Optional[Dict[str, Any]]:
    """Get the latest classification for an episode.
    
    Args:
        episode_id: Episode ID
        
    Returns:
        Latest classified episode record or None
    """
    episodes = load_learning_episodes()
    
    # Find all records for this episode with classification
    classified = [
        e for e in episodes
        if e.get("episode_id") == episode_id and "outcome" in e
    ]
    
    if not classified:
        return None
    
    # Return the most recent (last in file)
    return classified[-1]


def get_outcome_statistics() -> Dict[str, Any]:
    """Get statistics on outcome distribution.
    
    Returns:
        Dict with outcome counts and percentages
    """
    episodes = load_learning_episodes()
    
    # Only count classified episodes (those with outcome field)
    classified = [e for e in episodes if "outcome" in e]
    
    stats = {
        "total_episodes": len(episodes),
        "total_classified": len(classified),
        "by_outcome": {},
    }
    
    # Count unique episodes (by episode_id) with their latest classification
    episode_outcomes = {}
    for e in reversed(classified):  # Process in reverse to get latest first
        episode_id = e.get("episode_id")
        if episode_id and episode_id not in episode_outcomes:
            episode_outcomes[episode_id] = e.get("outcome", "unknown")
    
    for outcome in episode_outcomes.values():
        stats["by_outcome"][outcome] = stats["by_outcome"].get(outcome, 0) + 1
    
    # Calculate percentages based on unique classified episodes
    unique_count = len(episode_outcomes)
    if unique_count > 0:
        stats["percentages"] = {
            outcome: (count / unique_count) * 100
            for outcome, count in stats["by_outcome"].items()
        }
    else:
        stats["percentages"] = {}
    
    return stats


def classify_all_episodes() -> List[Dict[str, Any]]:
    """Classify all unclassified episodes.
    
    Returns:
        List of classification results
    """
    episodes = load_learning_episodes()
    
    # Get already classified episode IDs
    classified_ids = set()
    for e in episodes:
        if "outcome" in e and e.get("episode_id"):
            classified_ids.add(e["episode_id"])
    
    results = []
    for episode in episodes:
        episode_id = episode.get("episode_id")
        if episode_id and episode_id not in classified_ids:
            result = classify_episode_outcome(episode_id)
            results.append(result)
    
    return results
