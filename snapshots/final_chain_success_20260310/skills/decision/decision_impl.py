#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Dict


def run_decision(query: str) -> Dict[str, Any]:
    q = (query or "").strip()
    if not q:
        raise RuntimeError("decision query is empty")

    return {
        "summary": f"decision dry-run completed for: {q}",
        "status": "ok",
        "decision": "proceed",
        "reasoning": [
            "query was received",
            "decision skill stub is active",
            "real planning policy is not implemented yet"
        ],
        "next_skill": "execution"
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run_decision("sample decision task"), ensure_ascii=False, indent=2))
