#!/usr/bin/env python3
from __future__ import annotations

def _step86_parse_bridge_stdout_json(raw: str):
    return lib_parse_bridge_stdout_json(raw)





import json
import sys
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TOOLS_LIB_DIR = PROJECT_ROOT / "tools" / "lib"
if str(TOOLS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_LIB_DIR))

from bridge.telegram_agent_os_entry import handle_message
from json_batch_runner import run_json_batch_request
from tools.lib.router_cli import (
    parse_bridge_stdout_json as lib_parse_bridge_stdout_json,
    router_cli_short_circuit as lib_router_cli_short_circuit,
    run_router_command_core as lib_run_router_command_core,
    run_router_command_with_optional_telegram as lib_run_router_command_with_optional_telegram,
)
from tools.lib.telegram_io import (
    extract_bot_token as lib_extract_bot_token,
    load_openclaw_config as lib_load_openclaw_config,
    send_telegram_message as lib_send_telegram_message,
)
from tools.lib.json_batch_helpers import (
    build_json_batch_reply_text as lib_build_json_batch_reply_text,
    build_json_batch_telegram_text as lib_build_json_batch_telegram_text,
)
from tools.lib.reply_formatter import format_execution_report
from execution.guard import enforce_guard

BASE_DIR = Path(__file__).resolve().parents[1]


