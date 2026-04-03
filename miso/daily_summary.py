"""MISO daily summary — Daily mission summary with previous day comparison"""

from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from miso.dashboard import load_all_missions, filter_missions, get_today_range
from miso.formatter import STATE_LABELS
from miso.telegram_hooks import send_message


def get_day_range(date: datetime) -> tuple[datetime, datetime]:
    """Get UTC range for a specific date (00:00 to 23:59)"""
    start = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def count_by_state(missions: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count missions by state"""
    counts: Dict[str, int] = {
        "INIT": 0,
        "RUNNING": 0,
        "PARTIAL": 0,
        "RETRYING": 0,
        "AWAITING_APPROVAL": 0,
        "COMPLETE": 0,
        "ERROR": 0,
    }
    for m in missions:
        state = m.get("state", "INIT")
        counts[state] = counts.get(state, 0) + 1
    return counts


def format_change(current: int, previous: int) -> str:
    """Format change with emoji indicator"""
    diff = current - previous
    if diff > 0:
        return f"+{diff} 📈"
    elif diff < 0:
        return f"{diff} 📉"
    else:
        return "0 ➡️"


def format_daily_summary(
    today_missions: List[Dict[str, Any]],
    yesterday_missions: List[Dict[str, Any]],
    today_date: datetime,
) -> str:
    """Generate daily summary message with previous day comparison"""
    today_counts = count_by_state(today_missions)
    yesterday_counts = count_by_state(yesterday_missions)

    # Get yesterday's date string
    yesterday_date = today_date - timedelta(days=1)
    today_str = today_date.strftime("%Y/%m/%d (%a)")
    yesterday_str = yesterday_date.strftime("%m/%d")

    # Calculate changes
    completed_change = format_change(today_counts["COMPLETE"], yesterday_counts["COMPLETE"])
    error_change = format_change(today_counts["ERROR"], yesterday_counts["ERROR"])
    total_change = format_change(len(today_missions), len(yesterday_missions))

    # Average completion time (for completed missions only)
    completed_today = [m for m in today_missions if m.get("state") == "COMPLETE"]
    avg_time = 0
    if completed_today:
        total_minutes = 0
        for m in completed_today:
            created_str = m.get("created_at")
            updated_str = m.get("updated_at") or m.get("completed_at")
            if created_str and updated_str:
                try:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                    total_minutes += (updated - created).total_seconds() / 60
                except Exception:
                    pass
        avg_time = total_minutes / len(completed_today)

    lines = [
        "📅 MISO 日次サマリー",
        "——————————————",
        f"🗓 日付: {today_str}",
        "",
        "【今日のミッション】",
        f"総数: {len(today_missions)}件 ({total_change} vs {yesterday_str})",
        f"✅ 完了: {today_counts['COMPLETE']}件 ({completed_change})",
        f"❌ 失敗: {today_counts['ERROR']}件 ({error_change})",
        f"🔥 進行中: {today_counts['RUNNING'] + today_counts['PARTIAL'] + today_counts['RETRYING']}件",
        f"👀 確認待ち: {today_counts['AWAITING_APPROVAL']}件",
        "",
    ]

    if completed_today:
        lines.append(f"⏱ 平均完了時間: {avg_time:.1f}分")

    # Show yesterday's stats for reference
    if yesterday_missions:
        y_completed = yesterday_counts["COMPLETE"]
        y_error = yesterday_counts["ERROR"]
        lines.append("")
        lines.append(f"【昨日の参考】")
        lines.append(f"完了: {y_completed}件 ∣ 失敗: {y_error}件")

    lines.append("")
    lines.append("——————————————")
    lines.append("🌸 powered by miyabi")

    return "\n".join(lines)


def send_daily_summary(chat_id: str, date: Optional[datetime] = None) -> Dict[str, Any]:
    """Send daily summary to Telegram"""
    if date is None:
        date = datetime.now(timezone.utc)

    # Load all missions
    all_missions = load_all_missions()

    # Get today's and yesterday's missions
    today_start, today_end = get_day_range(date)
    yesterday_date = date - timedelta(days=1)
    yesterday_start, yesterday_end = get_day_range(yesterday_date)

    today_missions = filter_missions(all_missions, today_start, today_end)
    yesterday_missions = filter_missions(all_missions, yesterday_start, yesterday_end)

    # Generate and send summary
    message = format_daily_summary(today_missions, yesterday_missions, date)
    return send_message(chat_id=chat_id, message=message)


def main():
    parser = argparse.ArgumentParser(description="MISO Daily Summary CLI")
    parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    parser.add_argument(
        "--date",
        help="Target date (YYYY-MM-DD, default: today)",
    )

    args = parser.parse_args()

    # Parse date if provided
    target_date = None
    if args.date:
        try:
            target_date = datetime.fromisoformat(args.date).replace(tzinfo=timezone.utc)
        except ValueError:
            print(json.dumps({"ok": False, "error": "Invalid date format. Use YYYY-MM-DD"}, ensure_ascii=False))
            sys.exit(1)

    result = send_daily_summary(args.chat_id, target_date)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
