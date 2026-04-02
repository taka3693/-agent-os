"""MISO search — Search missions by keyword"""

from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from miso.dashboard import load_all_missions
from miso.formatter import STATE_LABELS, STATUS_ICONS
from miso.telegram_hooks import send_message


def format_datetime(iso_str: str) -> str:
    """Format ISO datetime to display format"""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str[:16]


def calculate_elapsed_minutes(mission: Dict[str, Any]) -> int:
    """Calculate elapsed minutes for a mission"""
    created_str = mission.get("created_at")
    if not created_str:
        return 0

    updated_str = mission.get("updated_at", created_str)
    start_time = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
    end_time = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))

    delta = end_time - start_time
    return int(delta.total_seconds() / 60)


def search_missions(
    keyword: str,
    case_sensitive: bool = False,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Search missions by keyword.

    Searches in:
    - mission_name
    - goal
    - agent names
    """
    if not case_sensitive:
        keyword = keyword.lower()

    all_missions = load_all_missions()
    results = []

    for m in all_missions:
        mission_name = m.get("mission_name", "")
        goal = m.get("goal", "")
        agents = m.get("agents", [])

        # Build search text
        search_text = mission_name + " " + goal
        for a in agents:
            search_text += " " + a.get("name", "")

        # Perform search
        if case_sensitive:
            match = keyword in search_text
        else:
            match = keyword in search_text.lower()

        if match:
            # Add metadata for display
            m_copy = m.copy()
            m_copy["_elapsed"] = calculate_elapsed_minutes(m)
            results.append(m_copy)

            if len(results) >= limit:
                break

    return results


def format_search_results(
    results: List[Dict[str, Any]],
    keyword: str,
) -> str:
    """Format search results as message"""
    lines = [
        f'🔍 検索結果: "{keyword}"',
        "——————————————",
    ]

    if not results:
        lines.append("該当するミッションがありませんでした。")
    else:
        for m in results:
            mission_name = m.get("mission_name", "不明")
            mission_id = m.get("mission_id", "N/A")[:8]
            state = m.get("state", "INIT")
            elapsed = m.get("_elapsed", 0)
            created_str = m.get("created_at", "")

            state_label = STATE_LABELS.get(state, state)
            icon = STATUS_ICONS.get(state, "⏳")
            created_display = format_datetime(created_str)

            lines.append(f"{icon} {mission_name} (#{mission_id})")
            lines.append(f" └ {state_label} ∣ {elapsed}m ∣ {created_display}")
            lines.append("")

        lines.append(f"計{len(results)}件")

    lines.append("——————————————")
    lines.append("🌸 powered by miyabi")

    return "\n".join(lines)


def search_and_send(
    keyword: str,
    chat_id: str,
    case_sensitive: bool = False,
    limit: int = 10,
) -> Dict[str, Any]:
    """Search missions and send results to Telegram"""
    results = search_missions(keyword, case_sensitive, limit)
    message = format_search_results(results, keyword)
    return send_message(chat_id=chat_id, message=message)


def main():
    parser = argparse.ArgumentParser(description="MISO Search")
    parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    parser.add_argument("--keyword", required=True, help="Search keyword")
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Case-sensitive search",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=10,
        help="Maximum results (default: 10)",
    )

    args = parser.parse_args()

    result = search_and_send(
        args.keyword,
        args.chat_id,
        args.case_sensitive,
        args.limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
