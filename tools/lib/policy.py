from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable


@dataclass(frozen=True)
class PolicyDecision:
    ok: bool
    reason: str = ""
    code: str = "ok"


DEFAULT_POLICY: Dict[str, Any] = {
    "allow_actions": {"deploy", "improve", "monitor"},
    "deploy_min_score": 70,
    "max_improve_steps": 2,
    "allow_external_send": False,
    "allow_real_execution": False,
    "allowed_output_prefixes": ("outputs/",),
    "deploy_rate_limit_count": 1,
    "deploy_rate_limit_window_seconds": 60,
}


def _get_score(result: Dict[str, Any]) -> int | None:
    summary = result.get("chain_summary")
    if isinstance(summary, dict):
        final_result = summary.get("final_result")
        if isinstance(final_result, dict):
            payload = final_result.get("result")
            if isinstance(payload, dict) and isinstance(payload.get("score"), int):
                return payload["score"]

    for item in reversed(result.get("chain_results") or []):
        if isinstance(item, dict):
            payload = item.get("result")
            if isinstance(payload, dict) and isinstance(payload.get("score"), int):
                return payload["score"]
    return None


def _count_skill(result: Dict[str, Any], skill_name: str) -> int:
    n = 0
    for item in result.get("chain_results") or []:
        if isinstance(item, dict) and item.get("skill") == skill_name:
            n += 1
    return n


def check_action_allowed(action: str | None, result: Dict[str, Any], policy: Dict[str, Any] | None = None) -> PolicyDecision:
    policy = policy or DEFAULT_POLICY
    action = str(action or "").strip()

    if not action:
        return PolicyDecision(False, "missing action", "missing_action")

    if action not in set(policy.get("allow_actions") or []):
        return PolicyDecision(False, f"action not allowed: {action}", "action_denied")

    if action == "deploy":
        score = _get_score(result)
        min_score = int(policy.get("deploy_min_score", 70))
        if score is None:
            return PolicyDecision(False, "deploy denied: score missing", "deploy_score_missing")
        if score < min_score:
            return PolicyDecision(False, f"deploy denied: score {score} < {min_score}", "deploy_score_low")

    if action == "improve":
        max_improve_steps = int(policy.get("max_improve_steps", 2))
        improve_count = _count_skill(result, "improve")
        if improve_count > max_improve_steps:
            return PolicyDecision(False, f"improve denied: improve_count {improve_count} > {max_improve_steps}", "improve_limit")

    return PolicyDecision(True, "allowed", "ok")
