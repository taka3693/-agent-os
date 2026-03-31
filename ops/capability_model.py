"""Capability Model - 自分の能力を定義

Agent-OSが何ができて何ができないかを明示的に定義する。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"
CAPABILITIES_FILE = STATE_DIR / "capabilities.json"


# コア能力の定義
CORE_CAPABILITIES = {
    "research": {
        "name": "リサーチ・調査",
        "description": "Web検索、情報収集、分析",
        "confidence": 0.9,
        "limitations": ["リアルタイムデータは遅延あり", "有料コンテンツはアクセス不可"],
    },
    "coding": {
        "name": "コーディング",
        "description": "Python, TypeScript, Bash等のコード作成・修正",
        "confidence": 0.85,
        "limitations": ["複雑なアーキテクチャ設計は人間の確認必要", "本番デプロイは承認必要"],
    },
    "planning": {
        "name": "計画・分解",
        "description": "タスクの分解、スケジューリング、優先度付け",
        "confidence": 0.8,
        "limitations": ["長期的な影響予測は不確実", "ドメイン知識に依存"],
    },
    "analysis": {
        "name": "分析・診断",
        "description": "ログ分析、問題特定、パターン認識",
        "confidence": 0.85,
        "limitations": ["未知のパターンは検出困難", "文脈依存の問題は難しい"],
    },
    "communication": {
        "name": "コミュニケーション",
        "description": "Telegram/Discord経由でのユーザーとの対話",
        "confidence": 0.9,
        "limitations": ["感情的なサポートは限定的", "曖昧な要求の解釈は誤る可能性"],
    },
    "self_improvement": {
        "name": "自己改善",
        "description": "失敗からの学習、コード修正提案",
        "confidence": 0.6,
        "limitations": ["根本的なアーキテクチャ変更は困難", "自分のバグを見つけにくい"],
    },
}

# できないことの明示的定義
KNOWN_LIMITATIONS = [
    {
        "category": "safety",
        "description": "本番環境への直接デプロイ",
        "reason": "リスクが高いため承認が必要",
        "mitigation": "承認キューを通す",
    },
    {
        "category": "access",
        "description": "認証が必要な外部サービス",
        "reason": "認証情報を持っていない",
        "mitigation": "ユーザーに委任",
    },
    {
        "category": "knowledge",
        "description": "リアルタイム情報（株価、ニュース等）",
        "reason": "知識のカットオフがある",
        "mitigation": "Web検索ツールを使用",
    },
    {
        "category": "physical",
        "description": "物理世界への直接操作",
        "reason": "ソフトウェアエージェントである",
        "mitigation": "指示を提供",
    },
    {
        "category": "judgment",
        "description": "倫理的・法的判断が必要な決定",
        "reason": "最終判断は人間が行うべき",
        "mitigation": "オプションを提示し人間に判断を委ねる",
    },
]


def get_capabilities() -> Dict[str, Any]:
    """全能力を取得"""
    return CORE_CAPABILITIES.copy()


def get_capability(name: str) -> Optional[Dict[str, Any]]:
    """特定の能力を取得"""
    return CORE_CAPABILITIES.get(name)


def get_limitations() -> List[Dict[str, Any]]:
    """全制限を取得"""
    return KNOWN_LIMITATIONS.copy()


def can_handle(task_type: str) -> Dict[str, Any]:
    """タスクを処理できるか評価"""
    capability = get_capability(task_type)
    
    if capability:
        return {
            "can_handle": True,
            "confidence": capability["confidence"],
            "limitations": capability["limitations"],
            "recommendation": "proceed" if capability["confidence"] >= 0.7 else "proceed_with_caution",
        }
    
    # 未知のタスクタイプ
    return {
        "can_handle": False,
        "confidence": 0.0,
        "limitations": ["Unknown task type"],
        "recommendation": "ask_for_clarification",
    }


def assess_task_complexity(task: Dict[str, Any]) -> Dict[str, Any]:
    """タスクの複雑度を評価"""
    complexity_factors = []
    score = 0
    
    # クエリの長さ
    query = task.get("query", "") or task.get("description", "")
    if len(query) > 500:
        complexity_factors.append("long_query")
        score += 1
    
    # 複数スキル必要
    if task.get("requires_skills") and len(task.get("requires_skills", [])) > 2:
        complexity_factors.append("multi_skill")
        score += 2
    
    # 外部依存
    if "api" in query.lower() or "external" in query.lower():
        complexity_factors.append("external_dependency")
        score += 1
    
    # 曖昧さ
    ambiguous_words = ["たぶん", "maybe", "perhaps", "何か", "something", "適当"]
    if any(w in query.lower() for w in ambiguous_words):
        complexity_factors.append("ambiguous")
        score += 2
    
    complexity = "low" if score <= 1 else "medium" if score <= 3 else "high"
    
    return {
        "complexity": complexity,
        "score": score,
        "factors": complexity_factors,
        "recommendation": "proceed" if complexity == "low" else "verify_with_user" if complexity == "medium" else "decompose_first",
    }


def save_capability_snapshot():
    """現在の能力スナップショットを保存"""
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "capabilities": CORE_CAPABILITIES,
        "limitations": KNOWN_LIMITATIONS,
    }
    
    with open(CAPABILITIES_FILE, "w") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    
    return CAPABILITIES_FILE
