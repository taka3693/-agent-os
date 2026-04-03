"""MISO cost tracker — Track API usage and costs"""

from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from miso.telegram_hooks import send_message

# Cost log file
COST_LOG_DIR = PROJECT_ROOT / "state" / "miso"
COST_LOG_DIR.mkdir(parents=True, exist_ok=True)
COST_LOG_FILE = COST_LOG_DIR / "cost_log.jsonl"

# Session budget file
SESSION_BUDGET_FILE = COST_LOG_DIR / "session_budget.json"

# Model pricing (USD per 1M tokens)
MODEL_PRICING = {
    "glm-4.7": {"input": 0.12, "output": 0.30},
    "glm-5": {"input": 0.15, "output": 0.60},
    "kimi-k2.5": {"input": 0.10, "output": 0.20},
    "gpt-5.4": {"input": 0.50, "output": 1.50},
    "claude-opus-4-5": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-6": {"input": 0.15, "output": 0.60},
    "unknown": {"input": 0.20, "output": 0.50},
}

# Context budget settings
CONTEXT_BUDGET = int(os.getenv("MISO_CONTEXT_BUDGET", 128000))
WARNING_THRESHOLD = 80  # percent
DANGER_THRESHOLD = 95  # percent


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Calculate cost based on model pricing"""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["unknown"])
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


def log_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    mission_id: str,
    cost_usd: float,
    session_id: str = "",
) -> Dict[str, Any]:
    """Log cost entry to JSONL file"""
    entry = {
        "timestamp": utc_now(),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "mission_id": mission_id,
        "session_id": session_id,
        "cost_usd": cost_usd,
    }

    with open(COST_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Update session budget if session_id is provided
    if session_id:
        update_session_tokens(session_id, input_tokens, output_tokens, model)

    return {"ok": True, "entry": entry}


def load_cost_logs() -> List[Dict[str, Any]]:
    """Load all cost log entries"""
    logs = []
    if not COST_LOG_FILE.exists():
        return logs

    try:
        with open(COST_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    logs.append(json.loads(line))
    except Exception:
        pass

    return logs


def get_period_stats(
    logs: List[Dict[str, Any]],
    start: datetime,
    end: datetime,
) -> Dict[str, Any]:
    """Calculate stats for a time period"""
    period_logs = [
        log for log in logs
        if start <= datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00")) < end
    ]

    total_cost = sum(log["cost_usd"] for log in period_logs)
    total_tokens = sum(log["total_tokens"] for log in period_logs)

    return {
        "cost_usd": total_cost,
        "total_tokens": total_tokens,
        "count": len(period_logs),
    }


def get_model_stats(
    logs: List[Dict[str, Any]],
    start: datetime,
    end: datetime,
) -> Dict[str, Dict[str, Any]]:
    """Calculate stats by model"""
    period_logs = [
        log for log in logs
        if start <= datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00")) < end
    ]

    model_stats: Dict[str, Dict[str, Any]] = {}
    total_cost = 0

    for log in period_logs:
        model = log["model"]
        if model not in model_stats:
            model_stats[model] = {
                "cost_usd": 0,
                "total_tokens": 0,
                "count": 0,
            }
        model_stats[model]["cost_usd"] += log["cost_usd"]
        model_stats[model]["total_tokens"] += log["total_tokens"]
        model_stats[model]["count"] += 1
        total_cost += log["cost_usd"]

    # Calculate percentages
    for stats in model_stats.values():
        stats["percentage"] = (stats["cost_usd"] / total_cost * 100) if total_cost > 0 else 0

    return model_stats


def format_cost_report(
    today_stats: Dict[str, Any],
    week_stats: Dict[str, Any],
    month_stats: Dict[str, Any],
    model_stats: Dict[str, Dict[str, Any]],
) -> str:
    """Format cost report as message"""
    lines = [
        "💰 MISO コスト追跡",
        "——————————————",
        f"📅 今日: ${today_stats['cost_usd']:.4f} ({today_stats['total_tokens']:,} tokens)",
        f"📅 今週: ${week_stats['cost_usd']:.4f} ({week_stats['total_tokens']:,} tokens)",
        f"📅 今月: ${month_stats['cost_usd']:.4f} ({month_stats['total_tokens']:,} tokens)",
        "",
        "【モデル別】",
    ]

    # Sort by cost descending
    sorted_models = sorted(model_stats.items(), key=lambda x: x[1]["cost_usd"], reverse=True)

    for model, stats in sorted_models:
        lines.append(f"・{model}: ${stats['cost_usd']:.4f} ({stats['percentage']:.1f}%)")

    lines.append("")
    lines.append("——————————————")
    lines.append("🌸 powered by miyabi")

    return "\n".join(lines)


def generate_and_send_report(chat_id: str) -> Dict[str, Any]:
    """Generate and send cost report to Telegram"""
    logs = load_cost_logs()

    if not logs:
        message = (
            "💰 MISO コスト追跡\n"
            "——————————————\n"
            "コストデータがまだありません。\n"
            "——————————————\n"
            "🌸 powered by miyabi"
        )
        return send_message(chat_id=chat_id, message=message)

    # Calculate period stats
    now = datetime.now(timezone.utc)

    # Today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    today_stats = get_period_stats(logs, today_start, today_end)

    # This week (Monday to Sunday)
    monday = now - timedelta(days=now.weekday())
    week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)
    week_stats = get_period_stats(logs, week_start, week_end)

    # This month
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (month_start.replace(day=28) + timedelta(days=4))
    month_end = next_month.replace(day=1)
    month_stats = get_period_stats(logs, month_start, month_end)

    # Model stats (this month)
    model_stats = get_model_stats(logs, month_start, month_end)

    # Generate and send report
    message = format_cost_report(today_stats, week_stats, month_stats, model_stats)
    return send_message(chat_id=chat_id, message=message)


# === Session Budget Management ===

def load_session_budget() -> Dict[str, Dict[str, Any]]:
    """Load session budget data"""
    if not SESSION_BUDGET_FILE.exists():
        return {}

    try:
        with open(SESSION_BUDGET_FILE, "r", encoding="utf-8") as f:
            return json.loads(f.read())
    except Exception:
        return {}


def save_session_budget(budget_data: Dict[str, Dict[str, Any]]) -> None:
    """Save session budget data"""
    SESSION_BUDGET_FILE.write_text(
        json.dumps(budget_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_session_token_usage(session_id: str) -> int:
    """
    Get accumulated token usage for a session.

    Returns: total tokens used in the session
    """
    budget_data = load_session_budget()
    session_data = budget_data.get(session_id, {})
    return session_data.get("total_tokens", 0)


def update_session_tokens(
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    model: str = "unknown",
) -> Dict[str, Any]:
    """
    Update session token usage.

    Returns: {"ok": True, "total": total_tokens, "percent": percent}
    """
    budget_data = load_session_budget()

    if session_id not in budget_data:
        budget_data[session_id] = {
            "session_id": session_id,
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "model": model,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

    session = budget_data[session_id]
    session["input_tokens"] += input_tokens
    session["output_tokens"] += output_tokens
    session["total_tokens"] += input_tokens + output_tokens
    session["updated_at"] = utc_now()

    # Update model if changed
    if model != "unknown":
        session["model"] = model

    save_session_budget(budget_data)

    percent = (session["total_tokens"] / CONTEXT_BUDGET * 100) if CONTEXT_BUDGET > 0 else 0

    return {
        "ok": True,
        "total": session["total_tokens"],
        "percent": round(percent, 1),
    }


def get_budget_status(session_id: str) -> Dict[str, Any]:
    """
    Get current budget status for a session.

    Returns: {
        "used": 50000,
        "limit": 128000,
        "percent": 39.0,
        "status": "ok" | "warning" | "danger",
        "remaining": 78000,
    }
    """
    used = get_session_token_usage(session_id)
    remaining = max(0, CONTEXT_BUDGET - used)
    percent = (used / CONTEXT_BUDGET * 100) if CONTEXT_BUDGET > 0 else 0

    # Determine status
    if percent >= DANGER_THRESHOLD:
        status = "danger"
    elif percent >= WARNING_THRESHOLD:
        status = "warning"
    else:
        status = "ok"

    return {
        "used": used,
        "limit": CONTEXT_BUDGET,
        "percent": round(percent, 1),
        "status": status,
        "remaining": remaining,
    }


def reset_session_budget(session_id: str) -> Dict[str, Any]:
    """
    Reset session budget (call when switching sessions).

    Returns: {"ok": True, "reset_tokens": 50000}
    """
    budget_data = load_session_budget()

    reset_tokens = 0
    if session_id in budget_data:
        reset_tokens = budget_data[session_id].get("total_tokens", 0)
        del budget_data[session_id]
        save_session_budget(budget_data)

    return {
        "ok": True,
        "reset_tokens": reset_tokens,
    }


def cleanup_old_sessions(max_age_hours: int = 24) -> Dict[str, Any]:
    """
    Remove old session budget entries.

    Returns: {"ok": True, "cleaned": 3, "remaining": 5}
    """
    budget_data = load_session_budget()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)

    removed = 0
    remaining = 0

    cleaned_data = {}
    for session_id, data in budget_data.items():
        try:
            updated = datetime.fromisoformat(data.get("updated_at", "").replace("Z", "+00:00"))
            if updated >= cutoff:
                cleaned_data[session_id] = data
                remaining += 1
            else:
                removed += 1
        except Exception:
            # Keep entries that can't be parsed
            cleaned_data[session_id] = data
            remaining += 1

    if removed > 0:
        save_session_budget(cleaned_data)

    return {
        "ok": True,
        "cleaned": removed,
        "remaining": remaining,
    }


def main():
    parser = argparse.ArgumentParser(description="MISO Cost Tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # log command
    log_parser = subparsers.add_parser("log", help="Log cost entry")
    log_parser.add_argument("--model", required=True, help="Model name")
    log_parser.add_argument("--input", type=int, required=True, help="Input tokens")
    log_parser.add_argument("--output", type=int, required=True, help="Output tokens")
    log_parser.add_argument("--mission", required=True, help="Mission ID")

    # report command
    report_parser = subparsers.add_parser("report", help="Generate cost report")
    report_parser.add_argument("--chat-id", required=True, help="Telegram chat ID")

    # session-status command
    session_parser = subparsers.add_parser("session-status", help="Get session budget status")
    session_parser.add_argument("--session-id", required=True, help="Session ID")
    session_parser.add_argument("--chat-id", help="Send to Telegram (optional)")

    # session-reset command
    reset_parser = subparsers.add_parser("session-reset", help="Reset session budget")
    reset_parser.add_argument("--session-id", required=True, help="Session ID")

    # cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Cleanup old sessions")
    cleanup_parser.add_argument(
        "--hours", "-h",
        type=int,
        default=24,
        help="Max age in hours (default: 24)",
    )

    args = parser.parse_args()

    if args.command == "log":
        cost = calculate_cost(args.model, args.input, args.output)
        result = log_cost(args.model, args.input, args.output, args.mission, cost)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "report":
        result = generate_and_send_report(args.chat_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "session-status":
        result = get_budget_status(args.session_id)

        if args.chat_id:
            # Send to Telegram
            status_emoji = {"ok": "✅", "warning": "⚠️", "danger": "🚨"}.get(result["status"], "❓")
            message = (
                f"💾 Session Budget Status\n"
                f"——————————————\n"
                f"Session: {args.session_id}\n"
                f"{status_emoji} Status: {result['status'].upper()}\n"
                f"📊 Used: {result['used']:,} / {result['limit']:,} tokens\n"
                f"📈 {result['percent']:.1f}% used\n"
                f"📉 Remaining: {result['remaining']:,} tokens\n"
                f"——————————————\n"
                f"🌸 powered by miyabi"
            )
            telegram_result = send_message(chat_id=args.chat_id, message=message)
            result["telegram"] = telegram_result

        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "session-reset":
        result = reset_session_budget(args.session_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "cleanup":
        result = cleanup_old_sessions(args.hours)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
