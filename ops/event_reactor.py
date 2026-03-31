"""Event Reactor - イベントに応じた自動アクション

外部イベントを検出し、適切なアクションを実行する。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from ops.github_observer import analyze_github_state, get_ci_status
from ops.environment_monitor import analyze_environment

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"
EVENT_LOG = STATE_DIR / "external_events.jsonl"


# イベントタイプと対応するアクション
EVENT_HANDLERS = {
    "ci_failure": {
        "priority": "high",
        "auto_action": "investigate",
        "description": "CI/CD failure detected",
    },
    "high_memory": {
        "priority": "medium",
        "auto_action": "alert",
        "description": "High memory usage",
    },
    "high_disk": {
        "priority": "high",
        "auto_action": "cleanup_suggest",
        "description": "High disk usage",
    },
    "openclaw_down": {
        "priority": "critical",
        "auto_action": "restart_suggest",
        "description": "OpenClaw service down",
    },
    "stale_pr": {
        "priority": "low",
        "auto_action": "remind",
        "description": "PR needs attention",
    },
    "bug_issue": {
        "priority": "medium",
        "auto_action": "analyze",
        "description": "Bug issue reported",
    },
}


def log_event(event: Dict[str, Any]) -> None:
    """イベントをログに記録"""
    event["logged_at"] = datetime.now(timezone.utc).isoformat()
    
    with open(EVENT_LOG, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def collect_events() -> List[Dict[str, Any]]:
    """全ソースからイベントを収集"""
    events = []
    
    # GitHub状態
    github = analyze_github_state()
    
    for warning in github.get("warnings", []):
        events.append({
            "source": "github",
            "type": warning["type"],
            "details": warning,
        })
    
    for action in github.get("suggested_actions", []):
        events.append({
            "source": "github",
            "type": action["type"],
            "details": action,
        })
    
    # 環境状態
    env = analyze_environment()
    
    for warning in env.get("warnings", []):
        events.append({
            "source": "environment",
            "type": warning["type"],
            "details": warning,
        })
    
    return events


def prioritize_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """イベントを優先度でソート"""
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    
    def get_priority(event: Dict[str, Any]) -> int:
        event_type = event.get("type", "unknown")
        handler = EVENT_HANDLERS.get(event_type, {})
        priority = handler.get("priority", "low")
        return priority_order.get(priority, 4)
    
    return sorted(events, key=get_priority)


def get_reaction(event: Dict[str, Any]) -> Dict[str, Any]:
    """イベントに対するリアクションを取得"""
    event_type = event.get("type", "unknown")
    handler = EVENT_HANDLERS.get(event_type)
    
    if not handler:
        return {
            "action": "log_only",
            "message": f"Unknown event type: {event_type}",
            "auto_execute": False,
        }
    
    reactions = {
        "investigate": {
            "action": "investigate",
            "message": f"Investigating: {handler['description']}",
            "auto_execute": False,
            "suggested_command": "python tools/self_improve_cli.py run",
        },
        "alert": {
            "action": "alert",
            "message": f"Alert: {handler['description']}",
            "auto_execute": True,
            "notification": True,
        },
        "cleanup_suggest": {
            "action": "suggest",
            "message": "Suggest running cleanup",
            "auto_execute": False,
            "suggested_command": "du -sh /home/milky/agent-os/* | sort -hr | head -10",
        },
        "restart_suggest": {
            "action": "suggest",
            "message": "Suggest restarting service",
            "auto_execute": False,
            "suggested_command": "systemctl --user restart openclaw-gateway",
        },
        "remind": {
            "action": "remind",
            "message": f"Reminder: {event.get('details', {}).get('reason', 'needs attention')}",
            "auto_execute": True,
        },
        "analyze": {
            "action": "analyze",
            "message": "Analyzing issue for potential fix",
            "auto_execute": False,
            "suggested_command": "python tools/self_improve_cli.py run",
        },
    }
    
    return reactions.get(handler["auto_action"], {
        "action": "log_only",
        "message": "No specific action defined",
        "auto_execute": False,
    })


def react_to_events(
    events: Optional[List[Dict[str, Any]]] = None,
    auto_execute: bool = False,
) -> Dict[str, Any]:
    """イベントに対してリアクション
    
    Args:
        events: イベントリスト（Noneの場合は自動収集）
        auto_execute: 自動実行可能なアクションを実行するか
    
    Returns:
        リアクション結果
    """
    if events is None:
        events = collect_events()
    
    events = prioritize_events(events)
    
    reactions = []
    executed = []
    
    for event in events:
        reaction = get_reaction(event)
        reaction["event"] = event
        reactions.append(reaction)
        
        # ログに記録
        log_event({
            "event": event,
            "reaction": reaction["action"],
        })
        
        # 自動実行
        if auto_execute and reaction.get("auto_execute"):
            executed.append({
                "event_type": event["type"],
                "action": reaction["action"],
            })
    
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "events_count": len(events),
        "reactions": reactions,
        "auto_executed": executed,
    }


def get_event_summary() -> Dict[str, Any]:
    """イベント履歴のサマリーを取得"""
    if not EVENT_LOG.exists():
        return {"total_events": 0, "by_type": {}}
    
    events = []
    for line in EVENT_LOG.read_text().strip().split("\n"):
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    
    by_type = {}
    for event in events:
        event_type = event.get("event", {}).get("type", "unknown")
        by_type[event_type] = by_type.get(event_type, 0) + 1
    
    return {
        "total_events": len(events),
        "by_type": by_type,
    }
