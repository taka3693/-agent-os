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


# === Phase 11: メタ認知拡張 ===

def estimate_uncertainty(task: Dict[str, Any]) -> Dict[str, Any]:
    """タスクの不確実性を推定"""
    uncertainty = 0.5  # ベースライン
    factors = []
    
    task_type = task.get("type", "")
    params = task.get("params", {})
    
    # 未知のタスクタイプは不確実性が高い
    known_types = ["code_execution", "file_operation", "web_search", "analysis", "generation"]
    if task_type not in known_types:
        uncertainty += 0.2
        factors.append("unknown_task_type")
    
    # 複雑なパラメータは不確実性が高い
    if len(params) > 5:
        uncertainty += 0.1
        factors.append("complex_parameters")
    
    # 過去の失敗履歴をチェック
    # (簡易実装 - 実際はlearning履歴を参照)
    
    uncertainty = min(1.0, max(0.0, uncertainty))
    
    confidence = 1.0 - uncertainty
    recommendation = "proceed" if confidence > 0.6 else "review" if confidence > 0.3 else "decline"
    
    return {
        "uncertainty": uncertainty,
        "confidence": confidence,
        "factors": factors,
        "recommendation": recommendation,
    }


def recognize_limitations(task: Dict[str, Any]) -> Dict[str, Any]:
    """能力限界を認識"""
    limitations = []
    can_handle = True
    
    task_type = task.get("type", "")
    requirements = task.get("requirements", [])
    
    # 知られている限界
    known_limitations = {
        "real_time_data": "リアルタイムデータへのアクセスが制限されています",
        "physical_action": "物理的なアクションは実行できません",
        "private_api": "プライベートAPIへのアクセスが必要です",
        "large_file": "大きなファイル（>100MB）の処理は制限されています",
        "gpu_intensive": "GPU集中処理は制限されています",
    }
    
    for req in requirements:
        if req in known_limitations:
            limitations.append({
                "type": req,
                "description": known_limitations[req],
                "severity": "blocking",
            })
            can_handle = False
    
    # タスクタイプに基づく制限
    if "video_edit" in task_type:
        limitations.append({
            "type": "video_editing",
            "description": "高度な動画編集は制限されています",
            "severity": "partial",
        })
    
    return {
        "can_handle": can_handle,
        "limitations": limitations,
        "alternatives": [] if can_handle else ["手動で実行", "別のツールを使用"],
    }


def self_reflect(execution_result: Dict[str, Any]) -> Dict[str, Any]:
    """実行結果を自己反省"""
    success = execution_result.get("success", False)
    error = execution_result.get("error")
    duration = execution_result.get("duration", 0)
    
    reflections = []
    improvements = []
    
    if not success:
        reflections.append(f"タスクが失敗しました: {error}")
        
        if "timeout" in str(error).lower():
            improvements.append("タイムアウト値を増加する")
        if "permission" in str(error).lower():
            improvements.append("権限設定を確認する")
        if "not found" in str(error).lower():
            improvements.append("入力の検証を強化する")
    else:
        reflections.append("タスクが正常に完了しました")
        
        if duration > 60:
            improvements.append("実行時間の最適化を検討する")
    
    return {
        "success": success,
        "reflections": reflections,
        "improvements": improvements,
        "learning_points": len(improvements),
    }


def calibrate_confidence(predictions: List[Dict], actuals: List[Dict]) -> Dict[str, Any]:
    """予測と実績を比較して信頼度を較正"""
    if not predictions or not actuals or len(predictions) != len(actuals):
        return {"ok": False, "error": "Invalid input"}
    
    correct = 0
    total = len(predictions)
    
    for pred, actual in zip(predictions, actuals):
        pred_success = pred.get("predicted_success", True)
        actual_success = actual.get("success", False)
        
        if pred_success == actual_success:
            correct += 1
    
    accuracy = correct / total if total > 0 else 0
    
    # 較正係数を計算
    calibration_factor = accuracy  # 簡易版
    
    return {
        "ok": True,
        "accuracy": accuracy,
        "calibration_factor": calibration_factor,
        "samples": total,
        "recommendation": "良好" if accuracy > 0.7 else "要改善",
    }
