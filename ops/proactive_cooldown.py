"""Proactive Cooldown - 重複タスク生成の防止

同じ種類のタスクが短期間に繰り返し生成されないようにする。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# タスク種類ごとのクールダウン時間（秒）
DEFAULT_COOLDOWNS = {
    "exploration": 3600 * 4,   # 4時間
    "maintenance": 3600 * 1,   # 1時間
    "improvement": 3600 * 2,   # 2時間
    "notification": 1800,      # 30分
}


def get_recent_tasks(state_root: Path, hours: int = 24) -> List[Dict[str, Any]]:
    """直近N時間以内に生成されたタスクを取得"""
    cycles_file = state_root / "proactive_cycles.jsonl"
    if not cycles_file.exists():
        return []
    
    cutoff = utc_now() - timedelta(hours=hours)
    recent = []
    
    for line in cycles_file.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            cycle = json.loads(line)
            cycle_time = parse_iso(cycle["executed_at"])
            if cycle_time >= cutoff:
                recent.extend(cycle.get("tasks", []))
        except Exception:
            continue
    
    return recent


def should_generate(
    task_type: str,
    state_root: Path,
    cooldown_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """タスクを生成すべきかどうか判定
    
    Returns:
        {"allowed": bool, "reason": str, "last_generated": str or None}
    """
    if cooldown_seconds is None:
        cooldown_seconds = DEFAULT_COOLDOWNS.get(task_type, 3600)
    
    recent_tasks = get_recent_tasks(state_root, hours=24)
    
    # 同じ種類のタスクを探す
    same_type = [t for t in recent_tasks if t.get("type") == task_type]
    
    if not same_type:
        return {"allowed": True, "reason": "no_recent_tasks", "last_generated": None}
    
    # 最新のタスク時刻を取得
    latest = max(same_type, key=lambda t: t.get("created_at", ""))
    latest_time = parse_iso(latest["created_at"])
    
    elapsed = (utc_now() - latest_time).total_seconds()
    
    if elapsed >= cooldown_seconds:
        return {
            "allowed": True,
            "reason": "cooldown_expired",
            "last_generated": latest["created_at"],
            "elapsed_seconds": int(elapsed),
        }
    else:
        remaining = int(cooldown_seconds - elapsed)
        return {
            "allowed": False,
            "reason": "cooldown_active",
            "last_generated": latest["created_at"],
            "remaining_seconds": remaining,
        }


def filter_tasks_by_cooldown(
    tasks: List[Dict[str, Any]],
    state_root: Path,
) -> List[Dict[str, Any]]:
    """クールダウン中のタスクを除外"""
    filtered = []
    for task in tasks:
        check = should_generate(task["type"], state_root)
        if check["allowed"]:
            filtered.append(task)
    return filtered
