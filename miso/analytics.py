"""MISO analytics — Mission statistics and trends"""

from __future__ import annotations
import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from miso.dashboard import load_all_missions, get_week_range


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


def get_mission_datetime(mission: Dict[str, Any]) -> datetime:
    """Get mission creation datetime"""
    created_str = mission.get("created_at")
    if created_str:
        return datetime.fromisoformat(created_str.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def analyze_by_agents(missions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze statistics by agent"""
    agent_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "total": 0,
        "completed": 0,
        "error": 0,
        "running": 0,
        "total_time": 0,
        "completed_time": 0,
    })

    for m in missions:
        agents = m.get("agents", [])
        for a in agents:
            agent_name = a.get("name", "Unknown")
            status = a.get("status", "INIT")

            stats = agent_stats[agent_name]
            stats["total"] += 1

            if status == "COMPLETE":
                stats["completed"] += 1
            elif status == "ERROR":
                stats["error"] += 1
            elif status in ("RUNNING", "PARTIAL", "RETRYING"):
                stats["running"] += 1

        # Add mission time for average calculation
        elapsed = calculate_elapsed_minutes(m)
        mission_state = m.get("state", "")
        for stats in agent_stats.values():
            stats["total_time"] += elapsed
            if mission_state == "COMPLETE":
                stats["completed_time"] += elapsed

    # Calculate averages and rates
    result: Dict[str, Any] = {}
    for agent_name, stats in agent_stats.items():
        total = stats["total"]
        completed = stats["completed"]
        error = stats["error"]

        avg_time = stats["total_time"] / total if total > 0 else 0
        avg_completed_time = stats["completed_time"] / completed if completed > 0 else 0
        success_rate = (completed / total * 100) if total > 0 else 0
        error_rate = (error / total * 100) if total > 0 else 0

        result[agent_name] = {
            "total": total,
            "completed": completed,
            "error": error,
            "running": stats["running"],
            "success_rate": round(success_rate, 1),
            "error_rate": round(error_rate, 1),
            "avg_time_minutes": round(avg_time, 1),
            "avg_completed_time_minutes": round(avg_completed_time, 1),
        }

    return result


def analyze_by_models(missions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze statistics by model (if model data is available)"""
    model_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "total": 0,
        "completed": 0,
        "error": 0,
        "total_time": 0,
    })

    for m in missions:
        # Try to extract model info from various possible fields
        model = m.get("model") or m.get("model_id") or "unknown"
        if not model or model == "unknown":
            # Try to infer from other fields
            if "glm-5" in json.dumps(m).lower():
                model = "glm-5"
            elif "kimi" in json.dumps(m).lower():
                model = "kimi-k2.5"
            elif "claude" in json.dumps(m).lower():
                model = "claude"
            else:
                model = "unknown"

        stats = model_stats[model]
        stats["total"] += 1

        state = m.get("state", "")
        if state == "COMPLETE":
            stats["completed"] += 1
        elif state == "ERROR":
            stats["error"] += 1

        stats["total_time"] += calculate_elapsed_minutes(m)

    # Calculate averages
    result: Dict[str, Any] = {}
    for model_name, stats in model_stats.items():
        total = stats["total"]
        completed = stats["completed"]
        error = stats["error"]

        avg_time = stats["total_time"] / total if total > 0 else 0
        success_rate = (completed / total * 100) if total > 0 else 0

        result[model_name] = {
            "total": total,
            "completed": completed,
            "error": error,
            "success_rate": round(success_rate, 1),
            "avg_time_minutes": round(avg_time, 1),
        }

    return result


