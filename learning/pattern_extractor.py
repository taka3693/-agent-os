"""Pattern Extractor - 学習エピソードからパターンを抽出

エピソードの成功/失敗パターンを分析し、
行動ポリシーに反映可能な形式で抽出する。
"""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from learning.episode_store import load_learning_episodes


def extract_patterns(
    episodes: Optional[List[Dict[str, Any]]] = None,
    min_occurrences: int = 2,
) -> Dict[str, Any]:
    """学習エピソードからパターンを抽出
    
    Args:
        episodes: エピソードリスト（Noneの場合はファイルから読み込み）
        min_occurrences: パターンとして認識する最小出現回数
    
    Returns:
        抽出されたパターン
    """
    if episodes is None:
        episodes = load_learning_episodes()
    
    if not episodes:
        return {"patterns": [], "summary": {"total_episodes": 0}}
    
    # outcome別に集計
    outcome_counts = Counter(e.get("outcome", "unknown") for e in episodes)
    
    # target_area別の成功率
    area_stats: Dict[str, Dict[str, int]] = {}
    for e in episodes:
        area = e.get("target_area", "unknown")
        outcome = e.get("outcome", "unknown")
        if area not in area_stats:
            area_stats[area] = {"total": 0, "success": 0, "failure": 0}
        area_stats[area]["total"] += 1
        if outcome in ("success_clean", "success_high_friction"):
            area_stats[area]["success"] += 1
        elif outcome in ("failed_verification", "blocked_by_governance"):
            area_stats[area]["failure"] += 1
    
    # 高摩擦パターンを抽出
    high_friction = [e for e in episodes if e.get("outcome") == "success_high_friction"]
    friction_factors = Counter()
    for e in high_friction:
        for factor in e.get("classification_factors", []):
            friction_factors[factor] += 1
    
    # 失敗パターンを抽出
    failures = [e for e in episodes if e.get("outcome") in (
        "failed_verification", "blocked_by_governance", "rejected_low_confidence"
    )]
    failure_factors = Counter()
    for e in failures:
        for code in e.get("failure_codes", []):
            failure_factors[code] += 1
    
    # パターンを生成
    patterns = []
    
    # 高リスクエリアのパターン
    for area, stats in area_stats.items():
        if stats["total"] >= min_occurrences:
            failure_rate = stats["failure"] / stats["total"] if stats["total"] > 0 else 0
            if failure_rate >= 0.5:  # 50%以上失敗
                patterns.append({
                    "type": "high_risk_area",
                    "area": area,
                    "failure_rate": round(failure_rate, 2),
                    "total": stats["total"],
                    "recommendation": "require_extra_review",
                })
    
    # 繰り返し摩擦パターン
    for factor, count in friction_factors.items():
        if count >= min_occurrences:
            patterns.append({
                "type": "recurring_friction",
                "factor": factor,
                "occurrences": count,
                "recommendation": "automate_or_simplify",
            })
    
    # 繰り返し失敗パターン
    for code, count in failure_factors.items():
        if count >= min_occurrences:
            patterns.append({
                "type": "recurring_failure",
                "failure_code": code,
                "occurrences": count,
                "recommendation": "add_guardrail",
            })
    
    return {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_episodes": len(episodes),
            "outcome_distribution": dict(outcome_counts),
            "areas_analyzed": len(area_stats),
        },
        "patterns": patterns,
        "area_stats": area_stats,
    }


def get_recommendations(patterns: Dict[str, Any]) -> List[Dict[str, Any]]:
    """パターンから行動推奨を生成"""
    recommendations = []
    
    for pattern in patterns.get("patterns", []):
        if pattern["type"] == "high_risk_area":
            recommendations.append({
                "action": "add_review_step",
                "target": pattern["area"],
                "reason": f"Failure rate {pattern['failure_rate']*100:.0f}%",
                "priority": "high" if pattern["failure_rate"] >= 0.7 else "medium",
            })
        
        elif pattern["type"] == "recurring_friction":
            recommendations.append({
                "action": "automate_approval",
                "target": pattern["factor"],
                "reason": f"Occurred {pattern['occurrences']} times",
                "priority": "medium",
            })
        
        elif pattern["type"] == "recurring_failure":
            recommendations.append({
                "action": "add_validation",
                "target": pattern["failure_code"],
                "reason": f"Failed {pattern['occurrences']} times",
                "priority": "high",
            })
    
    return recommendations
