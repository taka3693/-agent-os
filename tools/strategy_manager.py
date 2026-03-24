#!/usr/bin/env python3
"""Strategy layer management for AgentOS."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_DIR = ROOT / "state" / "strategy"
WEEKLY_GOALS = STRATEGY_DIR / "weekly_goals.json"
PRIORITY_RULES = STRATEGY_DIR / "priority_rules.json"
KPI_LOG = STRATEGY_DIR / "kpi_tracking.jsonl"

# キーワードマッピング（目標 → 関連キーワード）
GOAL_KEYWORDS = {
    "受託獲得": ["受託", "提案", "案件", "クライアント", "営業", "見積"],
    "agentos完成度向上": ["agentos", "agent-os", "cpt", "decision", "execution"],
    "openclawハーネス安定化": ["openclaw", "session", "guardian", "monitor", "ハーネス"],
}

def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def get_weekly_goals() -> dict:
    return load_json(WEEKLY_GOALS)

def get_priority_rules() -> dict:
    return load_json(PRIORITY_RULES)

def _matches_goal(task_lower: str, goal: str) -> bool:
    """Check if task matches goal using keywords."""
    goal_lower = goal.lower()
    # Direct match
    if goal_lower in task_lower:
        return True
    # Keyword match
    keywords = GOAL_KEYWORDS.get(goal_lower, [])
    return any(kw in task_lower for kw in keywords)

def check_goal_alignment(task_description: str) -> dict:
    """Check if task aligns with weekly goals."""
    goals = get_weekly_goals()
    primary = goals.get("primary_goal", "")
    secondary = goals.get("secondary_goals", [])
    
    task_lower = task_description.lower()
    
    aligns_primary = _matches_goal(task_lower, primary)
    aligns_secondary = any(_matches_goal(task_lower, s) for s in secondary)
    
    alignment = {
        "aligns_with_primary": aligns_primary,
        "aligns_with_secondary": aligns_secondary,
        "primary_goal": primary,
        "matched_keywords": [],
        "recommendation": "proceed" if aligns_primary else ("consider" if aligns_secondary else "review_priority"),
    }
    
    # Show which keywords matched
    for goal, keywords in GOAL_KEYWORDS.items():
        for kw in keywords:
            if kw in task_lower:
                alignment["matched_keywords"].append(kw)
    
    return alignment

def calculate_priority(task: dict) -> int:
    """Calculate task priority based on rules."""
    rules = get_priority_rules().get("rules", [])
    base_priority = task.get("priority", 50)
    
    for rule in rules:
        rule_id = rule.get("id", "")
        boost = rule.get("priority_boost", 0)
        
        if rule_id == "revenue_first" and task.get("category") == "revenue":
            base_priority += boost
        elif rule_id == "weekly_goal_alignment" and task.get("aligns_with_weekly_goal"):
            base_priority += boost
        elif rule_id == "low_cost_preference" and task.get("model") in ["glm-5", "kimi-k2.5"]:
            base_priority += boost
        elif rule_id == "blocked_deprioritize" and task.get("status") == "blocked":
            base_priority += boost
    
    return max(0, min(100, base_priority))

def log_kpi(metric: str, value: float, context: str = "") -> dict:
    """Log a KPI measurement."""
    STRATEGY_DIR.mkdir(parents=True, exist_ok=True)
    
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "metric": metric,
        "value": value,
        "context": context,
    }
    
    with KPI_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    return {"ok": True, "logged": record}

def get_strategy_summary() -> dict:
    """Get current strategy summary."""
    goals = get_weekly_goals()
    rules = get_priority_rules()
    
    return {
        "week": f"{goals.get('week_start', '?')} - {goals.get('week_end', '?')}",
        "primary_goal": goals.get("primary_goal"),
        "secondary_goals": goals.get("secondary_goals", []),
        "constraints": goals.get("constraints", []),
        "rule_count": len(rules.get("rules", [])),
        "ok": True,
    }

def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: strategy_manager.py <command> [args]"}, ensure_ascii=False))
        return 1
    
    cmd = sys.argv[1]
    
    if cmd == "summary":
        print(json.dumps(get_strategy_summary(), ensure_ascii=False, indent=2))
    elif cmd == "goals":
        print(json.dumps(get_weekly_goals(), ensure_ascii=False, indent=2))
    elif cmd == "rules":
        print(json.dumps(get_priority_rules(), ensure_ascii=False, indent=2))
    elif cmd == "check":
        task_desc = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        print(json.dumps(check_goal_alignment(task_desc), ensure_ascii=False, indent=2))
    elif cmd == "priority":
        task_json = sys.argv[2] if len(sys.argv) > 2 else "{}"
        task = json.loads(task_json)
        priority = calculate_priority(task)
        print(json.dumps({"priority": priority, "task": task}, ensure_ascii=False, indent=2))
    elif cmd == "log_kpi":
        if len(sys.argv) < 4:
            print(json.dumps({"error": "usage: log_kpi <metric> <value> [context]"}))
            return 1
        metric = sys.argv[2]
        value = float(sys.argv[3])
        context = sys.argv[4] if len(sys.argv) > 4 else ""
        print(json.dumps(log_kpi(metric, value, context), ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"error": f"unknown command: {cmd}"}, ensure_ascii=False))
        return 1
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
