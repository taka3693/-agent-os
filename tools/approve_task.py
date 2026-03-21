from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path("/home/milky/agent-os")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.config import AWAITING_APPROVAL_DIR, FAILED_DIR, QUEUED_DIR, ensure_dirs  # noqa: E402

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def _save(path: Path, payload: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def list_tasks(status: str = "awaiting_approval") -> List[Dict[str, Any]]:
    ensure_dirs()
    target_dir = {
        "queued": QUEUED_DIR,
        "awaiting_approval": AWAITING_APPROVAL_DIR,
        "failed": FAILED_DIR,
    }.get(status, AWAITING_APPROVAL_DIR)

    rows = []
    for task_file in sorted(target_dir.glob("*.json")):
        task = _load(task_file)
        rows.append(
            {
                "task_id": task.get("task_id"),
                "status": task.get("status"),
                "target_basename": task.get("args", {}).get("target_basename"),
                "approval_required": task.get("approval_required"),
                "audit_reason": task.get("audit_reason"),
            }
        )
    return rows

def approve_task(task_id: str, approved_by: str = "cli") -> Path:
    ensure_dirs()
    src = AWAITING_APPROVAL_DIR / f"{task_id}.json"
    if not src.exists():
        raise FileNotFoundError(f"task not found in awaiting_approval: {task_id}")

    task = _load(src)
    task["approved"] = True
    task["approved_at"] = _now_iso()
    task["approved_by"] = approved_by
    task["status"] = "queued"
    task["updated_at"] = _now_iso()

    dst = QUEUED_DIR / src.name
    _save(dst, task)
    src.unlink()
    return dst

def reject_task(task_id: str, reason: str = "rejected by user") -> Path:
    ensure_dirs()
    src = AWAITING_APPROVAL_DIR / f"{task_id}.json"
    if not src.exists():
        raise FileNotFoundError(f"task not found in awaiting_approval: {task_id}")

    task = _load(src)
    task["approved"] = False
    task["error"] = reason
    task["status"] = "failed"
    task["ended_at"] = _now_iso()
    task["updated_at"] = _now_iso()

    dst = FAILED_DIR / src.name
    _save(dst, task)
    src.unlink()
    return dst

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--status", default="awaiting_approval")

    p_approve = sub.add_parser("approve")
    p_approve.add_argument("task_id")
    p_approve.add_argument("--by", default="cli")

    p_reject = sub.add_parser("reject")
    p_reject.add_argument("task_id")
    p_reject.add_argument("--reason", default="rejected by user")

    args = parser.parse_args()

    if args.cmd == "list":
        print(json.dumps(list_tasks(args.status), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "approve":
        dst = approve_task(args.task_id, approved_by=args.by)
        print(dst)
        return 0

    if args.cmd == "reject":
        dst = reject_task(args.task_id, reason=args.reason)
        print(dst)
        return 0

    return 1

if __name__ == "__main__":
    raise SystemExit(main())
