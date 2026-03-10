#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

ROUTER = Path("/home/milky/agent-os/bridge/route_to_task.py")

def fail(msg, **kw):
    print(json.dumps({"ok": False, "error": msg, **kw}, ensure_ascii=False, indent=2))
    raise SystemExit(1)

def run_router(payload):
    p = subprocess.run(
        ["python3", str(ROUTER)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        encoding="utf-8"
    )
    return p

def load_task(path_str):
    with open(path_str, "r", encoding="utf-8") as f:
        return json.load(f)

def check_case(name, text, expected_skill, expected_model):
    payload = {
        "text": text,
        "source": "telegram",
        "chain_count": 0,
        "allowed_skills": None,
    }
    p = run_router(payload)
    if p.returncode != 0:
        fail(f"{name}: router failed", returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)

    try:
        out = json.loads(p.stdout)
    except Exception as e:
        fail(f"{name}: invalid stdout json", stdout=p.stdout, stderr=p.stderr, detail=str(e))

    if not out.get("ok"):
        fail(f"{name}: ok=false", output=out)

    task_path = out.get("task_path")
    if not task_path:
        fail(f"{name}: task_path missing", output=out)

    task = load_task(task_path)

    actual_skill = task.get("selected_skill")
    actual_model = task.get("model")
    actual_query = ((task.get("run_input") or {}).get("query"))

    if actual_skill != expected_skill:
        fail(f"{name}: skill mismatch", expected=expected_skill, actual=actual_skill, task=task)

    if actual_model != expected_model:
        fail(f"{name}: model mismatch", expected=expected_model, actual=actual_model, task=task)

    return {
        "name": name,
        "task_path": task_path,
        "skill": actual_skill,
        "model": actual_model,
        "query": actual_query,
    }

def main():
    if not ROUTER.exists():
        fail("route_to_task.py not found", path=str(ROUTER))

    cases = []
    cases.append(check_case(
        "research_default",
        "aos research: モデル割り当てテスト",
        "research",
        "zai/glm-5",
    ))
    cases.append(check_case(
        "aos_plain_default",
        "aos: 比較して整理したい",
        "research",
        "zai/glm-5",
    ))

    print(json.dumps({
        "ok": True,
        "cases": cases
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
