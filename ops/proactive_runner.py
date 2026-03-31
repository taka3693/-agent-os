"""Proactive Runner - 能動的タスク生成の実行エントリポイント

観察 → タスク生成 → 承認キュー登録 のサイクルを実行。
cronやタイマーから定期実行されることを想定。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ops.proactive_observer import observe_system
from ops.proactive_generator import generate_proactive_tasks
from ops.approval_queue import append_approval_queue_entry


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_proactive_cycle(
    state_root: Path,
    tasks_root: Path,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """能動的タスク生成サイクルを実行
    
    Args:
        state_root: state/ディレクトリのパス
        tasks_root: タスクディレクトリのパス
        dry_run: Trueの場合、承認キューに登録せず結果のみ返す
    
    Returns:
        サイクル実行結果
    """
    cycle_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    
    # 1. 観察
    observations = observe_system(state_root, tasks_root)
    
    # 2. タスク生成
    generated_tasks = generate_proactive_tasks(observations)
    
    # 3. 承認キューに登録（要承認タスクのみ）
    queued_tasks = []
    skipped_tasks = []
    
    for task in generated_tasks:
        if task.get("requires_approval", True):
            if not dry_run:
                # 承認キューに登録
                append_approval_queue_entry(
                    state_root=state_root,
                    timestamp=utc_now_iso(),
                    fingerprint=task["id"],
                    action=f"proactive_{task['type']}",
                    args={
                        "skill": task.get("skill"),
                        "query": task.get("query"),
                        "context": task.get("context"),
                        "priority": task.get("priority"),
                    },
                    policy="proactive_task",
                    reason=f"Proactive: {task.get('context', {}).get('trigger', 'unknown')}",
                    source="proactive_runner",
                )
            queued_tasks.append(task)
        else:
            skipped_tasks.append(task)
    
    # 4. 結果を記録
    result = {
        "cycle_id": cycle_id,
        "executed_at": utc_now_iso(),
        "dry_run": dry_run,
        "observations_summary": {
            "health_status": observations.get("health", {}).get("status"),
            "health_issues": len(observations.get("health", {}).get("issues", [])),
            "failure_patterns": len(observations.get("failures", {}).get("patterns", [])),
            "learning_insights": len(observations.get("learning", {}).get("insights", [])),
            "is_idle": observations.get("idle", {}).get("is_idle"),
        },
        "generated_tasks": len(generated_tasks),
        "queued_for_approval": len(queued_tasks),
        "skipped_no_approval": len(skipped_tasks),
        "tasks": generated_tasks,
    }
    
    # ログに記録
    if not dry_run:
        log_file = state_root / "proactive_cycles.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    
    return result


def get_proactive_status(state_root: Path) -> Dict[str, Any]:
    """直近のProactiveサイクル状態を取得"""
    log_file = state_root / "proactive_cycles.jsonl"
    if not log_file.exists():
        return {"status": "no_history", "last_cycle": None}
    
    try:
        lines = log_file.read_text().strip().split("\n")
        if not lines or not lines[-1]:
            return {"status": "no_history", "last_cycle": None}
        
        last_cycle = json.loads(lines[-1])
        return {
            "status": "active",
            "last_cycle": last_cycle,
            "total_cycles": len(lines),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
