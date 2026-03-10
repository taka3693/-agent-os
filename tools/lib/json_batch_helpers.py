from __future__ import annotations

from typing import Any, Dict, List


def summarize_json_batch_result(result: Dict[str, Any]) -> Dict[str, Any]:
    step_results = result.get("step_results")
    if not isinstance(step_results, list):
        step_results = result.get("results")
    if not isinstance(step_results, list):
        step_results = []

    operation_count = int(result.get("operation_count", len(step_results)) or 0)
    ok_count = int(result.get("ok_count", 0) or 0)
    ng_count = int(result.get("ng_count", 0) or 0)
    first_failed_step_index = result.get("first_failed_step_index")
    first_failed_step_id = result.get("first_failed_step_id")
    first_failed_mode = result.get("first_failed_mode")
    first_failed_reason = result.get("first_failed_reason")
    validate_only = bool(result.get("validate_only", False))
    stopped_early = bool(result.get("stopped_early", False))
    completed_all_steps = bool(result.get("completed_all_steps", False))
    has_errors = bool(result.get("has_errors", False))

    return {
        "step_results": step_results,
        "operation_count": operation_count,
        "ok_count": ok_count,
        "ng_count": ng_count,
        "first_failed_step_index": first_failed_step_index,
        "first_failed_step_id": first_failed_step_id,
        "first_failed_mode": first_failed_mode,
        "first_failed_reason": first_failed_reason,
        "validate_only": validate_only,
        "stopped_early": stopped_early,
        "completed_all_steps": completed_all_steps,
        "has_errors": has_errors,
    }


def build_json_batch_reply_text(result: Dict[str, Any]) -> str:
    s = summarize_json_batch_result(result)
    step_results = s["step_results"]

    lines: List[str] = []
    if s["validate_only"]:
        if s["has_errors"]:
            lines.append("json 検証完了（一部NGあり）")
        else:
            lines.append("json 検証完了")
    else:
        if s["has_errors"]:
            lines.append("json 実行完了（一部失敗あり）")
        else:
            lines.append("json 実行完了")

    lines.append(f"完了ステップ数: {s['operation_count']}")
    lines.append(f"成功: {s['ok_count']}")
    lines.append(f"失敗: {s['ng_count']}")

    if s["first_failed_step_index"]:
        lines.append(
            f"最初の失敗: step {s['first_failed_step_index']} "
            f"({s['first_failed_step_id']}) / mode={s['first_failed_mode']} / reason={s['first_failed_reason']}"
        )

    for idx, item in enumerate(step_results, start=1):
        if not isinstance(item, dict):
            continue
        step_id = item.get("step_id") or item.get("step_label") or f"step-{idx}"
        cmd = item.get("command") or ""
        mode = item.get("mode")
        ok = item.get("ok")
        continue_on_error = item.get("continue_on_error")
        reply = str(item.get("reply_text") or "").strip()

        lines.append("")
        lines.append(f"[step {idx}: {step_id}] {cmd}")
        lines.append(f"mode: {mode}")
        lines.append(f"ok: {ok}")
        lines.append(f"continue_on_error: {continue_on_error}")
        if reply:
            lines.append(reply)

        if idx != len(step_results):
            lines.append("")
            lines.append("---")

    return "\n".join(lines).strip()


def build_json_batch_telegram_text(result: Dict[str, Any]) -> str:
    s = summarize_json_batch_result(result)

    operation_count = s["operation_count"]
    ok_count = s["ok_count"]
    ng_count = s["ng_count"]

    if s["validate_only"]:
        head = (
            f"検証: NGあり ({operation_count}件中{operation_count}件 | OK {ok_count}件 / NG {ng_count}件)"
            if s["has_errors"]
            else f"検証: OK ({operation_count}件中{operation_count}件 | OK {ok_count}件 / NG {ng_count}件)"
        )
    else:
        if s["has_errors"]:
            head = f"実行: 失敗 ({operation_count}件中{operation_count - int(bool(s['stopped_early']))}件 | OK {ok_count}件 / NG {ng_count}件)"
        else:
            head = f"実行: 完了 ({operation_count}件中{operation_count}件 | OK {ok_count}件 / NG {ng_count}件)"

    lines = [head]

    if s["first_failed_step_index"]:
        mode_map = {
            "policy": "ポリシー",
            "execution": "実行",
            "validation": "検証",
        }
        reason_map = {
            "delete_disabled": "削除コマンドは未対応",
            "unsupported_command": "未対応コマンド",
        }
        failed_mode = mode_map.get(s["first_failed_mode"], s["first_failed_mode"])
        failed_reason = reason_map.get(s["first_failed_reason"], s["first_failed_reason"])
        lines.append(
            f"最初の失敗(1始まり): step={s['first_failed_step_id']} / "
            f"step#{s['first_failed_step_index']} / 種別={failed_mode} / 理由={failed_reason}"
        )

    if s["validate_only"] and s["has_errors"] and not s["stopped_early"]:
        lines.append("補足: NG後も継続")
    elif s["stopped_early"]:
        lines.append("補足: 途中停止 / 全step未完了")
    else:
        lines.append("補足: エラーなし")

    return "\n".join(lines).strip()
