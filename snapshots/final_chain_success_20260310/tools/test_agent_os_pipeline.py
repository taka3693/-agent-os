#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/milky/agent-os")
ROUTER = ROOT / "bridge" / "route_to_task.py"
RUNNER = ROOT / "runner" / "run_research_task.py"
TASKS = ROOT / "state" / "tasks"

def fail(msg, **kw):
    print(json.dumps({"ok": False, "error": msg, **kw}, ensure_ascii=False, indent=2))
    raise SystemExit(1)

def run(cmd, *, input_text=None):
    p = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        encoding="utf-8"
    )
    return p

def newest_task_before():
    xs = sorted(TASKS.glob("task-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(xs[0]) if xs else None

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    if not ROUTER.exists():
        fail("route_to_task.py not found", path=str(ROUTER))
    if not RUNNER.exists():
        fail("run_research_task.py not found", path=str(RUNNER))
    TASKS.mkdir(parents=True, exist_ok=True)

    before = newest_task_before()

    payload = {
        "text": "aos local pipeline test: 比較して整理したい",
        "source": "telegram",
        "chain_count": 0,
        "allowed_skills": None
    }

    p1 = run(["python3", str(ROUTER)], input_text=json.dumps(payload, ensure_ascii=False))
    if p1.returncode != 0:
        fail("route_to_task.py failed", returncode=p1.returncode, stdout=p1.stdout, stderr=p1.stderr)

    try:
        bridge_out = json.loads(p1.stdout)
    except Exception as e:
        fail("route_to_task.py stdout is not valid JSON", stdout=p1.stdout, stderr=p1.stderr, detail=str(e))

    task_path = bridge_out.get("task_path")
    if not task_path:
        fail("task_path missing from bridge output", bridge_output=bridge_out)

    task_file = Path(task_path)
    if not task_file.exists():
        fail("task file not found", task_path=task_path)

    queued = load_json(task_file)
    if queued.get("status") != "queued":
        fail("expected queued after bridge", task=queued)

    p2 = run(["python3", str(RUNNER), task_path])
    if p2.returncode != 0:
        fail("run_research_task.py failed", returncode=p2.returncode, stdout=p2.stdout, stderr=p2.stderr, task_path=task_path)

    done = load_json(task_file)

    status = done.get("status")
    selected_skill = done.get("selected_skill")
    summary = ((done.get("result") or {}).get("summary"))
    findings = ((done.get("result") or {}).get("findings"))

    if status != "completed":
        fail("expected completed after runner", task=done)
    if selected_skill != "research":
        fail("unexpected selected_skill", selected_skill=selected_skill, task=done)
    if not summary or not isinstance(summary, str):
        fail("summary missing", task=done)
    if findings is None:
        fail("findings missing", task=done)

    print(json.dumps({
        "ok": True,
        "task_path": task_path,
        "before_latest_task": before,
        "status": status,
        "selected_skill": selected_skill,
        "summary": summary,
        "findings_count": len(findings) if isinstance(findings, list) else None
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
