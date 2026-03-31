"""Progress Tracker - 進捗追跡・レポート生成

目標の進捗を追跡し、レポートを生成する。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ops.goal_store import (
    load_goals,
    get_goal_by_id,
    get_active_goals,
    get_top_level_goals,
    calculate_goal_progress,
    update_progress,
)


def generate_progress_report() -> Dict[str, Any]:
    """全体の進捗レポートを生成"""
    goals = load_goals()
    active_goals = get_active_goals()
    top_level = get_top_level_goals()
    
    # 統計
    total = len(goals)
    completed = len([g for g in goals if g.get("status") == "completed"])
    active = len(active_goals)
    
    # 優先度別
    high_priority = [g for g in active_goals if g.get("priority") == "high"]
    
    # 進捗が低い目標
    stalled = [g for g in active_goals if g.get("progress", 0) < 20]
    
    # トップレベル目標の進捗
    top_level_progress = []
    for goal in top_level:
        if goal.get("status") == "active":
            progress = calculate_goal_progress(goal["id"])
            top_level_progress.append({
                "id": goal["id"],
                "title": goal["title"],
                "progress": progress,
                "subgoals": len(goal.get("subgoal_ids", [])),
            })
    
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_goals": total,
            "completed": completed,
            "active": active,
            "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
        },
        "high_priority": [
            {"id": g["id"], "title": g["title"], "progress": g.get("progress", 0)}
            for g in high_priority
        ],
        "stalled_goals": [
            {"id": g["id"], "title": g["title"], "progress": g.get("progress", 0)}
            for g in stalled
        ],
        "top_level_progress": top_level_progress,
    }


def get_goal_tree(goal_id: str, depth: int = 0) -> Dict[str, Any]:
    """目標のツリー構造を取得"""
    goal = get_goal_by_id(goal_id)
    if not goal:
        return {}
    
    tree = {
        "id": goal["id"],
        "title": goal["title"],
        "status": goal.get("status"),
        "progress": goal.get("progress", 0),
        "depth": depth,
        "children": [],
    }
    
    for sub_id in goal.get("subgoal_ids", []):
        child_tree = get_goal_tree(sub_id, depth + 1)
        if child_tree:
            tree["children"].append(child_tree)
    
    return tree


def format_goal_tree(tree: Dict[str, Any], indent: str = "") -> str:
    """ツリーを文字列でフォーマット"""
    if not tree:
        return ""
    
    status_icon = {
        "active": "🔵",
        "completed": "✅",
        "paused": "⏸️",
        "cancelled": "❌",
    }.get(tree.get("status"), "⚪")
    
    progress = tree.get("progress", 0)
    progress_bar = f"[{'█' * (progress // 10)}{'░' * (10 - progress // 10)}] {progress}%"
    
    lines = [f"{indent}{status_icon} {tree['title']} {progress_bar}"]
    
    for child in tree.get("children", []):
        lines.append(format_goal_tree(child, indent + "  "))
    
    return "\n".join(lines)


def sync_parent_progress() -> int:
    """全親目標の進捗をサブゴールから同期"""
    updated = 0
    for goal in load_goals():
        if goal.get("subgoal_ids") and goal.get("status") == "active":
            new_progress = calculate_goal_progress(goal["id"])
            if new_progress != goal.get("progress", 0):
                update_progress(goal["id"], new_progress)
                updated += 1
    return updated
