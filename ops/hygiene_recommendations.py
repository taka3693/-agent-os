from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def build_hygiene_recommended_actions(
    archive_candidates: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for row in archive_candidates or []:
        basename = str(row.get("basename") or "").strip()
        reason = str(row.get("reason") or "").strip()

        if not basename:
            continue

        out.append(
            {
                "action": "session.archive",
                "args": {"target_basename": basename},
                "reason": reason or "session_hygiene_candidate",
                "source": "session_hygiene",
            }
        )

    return out
