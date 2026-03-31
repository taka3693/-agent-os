"""Self Assessor - タスクに対する自己評価

タスクを受け取り、自分が処理できるか、どの程度の確信度か、
何に注意すべきかを評価する。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ops.capability_model import (
    get_capabilities,
    can_handle,
    assess_task_complexity,
    get_limitations,
    CORE_CAPABILITIES,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"


def infer_task_type(task: Dict[str, Any]) -> str:
    """タスクからタイプを推論"""
    query = (task.get("query", "") or task.get("description", "")).lower()
    skill = task.get("skill", "").lower()
    
    # スキルが指定されていればそれを使用
    if skill in CORE_CAPABILITIES:
        return skill
    
    # キーワードから推論
    if any(w in query for w in ["調査", "調べ", "検索", "research", "search", "find"]):
        return "research"
    if any(w in query for w in ["コード", "実装", "修正", "code", "implement", "fix", "bug"]):
        return "coding"
    if any(w in query for w in ["計画", "分解", "plan", "decompose", "schedule"]):
        return "planning"
    if any(w in query for w in ["分析", "診断", "ログ", "analyze", "diagnose", "log"]):
        return "analysis"
    
    return "research"  # デフォルト


def assess_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """タスクの総合評価を行う
    
    Returns:
        {
            "can_proceed": bool,
            "confidence": float,
            "task_type": str,
            "complexity": str,
            "warnings": [...],
            "recommendations": [...],
            "limitations_applicable": [...],
        }
    """
    # タスクタイプを推論
    task_type = infer_task_type(task)
    
    # 能力評価
    capability_result = can_handle(task_type)
    
    # 複雑度評価
    complexity_result = assess_task_complexity(task)
    
    # 警告収集
    warnings = []
    recommendations = []
    
    # 低信頼度の場合
    if capability_result["confidence"] < 0.7:
        warnings.append(f"Low confidence for {task_type}: {capability_result['confidence']}")
        recommendations.append("Consider human review")
    
    # 高複雑度の場合
    if complexity_result["complexity"] == "high":
        warnings.append("High complexity task detected")
        recommendations.append(complexity_result["recommendation"])
    
    # 該当する制限を収集
    limitations_applicable = []
    query = task.get("query", "") or task.get("description", "")
    
    for limitation in get_limitations():
        # キーワードマッチで関連する制限を検出
        if limitation["category"] == "access" and any(w in query.lower() for w in ["api", "login", "認証"]):
            limitations_applicable.append(limitation)
        elif limitation["category"] == "judgment" and any(w in query.lower() for w in ["判断", "決定", "decide"]):
            limitations_applicable.append(limitation)
    
    # 総合判断
    can_proceed = (
        capability_result["can_handle"] and
        capability_result["confidence"] >= 0.5 and
        complexity_result["complexity"] != "high"
    )
    
    # 高複雑度でも分解すれば可能
    if complexity_result["complexity"] == "high":
        recommendations.append("decompose_first")
        can_proceed = True  # 分解すれば対応可能
    
    return {
        "can_proceed": can_proceed,
        "confidence": capability_result["confidence"],
        "task_type": task_type,
        "complexity": complexity_result["complexity"],
        "complexity_factors": complexity_result["factors"],
        "warnings": warnings,
        "recommendations": recommendations,
        "limitations_applicable": limitations_applicable,
        "capability_limitations": capability_result["limitations"],
    }


def should_ask_for_help(assessment: Dict[str, Any]) -> Dict[str, Any]:
    """助けを求めるべきか判断"""
    reasons = []
    
    if assessment["confidence"] < 0.5:
        reasons.append("Very low confidence")
    
    if assessment["complexity"] == "high" and "ambiguous" in assessment.get("complexity_factors", []):
        reasons.append("Ambiguous high-complexity task")
    
    if assessment["limitations_applicable"]:
        for lim in assessment["limitations_applicable"]:
            if lim["category"] == "judgment":
                reasons.append(f"Requires human judgment: {lim['description']}")
    
    return {
        "should_ask": len(reasons) > 0,
        "reasons": reasons,
        "suggested_question": _generate_clarification_question(assessment) if reasons else None,
    }


def _generate_clarification_question(assessment: Dict[str, Any]) -> str:
    """確認質問を生成"""
    if assessment["confidence"] < 0.5:
        return f"このタスク（{assessment['task_type']}）について、もう少し詳しく教えていただけますか？"
    
    if "ambiguous" in assessment.get("complexity_factors", []):
        return "いくつか曖昧な点があります。具体的にどのような結果を期待していますか？"
    
    if assessment["limitations_applicable"]:
        return "このタスクには制限があります。続行してもよろしいですか？"
    
    return "このタスクについて確認させてください。"


def generate_self_report() -> Dict[str, Any]:
    """自己認識レポートを生成"""
    capabilities = get_capabilities()
    limitations = get_limitations()
    
    # 能力サマリー
    avg_confidence = sum(c["confidence"] for c in capabilities.values()) / len(capabilities)
    
    strongest = max(capabilities.items(), key=lambda x: x[1]["confidence"])
    weakest = min(capabilities.items(), key=lambda x: x[1]["confidence"])
    
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_capabilities": len(capabilities),
            "total_limitations": len(limitations),
            "average_confidence": round(avg_confidence, 2),
        },
        "strongest_capability": {
            "name": strongest[0],
            "confidence": strongest[1]["confidence"],
        },
        "weakest_capability": {
            "name": weakest[0],
            "confidence": weakest[1]["confidence"],
        },
        "key_limitations": [l["description"] for l in limitations[:3]],
    }