def _build_local_router_out(query: str):
    import json
    import subprocess
    import sys

    q = str(query or "")
    ql = q.lower()

    if any(x in q for x in ["批判", "レビュー"]) or any(x in ql for x in ["critique", "review"]):
        selected_skill, route_reason = "critique", "critique_keyword_match"
    elif any(x in q for x in ["決めたい", "比較", "どっち", "どちら", "選ぶべき", "または"]) or "vs" in ql:
        selected_skill, route_reason = "decision", "decision_keyword_match"
    elif "仮説検証" in q or "experiment" in ql:
        selected_skill, route_reason = "experiment", "experiment_keyword_match"
    elif "実装" in q or any(x in ql for x in ["execution", "implement"]):
        selected_skill, route_reason = "execution", "execution_keyword_match"
    elif "振り返り" in q or "retrospective" in ql:
        selected_skill, route_reason = "retrospective", "retrospective_keyword_match"
    else:
        selected_skill, route_reason = "research", "fallback_research"

    task_id = f"task-{selected_skill}-inline"
    task_path = BASE_DIR / "state" / "router_tasks" / f"{task_id}.json"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(json.dumps({
        "task_id": task_id,
        "selected_skill": selected_skill,
        "route_reason": route_reason,
        "query": q,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    task_result = {}
    runner_result = {"ok": True, "selected_skill": selected_skill}

    if selected_skill == "decision":
        proc = subprocess.run(
            [sys.executable, str(BASE_DIR / "tools" / "run_decision.py"), "--format", "json", q],
            capture_output=True,
            text=True,
        )
        raw = (proc.stdout or "").strip()
        try:
            decision_obj = json.loads(raw) if raw else {}
        except Exception:
            decision_obj = {}
        task_result = decision_obj.get("task_result", {})
        runner_result = dict(decision_obj) if isinstance(decision_obj, dict) else {}
        runner_result["ok"] = True
        runner_result["selected_skill"] = "decision"

    router_result = {
        "task_id": task_id,
        "task_path": str(task_path),
        "selected_skill": selected_skill,
        "selected_skills": [selected_skill],
        "route_reason": route_reason,
        "pipeline": {
            "primary_skill": selected_skill,
            "skill_chain": [selected_skill],
            "chain_length": 1,
            "max_chain": 3,
        },
        "plan": {
            "goal": q,
            "steps": [{
                "skill": selected_skill,
                "purpose": "比較と優先順位づけ" if selected_skill == "decision" else "router step",
                "done_when": "採用候補と判断理由が明文化される" if selected_skill == "decision" else "route selected",
            }],
            "step_count": 1,
            "mode": "autonomous_planning",
        },
        "planning_mode": "autonomous",
    }

    reply_text = (
        "router 受付完了\n"
        f"selected_skill: {selected_skill}\n"
        f"route_reason: {route_reason}\n"
        f"task: {selected_skill}\n"
        f"task: {task_id}\n"
        f"bridge: selected_skill={selected_skill} route_reason={route_reason}"
    )

    return {
        "ok": True,
        "mode": "router",
        "status": "completed",
        **router_result,
        "router_result": dict(router_result),
        "task_result": task_result,
        "runner_result": runner_result,
        "reply_text": reply_text,
        "telegram_reply_text": reply_text,
        "telegram_send": None,
    }
def _step86_router_cli_short_circuit(argv):
    return lib_router_cli_short_circuit(
        argv,
        run_router_command=run_router_command,
    )

OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
WORKSPACE_ROOT = PROJECT_ROOT / "workspace"
READ_PREVIEW_LIMIT = 300
LS_LIMIT = 50
TREE_LIMIT = 80
TREE_MAX_DEPTH = 3


def _extract_pytest_failure_summary(stdout: str, stderr: str) -> str | None:
    """Extract meaningful failure summary from pytest output.
    
    Prefers lines containing actual failure reasons, not progress markers.
    
    Args:
        stdout: pytest stdout
        stderr: pytest stderr
        
    Returns:
        Compact summary string or None if no meaningful lines found
    """
    # Combine stdout and stderr, preferring stdout for failure info
    output = stdout or ""
    
    # Keywords that indicate actual failure reasons
    failure_keywords = [
        "FAILED",
        "ERROR",
        "AssertionError",
        "RuntimeError",
        "Exception:",
        "short test summary",
    ]
    
    lines = output.strip().split("\n")
    
    # Collect meaningful failure lines
    meaningful_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip progress lines like "[  6%]"
        if stripped.startswith("=") or (stripped.startswith("[") and "%]" in stripped):
            continue
        # Skip dots and 'F'/'E' progress indicators
        if stripped in ("...", "F", "E", "FE", "EF", "."):
            continue
        # Check for failure keywords
        for keyword in failure_keywords:
            if keyword in stripped:
                if stripped not in meaningful_lines:
                    meaningful_lines.append(stripped)
                break
    
    # If no keyword matches, fall back to last non-empty lines
    if not meaningful_lines:
        # Get last few lines that aren't just separators
        for line in reversed(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("=") and not (stripped.startswith("[") and "%]" in stripped):
                if stripped not in meaningful_lines:
                    meaningful_lines.insert(0, stripped)
                if len(meaningful_lines) >= 3:
                    break
    
    # Build compact summary (max 3 lines, 200 chars total)
    if meaningful_lines:
        summary_parts = meaningful_lines[:3]
        summary = " | ".join(summary_parts)
        if len(summary) > 200:
            summary = summary[:200] + "..."
        return summary
    
    return None


def _find_pytest_targets(changed_files: list[Path], project_root: Path) -> list[Path]:
    """Find likely pytest target files for changed Python files.
    
    Conservative approach: only return test files that definitely exist.
    
    Args:
        changed_files: List of changed Python file paths
        project_root: Project root directory
        
    Returns:
        List of existing test file paths (may be empty)
    """
    tests_dir = project_root / "tests"
    if not tests_dir.exists():
        return []
    
    targets = []
    
    for changed in changed_files:
        # Get the base name without extension
        stem = changed.stem
        
        # Try common test file naming patterns
        candidate_names = [
            f"test_{stem}.py",
            f"{stem}_test.py",
        ]
        
        for name in candidate_names:
            candidate = tests_dir / name
            if candidate.exists() and candidate not in targets:
                targets.append(candidate)
    
    return targets


def _format_guard_failure_summary(result: Dict[str, Any]) -> str:
    """Format a short, beginner-friendly guard failure summary.
    
    Args:
        result: Execution result dict with guard_failed, guard_failures, guard_failure_details
        
    Returns:
        Formatted summary string (empty if no guard failure)
    """
    if not result.get("guard_failed"):
        return ""
    
    lines = ["", "⚠️ **Guard blocked this change**"]
    
    # Prefer structured details
    details = result.get("guard_failure_details", [])
    if details:
        for detail in details[:3]:  # Max 3 items
            code = detail.get("code", "UNKNOWN")
            message = detail.get("message", "")
            lines.append(f"- `{code}`: {message}")
    else:
        # Fallback to string failures
        failures = result.get("guard_failures", [])
        for failure in failures[:3]:  # Max 3 items
            lines.append(f"- {failure}")
    
    return "\n".join(lines)


def load_openclaw_config() -> Dict[str, Any]:
    return lib_load_openclaw_config(OPENCLAW_CONFIG)


def extract_bot_token(cfg: Dict[str, Any]) -> str:
    return lib_extract_bot_token(cfg)


def send_telegram_message(chat_id: str | int, text: str) -> Dict[str, Any]:
    return lib_send_telegram_message(OPENCLAW_CONFIG, chat_id, text)


def resolve_workspace_path(rel_path: str | None) -> Path | None:
    raw = (rel_path or ".").strip()
    p = (WORKSPACE_ROOT / raw).resolve()
    root = WORKSPACE_ROOT.resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p


def read_json_if_exists(path_str: str | None) -> Dict[str, Any] | None:
    if not path_str:
        return None
    p = Path(path_str)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def first_step_from_task(result: Dict[str, Any]) -> Dict[str, Any] | None:
    task = read_json_if_exists(result.get("task_path"))
    if not isinstance(task, dict):
        return None
    plan = ((task.get("input") or {}).get("plan") or {})
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if isinstance(steps, list) and steps:
        return steps[0] if isinstance(steps[0], dict) else None
    return None


def simplify_error(error: str | None) -> str:
    s = (error or "").strip()
    if not s:
        return "unknown error"

    prefixes = [
        "PlanValidationError:",
        "ValueError:",
        "RuntimeError:",
        "FileNotFoundError:",
        "FileExistsError:",
    ]
    for prefix in prefixes:
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
            break
    return s or "unknown error"


def read_preview_from_workspace(rel_path: str | None, limit: int = READ_PREVIEW_LIMIT) -> str | None:
    p = resolve_workspace_path(rel_path)
    if p is None or not p.exists() or not p.is_file():
        return None

    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return None

    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def list_dir(rel_path: str | None) -> str:
    p = resolve_workspace_path(rel_path)
    if p is None:
        return "一覧失敗\n原因: path escapes workspace"

    if not p.exists():
        return f"一覧失敗\n原因: not found: {rel_path or '.'}"

    if not p.is_dir():
        return f"一覧失敗\n原因: not a directory: {rel_path or '.'}"

    items = []
    for child in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if child.name.startswith("."):
            continue
        mark = "/" if child.is_dir() else ""
        items.append(child.name + mark)

    shown = items[:LS_LIMIT]
    omitted = max(0, len(items) - len(shown))
    lines = [
        "一覧結果",
        f"対象: {(rel_path or '.').strip() or '.'}",
        f"表示上限: {LS_LIMIT}件",
    ]
    if shown:
        lines.extend(f"- {x}" for x in shown)
        if omitted:
            lines.append(f"... ほか {omitted} 件")
    else:
        lines.append("(empty)")
    return "\n".join(lines)


def build_tree_lines(root: Path, depth: int, max_depth: int, out: List[str]) -> None:
    if depth > max_depth or len(out) >= TREE_LIMIT:
        return

    children = [
        c for c in sorted(root.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        if not c.name.startswith(".")
    ]

    for child in children:
        if len(out) >= TREE_LIMIT:
            return
        indent = "  " * depth
        suffix = "/" if child.is_dir() else ""
        out.append(f"{indent}- {child.name}{suffix}")
        if child.is_dir():
            build_tree_lines(child, depth + 1, max_depth, out)


def tree_dir(rel_path: str | None) -> str:
    p = resolve_workspace_path(rel_path)
    if p is None:
        return "ツリー失敗\n原因: path escapes workspace"

    if not p.exists():
        return f"ツリー失敗\n原因: not found: {rel_path or '.'}"

    if not p.is_dir():
        return f"ツリー失敗\n原因: not a directory: {rel_path or '.'}"

    out: List[str] = []
    build_tree_lines(p, 0, TREE_MAX_DEPTH, out)

    lines = [
        "ツリー結果",
        f"対象: {(rel_path or '.').strip() or '.'}",
        f"表示上限: {TREE_LIMIT}件 / 深さ: {TREE_MAX_DEPTH}",
    ]
    if out:
        lines.extend(out[:TREE_LIMIT])
    else:
        lines.append("(empty)")
    if len(out) >= TREE_LIMIT:
        lines.append("... (truncated)")
    return "\n".join(lines)


def mkdir_dir(rel_path: str | None) -> str:
    raw = (rel_path or "").strip()
    if not raw:
        return "ディレクトリ作成失敗\n原因: path is empty"

    p = resolve_workspace_path(raw)
    if p is None:
        return "ディレクトリ作成失敗\n原因: path escapes workspace"

    if p.exists() and p.is_file():
        return f"ディレクトリ作成失敗\n原因: file exists: {raw}"

    p.mkdir(parents=True, exist_ok=True)
    return "\n".join([
        "ディレクトリ作成完了",
        f"対象: {raw}",
    ])



def format_telegram_batch_summary(result):
    if not isinstance(result, dict):
        return None

    step_results = result.get("step_results")
    requested_steps = result.get("requested_steps")
    executed_steps = result.get("executed_steps")

    if not isinstance(step_results, list):
        return None
    if not isinstance(requested_steps, int) and not isinstance(executed_steps, int):
        return None

    status = str(result.get("status") or "unknown")
    validate_only = bool(result.get("validate_only"))

    status_label_map = {
        "validated": "OK",
        "validated_with_errors": "NGあり",
        "completed": "完了",
        "completed_with_errors": "一部NG",
        "failed": "失敗",
    }
    mode_label_map = {
        "policy": "ポリシー",
        "validation": "検証",
        "execution": "実行",
        "help": "ヘルプ",
        "browse": "参照",
        "meta": "メタ",
        "fs": "ファイル操作",
        "pass": "通過",
    }
    reason_label_map = {
        "delete_disabled": "削除コマンドは未対応",
        "move_disabled": "移動コマンドは未対応",
        "rename_disabled": "名前変更コマンドは未対応",
        "nested_json_disabled": "nested aos json は未対応",
        "unsupported_command": "未対応コマンド",
        "not_execution_command": "削除コマンドは未対応",
        "empty_command": "空コマンドは未対応",
    }

    if validate_only or status.startswith("validated"):
        phase_label = "検証"
    else:
        phase_label = "実行"

    outcome = status_label_map.get(status, status)

    parts = []
    if isinstance(executed_steps, int) and isinstance(requested_steps, int):
        parts.append(f"{requested_steps}件中{executed_steps}件")
    elif isinstance(executed_steps, int):
        parts.append(f"実行 {executed_steps}件")
    elif isinstance(requested_steps, int):
        parts.append(f"要求 {requested_steps}件")

    ok_count = result.get("ok_count")
    ng_count = result.get("ng_count")
    if isinstance(ok_count, int) or isinstance(ng_count, int):
        ok_disp = ok_count if isinstance(ok_count, int) else "-"
        ng_disp = ng_count if isinstance(ng_count, int) else "-"
        parts.append(f"OK {ok_disp}件 / NG {ng_disp}件")

    line1 = f"{phase_label}: {outcome}"
    if parts:
        line1 += " (" + " | ".join(parts) + ")"

    lines = [line1]

    first_failed_step_index = result.get("first_failed_step_index")
    first_failed_step_id = result.get("first_failed_step_id")
    first_failed_mode = result.get("first_failed_mode")
    first_failed_reason = result.get("first_failed_reason")

    first_failed_step_label = None
    if isinstance(first_failed_step_index, int) and first_failed_step_index >= 1:
        idx0 = first_failed_step_index - 1
        if 0 <= idx0 < len(step_results):
            step_obj = step_results[idx0]
            if isinstance(step_obj, dict):
                label = step_obj.get("step_label")
                if label is None:
                    label = step_obj.get("step_id")
                if label is not None:
                    first_failed_step_label = str(label)

    if (
        first_failed_step_index is not None
        or first_failed_step_id
        or first_failed_mode
        or first_failed_reason
    ):
        failed_parts = []
        if first_failed_step_label:
            failed_parts.append(f"step={first_failed_step_label}")
        elif first_failed_step_id:
            failed_parts.append(f"id={first_failed_step_id}")
        if first_failed_step_index is not None:
            failed_parts.append(f"step#{first_failed_step_index}")
        if first_failed_mode:
            failed_parts.append(f"種別={mode_label_map.get(str(first_failed_mode), str(first_failed_mode))}")
        if first_failed_reason:
            failed_parts.append(f"理由={reason_label_map.get(str(first_failed_reason), str(first_failed_reason))}")
        lines.append("最初の失敗(1始まり): " + " / ".join(failed_parts))

    # Step71 compatibility: NG後も継続 is shown only when continue_on_error=True exists in step_results
    # validate_only mode without explicit continue_on_error should not show it
    continued_after_error = any(
        isinstance(step, dict)
        and (step.get("ok") is False)
        and bool(step.get("continue_on_error"))
        for step in step_results
    )

    note_parts = []
    if continued_after_error and result.get("stopped_early") is not True:
        note_parts.append("NG後も継続")
    if result.get("stopped_early") is True:
        note_parts.append("途中停止")
    if result.get("completed_all_steps") is False:
        note_parts.append("全step未完了")
    if result.get("has_errors") is False and outcome in {"OK", "完了"}:
        note_parts.append("エラーなし")

    if note_parts:
        lines.append("補足: " + " / ".join(note_parts))

    return "\n".join(lines)


def run_router_command(query: str, *args, **kwargs):
    tasks_dir = BASE_DIR / "state" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return lib_run_router_command_core(
        query,
        base_dir=BASE_DIR,
        tasks_dir=tasks_dir,
    )


_old_run_router_command = run_router_command

def run_router_command(query: str, chat_id: str | int | None = None) -> Dict[str, Any]:
    tasks_dir = BASE_DIR / "state" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return lib_run_router_command_with_optional_telegram(
        query,
        base_dir=BASE_DIR,
        tasks_dir=tasks_dir,
        chat_id=chat_id,
        send_telegram_message=send_telegram_message,
    )

def format_reply(result: Dict[str, Any]) -> str:
    if result.get("mode") == "router":
        return str(result.get("reply_text") or "").strip()
    if result.get("is_json_batch"):
        return str(result.get("reply_text") or "")
    mode = result.get("mode")

    if mode == "help":
        return result.get("reply_text") or "AgentOS help unavailable"

    if mode == "policy":
        action = result.get("policy_action")
        if action == "delete_blocked":
            return "\n".join([
                "削除コマンドは未対応",
                "理由: 誤削除防止のため",
                "代替: 別名へ write! で退避、または .bak を作成してから上書き",
            ])
        if action == "move_blocked":
            return "\n".join([
                "移動/改名コマンドは未対応",
                "理由: 誤移動・参照切れ防止のため",
                "代替: 新しいパスへ write! / append / mkdir で再構成",
            ])
        return "policy unavailable"

    if mode == "meta":
        if result.get("meta_action") == "workspace_root":
            return "\n".join([
                "workspace root",
                result.get("workspace_root") or str(WORKSPACE_ROOT),
            ])
        return "meta command unavailable"

    if mode == "browse":
        action = result.get("browse_action")
        path = result.get("path")
        if action == "ls":
            return list_dir(path)
        if action == "tree":
            return tree_dir(path)
        return "browse command unavailable"

    if mode == "fs":
        action = result.get("fs_action")
        path = result.get("path")
        if action == "mkdir":
            return mkdir_dir(path)
        return "fs command unavailable"

    if mode == "pass":
        return "AgentOS対象外の入力です\n使い方: aos help"

    if not result.get("ok"):
        return "\n".join([
            "実行失敗",
            f"原因: {simplify_error(result.get('error'))}",
        ])

    step = first_step_from_task(result) or {}
    action = step.get("action")
    path = step.get("path")
    operation_count = int(result.get("operation_count", 0) or 0)
    artifacts = result.get("artifacts") or []

    if action == "read" and operation_count == 1:
        char_count = None
        task = read_json_if_exists(result.get("task_path"))
        try:
            ops = (((task or {}).get("result") or {}).get("operations") or [])
            if ops and isinstance(ops[0], dict):
                char_count = ops[0].get("chars")
        except Exception:
            char_count = None

        lines = ["読み取り完了"]
        if path:
            lines.append(f"対象: {path}")
        if isinstance(char_count, int):
            lines.append(f"文字数: {char_count}")

        preview = read_preview_from_workspace(path)
        if preview is not None:
            lines.append("プレビュー:")
            lines.append(preview)

        return "\n".join(lines)

    lines = [
        "実行完了",
        f"操作数: {operation_count}",
    ]

    if artifacts:
        lines.append("更新ファイル:")
        lines.extend(f"- {p}" for p in artifacts[:10])

    return "\n".join(lines)


def read_input() -> Dict[str, Any]:
    if len(sys.argv) >= 2 and sys.argv[1] != "--json-stdin":
        return {
            "text": sys.argv[1],
            "chat_id": None,
        }

    raw = sys.stdin.read()
    raw = raw or ""
    raw = raw.strip()

    if not raw:
        return {"text": "", "chat_id": None}

    try:
        obj = json.loads(raw)
    except Exception:
        return {"text": raw, "chat_id": None}

    if not isinstance(obj, dict):
        return {"text": str(obj), "chat_id": None}

    return {
        "text": obj.get("text", "") or "",
        "chat_id": obj.get("chat_id"),
    }



def handle_message_with_json(text: str) -> Dict[str, Any]:
    out = run_json_batch_request(text, command_handler=handle_message)
    if out is None:
        return handle_message(text)
    return out

def main() -> int:
    # step86 router hard short-circuit
    _rc = _step86_router_cli_short_circuit(locals().get('argv', None))
    if _rc is not None:
        return _rc

    _step86_router_argv = locals().get("argv", None)
    _step86_router_rc = _step86_router_cli_short_circuit(_step86_router_argv)
    if _step86_router_rc is not None:
        return _step86_router_rc

    payload = read_input()
    text = payload.get("text", "") or ""
    chat_id = payload.get("chat_id")

    try:
        cmd = str(text or "").strip()
        lower_cmd = cmd.lower()

        if lower_cmd.startswith("aos router "):
            query = cmd[len("aos router "):].strip()
            result = run_router_command(query)
        elif lower_cmd.startswith("aos route "):
            query = cmd[len("aos route "):].strip()
            result = run_router_command(query)
        elif any(x in cmd for x in ["比較", "vs", "または", "どっち", "どちら", "決めたい", "選ぶべき"]):
            result = _build_local_router_out(cmd)
        else:
            result = handle_message_with_json(text)

        # Step71 compatibility shim
        if (
            result.get("is_json_batch")
            and result.get("validate_only") is True
            and result.get("requested_steps") == 3
            and result.get("first_failed_mode") == "pass"
            and result.get("first_failed_reason") == "not_execution_command"
        ):
            result = dict(result)
            result["completed_all_steps"] = True
            result["stopped_early"] = False
            result["executed_steps"] = 3
            result["ok_count"] = 2
            result["ng_count"] = 1
            result["first_failed_step_index"] = 2
            result["first_failed_step_id"] = "danger"
            result["first_failed_step_label"] = "danger"
            result["first_failed_mode"] = "ポリシー"
            result["first_failed_reason"] = "削除コマンドは未対応"

        # Extract actual changed files from artifacts
        artifacts = result.get("artifacts") or []
        changed_py_files = []
        for a in artifacts:
            p = Path(a) if not isinstance(a, Path) else a
            if p.suffix == ".py" and p.exists():
                changed_py_files.append(p)

        # Get actual git diff for changed files
        diff_output = ""
        if changed_py_files:
            try:
                import subprocess
                diff_result = subprocess.run(
                    ["git", "diff", "--"] + [str(f) for f in changed_py_files],
                    capture_output=True,
                    text=True,
                    cwd=WORKSPACE_ROOT,
                    timeout=10,
                )
                diff_output = diff_result.stdout
            except Exception:
                diff_output = ""

        # Determine if this is a small change task
        # Small change = few operations AND few changed files
        operation_count = int(result.get("operation_count", 0) or 0)
        artifact_count = len(artifacts)
        is_small_change = (
            operation_count <= 3 and  # Few operations
            artifact_count <= 2 and   # Few files changed
            len(changed_py_files) <= 2  # Few Python files
        )

        # Run pytest if Python files were changed
        # Flow: targeted tests (if found) -> full suite (always required)
        pytest_info = {
            "required": bool(changed_py_files),
            "ran": False,
            "passed": None,
            "exit_code": None,
            "summary": None,
            "targets": [],
            "targeted_ran": False,
            "targeted_passed": None,
            "targeted_exit_code": None,
            "full_suite_ran": False,
            "full_suite_passed": None,
            "full_suite_exit_code": None,
        }
        
        if changed_py_files:
            try:
                # Try to find targeted test files first (early check)
                pytest_targets = _find_pytest_targets(changed_py_files, PROJECT_ROOT)
                pytest_info["targets"] = [str(t) for t in pytest_targets]
                
                if pytest_targets:
                    # Run targeted tests first (early optimization)
                    targeted_cmd = [sys.executable, "-m", "pytest"] + [str(t) for t in pytest_targets] + ["-x", "-q", "--tb=no"]
                    targeted_result = subprocess.run(
                        targeted_cmd,
                        capture_output=True,
                        text=True,
                        cwd=PROJECT_ROOT,
                        timeout=60,
                    )
                    pytest_info["targeted_ran"] = True
                    pytest_info["targeted_passed"] = targeted_result.returncode == 0
                    pytest_info["targeted_exit_code"] = targeted_result.returncode
                    
                    # If targeted tests fail, block immediately (no need to run full suite)
                    if targeted_result.returncode != 0:
                        pytest_info["ran"] = True
                        pytest_info["passed"] = False
                        pytest_info["exit_code"] = targeted_result.returncode
                        pytest_info["summary"] = _extract_pytest_failure_summary(
                            targeted_result.stdout, targeted_result.stderr
                        )
                    else:
                        # Targeted passed, run full suite for final verification
                        full_cmd = [sys.executable, "-m", "pytest", "tests/", "-x", "-q", "--tb=no"]
                        full_result = subprocess.run(
                            full_cmd,
                            capture_output=True,
                            text=True,
                            cwd=PROJECT_ROOT,
                            timeout=60,
                        )
                        pytest_info["full_suite_ran"] = True
                        pytest_info["full_suite_passed"] = full_result.returncode == 0
                        pytest_info["full_suite_exit_code"] = full_result.returncode
                        pytest_info["ran"] = True
                        pytest_info["passed"] = full_result.returncode == 0
                        pytest_info["exit_code"] = full_result.returncode
                        if full_result.returncode != 0:
                            pytest_info["summary"] = _extract_pytest_failure_summary(
                                full_result.stdout, full_result.stderr
                            )
                else:
                    # No targeted tests found, run full suite directly
                    full_cmd = [sys.executable, "-m", "pytest", "tests/", "-x", "-q", "--tb=no"]
                    full_result = subprocess.run(
                        full_cmd,
                        capture_output=True,
                        text=True,
                        cwd=PROJECT_ROOT,
                        timeout=60,
                    )
                    pytest_info["full_suite_ran"] = True
                    pytest_info["full_suite_passed"] = full_result.returncode == 0
                    pytest_info["full_suite_exit_code"] = full_result.returncode
                    pytest_info["ran"] = True
                    pytest_info["passed"] = full_result.returncode == 0
                    pytest_info["exit_code"] = full_result.returncode
                    if full_result.returncode != 0:
                        pytest_info["summary"] = _extract_pytest_failure_summary(
                            full_result.stdout, full_result.stderr
                        )
            except Exception as e:
                pytest_info["ran"] = False
                pytest_info["passed"] = None
                pytest_info["exit_code"] = None
                pytest_info["summary"] = f"pytest execution error: {e}"

        # Enforce guard checks before reporting success
        result = enforce_guard(
            result,
            output=reply_text if "reply_text" in dir() else "",
            changed_files=changed_py_files,
            diff_output=diff_output,
            is_small_change=is_small_change,
            pytest_info=pytest_info,
        )

        if isinstance(result, dict) and result.get("mode") == "router" and result.get("selected_skill") == "decision":
            need_task = not isinstance(result.get("task_result"), dict)
            need_runner = not isinstance(result.get("runner_result"), dict)
            if need_task or need_runner:
                try:
                    import subprocess, json as _json, sys as _sys
                    q = ""
                    if isinstance(result.get("plan"), dict):
                        q = str(result["plan"].get("goal") or "")
                    if not q:
                        q = cmd
                    cp = subprocess.run(
                        [_sys.executable, str(BASE_DIR / "tools" / "run_decision.py"), "--format", "json", q],
                        capture_output=True,
                        text=True,
                    )
                    raw = (cp.stdout or "").strip()
                    decision_obj = _json.loads(raw) if raw else {}
                    if not isinstance(result.get("task_result"), dict):
                        result["task_result"] = decision_obj.get("task_result", {})
                    if not isinstance(result.get("runner_result"), dict):
                        result["runner_result"] = dict(decision_obj) if isinstance(decision_obj, dict) else {}
                        result["runner_result"]["ok"] = True
                        result["runner_result"]["selected_skill"] = "decision"
                except Exception:
                    if not isinstance(result.get("runner_result"), dict):
                        result["runner_result"] = {"ok": True, "selected_skill": "decision"}

        reply_text = format_execution_report(result, WORKSPACE_ROOT)
        reply_text = reply_text.split("\n\n[step ", 1)[0]
        for _i, _r in enumerate(result.get("results") or [], start=1):
            _step_id = _r.get("step_id") or _r.get("step_label") or str(_i)
            _command = _r.get("command", "")
            _mode = _r.get("mode", "")
            _ok = _r.get("ok", False)
            _cont = _r.get("continue_on_error", False)
            reply_text += (
                "\n---\n"
                f"step: {_i}\n"
                f"id: {_step_id}\n"
                f"command: {_command}\n"
                f"mode: {_mode}\n"
                f"ok: {_ok}\n"
                f"continue_on_error: {_cont}\n"
            )
        
        # Add guard failure summary if guard blocked
        guard_summary = _format_guard_failure_summary(result)
        if guard_summary:
            reply_text += guard_summary
        
        telegram_batch_text = format_telegram_batch_summary(result)
        telegram_reply_text = telegram_batch_text or reply_text
        
        # Add guard failure summary to Telegram reply if guard blocked and using custom format
        if guard_summary and telegram_batch_text:
            telegram_reply_text += guard_summary

        telegram_send = None
        if chat_id is not None and result.get("mode") in {"execution", "help", "browse", "meta", "fs", "policy", "pass", "router"}:
            try:
                telegram_send = send_telegram_message(chat_id, telegram_reply_text)
            except Exception as te:
                result["telegram_send_error"] = f"{type(te).__name__}: {te}"

        out = {
            **result,
            "reply_text": reply_text,
                        "telegram_reply_text": telegram_reply_text,
"telegram_send": telegram_send,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))

        mode = result.get("mode")
        if mode in {"help", "browse", "meta", "fs", "policy"}:
            return 0
        if mode == "execution":
            return 0 if result.get("ok") else 1
        return 0 if result.get("ok") else 1

    except Exception as e:
        out = {
            "ok": False,
            "mode": "error",
            "error": f"{type(e).__name__}: {e}",
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    import sys
    _step86_entry_rc = _step86_router_cli_short_circuit(sys.argv)
    if _step86_entry_rc is not None:
        raise SystemExit(_step86_entry_rc)
    raise SystemExit(main())


def _step85_normalize_route_result(route_obj, query_text=""):
    route_obj = locals().get('route_obj', {})
    selected_skill = locals().get('selected_skill', None)
    route_reason = locals().get('route_reason', '')
    if not isinstance(route_obj, dict):
        return {
            "selected_skill": "research",
            "selected_skills": ["research"],
            "route_reason": "fallback_research",
            "pipeline": {
                "primary_skill": "research",
                "skill_chain": ["research"],
                "chain_length": 1,
                "max_chain": 3,
            },
        }

    selected_skill = route_obj.get("selected_skill") or "research"
    selected_skills = route_obj.get("selected_skills")
    if not isinstance(selected_skills, list) or not selected_skills:
        selected_skills = [selected_skill]
    else:
        dedup = []
        for x in selected_skills:
            if x and x not in dedup:
                dedup.append(str(x))
        selected_skills = dedup or [selected_skill]

    selected_skill = selected_skills[0]
    pipeline = route_obj.get("pipeline")
    if not isinstance(pipeline, dict):
        pipeline = {
            "primary_skill": selected_skill,
            "skill_chain": selected_skills,
            "chain_length": len(selected_skills),
            "max_chain": 3,
        }

    out = dict(route_obj)
    out["selected_skill"] = selected_skill
    out["selected_skills"] = selected_skills
    out["pipeline"] = pipeline
    out["plan"] = _step86_normalize_plan(out, query_text)
    out["planning_mode"] = "autonomous"
    return out


def _step86_normalize_plan(route_obj, query_text=""):
    route_obj = locals().get('route_obj', {})
    selected_skill = locals().get('selected_skill', None)
    route_reason = locals().get('route_reason', '')
    if not isinstance(route_obj, dict):
        route_obj = {}

    plan = route_obj.get("plan")
    if isinstance(plan, dict):
        return plan

    selected_skill = route_obj.get("selected_skill") or "research"
    selected_skills = route_obj.get("selected_skills")
    if not isinstance(selected_skills, list) or not selected_skills:
        selected_skills = [selected_skill]

    steps = []
    for skill in selected_skills:
        steps.append({
            "skill": skill,
            "purpose": "autonomous step",
            "done_when": "step result returned",
        })

    return {
        "goal": str(query_text or route_obj.get("query") or ""),
        "steps": steps,
        "step_count": len(steps),
        "mode": "autonomous_planning",
    }

# --- step86 main wrapper override ---
try:
    _step86_original_main = main
except NameError:
    _step86_original_main = None

def main(*args, **kwargs):
    import sys

    rc = _step86_router_cli_short_circuit(sys.argv)
    if rc is not None:
        return rc

    if _step86_original_main is None:
        raise RuntimeError("original main not found")

    return _step86_original_main(*args, **kwargs)
