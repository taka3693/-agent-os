"""MISO dashboard — Mission statistics and history"""

from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from miso.bridge import MISO_STATE_DIR, _load_mission
from miso.formatter import STATE_LABELS, STATUS_ICONS
from miso.telegram_hooks import send_message


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_all_missions() -> List[Dict[str, Any]]:
    """Load all missions from MISO_STATE_DIR"""
    missions = []
    for path in MISO_STATE_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data:
                missions.append(data)
        except Exception:
            continue
    # Sort by created_at descending (newest first)
    missions.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return missions


def filter_missions(
    missions: List[Dict[str, Any]],
    start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
    """Filter missions by created_at time range (inclusive start, exclusive end)"""
    filtered = []
    for m in missions:
        created_str = m.get("created_at")
        if not created_str:
            continue
        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            created_utc = created.replace(tzinfo=timezone.utc)
            if start <= created_utc < end:
                filtered.append(m)
        except Exception:
            continue
    return filtered


def get_today_range() -> tuple[datetime, datetime]:
    """Get today's UTC range (00:00 to 23:59)"""
    now = utc_now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def get_week_range() -> tuple[datetime, datetime]:
    """Get this week's UTC range (Monday 00:00 to Sunday 23:59)"""
    now = utc_now()
    # Monday = 0, Sunday = 6 in Python weekday
    monday = now - timedelta(days=now.weekday())
    start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start, end


def calculate_elapsed_minutes(mission: Dict[str, Any]) -> int:
    """Calculate elapsed minutes for a mission"""
    created_str = mission.get("created_at")
    if not created_str:
        return 0

    # Use completed_at if available, otherwise use updated_at
    completed_str = mission.get("completed_at")
    if completed_str:
        end_time = datetime.fromisoformat(completed_str.replace("Z", "+00:00"))
    else:
        updated_str = mission.get("updated_at", created_str)
        end_time = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))

    start_time = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
    delta = end_time - start_time
    return int(delta.total_seconds() / 60)


def format_dashboard_message(missions: List[Dict[str, Any]]) -> str:
    """Generate dashboard summary message"""
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Count by state
    running = 0
    awaiting_approval = 0
    today_completed = 0
    today_error = 0

    for m in missions:
        state = m.get("state", "INIT")
        created_str = m.get("created_at")
        is_today = False

        if created_str:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            is_today = created.replace(tzinfo=timezone.utc) >= today_start

        if state in ("RUNNING", "PARTIAL", "RETRYING"):
            running += 1
        elif state == "AWAITING_APPROVAL":
            awaiting_approval += 1
        elif state == "COMPLETE" and is_today:
            today_completed += 1
        elif state == "ERROR" and is_today:
            today_error += 1

    lines = [
        "📊 MISO DASHBOARD",
        "——————————————",
        f"🔥 進行中: {running}件",
        f"👀 確認待ち: {awaiting_approval}件",
        f"✅ 本日完了: {today_completed}件",
        f"❌ 本日エラー: {today_error}件",
        "——————————————",
        f"総ミッション数: {len(missions)}件",
        "——————————————",
        "🌸 powered by miyabi",
    ]

    return "\n".join(lines)


def format_stats_message(missions: List[Dict[str, Any]]) -> str:
    """Generate full statistics message"""
    if not missions:
        return "📊 統計情報\n——————————————\nミッションがありません。\n——————————————\n🌸 powered by miyabi"

    now = utc_now()
    today_start, today_end = get_today_range()
    week_start, week_end = get_week_range()

    # Count stats
    total = len(missions)
    completed = 0
    failed = 0
    today_count = 0
    week_count = 0
    total_elapsed = 0

    for m in missions:
        state = m.get("state", "INIT")
        created_str = m.get("created_at")

        if state == "COMPLETE":
            completed += 1
        elif state == "ERROR":
            failed += 1

        if created_str:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            created_utc = created.replace(tzinfo=timezone.utc)
            if today_start <= created_utc < today_end:
                today_count += 1
            if week_start <= created_utc < week_end:
                week_count += 1

        total_elapsed += calculate_elapsed_minutes(m)

    # Calculate metrics
    success_rate = 0
    if completed + failed > 0:
        success_rate = (completed / (completed + failed)) * 100

    avg_elapsed = 0
    if total > 0:
        avg_elapsed = total_elapsed / total

    lines = [
        "📊 MISO 統計情報",
        "——————————————",
        "【全期間統計】",
        f"総ミッション数: {total}件",
        f"完了: {completed}件 ∣ 失敗: {failed}件",
        f"成功率: {success_rate:.1f}%",
        f"平均実行時間: {avg_elapsed:.1f}分",
        "",
        "【期間別件数】",
        f"今日: {today_count}件",
        f"今週: {week_count}件",
        "——————————————",
        "🌸 powered by miyabi",
    ]

    return "\n".join(lines)


def format_history_message(missions: List[Dict[str, Any]], limit: int = 10) -> str:
    """Generate history list message"""
    if not missions:
        return "📜 履歴\n——————————————\nミッションがありません。\n——————————————\n🌸 powered by miyabi"

    lines = [
        "📜 MISSION 履歴",
        "——————————————",
    ]

    # Show last N missions
    for m in missions[:limit]:
        mission_id = m.get("mission_id", "N/A")[:8]
        mission_name = m.get("mission_name", "不明")
        state = m.get("state", "INIT")
        created_str = m.get("created_at", "")
        elapsed = calculate_elapsed_minutes(m)

        state_label = STATE_LABELS.get(state, state)
        icon = STATUS_ICONS.get(state, "⏳")

        # Format created time
        created_display = ""
        if created_str:
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                created = created.astimezone()
                created_display = created.strftime("%m/%d %H:%M")
            except Exception:
                pass

        lines.append(f"{icon} {mission_name}")
        lines.append(f"   ID: {mission_id} ∣ {state_label} ∣ {created_display} ∣ {elapsed}分")

        # Show next_action if available
        next_action = m.get("next_action", "")
        if next_action:
            lines.append(f"   次に: {next_action[:50]}")

        lines.append("")

    lines.append("——————————————")
    lines.append("🌸 powered by miyabi")

    return "\n".join(lines)


def dashboard(chat_id: str) -> Dict[str, Any]:
    """Send dashboard summary to Telegram"""
    missions = load_all_missions()
    message = format_dashboard_message(missions)
    return send_message(chat_id=chat_id, message=message)


def stats(chat_id: str) -> Dict[str, Any]:
    """Send full statistics to Telegram"""
    missions = load_all_missions()
    message = format_stats_message(missions)
    return send_message(chat_id=chat_id, message=message)


def history(chat_id: str, limit: int = 10) -> Dict[str, Any]:
    """Send history list to Telegram"""
    missions = load_all_missions()
    message = format_history_message(missions, limit)
    return send_message(chat_id=chat_id, message=message)


def main():
    parser = argparse.ArgumentParser(description="MISO Dashboard CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # dashboard command
    dashboard_parser = subparsers.add_parser("dashboard", help="Show dashboard summary")
    dashboard_parser.add_argument("--chat-id", required=True, help="Telegram chat ID")

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show full statistics")
    stats_parser.add_argument("--chat-id", required=True, help="Telegram chat ID")

    # history command
    history_parser = subparsers.add_parser("history", help="Show mission history")
    history_parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    history_parser.add_argument("--limit", type=int, default=10, help="Number of missions to show (default: 10)")

    args = parser.parse_args()

    if args.command == "dashboard":
        result = dashboard(args.chat_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "stats":
        result = stats(args.chat_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "history":
        result = history(args.chat_id, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
