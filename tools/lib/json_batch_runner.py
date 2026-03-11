from __future__ import annotations

from typing import Any, Callable, Dict

from json_batch_parser import parse_json_batch_request
from json_batch_helpers import (
    build_json_batch_reply_text,
    build_json_batch_telegram_text,
)


def run_json_batch_request(
    text: str,
    *,
    command_handler: Callable[[str], Dict[str, Any]],
) -> Dict[str, Any] | None:
    matched, parsed, error = parse_json_batch_request(text)
    if not matched:
        return None
    if error is not None:
        return error

    obj = parsed or {}
    steps = obj.get("steps") or []
    validate_only = bool(obj.get("validate_only", False) or obj.get("dry_run", False))

    step_results = []
    first_failed_step_index = None
    first_failed_step_id = None
    first_failed_mode = None
    first_failed_reason = None
    stopped_early = False
    ok_count = 0
    ng_count = 0

    for i, step in enumerate(steps, start=1):
        continue_on_error = False
        step_id = None
        step_label = None
        command = None

        if isinstance(step, str):
            command = step.strip()
        elif isinstance(step, dict):
            command = str(step.get("command") or "").strip()
            continue_on_error = bool(step.get("continue_on_error", False))
            step_id = step.get("id")
            step_label = step.get("label") or step_id
        else:
            command = ""

        if not command:
            result = {
                "ok": False,
                "mode": "execution",
                "status": "failed",
                "error": "empty_command",
                "command": command,
            }
        else:
            cmd = command
            if validate_only:
                if cmd.lower().startswith("aos validate "):
                    pass
                elif cmd.lower().startswith("aos "):
                    cmd = "aos validate " + cmd
                else:
                    cmd = "aos validate " + cmd

            result = command_handler(cmd)

        if not isinstance(result, dict):
            result = {
                "ok": False,
                "mode": "execution",
                "status": "failed",
                "error": "invalid_step_result",
                "command": command,
            }

        result = dict(result)
        result["command"] = command
        result["step_id"] = step_id
        result["step_label"] = step_label or step_id or f"step{i}"
        result["continue_on_error"] = continue_on_error
        step_results.append(result)

        if bool(result.get("ok")):
            ok_count += 1
        else:
            ng_count += 1
            if first_failed_step_index is None:
                first_failed_step_index = i
                first_failed_step_id = result.get("step_id")
                first_failed_mode = result.get("mode")
                first_failed_reason = (
                    result.get("reason")
                    or result.get("error")
                    or result.get("status")
                    or "unknown"
                )
            if not continue_on_error:
                stopped_early = True
                break

    requested_steps = len(steps)
    executed_steps = len(step_results)
    has_errors = ng_count > 0
    completed_all_steps = (executed_steps == requested_steps) and (not stopped_early)

    if validate_only and has_errors:
        status = "validated_with_errors"
    elif validate_only:
        status = "validated"
    elif has_errors and stopped_early:
        status = "failed"
    elif has_errors:
        status = "completed_with_errors"
    else:
        status = "completed"

    out = {
        "ok": not has_errors,
        "mode": "execution",
        "status": status,
        "is_json_batch": True,
        "validate_only": validate_only,
        "completed_all_steps": completed_all_steps,
        "has_errors": has_errors,
        "stopped_early": stopped_early,
        "requested_steps": requested_steps,
        "executed_steps": executed_steps,
        "operation_count": executed_steps,
        "ok_count": ok_count,
        "ng_count": ng_count,
        "first_failed_step_index": first_failed_step_index,
        "first_failed_step_id": first_failed_step_id,
        "first_failed_mode": first_failed_mode,
        "first_failed_reason": first_failed_reason,
        "step_results": step_results,
        "results": step_results,
        "telegram_send": None,
    }

    out["reply_text"] = build_json_batch_reply_text(out)
    out["telegram_reply_text"] = build_json_batch_telegram_text(out)
    return out
