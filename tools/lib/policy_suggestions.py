from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import json

from tools.lib.failure_insights import load_failure_insights


def _resolve_base_dir(base_dir):
    if base_dir:
        return Path(base_dir)

    import tools.run_agent_os_request as mod
    return Path(mod.__file__).resolve().parents[1]


def _suggestion_store_path(base_dir=None) -> Path:
    root = _resolve_base_dir(base_dir)
    p = root / "state" / "policy_suggestions" / "policy_suggestions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def build_policy_suggestions(*, base_dir=None) -> List[Dict[str, Any]]:
    insights = load_failure_insights(base_dir=base_dir)
    if not isinstance(insights, dict):
        return []

    suggestions: List[Dict[str, Any]] = []
    risk_summary = insights.get("risk_summary", {})
    if not isinstance(risk_summary, dict):
        risk_summary = {}

    top_failure_types = insights.get("top_failure_types", [])
    if not isinstance(top_failure_types, list):
        top_failure_types = []

    counts = {}
    for item in top_failure_types:
        if isinstance(item, dict):
            ftype = str(item.get("failure_type") or "")
            count = int(item.get("count", 0))
            if ftype:
                counts[ftype] = count

    ts = datetime.now(timezone.utc).isoformat()

    for ftype, count in counts.items():
        risks = risk_summary.get(ftype, {})
        if not isinstance(risks, dict):
            risks = {}

        high = int(risks.get("high", 0))
        mid = int(risks.get("mid", 0))
        low = int(risks.get("low", 0))

        if ftype == "execution_failure" and high >= 3:
            suggestions.append({
                "ts": ts,
                "kind": "policy_suggestion",
                "failure_type": ftype,
                "current_bias": "retry_or_skip",
                "suggested_action": "manual_review_bias",
                "reason": "high_risk_execution_failures_accumulated",
                "evidence": {
                    "count": count,
                    "high_risk": high,
                    "mid_risk": mid,
                    "low_risk": low,
                },
                "status": "pending_review",
            })

        elif ftype == "state_failure" and count >= 5 and high >= 3:
            suggestions.append({
                "ts": ts,
                "kind": "policy_suggestion",
                "failure_type": ftype,
                "current_bias": "auto_heal",
                "suggested_action": "tighten_auto_heal_scope",
                "reason": "repeated_high_risk_state_failures",
                "evidence": {
                    "count": count,
                    "high_risk": high,
                    "mid_risk": mid,
                    "low_risk": low,
                },
                "status": "pending_review",
            })

        elif ftype == "rate_limit_failure" and count >= 5 and low >= 5:
            suggestions.append({
                "ts": ts,
                "kind": "policy_suggestion",
                "failure_type": ftype,
                "current_bias": "retry_or_skip",
                "suggested_action": "backoff_retry_bias",
                "reason": "repeated_low_risk_rate_limits",
                "evidence": {
                    "count": count,
                    "high_risk": high,
                    "mid_risk": mid,
                    "low_risk": low,
                },
                "status": "pending_review",
            })

    return suggestions


def append_policy_suggestions(*, base_dir=None) -> Dict[str, Any]:
    suggestions = build_policy_suggestions(base_dir=base_dir)
    path = _suggestion_store_path(base_dir=base_dir)

    with path.open("a", encoding="utf-8") as f:
        for item in suggestions:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return {
        "ok": True,
        "path": str(path),
        "count": len(suggestions),
    }
