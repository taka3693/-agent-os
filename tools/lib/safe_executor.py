from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from tools.lib.policy import DEFAULT_POLICY, PolicyDecision, check_action_allowed


ActionHandler = Callable[[str, Dict[str, Any]], Dict[str, Any]]


def safe_execute_action(
    *,
    action: str | None,
    result: Dict[str, Any],
    handler: ActionHandler,
    policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    policy = policy or DEFAULT_POLICY
    decision: PolicyDecision = check_action_allowed(action, result, policy)

    result["policy_decision"] = {
        "ok": decision.ok,
        "reason": decision.reason,
        "code": decision.code,
        "action": action,
    }

    if not decision.ok:
        result["executed_action"] = None
        result["execution_log"] = f"blocked: {decision.reason}"
        return result

    execution = handler(str(action), result)
    if not isinstance(execution, dict):
        execution = {"execution_log": str(execution)}

    for k, v in execution.items():
        result[k] = v

    return result


def ensure_output_path_allowed(path: str, policy: Dict[str, Any] | None = None) -> None:
    policy = policy or DEFAULT_POLICY
    prefixes = tuple(policy.get("allowed_output_prefixes") or ("outputs/",))

    p = Path(path).expanduser()
    try:
        resolved = p.resolve(strict=False)
    except Exception:
        resolved = p

    normalized = str(resolved).replace("\\", "/")
    cwd_normalized = str(Path.cwd().resolve()).replace("\\", "/")

    allowed = False
    for prefix in prefixes:
        prefix_norm = str(prefix).replace("\\", "/").lstrip("./")
        rel_candidate = f"/{prefix_norm.rstrip('/')}/"
        abs_candidate = f"{cwd_normalized}/{prefix_norm.rstrip('/')}/"

        if rel_candidate in normalized or normalized.startswith(abs_candidate):
            allowed = True
            break

    if not allowed:
        raise ValueError(f"output path denied by policy: {path}")


def write_text_under_policy(path: Path, text: str, *, policy: Dict[str, Any] | None = None) -> None:
    ensure_output_path_allowed(str(path), policy)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
