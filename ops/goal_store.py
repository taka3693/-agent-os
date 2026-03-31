"""Goal Store - 長期目標の保存・追跡

目標の作成、更新、進捗管理を行う。
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"
GOALS_FILE = STATE_DIR / "goals.jsonl"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_goal(
    title: str,
    description: str,
    priority: str = "medium",  # high, medium, low
    deadline: Optional[str] = None,
    parent_goal_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """新しい目標を作成"""
    goal = {
        "id": f"goal-{uuid.uuid4().hex[:8]}",
        "title": title,
        "description": description,
        "priority": priority,
        "status": "active",  # active, completed, paused, cancelled
        "progress": 0,  # 0-100
        "deadline": deadline,
        "parent_goal_id": parent_goal_id,
        "subgoal_ids": [],
        "tags": tags or [],
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "completed_at": None,
        "notes": [],
    }
    
    # 保存
    with open(GOALS_FILE, "a") as f:
        f.write(json.dumps(goal, ensure_ascii=False) + "\n")
    
    return goal


def load_goals() -> List[Dict[str, Any]]:
    """全目標を読み込む"""
    if not GOALS_FILE.exists():
        return []
    
    goals = {}
    for line in GOALS_FILE.read_text().strip().split("\n"):
        if line.strip():
            try:
                goal = json.loads(line)
                goals[goal["id"]] = goal  # 最新版で上書き
            except json.JSONDecodeError:
                continue
    
    return list(goals.values())


def get_goal_by_id(goal_id: str) -> Optional[Dict[str, Any]]:
    """IDで目標を取得"""
    for goal in load_goals():
        if goal["id"] == goal_id:
            return goal
    return None


def get_active_goals() -> List[Dict[str, Any]]:
    """アクティブな目標のみ取得"""
    return [g for g in load_goals() if g.get("status") == "active"]


def get_top_level_goals() -> List[Dict[str, Any]]:
    """トップレベル（親なし）の目標を取得"""
    return [g for g in load_goals() if not g.get("parent_goal_id")]


def update_goal(
    goal_id: str,
    **updates
) -> Optional[Dict[str, Any]]:
    """目標を更新"""
    goal = get_goal_by_id(goal_id)
    if not goal:
        return None
    
    # 更新
    for key, value in updates.items():
        if key in goal and key not in ("id", "created_at"):
            goal[key] = value
    
    goal["updated_at"] = utc_now_iso()
    
    # 完了時の処理
    if updates.get("status") == "completed" and not goal.get("completed_at"):
        goal["completed_at"] = utc_now_iso()
        goal["progress"] = 100
    
    # 追記保存
    with open(GOALS_FILE, "a") as f:
        f.write(json.dumps(goal, ensure_ascii=False) + "\n")
    
    return goal


def update_progress(goal_id: str, progress: int) -> Optional[Dict[str, Any]]:
    """進捗を更新（0-100）"""
    progress = max(0, min(100, progress))
    return update_goal(goal_id, progress=progress)


def add_note(goal_id: str, note: str) -> Optional[Dict[str, Any]]:
    """目標にノートを追加"""
    goal = get_goal_by_id(goal_id)
    if not goal:
        return None
    
    notes = goal.get("notes", [])
    notes.append({
        "timestamp": utc_now_iso(),
        "content": note,
    })
    
    return update_goal(goal_id, notes=notes)


def add_subgoal(parent_id: str, subgoal_id: str) -> bool:
    """親目標にサブゴールを追加"""
    parent = get_goal_by_id(parent_id)
    if not parent:
        return False
    
    subgoal_ids = parent.get("subgoal_ids", [])
    if subgoal_id not in subgoal_ids:
        subgoal_ids.append(subgoal_id)
        update_goal(parent_id, subgoal_ids=subgoal_ids)
    
    return True


def calculate_goal_progress(goal_id: str) -> int:
    """サブゴールから親の進捗を計算"""
    goal = get_goal_by_id(goal_id)
    if not goal:
        return 0
    
    subgoal_ids = goal.get("subgoal_ids", [])
    if not subgoal_ids:
        return goal.get("progress", 0)
    
    total_progress = 0
    for sub_id in subgoal_ids:
        subgoal = get_goal_by_id(sub_id)
        if subgoal:
            total_progress += subgoal.get("progress", 0)
    
    return total_progress // len(subgoal_ids)
