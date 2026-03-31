"""Goal Decomposer - 目標をサブゴールに分解

大きな目標を実行可能なサブゴールに分解する。
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ops.goal_store import create_goal, add_subgoal, get_goal_by_id


def decompose_goal(
    goal_id: str,
    subgoals: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """目標をサブゴールに分解
    
    Args:
        goal_id: 親目標のID
        subgoals: [{"title": "...", "description": "..."}]
    
    Returns:
        作成されたサブゴールのリスト
    """
    parent = get_goal_by_id(goal_id)
    if not parent:
        return []
    
    created_subgoals = []
    
    for sub in subgoals:
        subgoal = create_goal(
            title=sub["title"],
            description=sub.get("description", ""),
            priority=sub.get("priority", parent.get("priority", "medium")),
            parent_goal_id=goal_id,
            tags=parent.get("tags", []),
        )
        add_subgoal(goal_id, subgoal["id"])
        created_subgoals.append(subgoal)
    
    return created_subgoals


def suggest_decomposition(goal: Dict[str, Any]) -> List[Dict[str, str]]:
    """目標に対する分解案を提案（ルールベース）"""
    title = goal.get("title", "").lower()
    description = goal.get("description", "").lower()
    
    suggestions = []
    
    # パターンベースの分解提案
    if "システム" in title or "system" in title:
        suggestions = [
            {"title": "要件定義", "description": "必要な機能と制約を明確化"},
            {"title": "設計", "description": "アーキテクチャと詳細設計"},
            {"title": "実装", "description": "コードの作成"},
            {"title": "テスト", "description": "動作確認と品質保証"},
            {"title": "デプロイ", "description": "本番環境への展開"},
        ]
    
    elif "改善" in title or "improve" in title:
        suggestions = [
            {"title": "現状分析", "description": "現在の状態を把握"},
            {"title": "課題特定", "description": "改善ポイントを明確化"},
            {"title": "改善案作成", "description": "具体的な改善策を立案"},
            {"title": "実施", "description": "改善を実行"},
            {"title": "効果測定", "description": "改善効果を確認"},
        ]
    
    elif "学習" in title or "learn" in title:
        suggestions = [
            {"title": "基礎理解", "description": "基本概念を学ぶ"},
            {"title": "実践", "description": "手を動かして試す"},
            {"title": "応用", "description": "実際の問題に適用"},
            {"title": "振り返り", "description": "学びを整理"},
        ]
    
    elif "agi" in title.lower() or "自律" in title:
        suggestions = [
            {"title": "Phase 1: 能動的タスク生成", "description": "システムが自ら行動を起こす"},
            {"title": "Phase 2: 学習→行動ループ", "description": "経験から学び行動を改善"},
            {"title": "Phase 3: 自己改善", "description": "自分のコードを改善"},
            {"title": "Phase 4: 目標設定", "description": "長期目標を設定・追跡"},
        ]
    
    return suggestions


def auto_decompose(goal_id: str) -> List[Dict[str, Any]]:
    """目標を自動分解"""
    goal = get_goal_by_id(goal_id)
    if not goal:
        return []
    
    suggestions = suggest_decomposition(goal)
    if not suggestions:
        return []
    
    return decompose_goal(goal_id, suggestions)
