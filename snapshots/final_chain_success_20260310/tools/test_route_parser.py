#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

ROUTER = Path("/home/milky/agent-os/bridge/route_to_task.py")
TASK_DIR = Path("/home/milky/agent-os/state/tasks")

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

def assert_case(name, payload, expected_query, expected_allowed, expected_ok=True, expected_error_substr=None):
    p = run_router(payload)

    if expected_ok:
        if p.returncode != 0:
            fail(f"{name}: router returned non-zero", returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)

        try:
            out = json.loads(p.stdout)
        except Exception as e:
            fail(f"{name}: stdout is not valid JSON", stdout=p.stdout, stderr=p.stderr, detail=str(e))

        if not out.get("ok"):
            fail(f"{name}: expected ok=true", output=out)

        task_path = out.get("task_path")
        if not task_path:
            fail(f"{name}: task_path missing", output=out)

        task = load_task(task_path)
        query = ((task.get("run_input") or {}).get("query"))
        allowed = task.get("allowed_skills")

        if query != expected_query:
            fail(f"{name}: unexpected query", expected=expected_query, actual=query, task=task)

        if allowed != expected_allowed:
            fail(f"{name}: unexpected allowed_skills", expected=expected_allowed, actual=allowed, task=task)

        return {
            "name": name,
            "ok": True,
            "task_path": task_path,
            "query": query,
            "allowed_skills": allowed,
            "selected_skill": task.get("selected_skill"),
        }

    else:
        if p.returncode == 0:
            try:
                out = json.loads(p.stdout)
            except Exception:
                out = {"stdout": p.stdout}
            fail(f"{name}: expected failure but got success", output=out, stderr=p.stderr)

        try:
            out = json.loads(p.stdout)
        except Exception as e:
            fail(f"{name}: failure stdout is not valid JSON", stdout=p.stdout, stderr=p.stderr, detail=str(e))

        if out.get("ok") is not False:
            fail(f"{name}: expected ok=false", output=out)

        err = out.get("error", "")
        if expected_error_substr and expected_error_substr not in err:
            fail(f"{name}: error mismatch", expected_substr=expected_error_substr, actual=err, output=out)

        return {
            "name": name,
            "ok": True,
            "error": err,
        }

def main():
    if not ROUTER.exists():
        fail("route_to_task.py not found", path=str(ROUTER))

    results = []

    base = {
        "source": "telegram",
        "chain_count": 0,
        "allowed_skills": None,
    }

    results.append(assert_case(
        "aos_plain",
        {**base, "text": "aos: 比較して整理したい"},
        expected_query="比較して整理したい",
        expected_allowed=None,
        expected_ok=True,
    ))

    results.append(assert_case(
        "aos_research",
        {**base, "text": "aos research: 比較して整理したい"},
        expected_query="比較して整理したい",
        expected_allowed=["research"],
        expected_ok=True,
    ))

    results.append(assert_case(
        "aos_unknown",
        {**base, "text": "aos unknown: hello"},
        expected_query=None,
        expected_allowed=None,
        expected_ok=False,
        expected_error_substr="unknown skill prefix: unknown",
    ))

    print(json.dumps({
        "ok": True,
        "cases": results
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
