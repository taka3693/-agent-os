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


# === Phase 10: 目標管理拡張 ===

def auto_decompose(goal_id: str, depth: int = 3) -> Dict[str, Any]:
    """長期目標を自動的にサブゴールに分解"""
    from ops.goal_store import get_goal_by_id, create_goal, add_subgoal
    
    goal = get_goal_by_id(goal_id)
    if not goal:
        return {"ok": False, "error": "Goal not found"}
    
    subgoals = []
    goal_title = goal.get("title", "")
    goal_desc = goal.get("description", "")
    
    # 簡易的な分解ロジック（実際はLLMを使用）
    decomposition_templates = {
        "開発": ["設計", "実装", "テスト", "デプロイ"],
        "調査": ["情報収集", "分析", "レポート作成"],
        "改善": ["現状分析", "計画策定", "実行", "検証"],
    }
    
    template = ["計画", "実行", "検証"]  # デフォルト
    for key, steps in decomposition_templates.items():
        if key in goal_title or key in goal_desc:
            template = steps
            break
    
    for i, step in enumerate(template[:depth]):
        subgoal = create_goal(
            title=f"{goal_title} - {step}",
            description=f"{goal_desc}の{step}フェーズ",
            priority=goal.get("priority", "medium"),
            parent_id=goal_id,
        )
        if subgoal.get("ok"):
            subgoals.append(subgoal)
            add_subgoal(goal_id, subgoal.get("goal_id"))
    
    return {"ok": True, "goal_id": goal_id, "subgoals": subgoals, "depth": depth}


def analyze_dependencies(goal_id: str) -> Dict[str, Any]:
    """目標間の依存関係を分析"""
    from ops.goal_store import get_goal_by_id, load_goals
    
    goal = get_goal_by_id(goal_id)
    if not goal:
        return {"ok": False, "error": "Goal not found"}
    
    all_goals = load_goals()
    
    dependencies = {
        "depends_on": [],
        "blocks": [],
        "related": [],
    }
    
    goal_keywords = set((goal.get("title", "") + " " + goal.get("description", "")).lower().split())
    
    for other in all_goals:
        if other.get("id") == goal_id:
            continue
        
        other_keywords = set((other.get("title", "") + " " + other.get("description", "")).lower().split())
        overlap = len(goal_keywords & other_keywords)
        
        if overlap > 3:
            dependencies["related"].append({
                "goal_id": other.get("id"),
                "title": other.get("title"),
                "overlap": overlap,
            })
        
        # 親子関係
        if other.get("parent_id") == goal_id:
            dependencies["blocks"].append({"goal_id": other.get("id"), "title": other.get("title")})
        if goal.get("parent_id") == other.get("id"):
            dependencies["depends_on"].append({"goal_id": other.get("id"), "title": other.get("title")})
    
    return {"ok": True, "goal_id": goal_id, "dependencies": dependencies}


def auto_prioritize(goals: List[Dict] = None) -> List[Dict]:
    """優先度を自動計算"""
    from ops.goal_store import load_goals
    
    if goals is None:
        goals = load_goals()
    
    for goal in goals:
        score = 0
        
        # 期限が近いほど優先度UP
        if goal.get("deadline"):
            from datetime import datetime, timezone
            try:
                deadline = datetime.fromisoformat(goal["deadline"].replace("Z", "+00:00"))
                days_left = (deadline - datetime.now(timezone.utc)).days
                if days_left < 1:
                    score += 100
                elif days_left < 7:
                    score += 50
                elif days_left < 30:
                    score += 20
            except:
                pass
        
        # 進捗が高いほど優先度UP（完了間近）
        progress = goal.get("progress", 0)
        if progress > 80:
            score += 30
        elif progress > 50:
            score += 15
        
        # 明示的な優先度
        priority_map = {"critical": 50, "high": 30, "medium": 15, "low": 5}
        score += priority_map.get(goal.get("priority", "medium"), 15)
        
        goal["auto_priority_score"] = score
    
    goals.sort(key=lambda x: x.get("auto_priority_score", 0), reverse=True)
    return goals


def replan_goal(goal_id: str) -> Dict[str, Any]:
    """進捗に基づいて再計画"""
    from ops.goal_store import get_goal_by_id, update_goal
    
    goal = get_goal_by_id(goal_id)
    if not goal:
        return {"ok": False, "error": "Goal not found"}
    
    progress = goal.get("progress", 0)
    subgoals = goal.get("subgoals", [])
    
    adjustments = []
    
    # 進捗が遅れている場合
    if progress < 30 and subgoals:
        adjustments.append({
            "type": "scope_reduction",
            "suggestion": "進捗が遅れています。スコープの縮小を検討してください。",
        })
    
    # 進捗が予想以上の場合
    if progress > 70:
        adjustments.append({
            "type": "scope_expansion",
            "suggestion": "順調です。追加の目標を検討できます。",
        })
    
    # サブゴールの再優先順位付け
    if subgoals:
        adjustments.append({
            "type": "reprioritize",
            "suggestion": f"{len(subgoals)}個のサブゴールを再優先順位付けしました。",
        })
    
    return {"ok": True, "goal_id": goal_id, "progress": progress, "adjustments": adjustments}
