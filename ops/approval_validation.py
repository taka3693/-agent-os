from __future__ import annotations

from typing import Any, Dict

VALID_DECISIONS = {"approved", "rejected"}


def validate_approval_decision_input(*, fingerprint: str, decision: str) -> Dict[str, Any]:
    if not fingerprint:
        return {"ok": False, "status": "invalid_fingerprint"}

    if decision not in VALID_DECISIONS:
        return {"ok": False, "status": "invalid_decision", "decision": decision}

    return {"ok": True}
