from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from runner.parse_approval_command import parse_approval_command
from runner.run_approval_ops import run_approval_ops


def run_approval_command(
    *,
    state_root: Path,
    command: str,
    timestamp: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    parsed = parse_approval_command(command)
    if not parsed["ok"]:
        status = parsed["status"]
        return {
            "ok": False,
            "status": status,
            "command": command,
            "reply_text": f"approval: {status} ({command})",
        }

    if parsed["mode"] == "status":
        return run_approval_ops(
            state_root=state_root,
            mode="status",
        )

    return run_approval_ops(
        state_root=state_root,
        mode="apply",
        timestamp=timestamp,
        fingerprint=parsed["fingerprint"],
        decision=parsed["decision"],
        reason=reason,
    )
