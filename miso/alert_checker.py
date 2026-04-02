"""MISO alert checker — Detect long-running missions"""

from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from miso.dashboard import load_all_missions
from miso.formatter import STATE_LABELS
from miso.telegram_hooks import send_message

# Alert state storage
ALERT_STATE_DIR = PROJECT_ROOT / "state" / "alerts"
ALERT_STATE_DIR.mkdir(parents=True, exist_ok=True)
ALERT_STATE_FILE = ALERT_STATE_DIR / "long_running_alerts.json"


def load_alerted_missions() -> Dict[str, str]:
    """Load set of already alerted mission IDs with alert timestamps"""
    if ALERT_STATE_FILE.exists():
        try:
            return json.loads(ALERT_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_alerted_missions(alerted: Dict[str, str]) -> None:
    """Save alerted mission IDs with timestamps"""
    ALERT_STATE_FILE.write_text(json.dumps(alerted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cleanup_old_alerts(alerted: Dict[str, str], max_age_hours: int = 24) -> Dict[str, str]:
    """Remove alert records older than max_age_hours"""
    if not alerted:
        return alerted

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    cleaned = {}
    for mission_id, alert_time_str in alerted.items():
        try:
            alert_time = datetime.fromisoformat(alert_time_str.replace("Z", "+00:00"))
            if alert_time >= cutoff:
                cleaned[mission_id] = alert_time_str
        except Exception:
            # Keep entries that can't be parsed
            cleaned[mission_id] = alert_time_str

    return cleaned


def calculate_elapsed_minutes(mission: Dict[str, Any]) -> int:
    """Calculate elapsed minutes for a mission"""
    created_str = mission.get("created_at")
    if not created_str:
        return 0

    # Use updated_at as current time reference
    updated_str = mission.get("updated_at", created_str)
    start_time = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
    end_time = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))

    delta = end_time - start_time
    return int(delta.total_seconds() / 60)


def check_long_running_missions(
    threshold_minutes: int = 30,
    chat_id: str = "6474742983",
) -> List[Dict[str, Any]]:
    """
    Check for missions running longer than threshold.

    Returns: List of mission dicts that exceed threshold and haven't been alerted.
    """
    # Load missions
    all_missions = load_all_missions()

    # Filter running missions
    running_states = ("RUNNING", "PARTIAL", "RETRYING")
    running_missions = [
        m for m in all_missions
        if m.get("state") in running_states
    ]

    # Calculate elapsed times
    long_running = []
    for m in running_missions:
        elapsed = calculate_elapsed_minutes(m)
        if elapsed >= threshold_minutes:
            m["_elapsed"] = elapsed
            long_running.append(m)

    if not long_running:
        return []

    # Load alerted missions and cleanup old entries
    alerted = load_alerted_missions()
    alerted = cleanup_old_alerts(alerted)

    # Filter out already alerted missions
    new_alerts = [m for m in long_running if m.get("mission_id") not in alerted]

    if new_alerts:
        # Mark as alerted
        now = datetime.now(timezone.utc).isoformat()
        for m in new_alerts:
            mission_id = m.get("mission_id")
            if mission_id:
                alerted[mission_id] = now
        save_alerted_missions(alerted)

    return new_alerts


def format_alert_message(
    missions: List[Dict[str, Any]],
    threshold_minutes: int,
) -> str:
    """Generate alert message for long-running missions"""
    lines = [
        "⚠️ MISO 長時間アラート",
        "——————————————",
        f"以下のミッションが{threshold_minutes}分以上進行中：",
        "",
    ]

    for m in missions:
        mission_id = m.get("mission_id", "N/A")[:8]
        mission_name = m.get("mission_name", "不明")
        elapsed = m.get("_elapsed", 0)

        # Count completed agents
        agents = m.get("agents", [])
        total = len(agents)
        done = sum(1 for a in agents if a.get("status") == "COMPLETE")

        lines.append(f"🔥 {mission_id}")
        lines.append(f" └ {mission_name} ∣ {elapsed}分経過 ∣ {done}/{total}件完了")
        lines.append("")

    lines.append("対応: /miso dashboard で確認")
    lines.append("——————————————")
    lines.append("🌸 powered by miyabi")

    return "\n".join(lines)


def send_alert(
    threshold_minutes: int = 30,
    chat_id: str = "6474742983",
) -> Dict[str, Any]:
    """Check and send alerts for long-running missions"""
    long_running = check_long_running_missions(threshold_minutes, chat_id)

    if not long_running:
        return {"ok": True, "alerted": 0, "message": "No long-running missions found"}

    message = format_alert_message(long_running, threshold_minutes)
    result = send_message(chat_id=chat_id, message=message)

    if result.get("ok"):
        result["alerted"] = len(long_running)
    else:
        result["alerted"] = 0

    return result


def main():
    parser = argparse.ArgumentParser(description="MISO Alert Checker")
    parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    parser.add_argument(
        "--threshold",
        type=int,
        default=30,
        help="Threshold in minutes (default: 30)",
    )

    args = parser.parse_args()

    result = send_alert(args.threshold, args.chat_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
