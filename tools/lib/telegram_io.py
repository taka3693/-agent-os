from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict


def load_openclaw_config(config_path: Path) -> Dict[str, Any]:
    return json.loads(config_path.read_text(encoding="utf-8"))


def extract_bot_token(cfg: Dict[str, Any]) -> str:
    candidates = [
        (((cfg.get("channels") or {}).get("telegram") or {}).get("botToken")),
        (((cfg.get("channels") or {}).get("telegram") or {}).get("token")),
    ]
    for token in candidates:
        if isinstance(token, str) and token.strip():
            return token.strip()
    raise RuntimeError("telegram bot token not found in ~/.openclaw/openclaw.json")


def send_telegram_message(config_path: Path, chat_id: str | int, text: str) -> Dict[str, Any]:
    cfg = load_openclaw_config(config_path)
    token = extract_bot_token(cfg)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": str(chat_id),
        "text": text,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)
