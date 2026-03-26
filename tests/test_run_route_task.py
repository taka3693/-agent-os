#!/usr/bin/env python3
import json
import subprocess
import uuid
from pathlib import Path

BASE_DIR = Path("/home/milky/agent-os")
TASKS_DIR = BASE_DIR / "state" / "tasks"
RUNNER = BASE_DIR / "runner" / "run_route_task.py"


def make_task(handler: str = "handle_direct_install", chosen_route: str = "direct_install", target: str = "scrapling") -> Path:
    task_id = f"task-route-{uuid.uuid4().hex[:8]}"
    p = TASKS_DIR / f"{task_id}.json"
    action = "direct install path for scrapling" if handler == "handle_direct_install" else "clawhub install path for scrapling"
    obj = {
        "task_id": task_id,
        "status": "completed",
        "route_execution": {
            "status": "planned",
            "action": action,
            "handler": handler,
            "chosen_route": chosen_route,
            "target": target,
        },
    }
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def _run_and_assert(task_path: Path, expected_handler: str, expected_route: str, expected_summary: str, expected_command: str) -> None:
    cp = subprocess.run(
        ["python3", str(RUNNER), str(task_path)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 0, cp.stdout + "\n" + cp.stderr

    out = json.loads(cp.stdout)
    assert out["route_execution"]["status"] == "simulated_done"
    assert out["route_result"]["route_handler"] == expected_handler
    assert out["route_result"]["chosen_route"] == expected_route
    assert out["route_result"]["next_command"] == expected_command
    assert out["route_result"]["policy"]["allowed"] is True
    assert out["route_result"]["policy"]["dry_run"] is True

    task = json.loads(task_path.read_text(encoding="utf-8"))
    assert task["route_execution"]["status"] == "simulated_done"
    assert task["route_execution"]["policy"]["allowed"] is True
    assert task["route_result"]["summary"] == expected_summary


def main() -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    direct_task = make_task(handler="handle_direct_install", chosen_route="direct_install")
    clawhub_task = make_task(handler="handle_clawhub_skill", chosen_route="clawhub_skill")
    try:
        _run_and_assert(
            direct_task,
            expected_handler="handle_direct_install",
            expected_route="direct_install",
            expected_summary="scrapling を直接導入する実行計画を確認",
            expected_command="pip install scrapling",
        )
        _run_and_assert(
            clawhub_task,
            expected_handler="handle_clawhub_skill",
            expected_route="clawhub_skill",
            expected_summary="scrapling を ClawHub 経由で導入する実行計画を確認",
            expected_command="clawhub install scrapling-official",
        )

        blocked_task = make_task(handler="handle_direct_install", chosen_route="direct_install", target="unknownpkg")
        try:
            cp = subprocess.run(
                ["python3", str(RUNNER), str(blocked_task)],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                check=False,
            )
            assert cp.returncode == 0, cp.stdout + "\n" + cp.stderr
            out = json.loads(cp.stdout)
            assert out["route_execution"]["status"] == "approval_required"
            assert out["route_result"]["policy"]["allowed"] is False
            assert out["route_result"]["summary"] == "unknownpkg は allowlist 外のため確認待ち"
            blocked_saved = json.loads(blocked_task.read_text(encoding="utf-8"))
            assert blocked_saved["approval_state"]["status"] == "approval_required"
            assert blocked_saved["approval_state"]["route_handler"] == "handle_direct_install"
            assert blocked_saved["approval_state"]["target"] == "unknownpkg"

            approve_cp = subprocess.run(
                ["python3", str(RUNNER), str(blocked_task), "approve"],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                check=False,
            )
            assert approve_cp.returncode == 0, approve_cp.stdout + "\n" + approve_cp.stderr
            approved = json.loads(approve_cp.stdout)
            assert approved["approval_state"]["status"] == "approved"
            assert approved["route_execution"]["status"] == "planned"
            assert approved["route_result"]["status"] == "approved"

            reject_task = make_task(handler="handle_direct_install", chosen_route="direct_install", target="anotherpkg")
            reject_cp0 = subprocess.run(
                ["python3", str(RUNNER), str(reject_task)],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                check=False,
            )
            assert reject_cp0.returncode == 0, reject_cp0.stdout + "\n" + reject_cp0.stderr
            reject_cp = subprocess.run(
                ["python3", str(RUNNER), str(reject_task), "reject"],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                check=False,
            )
            assert reject_cp.returncode == 0, reject_cp.stdout + "\n" + reject_cp.stderr
            rejected = json.loads(reject_cp.stdout)
            assert rejected["approval_state"]["status"] == "rejected"
            assert rejected["route_execution"]["status"] == "rejected"
            assert rejected["route_result"]["status"] == "rejected"
        finally:
            for p in (blocked_task, locals().get("reject_task")):
                if p and Path(p).exists():
                    Path(p).unlink()

        print("PASS: run_route_task OK")
    finally:
        for task_path in (direct_task, clawhub_task):
            if task_path.exists():
                task_path.unlink()


if __name__ == "__main__":
    main()
