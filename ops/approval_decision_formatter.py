from __future__ import annotations

from typing import Any, Dict, List


def format_approval_decisions(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "承認決定履歴: 0件"

    lines = [f"承認決定履歴: {len(rows)}件"]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"{i}. {row.get('decision', '-')}"
            f" | action={row.get('action', '-')}"
            f" | fp={row.get('fingerprint', '-')}"
        )
    return "\n".join(lines)
