"""Approval Executor - 承認されたアクションの自動実行

承認フローの最終段階: approve決定後にアクションを実行する
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def execution_log_path(state_root: Path) -> Path:
    return state_root / "approval_executions.jsonl"


def append_execution_log(
    state_root: Path,
    *,
    timestamp: str,
    fingerprint: str,
    action: str,
    args: Dict[str, Any],
    result: Dict[str, Any],
) -> Path:
    """実行結果をログに記録"""
    path = execution_log_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": timestamp,
        "fingerprint": fingerprint,
        "action": action,
        "args": args,
        "result": result,
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return path


def execute_approved_action(
    action: str,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """承認されたアクションを実行"""
    try:
        if action == "restart_openclaw_gateway":
            return _execute_restart_openclaw_gateway(args)
        elif action == "apply_config_change":
            return _execute_apply_config_change(args)
        elif action == "run_skill":
            return _execute_run_skill(args)
        elif action == "execute_task":
            return _execute_task(args)
        elif action.startswith("proactive_"):
            # Proactive tasks use run_skill
            return _execute_proactive_task(action, args)
        else:
            return {
                "ok": False,
                "status": "unknown_action",
                "action": action,
            }
    except Exception as e:
        logger.exception(f"Failed to execute action {action}: {e}")
        return {
            "ok": False,
            "status": "execution_error",
            "action": action,
            "error": f"{type(e).__name__}: {e}",
        }


def _execute_restart_openclaw_gateway(args: Dict[str, Any]) -> Dict[str, Any]:
    """OpenClaw Gatewayを再起動"""
    import subprocess

    try:
        result = subprocess.run(
            ["systemctl", "--user", "restart", "openclaw-gateway"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "ok": result.returncode == 0,
            "status": "restarted" if result.returncode == 0 else "restart_failed",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout"}


def _execute_apply_config_change(args: Dict[str, Any]) -> Dict[str, Any]:
    """設定変更を適用"""
    config_path = args.get("config_path")
    changes = args.get("changes", {})

    if not config_path:
        return {"ok": False, "status": "missing_config_path"}

    try:
        path = Path(config_path)
        if not path.exists():
            return {"ok": False, "status": "config_not_found", "path": config_path}

        with path.open("r", encoding="utf-8") as f:
            config = json.load(f)

        # Apply changes
        for key, value in changes.items():
            keys = key.split(".")
            target = config
            for k in keys[:-1]:
                target = target.setdefault(k, {})
            target[keys[-1]] = value

        with path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        return {"ok": True, "status": "applied", "path": config_path}
    except Exception as e:
        return {"ok": False, "status": "apply_failed", "error": str(e)}


def _execute_run_skill(args: Dict[str, Any]) -> Dict[str, Any]:
    """スキルを実行"""
    from runner.orchestrator import run_skill_with_chain

    skill = args.get("skill", "research")
    query = args.get("query", "")

    task = {
        "task_id": f"approved_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "selected_skill": skill,
        "query": query,
        "status": "queued",
    }

    result = run_skill_with_chain(task)
    return {
        "ok": result.get("status") == "completed",
        "status": result.get("status"),
        "chain_count": result.get("chain_count", 0),
    }


def _execute_task(args: Dict[str, Any]) -> Dict[str, Any]:
    """タスクを実行"""
    from tools.entrypoint import run_task_action

    return run_task_action(args)


def execute_and_log(
    state_root: Path,
    *,
    fingerprint: str,
    action: str,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """アクションを実行してログに記録"""
    timestamp = datetime.now(timezone.utc).isoformat()

    result = execute_approved_action(action, args)

    append_execution_log(
        state_root,
        timestamp=timestamp,
        fingerprint=fingerprint,
        action=action,
        args=args,
        result=result,
    )

    return {
        "ok": result.get("ok", False),
        "status": result.get("status", "unknown"),
        "fingerprint": fingerprint,
        "action": action,
        "execution_result": result,
    }


def _execute_proactive_task(action: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Proactiveタスクを実行
    
    proactive_exploration, proactive_maintenance, proactive_improvement を処理
    """
    from runner.orchestrator import run_skill_with_chain
    
    skill = args.get("skill")
    query = args.get("query")
    context = args.get("context", {})
    
    if not skill or not query:
        return {
            "ok": False,
            "status": "missing_skill_or_query",
            "action": action,
        }
    
    task = {
        "skill": skill,
        "query": query,
        "context": context,
        "source": "proactive",
        "proactive_action": action,
    }
    
    try:
        result = run_skill_with_chain(task)
        return {
            "ok": True,
            "status": "executed",
            "action": action,
            "skill": skill,
            "result": result,
        }
    except Exception as e:
        return {
            "ok": False,
            "status": "execution_failed",
            "action": action,
            "error": str(e),
        }