def analyze_by_hour(missions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze statistics by hour of day (0-23)"""
    hour_stats: Dict[int, Dict[str, int]] = defaultdict(lambda: {"total": 0, "completed": 0, "error": 0})

    for m in missions:
        dt = get_mission_datetime(m)
        hour = dt.hour

        hour_stats[hour]["total"] += 1

        state = m.get("state", "")
        if state == "COMPLETE":
            hour_stats[hour]["completed"] += 1
        elif state == "ERROR":
            hour_stats[hour]["error"] += 1

    # Convert to list and sort by hour
    result: List[Dict[str, Any]] = []
    for hour in range(24):
        if hour in hour_stats:
            stats = hour_stats[hour]
            total = stats["total"]
            success_rate = (stats["completed"] / total * 100) if total > 0 else 0

            result.append({
                "hour": hour,
                "time_range": f"{hour:02d}:00-{(hour+1)%24:02d}:00",
                "total": total,
                "completed": stats["completed"],
                "error": stats["error"],
                "success_rate": round(success_rate, 1),
            })
        else:
            result.append({
                "hour": hour,
                "time_range": f"{hour:02d}:00-{(hour+1)%24:02d}:00",
                "total": 0,
                "completed": 0,
                "error": 0,
                "success_rate": 0.0,
            })

    return {"by_hour": result}


def analyze_trends(missions: List[Dict[str, Any]], days: int = 30) -> Dict[str, Any]:
    """Analyze daily trends over the last N days"""
    today = datetime.now(timezone.utc)
    daily_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "completed": 0, "error": 0})

    # Initialize for all days
    for i in range(days):
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_stats[date] = {"total": 0, "completed": 0, "error": 0}

    # Count missions by date
    for m in missions:
        dt = get_mission_datetime(m)
        date_key = dt.strftime("%Y-%m-%d")
        if date_key in daily_stats:
            daily_stats[date_key]["total"] += 1
            state = m.get("state", "")
            if state == "COMPLETE":
                daily_stats[date_key]["completed"] += 1
            elif state == "ERROR":
                daily_stats[date_key]["error"] += 1

    # Convert to list (oldest first)
    result: List[Dict[str, Any]] = []
    for date_key in sorted(daily_stats.keys(), reverse=True)[:days][::-1]:
        stats = daily_stats[date_key]
        total = stats["total"]
        success_rate = (stats["completed"] / total * 100) if total > 0 else 0

        result.append({
            "date": date_key,
            "total": total,
            "completed": stats["completed"],
            "error": stats["error"],
            "success_rate": round(success_rate, 1),
        })

    return {"trends": result, "period_days": days}


def generate_summary(missions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate overall summary"""
    total = len(missions)
    completed = sum(1 for m in missions if m.get("state") == "COMPLETE")
    error = sum(1 for m in missions if m.get("state") == "ERROR")
    running = sum(1 for m in missions if m.get("state") in ("RUNNING", "PARTIAL", "RETRYING"))
    awaiting = sum(1 for m in missions if m.get("state") == "AWAITING_APPROVAL")

    # Average time
    total_time = sum(calculate_elapsed_minutes(m) for m in missions)
    avg_time = total_time / total if total > 0 else 0

    # Success rate
    success_rate = (completed / total * 100) if total > 0 else 0

    # Date range
    if missions:
        created_times = [get_mission_datetime(m) for m in missions if m.get("created_at")]
        if created_times:
            date_range = {
                "earliest": min(created_times).strftime("%Y-%m-%d %H:%M"),
                "latest": max(created_times).strftime("%Y-%m-%d %H:%M"),
            }
        else:
            date_range = None
    else:
        date_range = None

    return {
        "total_missions": total,
        "completed": completed,
        "error": error,
        "running": running,
        "awaiting_approval": awaiting,
        "success_rate": round(success_rate, 1),
        "avg_time_minutes": round(avg_time, 1),
        "date_range": date_range,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="MISO Analytics")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # agents command
    agents_parser = subparsers.add_parser("agents", help="Agent statistics")
    agents_parser.add_argument(
        "--output", "-o",
        help="Output JSON file path",
    )

    # trends command
    trends_parser = subparsers.add_parser("trends", help="Daily trends")
    trends_parser.add_argument(
        "--days", "-d",
        type=int,
        default=30,
        help="Number of days to analyze (default: 30)",
    )
    trends_parser.add_argument(
        "--output", "-o",
        help="Output JSON file path",
    )

    # hourly command
    hourly_parser = subparsers.add_parser("hourly", help="Hourly statistics")
    hourly_parser.add_argument(
        "--output", "-o",
        help="Output JSON file path",
    )

    # summary command
    summary_parser = subparsers.add_parser("summary", help="Overall summary")
    summary_parser.add_argument(
        "--output", "-o",
        help="Output JSON file path",
    )

    args = parser.parse_args()

    # Load all missions
    missions = load_all_missions()

    # Run command
    result: Dict[str, Any] = {}

    if args.command == "agents":
        result = analyze_by_agents(missions)
    elif args.command == "trends":
        result = analyze_trends(missions, args.days)
    elif args.command == "hourly":
        result = analyze_by_hour(missions)
    elif args.command == "summary":
        result = generate_summary(missions)

    # Output
    output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(json.dumps({"ok": True, "output": args.output}, ensure_ascii=False))
    else:
        print(output)


if __name__ == "__main__":
    main()
