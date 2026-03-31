#!/usr/bin/env python3
"""
Learning Insight Report

This module generates structured learning insights from accumulated episodes.

Key principles:
- READ-ONLY analysis
- Insight generation only (NO execution)
- NO automatic policy/governance modification
- Conservative pattern detection only

Insight types:
- Repeated verification failures by patch type/area
- Repeated governance denials by reason
- Repeated stale/manual bottlenecks
- Repeated revert recommendations
- Repeated ambiguous/incomplete states
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from learning.episode_store import load_learning_episodes, _append_jsonl_record

# State directory
STATE_DIR = PROJECT_ROOT / "state"


def _get_classified_episodes() -> Dict[str, Dict[str, Any]]:
    """Get latest classification for each episode.
    
    Returns:
        Dict mapping episode_id to latest classified episode record
    """
    episodes = load_learning_episodes()
    
    # Only count episodes with classification (outcome field)
    classified = [e for e in episodes if "outcome" in e]
    
    # Build lookup with latest classification (last in file wins)
    result = {}
    for e in classified:
        episode_id = e.get("episode_id")
        if episode_id:
            result[episode_id] = e
    
    return result


def generate_learning_insights() -> Dict[str, Any]:
    """Generate learning insights from accumulated episodes.
    
    This function READS from episode and classification data
    and generates structured insights.
    
    It does NOT modify any execution state.
    
    Returns:
        Insights dict
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    insights = {
        "generated_at": now,
        "insight_id": None,
        "patterns": [],
        "recommendations": [],
        "statistics": {},
        "note": "Insights are recommendations only. No automatic execution.",
    }
    
    # Load data
    all_episodes = load_learning_episodes()
    classified_episodes = _get_classified_episodes()
    
    if not all_episodes:
        insights["note"] = "No episodes available for analysis"
        return insights
    
    # Build lookup for original episodes
    episode_by_id = {}
    for e in all_episodes:
        episode_id = e.get("episode_id")
        if episode_id and episode_id not in episode_by_id:
            episode_by_id[episode_id] = e
    
    # Analyze patterns
    
    # 1. Verification failures by patch type
    verification_failures_by_type = defaultdict(list)
    verification_failures_by_area = defaultdict(list)
    
    for episode_id, episode in classified_episodes.items():
        if episode.get("outcome") == "failed_verification":
            patch_type = episode.get("patch_type", "unknown")
            target_area = episode.get("target_area", "unknown")
            failure_codes = episode.get("failure_codes", [])
            
            verification_failures_by_type[patch_type].append({
                "episode_id": episode_id,
                "failure_codes": failure_codes,
            })
            verification_failures_by_area[target_area].append({
                "episode_id": episode_id,
                "failure_codes": failure_codes,
            })
    
    # Generate verification failure insights
    for patch_type, failures in verification_failures_by_type.items():
        if patch_type == "unknown":
            continue
        if len(failures) >= 2:  # Pattern threshold
            insights["patterns"].append({
                "type": "repeated_verification_failures",
                "dimension": "patch_type",
                "value": patch_type,
                "count": len(failures),
                "episodes": [f["episode_id"] for f in failures[:5]],
                "common_failure_codes": _get_common_failure_codes(failures),
            })
    
    for area, failures in verification_failures_by_area.items():
        if len(failures) >= 2:
            insights["patterns"].append({
                "type": "repeated_verification_failures",
                "dimension": "target_area",
                "value": area,
                "count": len(failures),
                "episodes": [f["episode_id"] for f in failures[:5]],
                "common_failure_codes": _get_common_failure_codes(failures),
            })
    
    # 2. Governance denials by reason
    governance_denials_by_reason = defaultdict(list)
    
    for episode_id, episode in classified_episodes.items():
        if episode.get("outcome") == "blocked_by_governance":
            failure_codes = episode.get("failure_codes", [])
            reason = "unknown"
            for code in failure_codes:
                if code != "governance_blocked":
                    reason = code
                    break
            governance_denials_by_reason[reason].append(episode_id)
    
    for reason, episode_ids in governance_denials_by_reason.items():
        if len(episode_ids) >= 2:
            insights["patterns"].append({
                "type": "repeated_governance_denials",
                "reason": reason,
                "count": len(episode_ids),
                "episodes": episode_ids[:5],
            })
    
    # 3. Stale episodes
    stale_episodes = [
        episode_id for episode_id, episode in classified_episodes.items()
        if episode.get("outcome") == "stale_abandoned"
    ]
    
    if len(stale_episodes) >= 2:
        insights["patterns"].append({
            "type": "repeated_stale_abandoned",
            "count": len(stale_episodes),
            "episodes": stale_episodes[:5],
        })
    
    # 4. Revert recommendations
    revert_episodes = [
        episode_id for episode_id, episode in classified_episodes.items()
        if episode.get("outcome") == "revert_recommended"
    ]
    
    if len(revert_episodes) >= 2:
        insights["patterns"].append({
            "type": "repeated_revert_recommendations",
            "count": len(revert_episodes),
            "episodes": revert_episodes[:5],
        })
    
    # Generate recommendations (conservative)
    for pattern in insights["patterns"]:
        if pattern["type"] == "repeated_verification_failures":
            insights["recommendations"].append({
                "pattern_type": "repeated_verification_failures",
                "recommendation": f"Review verification process for {pattern.get('value', 'unknown')} changes",
                "priority": "medium",
                "automatic": False,
            })
        elif pattern["type"] == "repeated_governance_denials":
            insights["recommendations"].append({
                "pattern_type": "repeated_governance_denials",
                "recommendation": f"Review governance criteria: {pattern.get('reason', 'unknown')}",
                "priority": "medium",
                "automatic": False,
            })
        elif pattern["type"] == "repeated_stale_abandoned":
            insights["recommendations"].append({
                "pattern_type": "repeated_stale_abandoned",
                "recommendation": "Review operational workflow to reduce stale episodes",
                "priority": "low",
                "automatic": False,
            })
        elif pattern["type"] == "repeated_revert_recommendations":
            insights["recommendations"].append({
                "pattern_type": "repeated_revert_recommendations",
                "recommendation": "Review quality of proposals before apply",
                "priority": "medium",
                "automatic": False,
            })
    
    # Statistics
    by_outcome = defaultdict(int)
    for episode in classified_episodes.values():
        by_outcome[episode.get("outcome", "unknown")] += 1
    
    insights["statistics"] = {
        "total_episodes": len(episode_by_id),
        "total_classified": len(classified_episodes),
        "by_outcome": dict(by_outcome),
        "pattern_count": len(insights["patterns"]),
        "recommendation_count": len(insights["recommendations"]),
    }
    
    # Store insights
    insight_id = now.replace(":", "").replace("-", "").replace("T", "")[:14]
    insights["insight_id"] = insight_id
    
    insights_path = STATE_DIR / "learning_insights.jsonl"
    _append_jsonl_record(insights, insights_path)
    
    return insights


