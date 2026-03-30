"""Telegram message/reaction operations for MISO"""

from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

# OpenClaw message tool path (use CLI for portability)
OPENCLAW_BIN = "openclaw"


def _run_openclaw_message(action: str, **kwargs) -> Dict[str, Any]:
    """Run openclaw message command via subprocess"""
    # Build command
    cmd = [OPENCLAW_BIN, "message", action]
    
    for key, value in kwargs.items():
        if value is not None:
            # Convert snake_case to kebab-case for CLI
            cli_key = f"--{key.replace('_', '-')}"
            if isinstance(value, bool):
                if value:
                    cmd.append(cli_key)
            elif isinstance(value, list):
                for item in value:
                    cmd.extend([cli_key, str(item)])
            else:
                cmd.extend([cli_key, str(value)])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"ok": True, "stdout": result.stdout}
        else:
            return {"ok": False, "error": result.stderr or result.stdout}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_message(
    chat_id: str,
    message: str,
    buttons: Optional[List[List[Dict[str, str]]]] = None,
    silent: bool = True,
) -> Dict[str, Any]:
    """
    Send a new message to Telegram.
    
    Returns: {"ok": True, "message_id": "..."} or {"ok": False, "error": "..."}
    """
    kwargs = {
        "target": chat_id,
        "message": message,
        "silent": silent,
    }
    if buttons:
        kwargs["buttons"] = json.dumps(buttons)
    
    return _run_openclaw_message("send", **kwargs)


def edit_message(
    chat_id: str,
    message_id: str,
    message: str,
    buttons: Optional[List[List[Dict[str, str]]]] = None,
) -> Dict[str, Any]:
    """
    Edit an existing message.
    
    Returns: {"ok": True} or {"ok": False, "error": "..."}
    """
    kwargs = {
        "target": chat_id,
        "message_id": message_id,
        "message": message,
    }
    if buttons:
        kwargs["buttons"] = json.dumps(buttons)
    
    return _run_openclaw_message("edit", **kwargs)


def react_to_message(
    chat_id: str,
    message_id: str,
    emoji: str,
) -> Dict[str, Any]:
    """
    Add reaction to a message.
    
    Returns: {"ok": True} or {"ok": False, "error": "..."}
    """
    return _run_openclaw_message(
        "react",
        target=chat_id,
        message_id=message_id,
        emoji=emoji,
    )


def make_approval_buttons(task_id: str) -> List[List[Dict[str, str]]]:
    """Generate inline buttons for approval gate"""
    return [
        [
            {"text": "✅ 承認", "callback_data": f"miso:approve:{task_id}"},
            {"text": "❌ 却下", "callback_data": f"miso:reject:{task_id}"},
        ]
    ]


def make_retry_buttons(task_id: str) -> List[List[Dict[str, str]]]:
    """Generate inline buttons for error recovery"""
    return [
        [
            {"text": "🔄 再試行", "callback_data": f"miso:retry:{task_id}"},
            {"text": "⏭ スキップ", "callback_data": f"miso:skip:{task_id}"},
        ],
        [
            {"text": "❌ 中止", "callback_data": f"miso:abort:{task_id}"},
        ],
    ]
