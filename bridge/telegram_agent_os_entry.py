#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
import re
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT / "workspace"
TASKS_DIR = PROJECT_ROOT / "state" / "tasks"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from router.route_to_task import route_message_to_task
from runner.run_route_task import apply_approval_decision as apply_route_approval_decision
from runner.run_execution_task import run_task as run_execution_task_run_task
from miso.bridge import handle_approval_callback as miso_handle_approval_callback


HELP_TEXT = """AgentOS 使い方

実行コマンド
aos read <path>
aos cat <path>

aos write <path>
<content>

aos write! <path>
<content>   # 既存ファイルを上書き

aos append <path>
<content>

aos json {"steps":[...]}

閲覧コマンド
aos ls
aos ls <dir>
aos tree
aos tree <dir>
aos pwd
aos root

ディレクトリ操作
aos mkdir <dir>

承認コマンド
aos approve <task_id|task_path>
aos reject <task_id|task_path>

未対応
aos rm / aos del / aos delete
aos mv / aos move / aos rename
※ 誤削除・誤移動防止のため未解禁

互換コマンド
aos decision: read <path>
aos decision: write <path>
<content>
aos decision: append <path>
<content>
aos decision: json {"steps":[...]}

例
aos cat notes/hook_success.txt
aos pwd
aos ls notes
aos tree notes
aos mkdir notes/new_dir
"""


def is_help_command(text: str) -> bool:
    s = (text or "").strip().lower()
    return s in {"aos help", "aos usage"}


def is_policy_command(text: str) -> bool:
    s = (text or "").strip().lower()
    return (
        s.startswith("aos rm ")
        or s.startswith("aos del ")
        or s.startswith("aos delete ")
        or s.startswith("aos mv ")
        or s.startswith("aos move ")
        or s.startswith("aos rename ")
    )


def parse_policy_command(text: str) -> Dict[str, Any]:
    s = (text or "").strip().lower()

    if s.startswith("aos rm ") or s.startswith("aos del ") or s.startswith("aos delete "):
        return {
            "ok": False,
            "mode": "policy",
            "policy_action": "delete_blocked",
            "reason": "delete_disabled",
        }

    if s.startswith("aos mv ") or s.startswith("aos move ") or s.startswith("aos rename "):
        return {
            "ok": False,
            "mode": "policy",
            "policy_action": "move_blocked",
            "reason": "move_disabled",
        }

    return {"ok": False, "mode": "pass", "reason": "not_policy_command"}


def is_meta_command(text: str) -> bool:
    s = (text or "").strip().lower()
    return s in {"aos pwd", "aos root"}


def parse_meta_command(text: str) -> Dict[str, Any]:
    s = (text or "").strip().lower()
    if s in {"aos pwd", "aos root"}:
        return {
            "ok": True,
            "mode": "meta",
            "meta_action": "workspace_root",
            "workspace_root": str(WORKSPACE_ROOT),
        }
    return {"ok": False, "mode": "pass", "reason": "not_meta_command"}


def is_browse_command(text: str) -> bool:
    s = (text or "").strip().lower()
    return s == "aos ls" or s.startswith("aos ls ") or s == "aos tree" or s.startswith("aos tree ")


