#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SAFE_DIRECT_INSTALL_TARGETS = {"scrapling"}
SAFE_CLAWHUB_TARGETS = {"scrapling"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_route_execution(task: Dict[str, Any]) -> Dict[str, Any]:
    route_execution = task.get("route_execution")
    if not isinstance(route_execution, dict):
        raise ValueError("route_execution not found")
    return route_execution


def _simulate_direct_install(target: str, action: str) -> Dict[str, Any]:
    return {
        "summary": f"{target} を直接導入する実行計画を確認",
        "status": "simulated_done",
        "next_command": f"pip install {target}" if target else "pip install <target>",
        "notes": [action, "direct install simulation only"],
    }


def _simulate_clawhub_install(target: str, action: str) -> Dict[str, Any]:
    skill_name = f"{target}-official" if target else "<skill>"
    return {
        "summary": f"{target} を ClawHub 経由で導入する実行計画を確認",
        "status": "simulated_done",
        "next_command": f"clawhub install {skill_name}",
        "notes": [action, "clawhub install simulation only"],
    }


def evaluate_route_policy(route_execution: Dict[str, Any]) -> Dict[str, Any]:
    handler = str(route_execution.get("handler") or "").strip()
    target = str(route_execution.get("target") or "").strip()
    dry_run = os.environ.get("AGENTOS_ROUTE_DRY_RUN", "1") != "0"

    if handler == "handle_direct_install":
        allowed = target in SAFE_DIRECT_INSTALL_TARGETS
    elif handler == "handle_clawhub_skill":
        allowed = target in SAFE_CLAWHUB_TARGETS
    else:
        allowed = False

    return {
        "allowed": allowed,
        "dry_run": dry_run,
        "policy": "allowlist_only",
        "approval_required": not allowed or not dry_run,
    }


def run_route_execution(route_execution: Dict[str, Any]) -> Dict[str, Any]:
    action = str(route_execution.get("action") or "").strip()
    handler = str(route_execution.get("handler") or "").strip()
    chosen_route = str(route_execution.get("chosen_route") or "").strip()
    target = str(route_execution.get("target") or "").strip()

    if not action:
        raise ValueError("route action is empty")

    policy = evaluate_route_policy(route_execution)
    if not policy["allowed"]:
        result = {
            "summary": f"{target or 'target'} は allowlist 外のため確認待ち",
            "status": "approval_required",
            "notes": [action, "blocked by allowlist"],
        }
    elif handler == "handle_direct_install":
        result = _simulate_direct_install(target, action)
    elif handler == "handle_clawhub_skill":
        result = _simulate_clawhub_install(target, action)
    else:
        result = {
            "summary": f"{target or 'target'} の route 実行計画を確認",
            "status": "simulated_done",
            "notes": [action],
        }

    result["route_action"] = action
    result["route_handler"] = handler
    result["chosen_route"] = chosen_route
    result["target"] = target
    result["policy"] = policy
    result.setdefault("artifacts", [])
    return result


def apply_approval_decision(task_path: Path, decision: str) -> Dict[str, Any]:
    task = load_json(task_path)
    approval_state = task.get("approval_state")
    if not isinstance(approval_state, dict):
        raise ValueError("approval_state not found")

    normalized = (decision or "").strip().lower()
    if normalized not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")

    task["approval_state"]["status"] = "approved" if normalized == "approve" else "rejected"
    task["approval_state"]["decided_at"] = utc_now()
    task["approval_state"]["decision"] = normalized

    if normalized == "approve":
        if isinstance(task.get("route_execution"), dict):
            task["route_execution"]["status"] = "planned"
        task["route_result"] = {
            "status": "approved",
            "summary": "承認を受けて route 実行へ戻す",
            "route_handler": approval_state.get("route_handler"),
            "target": approval_state.get("target"),
        }
    else:
        if isinstance(task.get("route_execution"), dict):
            task["route_execution"]["status"] = "rejected"
        task["route_result"] = {
            "status": "rejected",
            "summary": "承認が見送られたため route 実行を停止",
            "route_handler": approval_state.get("route_handler"),
            "target": approval_state.get("target"),
        }

    save_json(task_path, task)
    return {
        "task_id": task.get("task_id") or task_path.stem,
        "approval_state": task.get("approval_state"),
        "route_execution": task.get("route_execution"),
        "route_result": task.get("route_result"),
    }


def run_task(task_path: Path) -> Dict[str, Any]:
    task = load_json(task_path)
    task_id = task.get("task_id") or task_path.stem

    task["route_execution_started_at"] = utc_now()
    save_json(task_path, task)

    route_execution = extract_route_execution(task)
    result = run_route_execution(route_execution)

    task["route_execution"] = dict(route_execution)
    task["route_execution"]["status"] = result["status"]
    task["route_execution"]["completed_at"] = utc_now()
    task["route_execution"]["policy"] = result.get("policy")
    task["route_result"] = result
    task["route_execution_error"] = None
    if result.get("status") == "approval_required":
        task["approval_state"] = {
            "status": "approval_required",
            "reason": result.get("summary"),
            "route_handler": result.get("route_handler"),
            "target": result.get("target"),
            "created_at": utc_now(),
        }
    else:
        task["approval_state"] = None
    save_json(task_path, task)
    return {
        "task_id": task_id,
        "route_execution": task["route_execution"],
        "route_result": task["route_result"],
    }


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print("usage: run_route_task.py /home/milky/agent-os/state/tasks/task-xxxx.json [approve|reject]", file=sys.stderr)
        return 2

    task_path = Path(sys.argv[1]).resolve()
    if not task_path.exists():
        print(f"task not found: {task_path}", file=sys.stderr)
        return 2

    if len(sys.argv) == 3:
        out = apply_approval_decision(task_path, sys.argv[2])
    else:
        out = run_task(task_path)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
