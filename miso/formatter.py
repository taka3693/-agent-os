"""MISO message formatter — Telegram-safe format generation"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

# State → Reaction mapping
STATE_REACTIONS = {
    "INIT": "🔥",
    "RUNNING": "🔥",
    "PARTIAL": "🔥",
    "RETRYING": "🔥",
    "AWAITING_APPROVAL": "👀",
    "COMPLETE": "🎉",
    "ERROR": "❌",
}

# State display names (Japanese)
STATE_LABELS = {
    "INIT": "開始",
    "RUNNING": "進行中",
    "PARTIAL": "一部完了",
    "RETRYING": "再試行中",
    "AWAITING_APPROVAL": "確認待ち",
    "COMPLETE": "完了",
    "ERROR": "失敗",
}

# Status icons
STATUS_ICONS = {
    "INIT": "⏳",
    "RUNNING": "🔥",
    "PARTIAL": "🔥",
    "RETRYING": "🔄",
    "AWAITING_APPROVAL": "⏸️",
    "COMPLETE": "✅",
    "ERROR": "❌",
}


def progress_bar(percent: int, width: int = 16) -> str:
    """Generate progress bar: ▓▓▓▓░░░░░░░░░░░░ 25%"""
    percent = max(0, min(100, percent))
    filled = round(percent / 100 * width)
    bar = "▓" * filled + "░" * (width - filled)
    return f"{bar} {percent}%"


def format_agent_line(name: str, status: str, detail: str = "") -> str:
    """Format single agent line: ↳ 担当A: 進行中（準備完了）"""
    icon = STATUS_ICONS.get(status, "⏳")
    label = STATE_LABELS.get(status, status)
    line = f"↳ {name}: {icon} {label}"
    if detail:
        line += f"（{detail}）"
    return line


def normalize_detail(detail: str) -> str:
    """Normalize detail text to short Japanese"""
    mappings = {
        "worker attached and ready": "準備完了",
        "再試行後も失敗。確認をお願いします": "再試行後も解決せず",
        "approval required": "承認待ち",
        "blocked by allowlist": "allowlist外",
        "simulated_done": "シミュレーション完了",
    }
    lower = (detail or "").strip().lower()
    for pattern, replacement in mappings.items():
        if pattern.lower() in lower:
            return replacement
    return detail[:20] if len(detail) > 20 else detail


def format_mission_message(
    mission_name: str,
    goal: str,
    agents: List[Dict[str, Any]],
    state: str,
    elapsed: str = "0m",
    next_action: str = "",
) -> str:
    """
    Generate full MISO mission message.
    
    agents: [{"name": "担当A", "status": "RUNNING", "detail": "準備完了"}, ...]
    """
    done_count = sum(1 for a in agents if a.get("status") == "COMPLETE")
    total = len(agents)
    state_label = STATE_LABELS.get(state, state)
    
    lines = [
        "🤖 MISSION CONTROL",
        "——————————————",
        f"📋 {mission_name}",
        f"⏱ {elapsed} ∣ {done_count}件中{total}件完了 ∣ {state_label}",
        f"・目的: {goal}",
        "",
    ]
    
    for agent in agents:
        name = agent.get("display_label") or agent.get("name", "担当")
        status = agent.get("status", "INIT")
        detail = normalize_detail(agent.get("detail", ""))
        lines.append(format_agent_line(name, status, detail))
    
    lines.append("")
    if next_action:
        lines.append(f"・次にすること: {next_action}")
    lines.append("——————————————")
    lines.append("🌸 powered by miyabi")
    
    return "\n".join(lines)


def format_approval_message(
    task_id: str,
    target: str,
    handler: str,
    reason: str,
) -> str:
    """Generate approval request message"""
    lines = [
        "🤖 MISSION CONTROL",
        "——————————————",
        "⏸️ 承認待ち",
        "",
        f"・タスク: {task_id}",
        f"・対象: {target}",
        f"・操作: {handler}",
        f"・理由: {reason}",
        "",
        "承認しますか？",
        "——————————————",
        "🌸 powered by miyabi",
    ]
    return "\n".join(lines)


def get_reaction_for_state(state: str) -> str:
    """Get appropriate reaction emoji for state"""
    return STATE_REACTIONS.get(state, "🔥")