def parse_browse_command(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    lower = s.lower()

    if lower == "aos ls":
        return {"ok": True, "mode": "browse", "browse_action": "ls", "path": "."}

    if lower.startswith("aos ls "):
        return {"ok": True, "mode": "browse", "browse_action": "ls", "path": s[7:].strip() or "."}

    if lower == "aos tree":
        return {"ok": True, "mode": "browse", "browse_action": "tree", "path": "."}

    if lower.startswith("aos tree "):
        return {"ok": True, "mode": "browse", "browse_action": "tree", "path": s[9:].strip() or "."}

    return {"ok": False, "mode": "pass", "reason": "not_browse_command"}


def is_fs_command(text: str) -> bool:
    s = (text or "").strip().lower()
    return s.startswith("aos mkdir ")


def parse_fs_command(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    lower = s.lower()

    if lower.startswith("aos mkdir "):
        return {
            "ok": True,
            "mode": "fs",
            "fs_action": "mkdir",
            "path": s[10:].strip(),
        }

    return {"ok": False, "mode": "pass", "reason": "not_fs_command"}


def is_execution_command(text: str) -> bool:
    s = (text or "").strip().lower()
    if not s:
        return False

    prefixes = (
        "aos decision: json",
        "aos decision: write!",
        "aos decision: write",
        "aos decision: append",
        "aos decision: read",
        "aos json",
        "aos write!",
        "aos write",
        "aos append",
        "aos read",
        "aos cat",
    )
    return any(s.startswith(p) for p in prefixes)




def is_status_command(text: str) -> bool:
    """aos status <task_id> - タスク状態確認"""
    return bool(re.match(r"^aos\s+status\s+", text, re.IGNORECASE))

def parse_status_command(text: str) -> Dict[str, Any]:
    """aos status <task_id>"""
    m = re.match(r"^aos\s+status\s+(\S+)", text, re.IGNORECASE)
    if not m:
        return {"ok": False, "mode": "status", "error": "invalid_syntax", "reply_text": "使い方: aos status <task_id>"}
    
    task_id = m.group(1)
    task_path = PROJECT_ROOT / "state" / "tasks" / f"{task_id}.json"
    
    if not task_path.exists():
        return {"ok": False, "mode": "status", "error": "not_found", "reply_text": f"タスク {task_id} が見つかりません"}
    
    import json
    task = json.loads(task_path.read_text())
    status = task.get("status", "unknown")
    query = task.get("query", task.get("request", {}).get("text", ""))
    skill = task.get("selected_skill", task.get("plan", {}).get("selected_skill", ""))
    result = task.get("result", {})
    summary = result.get("summary", "") if result else ""
    
    reply = f"タスク: {task_id}\nステータス: {status}\nスキル: {skill}\nクエリ: {query}"
    if summary:
        reply += f"\n結果: {summary}"
    
    return {"ok": True, "mode": "status", "task_id": task_id, "status": status, "reply_text": reply}

def is_spawn_command(text: str) -> bool:
    """aos spawn <query> - バックグラウンドタスク投入"""
    return bool(re.match(r"^aos\s+spawn\s+", text, re.IGNORECASE))

def parse_spawn_command(text: str) -> Dict[str, Any]:
    """aos spawn <query> [--skill <skill>]"""
    m = re.match(r"^aos\s+spawn\s+(.+)$", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return {"ok": False, "mode": "spawn", "error": "invalid_syntax", "reply_text": "使い方: aos spawn <クエリ> [--skill <スキル>]"}
    
    rest = m.group(1).strip()
    skill = "research"
    
    # --skill オプション抽出
    skill_match = re.search(r"--skill\s+(\S+)", rest)
    if skill_match:
        skill = skill_match.group(1)
        rest = re.sub(r"--skill\s+\S+", "", rest).strip()
    
    if not rest:
        return {"ok": False, "mode": "spawn", "error": "empty_query", "reply_text": "エラー: クエリが空です"}
    
    # spawn_and_attach を使ってタスク投入
    try:
        import sys
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from runner.spawn_and_attach import WorkerPool
        pool = WorkerPool()
        task_id = pool.submit(query=rest, skill=skill)
        return {
            "ok": True,
            "mode": "spawn",
            "task_id": task_id,
            "query": rest,
            "skill": skill,
            "reply_text": f"タスク投入完了\nID: {task_id}\nクエリ: {rest}\nスキル: {skill}",
        }
    except Exception as e:
        return {"ok": False, "mode": "spawn", "error": str(e), "reply_text": f"エラー: {e}"}

def is_route_approval_command(text: str) -> bool:
    s = (text or "").strip().lower()
    return s.startswith("aos approve ") or s.startswith("aos reject ")


def is_miso_callback(text: str) -> bool:
    """Check if text is a MISO inline button callback"""
    s = (text or "").strip()
    return s.startswith("miso:approve:") or s.startswith("miso:reject:") or s.startswith("miso:retry:") or s.startswith("miso:skip:") or s.startswith("miso:abort:")


def handle_miso_callback(callback_data: str) -> Dict[str, Any]:
    """Handle MISO inline button callback"""
    try:
        result = miso_handle_approval_callback(callback_data)
        if result.get("ok"):
            action = result.get("action", "unknown")
            task_id = result.get("task_id", "unknown")
            return {
                "ok": True,
                "mode": "miso_callback",
                "action": action,
                "task_id": task_id,
                "reply_text": f"MISO: {action} {task_id}",
                "telegram_reply_text": f"✅ {action}: {task_id}",
            }
        else:
            return {
                "ok": False,
                "mode": "miso_callback",
                "error": result.get("error", "unknown error"),
                "reply_text": f"MISO error: {result.get('error')}",
            }
    except Exception as e:
        return {
            "ok": False,
            "mode": "miso_callback",
            "error": str(e),
            "reply_text": f"MISO error: {e}",
        }


def parse_route_approval_command(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    parts = s.split(maxsplit=2)
    if len(parts) != 3:
        return {
            "ok": False,
            "mode": "route_approval",
            "status": "invalid_args",
            "reason": "task_id_or_path_required",
            "reply_text": "route approval: invalid_args",
        }

    decision = parts[1].strip().lower()
    if decision not in {"approve", "reject"}:
        return {
            "ok": False,
            "mode": "route_approval",
            "status": "invalid_args",
            "reason": "decision_must_be_approve_or_reject",
            "reply_text": "route approval: invalid_args",
        }

    return {
        "ok": True,
        "mode": "route_approval",
        "decision": decision,
        "task_ref": parts[2].strip(),
    }


def resolve_route_task_path(task_ref: str) -> Path:
    raw = str(task_ref or "").strip()
    if not raw:
        raise ValueError("task_ref is empty")

    path = Path(raw)
    if path.suffix == ".json" or "/" in raw:
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        return path

    return (TASKS_DIR / f"{raw}.json").resolve()


def summarize_route_approval(task_path: Path, decision: str, result: Dict[str, Any]) -> Dict[str, Any]:
    approval_state = result.get("approval_state") if isinstance(result.get("approval_state"), dict) else {}
    route_execution = result.get("route_execution") if isinstance(result.get("route_execution"), dict) else {}
    route_result = result.get("route_result") if isinstance(result.get("route_result"), dict) else {}
    task_id = str(result.get("task_id") or task_path.stem)
    target = str(route_result.get("target") or approval_state.get("target") or "").strip()

    summary = str(route_result.get("summary") or "").strip()
    reply_text = f"route {decision}: {task_id}"
    if target:
        reply_text += f" target={target}"
    if summary:
        reply_text += f"\n{summary}"

    return {
        "ok": True,
        "mode": "route_approval",
        "status": "completed",
        "decision": decision,
        "task_id": task_id,
        "task_path": str(task_path),
        "approval_state": approval_state,
        "route_execution": route_execution,
        "route_result": route_result,
        "reply_text": reply_text,
        "telegram_reply_text": reply_text,
    }


def handle_route_approval(message_text: str) -> Dict[str, Any]:
    parsed = parse_route_approval_command(message_text)
    if not parsed.get("ok"):
        return parsed

    task_path = resolve_route_task_path(parsed["task_ref"])
    if not task_path.exists():
        return {
            "ok": False,
            "mode": "route_approval",
            "status": "task_not_found",
            "decision": parsed["decision"],
            "task_path": str(task_path),
            "reply_text": f"route {parsed['decision']}: task_not_found",
            "telegram_reply_text": f"route {parsed['decision']}: task_not_found",
        }

    try:
        result = apply_route_approval_decision(task_path, parsed["decision"])
    except Exception as e:
        return {
            "ok": False,
            "mode": "route_approval",
            "status": "error",
            "decision": parsed["decision"],
            "task_path": str(task_path),
            "error": f"{type(e).__name__}: {e}",
            "reply_text": f"route {parsed['decision']}: error ({type(e).__name__}: {e})",
            "telegram_reply_text": f"route {parsed['decision']}: error ({type(e).__name__}: {e})",
        }

    return summarize_route_approval(task_path, parsed["decision"], result)


def summarize_task(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": task.get("status") == "completed",
        "mode": "execution",
        "task_id": task.get("id"),
        "status": task.get("status"),
        "error": task.get("error"),
        "operation_count": task.get("operation_count", 0),
        "artifacts": task.get("artifacts", []),
        "run_log_path": task.get("run_log_path"),
    }


def handle_message(message_text: str) -> Dict[str, Any]:
    if is_help_command(message_text):
        return {
            "ok": True,
            "mode": "help",
            "reply_text": HELP_TEXT,
        }

    if is_policy_command(message_text):
        return parse_policy_command(message_text)

    if is_meta_command(message_text):
        return parse_meta_command(message_text)

    if is_browse_command(message_text):
        return parse_browse_command(message_text)

    if is_fs_command(message_text):
        return parse_fs_command(message_text)

    if is_status_command(message_text):
        return parse_status_command(message_text)
    if is_spawn_command(message_text):
        return parse_spawn_command(message_text)
    if is_miso_callback(message_text):
        return handle_miso_callback(message_text)
    if is_route_approval_command(message_text):
        return handle_route_approval(message_text)

    if not is_execution_command(message_text):
        return {
            "ok": False,
            "mode": "pass",
            "reason": "not_execution_command",
        }

    routed = route_message_to_task(message_text)
    task_path = Path(routed["task_path"])
    task = run_execution_task_run_task(task_path)

    out = summarize_task(task)
    out["task_path"] = str(task_path)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: telegram_agent_os_entry.py '<message text>'", file=sys.stderr)
        return 2

    message_text = sys.argv[1]
    result = handle_message(message_text)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
