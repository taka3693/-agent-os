"""
Agent-OS Telegram Handler - 契約完愖準拚版
"""

from typing import Any, Dict, Optional


def telegram_send(
    chat_id: str,
    text: str,
    parse_mode: Optional[str] = None,
) -> Dict[str, Any]:
    if not chat_id:
        raise ValueError("chat_id is required")
    
    if not text:
        raise ValueError("text is required")

    result: Dict[str, Any] = {
        "ok": True,
        "chat_id": chat_id,
        "text": text,
    }
    
    if parse_mode:
        result["parse_mode"] = parse_mode
    
    return result


def extract_chat_id(update: Dict[str, Any]) -> str:
    if "message" in update:
        return str(update["message"]["chat"]["id"])
    elif "callback_query" in update:
        return str(update["callback_query"]["message"]["chat"]["id"])
    elif "edited_message" in update:
        return str(update["edited_message"]["chat"]["id"])
    else:
        raise KeyError("chat_id not found in update")


__all__ = [
    "telegram_send",
    "extract_chat_id",
]
