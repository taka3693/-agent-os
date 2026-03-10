#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


BASE_DIR = Path(__file__).resolve().parent.parent
ROUTER = BASE_DIR / "bridge" / "route_to_task.py"
ORCH = BASE_DIR / "orchestrator" / "run_chain.py"


def python_cmd() -> str:
    if sys.executable:
        return sys.executable
    found = shutil.which("python3") or shutil.which("python")
    if found:
        return found
    return "/usr/bin/python3"


def child_env() -> Dict[str, str]:
    env = os.environ.copy()
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(BASE_DIR) if not prev else f"{str(BASE_DIR)}:{prev}"
    return env


def run_json(cmd: list[str], stdin_obj: Dict[str, Any] | None = None) -> Dict[str, Any]:
    proc = subprocess.run(
        cmd,
        input=(json.dumps(stdin_obj, ensure_ascii=False) if stdin_obj is not None else None),
        text=True,
        capture_output=True,
        cwd=str(BASE_DIR),
        env=child_env(),
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    out = proc.stdout.strip().splitlines()
    if not out:
        raise RuntimeError(f"no stdout from command: {' '.join(cmd)}")

    return json.loads(out[-1])


def load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text())


def summarize_final(root_task_path: str, final_task_path: str) -> Dict[str, Any]:
    root = load_json(root_task_path)
    final = load_json(final_task_path)

    return {
        "ok": True,
        "root_task_id": root.get("task_id"),
        "root_selected_skill": root.get("selected_skill"),
        "root_status": root.get("status"),
        "final_task_id": final.get("task_id"),
        "final_selected_skill": final.get("selected_skill"),
        "final_status": final.get("status"),
        "final_summary": (final.get("result") or {}).get("summary"),
        "root_task_path": root_task_path,
        "final_task_path": final_task_path,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_agent_os_request.py 'aos decision: ...' [source]", file=sys.stderr)
        return 2

    py = python_cmd()
    text = sys.argv[1]
    source = sys.argv[2] if len(sys.argv) >= 3 else "telegram"

    req = {
        "text": text,
        "source": source,
        "chain_count": 0,
    }

    routed = run_json([py, str(ROUTER)], req)
    root_task_path = routed["task_path"]

    chained = run_json([py, str(ORCH), root_task_path])
    final_task_path = chained["final_task_path"]

    summary = summarize_final(root_task_path, final_task_path)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
