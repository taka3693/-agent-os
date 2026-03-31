from __future__ import annotations

from typing import Any, Dict, List


def format_pending_approvals(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "承認待ち: 0件"

    lines = [f"承認待ち: {len(rows)}件"]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"{i}. {row.get('action', '-')}"
            f" | fp={row.get('fingerprint', '-')}"
            f" | source={row.get('source', '-')}"
        )
    return "\n".join(lines)
