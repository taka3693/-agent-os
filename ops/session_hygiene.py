from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set


def select_archive_candidates(
    session_sizes: Optional[Iterable[Dict[str, Any]]],
    *,
    warn_bytes: int = 5_000_000,
    active_basenames: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    active: Set[str] = {
        str(x).strip()
        for x in (active_basenames or [])
        if str(x).strip()
    }

    out: List[Dict[str, Any]] = []

    for row in session_sizes or []:
        basename = str(row.get("basename") or "").strip()
        if not basename:
            continue

        try:
            size_bytes = int(row.get("bytes", 0))
        except (TypeError, ValueError):
            size_bytes = 0

        if size_bytes < 0:
            size_bytes = 0

        if basename in active:
            continue

        if size_bytes >= warn_bytes:
            out.append(
                {
                    "basename": basename,
                    "bytes": size_bytes,
                    "reason": "oversize_inactive_session",
                }
            )

    out.sort(key=lambda x: int(x["bytes"]), reverse=True)
    return out
