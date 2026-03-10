#!/usr/bin/env python3
import importlib.util
import json
import subprocess
from pathlib import Path

BASE_DIR = Path("/home/milky/agent-os")
BRIDGE = BASE_DIR / "bridge" / "route_to_task.py"
REQ = BASE_DIR / "tools" / "run_agent_os_request.py"

def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_choose_skill():
    mod = load(BRIDGE, "route_to_task")
    skill, reason = mod.choose_skill("AとBを比較して決めたい")
    assert skill == "decision"
    assert reason == "decision_keyword_match"

    skill, reason = mod.choose_skill("調査して整理したい")
    assert skill == "research"
    assert reason == "keyword match"

def test_router_decision_autorun():
    cp = subprocess.run(
        ["python3", str(REQ), "aos router AとBを比較して決めたい"],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 0, cp.stdout + "\n" + cp.stderr
    out = json.loads(cp.stdout)

    assert out["ok"] is True
    assert out["mode"] == "router"
    assert out["status"] == "completed"
    assert out["selected_skill"] == "decision"
    assert out["route_reason"] == "decision_keyword_match"
    assert isinstance(out.get("runner_result"), dict)
    assert out["runner_result"]["ok"] is True
    assert out["runner_result"]["selected_skill"] == "decision"

    task_path = Path(out["task_path"])
    task = json.loads(task_path.read_text(encoding="utf-8"))
    assert task["selected_skill"] == "decision"

    assert isinstance(out.get("task_result"), dict)
    assert "summary" in out["task_result"]
    assert "findings" in out["task_result"]

if __name__ == "__main__":
    test_choose_skill()
    test_router_decision_autorun()
    print("PASS: Step79 router policy OK")
