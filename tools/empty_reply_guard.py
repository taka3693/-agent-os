from __future__ import annotations

def ensure_non_empty_reply(text: object) -> str:
    if text is None:
        return "internal: empty response prevented"
    s = str(text).strip()
    if not s:
        return "internal: empty response prevented"
    return s
