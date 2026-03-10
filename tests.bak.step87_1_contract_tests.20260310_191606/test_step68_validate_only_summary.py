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

sample_validate_ok = {
    "ok": True,
    "mode": "execution",
    "status": "validated",
    "validate_only": True,
    "completed_all_steps": True,
    "has_errors": False,
    "stopped_early": False,
    "requested_steps": 2,
    "executed_steps": 2,
    "ok_count": 2,
    "ng_count": 0,
    "step_results": [
        {"ok": True, "step_label": "scan"},
        {"ok": True, "step_label": "read"},
    ],
}

sample_validate_ng = {
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
        {"ok": True, "step_label": "scan", "continue_on_error": False},
        {"ok": False, "step_label": "danger", "continue_on_error": True},
        {"ok": True, "step_label": "read", "continue_on_error": False},
    ],
}

sample_exec_ok = {
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

out_validate_ok = fmt(copy.deepcopy(sample_validate_ok))
out_validate_ng = fmt(copy.deepcopy(sample_validate_ng))
out_exec_ok = fmt(copy.deepcopy(sample_exec_ok))

print("=== validate_only OK ===")
print(out_validate_ok)
print("=== validate_only NG ===")
print(out_validate_ng)
print("=== execution OK ===")
print(out_exec_ok)

assert out_validate_ok.startswith("検証: OK"), "validate_only OK must start with '検証: OK'"
assert out_validate_ng.startswith("検証: NGあり"), "validate_only NG must start with '検証: NGあり'"
assert "実行:" not in out_validate_ok, "validate_only OK summary must not contain '実行:'"
assert "実行:" not in out_validate_ng, "validate_only NG summary must not contain '実行:'"
assert "実行は未実施" not in out_validate_ok, "batch summary should not leak step reply text"
assert "実行は未実施" not in out_validate_ng, "batch summary should not leak step reply text"

assert out_exec_ok.startswith("実行: 完了"), "execution summary must start with '実行: 完了'"
assert "検証:" not in out_exec_ok, "execution summary must not contain '検証:'"

print("PASS: Step68 regression checks OK")
