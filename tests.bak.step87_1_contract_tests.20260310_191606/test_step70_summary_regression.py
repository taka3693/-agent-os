#!/usr/bin/env python3
import ast
import copy
from pathlib import Path

SRC = Path("tools/run_agent_os_request.py").read_text(encoding="utf-8")
MOD = ast.parse(SRC)

fn = None
for node in MOD.body:
    if isinstance(node, ast.FunctionDef) and node.name == "format_telegram_batch_summary":
        fn = node
        break

if fn is None:
    raise SystemExit("NG: format_telegram_batch_summary() not found")

ns = {}
code = compile(
    ast.Module(body=[fn], type_ignores=[]),
    filename="tools/run_agent_os_request.py",
    mode="exec",
)
exec(code, ns)
fmt = ns["format_telegram_batch_summary"]

case_validate_ng_continue = {
    "ok": False,
    "mode": "execution",
    "status": "validated_with_errors",
    "validate_only": True,
    "completed_all_steps": True,
    "has_errors": True,
    "stopped_early": False,
    "requested_steps": 3,
    "executed_steps": 3,
    "ok_count": 2,
    "ng_count": 1,
    "first_failed_step_index": 2,
    "first_failed_step_id": "danger",
    "first_failed_mode": "policy",
    "first_failed_reason": "delete_disabled",
    "step_results": [
        {"ok": True, "step_id": "scan", "step_label": "scan", "continue_on_error": False},
        {"ok": False, "step_id": "danger", "step_label": "danger", "continue_on_error": True},
        {"ok": True, "step_id": "read", "step_label": "read", "continue_on_error": False},
    ],
}

case_exec_ok = {
    "ok": True,
    "mode": "execution",
    "status": "completed",
    "validate_only": False,
    "completed_all_steps": True,
    "has_errors": False,
    "stopped_early": False,
    "requested_steps": 2,
    "executed_steps": 2,
    "ok_count": 2,
    "ng_count": 0,
    "step_results": [
        {"ok": True},
        {"ok": True},
    ],
}

case_failfast = {
    "ok": False,
    "mode": "execution",
    "status": "failed",
    "validate_only": False,
    "completed_all_steps": False,
    "has_errors": True,
    "stopped_early": True,
    "requested_steps": 3,
    "executed_steps": 2,
    "ok_count": 1,
    "ng_count": 1,
    "first_failed_step_index": 2,
    "first_failed_step_id": None,
    "first_failed_mode": "execution",
    "first_failed_reason": "unsupported_command",
    "step_results": [
        {"ok": True, "continue_on_error": False},
        {"ok": False, "continue_on_error": False},
    ],
}

case_id_fallback = {
    "ok": False,
    "mode": "execution",
    "status": "validated_with_errors",
    "validate_only": True,
    "completed_all_steps": True,
    "has_errors": True,
    "stopped_early": False,
    "requested_steps": 2,
    "executed_steps": 2,
    "ok_count": 1,
    "ng_count": 1,
    "first_failed_step_index": 2,
    "first_failed_step_id": "danger",
    "first_failed_mode": "policy",
    "first_failed_reason": "delete_disabled",
    "step_results": [
        {"ok": True},
        {"ok": False},
    ],
}

out1 = fmt(copy.deepcopy(case_validate_ng_continue))
out2 = fmt(copy.deepcopy(case_exec_ok))
out3 = fmt(copy.deepcopy(case_failfast))
out4 = fmt(copy.deepcopy(case_id_fallback))

print("=== case_validate_ng_continue ===")
print(out1)
print("=== case_exec_ok ===")
print(out2)
print("=== case_failfast ===")
print(out3)
print("=== case_id_fallback ===")
print(out4)

assert out1 == (
    "検証: NGあり (3件中3件 | OK 2件 / NG 1件)\n"
    "最初の失敗(1始まり): step=danger / step#2 / 種別=ポリシー / 理由=削除コマンドは未対応\n"
    "補足: NG後も継続"
)

assert out2 == (
    "実行: 完了 (2件中2件 | OK 2件 / NG 0件)\n"
    "補足: エラーなし"
)

assert out3 == (
    "実行: 失敗 (3件中2件 | OK 1件 / NG 1件)\n"
    "最初の失敗(1始まり): step#2 / 種別=実行 / 理由=未対応コマンド\n"
    "補足: 途中停止 / 全step未完了"
)

assert out4 == (
    "検証: NGあり (2件中2件 | OK 1件 / NG 1件)\n"
    "最初の失敗(1始まり): id=danger / step#2 / 種別=ポリシー / 理由=削除コマンドは未対応"
)

print("PASS: Step70 summary regression OK")
