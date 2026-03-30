from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestContext:
    source: str
    raw_text: str
    chat_id: str | None = None
    validate_only: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandEnvelope:
    kind: str
    raw_command: str
    query: str = ""
    validate_only: bool = False


@dataclass
class ResultEnvelope:
    ok: bool
    mode: str
    status: str
    reply_text: str
    telegram_reply_text: str
    telegram_send: dict[str, Any] | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = dict(self.payload)
        out.update(
            {
                "ok": self.ok,
                "mode": self.mode,
                "status": self.status,
                "reply_text": self.reply_text,
                "telegram_reply_text": self.telegram_reply_text,
                "telegram_send": self.telegram_send,
            }
        )
        return out
