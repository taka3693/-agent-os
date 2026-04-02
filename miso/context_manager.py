"""MISO context manager — Monitor and manage context health"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from miso.cost_tracker import get_budget_status, WARNING_THRESHOLD, DANGER_THRESHOLD
from miso.dashboard import load_all_missions
from miso.telegram_hooks import send_message


def is_safe_to_switch() -> Dict[str, Any]:
    """
    Check if it's safe to switch sessions.

    Safe if:
    - No running missions (RUNNING/PARTIAL/RETRYING)
    - No awaiting approval missions (AWAITING_APPROVAL)

    Returns: {"safe": True/False, "running": 0, "awaiting": 0}
    """
    missions = load_all_missions()

    running_states = ("RUNNING", "PARTIAL", "RETRYING")
    running = sum(1 for m in missions if m.get("state") in running_states)
    awaiting = sum(1 for m in missions if m.get("state") == "AWAITING_APPROVAL")

    safe = (running == 0) and (awaiting == 0)

    return {
        "safe": safe,
        "running": running,
        "awaiting": awaiting,
    }


def check_context_health(
    session_id: str,
    chat_id: str = "",
) -> Dict[str, Any]:
    """
    Check overall context health.

    Returns: {
        "budget": {...},
        "safe_to_switch": {...},
        "overall_status": "ok" | "warning" | "danger",
        "recommendation": "...",
    }
    """
    # Check budget status
    budget = get_budget_status(session_id)

    # Check if safe to switch
    switch_status = is_safe_to_switch()

    # Determine overall status
    if budget["percent"] >= DANGER_THRESHOLD:
        overall_status = "danger"
        recommendation = "緊急: セッションを切り替えてください"
    elif budget["percent"] >= WARNING_THRESHOLD or not switch_status["safe"]:
        overall_status = "warning"
        if not switch_status["safe"]:
            recommendation = "警告: 実行中ミッションが完了してから切替してください"
        else:
            recommendation = "警告: トークン使用量が80%を超えています"
    else:
        overall_status = "ok"
        recommendation = "健全: コンテキストは正常です"

    return {
        "budget": budget,
        "safe_to_switch": switch_status,
        "overall_status": overall_status,
        "recommendation": recommendation,
    }


def format_context_warning(
    budget: Dict[str, Any],
    switch_status: Dict[str, Any],
    overall_status: str,
) -> str:
    """Format context warning message"""
    status_emoji = {"ok": "✅", "warning": "⚠️", "danger": "🚨"}.get(overall_status, "❓")

    lines = [
        f"{status_emoji} コンテキス{'ト警告' if overall_status != 'ok' else 'ト状況'}",
        "——————————————",
        f"📊 トークン使用: {budget['used']:,} / {budget['limit']:,} ({budget['percent']:.1f}%)",
        f"🔥 実行中ミッション: {switch_status['running']}件",
        f"👀 承認待ち: {switch_status['awaiting']}件",
        "",
    ]

    if switch_status["safe"]:
        lines.append("✅ セッション切替可能です")
    else:
        lines.append("❌ セッション切替不可（実行中ミッションがあります）")

    lines.append("")
    lines.append("——————————————")
    lines.append("🌸 powered by miyabi")

    return "\n".join(lines)


def send_context_warning(
    session_id: str,
    chat_id: str,
) -> Dict[str, Any]:
    """
    Check context health and send warning to Telegram if needed.

    Only sends message if status is warning or danger.
    """
    health = check_context_health(session_id, chat_id)

    # Only send if warning or danger
    if health["overall_status"] == "ok":
        return {
            "ok": True,
            "sent": False,
            "reason": "status is ok",
            "health": health,
        }

    # Format message
    message = format_context_warning(
        health["budget"],
        health["safe_to_switch"],
        health["overall_status"],
    )

    # Add inline buttons if safe to switch
    buttons = None
    if health["safe_to_switch"]["safe"]:
        buttons = [
            [
                {"text": "🔄 新セッション作成", "callback_data": "ctx:new_session"},
                {"text": "⏸️ 後で", "callback_data": "ctx:dismiss"},
            ]
        ]

    # Send message
    result = send_message(chat_id=chat_id, message=message, buttons=buttons)

    return {
        "ok": result.get("ok", False),
        "sent": result.get("ok", False),
        "message_id": result.get("message_id"),
        "health": health,
    }


def handle_context_callback(
    callback_data: str,
    chat_id: str,
) -> Dict[str, Any]:
    """
    Handle context inline button callback.

    callback_data format: "ctx:new_session" or "ctx:dismiss"
    """
    if callback_data == "ctx:new_session":
        # TODO: Implement new session creation
        # For now, just send a message
        message = (
            "🔄 新しいセッションを作成します...\n"
            "（この機能は未実装です）"
        )
        result = send_message(chat_id=chat_id, message=message)
        return {
            "ok": True,
            "action": "new_session",
            "result": result,
        }
    elif callback_data == "ctx:dismiss":
        # Send confirmation
        message = "⏸️ 確認しました。後で再通知します。"
        result = send_message(chat_id=chat_id, message=message)
        return {
            "ok": True,
            "action": "dismiss",
            "result": result,
        }
    else:
        return {
            "ok": False,
            "error": f"Unknown callback: {callback_data}",
        }


def main():
    parser = argparse.ArgumentParser(description="MISO Context Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # check command
    check_parser = subparsers.add_parser("check", help="Check context health")
    check_parser.add_argument("--session-id", required=True, help="Session ID")
    check_parser.add_argument("--chat-id", help="Send warning to Telegram (optional)")

    # status command
    status_parser = subparsers.add_parser("status", help="Get context status")
    status_parser.add_argument("--session-id", required=True, help="Session ID")

    # safe command
    safe_parser = subparsers.add_parser("safe", help="Check if safe to switch")

    # handle-callback command
    callback_parser = subparsers.add_parser("handle-callback", help="Handle callback")
    callback_parser.add_argument("--callback-data", required=True, help="Callback data")
    callback_parser.add_argument("--chat-id", required=True, help="Chat ID")

    args = parser.parse_args()

    if args.command == "check":
        result = send_context_warning(args.session_id, args.chat_id or "")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "status":
        health = check_context_health(args.session_id)
        print(json.dumps(health, ensure_ascii=False, indent=2))
    elif args.command == "safe":
        result = is_safe_to_switch()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "handle-callback":
        result = handle_context_callback(args.callback_data, args.chat_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
