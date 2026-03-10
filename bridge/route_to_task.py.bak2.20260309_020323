#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from datetime import datetime, timezone


def resolve_base_dir() -> Path:
    # 想定配置: ~/agent-os/bridge/route_to_task.py
    # 親の親 = ~/agent-os
    return Path(__file__).resolve().parent.parent


BASE_DIR = resolve_base_dir()

# router importのために最小追加
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Router import (確定仕様)
from router.router import route, RouteResult  # noqa: E402,F401


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def yyyymmdd_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def ensure_tasks_dir(base_dir: Path) -> Path:
    tasks_dir = base_dir / "state" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return tasks_dir


def next_task_id(tasks_dir: Path, date_str: str) -> str:
    # 既存: task-YYYYMMDD-XXX.json
    prefix = f"task-{date_str}-"
    max_seq = 0
    for p in tasks_dir.glob(f"{prefix}*.json"):
        stem = p.stem  # task-YYYYMMDD-XXX
        parts = stem.split("-")
        if len(parts) != 3:
            continue
        seq = parts[2]
        if seq.isdigit():
            max_seq = max(max_seq, int(seq))
    return f"task-{date_str}-{max_seq + 1:03d}"


def build_task_payload(
    task_id: str,
    ts: str,
    source: str,
    text: str,
    selected_skill,
    route_reason: str,
    chain_count: int,
):
    return {
        "task_id": task_id,
        "created_at": ts,
        "updated_at": ts,
        "source": source,
        "input_text": text,
        "selected_skill": selected_skill,
        "route_reason": route_reason,
        "status": "queued",
        "chain_count": chain_count,
        "run_input": {"query": text},
        "result": None,
        "error": None,
    }


def read_stdin_json() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("empty stdin")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("stdin JSON must be an object")
    return obj


def main() -> int:
    try:
        tasks_dir = ensure_tasks_dir(BASE_DIR)
        req = read_stdin_json()

        text = req.get("text", "")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")

        allowed = req.get("allowed_skills")
        if allowed is not None:
            if not isinstance(allowed, list) or not all(isinstance(x, str) for x in allowed):
                raise ValueError("allowed_skills must be list[str] or null")

        chain_count = req.get("chain_count", 0)
        if not isinstance(chain_count, int):
            raise ValueError("chain_count must be int")

        source = req.get("source", "telegram")
        if not isinstance(source, str) or not source.strip():
            source = "telegram"

        rr = route(text, allowed, chain_count)

        date_str = yyyymmdd_utc()
        task_id = next_task_id(tasks_dir, date_str)
        ts = now_iso()

        task_payload = build_task_payload(
            task_id=task_id,
            ts=ts,
            source=source,
            text=text,
            selected_skill=rr.skill,
            route_reason=rr.reason,
            chain_count=chain_count,
        )

        task_path = tasks_dir / f"{task_id}.json"
        with task_path.open("w", encoding="utf-8") as f:
            json.dump(task_payload, f, ensure_ascii=False, indent=2)
            f.write("\n")

        selected = rr.skill if rr.skill is not None else "none"
        out = {
            "ok": True,
            "selected_skill": rr.skill,
            "route_reason": rr.reason,
            "task_id": task_id,
            "task_path": str(task_path),
            "reply": f"routed={selected} task={task_id}",
        }
        print(json.dumps(out, ensure_ascii=False))
        return 0

    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
