from __future__ import annotations

from typing import Any, Dict


def parse_approval_command(command: str) -> Dict[str, Any]:
    text = command.strip()
    if not text:
        return {"ok": False, "status": "empty_command"}

    parts = text.split()
    if len(parts) < 2 or parts[0] != "approval":
        return {"ok": False, "status": "invalid_command"}

    sub = parts[1]
    if sub == "status" and len(parts) == 2:
        return {"ok": True, "mode": "status"}

    if sub == "apply" and len(parts) >= 4:
        return {
            "ok": True,
            "mode": "apply",
            "fingerprint": parts[2],
            "decision": parts[3],
        }

    return {"ok": False, "status": "invalid_command"}
