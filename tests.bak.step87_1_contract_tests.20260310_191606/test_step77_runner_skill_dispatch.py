#!/usr/bin/env python3
import importlib.util
from pathlib import Path

RUNNER = Path("/home/milky/agent-os/runner/run_task_once.py")

spec = importlib.util.spec_from_file_location("run_task_once", str(RUNNER))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def main() -> None:
    assert isinstance(mod.SKILL_MODULES, dict)
    assert "research" in mod.SKILL_MODULES

    out = mod.dispatch_skill("research", "比較して整理したい")
    assert isinstance(out, dict)
    assert "summary" in out
    assert "findings" in out
    assert isinstance(out["findings"], list)

    task = {
        "status": "queued",
        "selected_skill": "research",
        "query": "比較して整理したい",
    }
    executed = mod.execute_task(task)
    assert executed["selected_skill"] == "research"
    assert executed["query"] == "比較して整理したい"
    assert isinstance(executed["result"], dict)
    assert "summary" in executed["result"]
    assert "findings" in executed["result"]

    print("PASS: Step77 runner skill dispatch OK")

if __name__ == "__main__":
    main()