def _get_common_failure_codes(failures: List[Dict[str, Any]]) -> List[str]:
    """Get common failure codes across failures.
    
    Args:
        failures: List of failure dicts with failure_codes
        
    Returns:
        List of common failure codes
    """
    code_counts = defaultdict(int)
    
    for f in failures:
        for code in f.get("failure_codes", []):
            code_counts[code] += 1
    
    # Return codes that appear in at least half of failures
    threshold = len(failures) / 2
    common = [code for code, count in code_counts.items() if count >= threshold]
    
    return sorted(common)


def load_learning_insights(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all learning insights.
    
    Args:
        path: Optional path to insights file
        
    Returns:
        List of insight records
    """
    if path is None:
        path = STATE_DIR / "learning_insights.jsonl"
    
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


def get_latest_insights() -> Optional[Dict[str, Any]]:
    """Get the most recent insights.
    
    Returns:
        Latest insights dict or None
    """
    insights = load_learning_insights()
    if insights:
        return insights[-1]
    return None


def get_similar_past_episodes(
    patch_type: Optional[str] = None,
    target_area: Optional[str] = None,
    failure_codes: Optional[List[str]] = None,
    governance_outcome: Optional[str] = None,
    verification_outcome: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Retrieve similar past episodes based on conservative criteria.
    
    This function uses simple matching on derived fields.
    It does NOT use vector similarity or heavyweight infrastructure.
    
    Args:
        patch_type: Match episodes with this patch type
        target_area: Match episodes with this target area
        failure_codes: Match episodes with any of these failure codes
        governance_outcome: Match episodes with this governance outcome
        verification_outcome: Match episodes with this verification outcome
        limit: Maximum number of episodes to return
        
    Returns:
        List of matching episodes with similarity scores
    """
    all_episodes = load_learning_episodes()
    classified_episodes = _get_classified_episodes()
    
    # Build lookup with original episode data + classification
    episode_by_id = {}
    for e in all_episodes:
        episode_id = e.get("episode_id")
        if episode_id and episode_id not in episode_by_id:
            # Use classified version if available, otherwise original
            if episode_id in classified_episodes:
                episode_by_id[episode_id] = classified_episodes[episode_id]
            else:
                episode_by_id[episode_id] = e
    
    matches = []
    
    for episode_id, episode in episode_by_id.items():
        score = 0
        reasons = []
        
        # Check patch type
        if patch_type and episode.get("patch_type") == patch_type:
            score += 1
            reasons.append(f"patch_type:{patch_type}")
        
        # Check target area
        if target_area and episode.get("target_area") == target_area:
            score += 1
            reasons.append(f"target_area:{target_area}")
        
        # Check failure codes
        if failure_codes:
            episode_codes = set(episode.get("failure_codes", []))
            matching_codes = episode_codes.intersection(set(failure_codes))
            if matching_codes:
                score += 1
                reasons.append(f"failure_codes:{','.join(sorted(matching_codes)[:3])}")
        
        # Check governance outcome (from episode)
        if governance_outcome and episode.get("governance_outcome") == governance_outcome:
            score += 1
            reasons.append(f"governance:{governance_outcome}")
        
        # Check verification outcome (from episode)
        if verification_outcome and episode.get("verification_outcome") == verification_outcome:
            score += 1
            reasons.append(f"verification:{verification_outcome}")
        
        # Only include if at least one match
        if score > 0:
            matches.append({
                "episode": episode,
                "similarity_score": score,
                "match_reasons": reasons,
            })
    
    # Sort by score descending
    matches.sort(key=lambda x: x["similarity_score"], reverse=True)
    
    # Limit results
    return matches[:limit]
