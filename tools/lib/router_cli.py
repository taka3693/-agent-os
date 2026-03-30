from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def parse_bridge_stdout_json(raw: str) -> Dict[str, Any]:
    text = "" if raw is None else str(raw).strip()
    if not text:
        raise ValueError("empty stdout")

    candidates = [text]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        candidates.append(lines[-1])
        if len(lines) > 1:
            candidates.append("".join(lines))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start <= end:
        candidates.append(text[start:end + 1])

    seen = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    raise ValueError(f"bridge stdout is not valid json: {text[:500]}")


def run_router_command_core(
    query: str,
    *,
    base_dir: Path,
    tasks_dir: Path,
) -> Dict[str, Any]:
    bridge_script = base_dir / "bridge" / "route_to_task.py"
    if not bridge_script.exists():
        return {
            "ok": False,
            "mode": "router",
            "status": "bridge_missing",
            "reason": "bridge_missing",
            "router_result": {},
            "reply_text": f"router 実行失敗\n理由: bridge が存在しません\npath: {bridge_script}",
            "telegram_send": None,
            "telegram_reply_text": f"router 実行失敗\n理由: bridge が存在しません\npath: {bridge_script}",
        }

    cp = subprocess.run(
        [sys.executable, str(bridge_script), str(query or "")],
        capture_output=True,
        text=True,
    )

    stdout = (cp.stdout or "").strip()
    stderr = (cp.stderr or "").strip()

    try:
        route_obj = parse_bridge_stdout_json(stdout)
    except Exception:
        return {
            "ok": False,
            "mode": "router",
            "status": "bridge_invalid_json",
            "reason": "router_invalid_json",
            "router_result": {},
            "reply_text": "router 実行失敗\n理由: bridge 出力が JSON ではありません\nstdout: " + (stdout or "(empty)"),
            "telegram_send": None,
            "telegram_reply_text": "router 実行失敗\n理由: bridge 出力が JSON ではありません\nstdout: " + (stdout or "(empty)"),
        }

    if cp.returncode != 0 or route_obj.get("ok") is False:
        err = route_obj.get("error") or stderr or stdout or "(empty)"
        return {
            "ok": False,
            "mode": "router",
            "status": "bridge_failed",
            "reason": "bridge_failed",
            "router_result": route_obj if isinstance(route_obj, dict) else {},
            "reply_text": f"router 実行失敗\n理由: bridge 実行エラー\n詳細: {err}",
            "telegram_send": None,
            "telegram_reply_text": f"router 実行失敗\n理由: bridge 実行エラー\n詳細: {err}",
        }

    selected_skill = route_obj.get("selected_skill") or "research"
    selected_skills = route_obj.get("selected_skills")
    if not isinstance(selected_skills, list) or not selected_skills:
        selected_skills = [selected_skill]

    route_reason = route_obj.get("route_reason") or (
        "fallback_research" if selected_skill == "research" else f"{selected_skill}_keyword_match"
    )

    route_obj = dict(route_obj)
    route_obj["selected_skill"] = selected_skill
    route_obj["selected_skills"] = selected_skills
    route_obj.setdefault("route_reason", route_reason)
    route_obj.setdefault("pipeline", {
        "primary_skill": selected_skill,
        "skill_chain": selected_skills,
        "chain_length": len(selected_skills),
        "max_chain": 3,
    })
    route_obj.setdefault("plan", {
        "goal": str(query or ""),
        "steps": [{"skill": selected_skill, "purpose": "router step", "done_when": "route selected"}],
        "step_count": len(selected_skills),
        "mode": "autonomous_planning",
    })
    route_obj.setdefault("planning_mode", "autonomous")

    now = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    task_id = route_obj.get("task_id")
    if not isinstance(task_id, str) or not task_id.startswith("task-"):
        task_id = f"task-{now}"

    task_path = tasks_dir / f"{task_id}.json"
    route_obj["task_id"] = task_id
    route_obj["task_path"] = str(task_path)

    task_obj = {
        "task_id": task_id,
        "status": "completed",
        "query": str(query or ""),
        "selected_skill": selected_skill,
        "selected_skills": selected_skills,
        "route_reason": route_reason,
        "router_result": route_obj,
        "pipeline": route_obj.get("pipeline"),
        "plan": route_obj.get("plan"),
        "planning_mode": route_obj.get("planning_mode", "autonomous"),
        "result": {
            "summary": route_obj.get("reply_text") or "",
            "findings": [],
        },
    }
    task_path.write_text(json.dumps(task_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    bridge_reply = route_obj.get("reply_text") or (
        f"selected_skill={selected_skill} route_reason={route_reason}"
    )
    reply_text = (
        "router 受付完了\n"
        f"task: {task_id}\n"
        f"selected_skill: {selected_skill}\n"
        f"route_reason: {route_reason}\n"
        f"bridge: {bridge_reply}"
    )

    return {
        "ok": True,
        "mode": "router",
        "status": "completed",
        "task_id": task_id,
        "task_path": str(task_path),
        "selected_skill": selected_skill,
        "selected_skills": selected_skills,
        "route_reason": route_reason,
        "router_policy": route_obj.get("router_policy"),
        "pipeline": route_obj.get("pipeline"),
        "plan": route_obj.get("plan"),
        "planning_mode": route_obj.get("planning_mode", "autonomous"),
        "router_result": route_obj,
        "reply_text": reply_text,
        "telegram_send": None,
        "telegram_reply_text": reply_text,
    }


def run_router_command_with_optional_telegram(
    query: str,
    *,
    base_dir: Path,
    tasks_dir: Path,
    chat_id: str | int | None,
    send_telegram_message,
) -> Dict[str, Any]:
    out = run_router_command_core(query, base_dir=base_dir, tasks_dir=tasks_dir)

    if chat_id is None:
        return out

    if out.get("telegram_send") is not None:
        return out

    text = out.get("telegram_reply_text") or out.get("reply_text")
    if not isinstance(text, str) or not text.strip():
        return out

    out = dict(out)
    try:
        out["telegram_send"] = send_telegram_message(chat_id, text)
    except Exception as e:
        out["telegram_send"] = {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
        }
    return out


def router_cli_short_circuit(
    argv,
    *,
    run_router_command,
) -> int | None:
    args = list(sys.argv if argv is None else argv)
    norm = [str(x).strip() for x in args if str(x).strip()]
    low = [x.lower() for x in norm]

    router_idx = None
    for i, token in enumerate(low):
        if token in {"router", "route"}:
            router_idx = i
            break

    if router_idx is None:
        return None

    query = " ".join(norm[router_idx + 1:]).strip()

    for flag in ("--query", "--text", "-q", "-t"):
        if flag in low:
            j = low.index(flag)
            if j + 1 < len(norm):
                query = str(norm[j + 1]).strip()
                break

    out = run_router_command(query)
    rc = 0 if out.get("ok") else 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return rc


# =============================================================================
# Step91: Pipeline Executor
# =============================================================================

import tempfile
import time
from datetime import timezone


def _now_iso() -> str:
    """Return current timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Atomically write JSON to avoid partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as tmp:
        tmp.write(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _load_task(path: Path) -> Dict[str, Any]:
    """Load task JSON with error handling."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _init_task_state(
    task_id: str,
    query: str,
    selected_skill: str,
    skill_chain: List[str],
    source: str = "cli",
) -> Dict[str, Any]:
    """Initialize a new task state with Step91 schema."""
    now = _now_iso()
    return {
        "task_id": task_id,
        "status": "pending",
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "request": {
            "source": source,
            "text": query,
        },
        "plan": {
            "selected_skill": selected_skill,
            "skill_chain": skill_chain,
        },
        "execution": {
            "current_step_index": 0,
            "completed_steps": 0,
            "resume_count": 0,
        },
        "step_results": [],
    }


def _execute_single_step(
    task: Dict[str, Any],
    step_index: int,
    skill: str,
    step_fn,  # Callable[[Dict], Dict] - step implementation
    continue_on_error: bool = False,
) -> Dict[str, Any]:
    """Execute a single step and return updated task state.

    Args:
        task: Current task state
        step_index: 0-based step index
        skill: Skill name for this step
        step_fn: Function to execute (receives task, returns result dict)
        continue_on_error: Whether to continue on error

    Returns:
        Updated task state with step_result appended
    """
    started_at = _now_iso()
    start_time = time.time()

    step_result = {
        "step_index": step_index,
        "skill": skill,
        "status": "ok",
        "continue_on_error": continue_on_error,
        "started_at": started_at,
        "finished_at": None,
        "duration_ms": None,
        "output": {},
        "error_type": None,
        "error_message": None,
    }

    try:
        output = step_fn(task) if step_fn else {}
        if not isinstance(output, dict):
            output = {"raw": output}
        step_result["output"] = output
        step_result["status"] = "ok"
    except Exception as e:
        step_result["status"] = "error"
        step_result["error_type"] = type(e).__name__
        step_result["error_message"] = str(e)

    finished_at = _now_iso()
    step_result["finished_at"] = finished_at
    step_result["duration_ms"] = int((time.time() - start_time) * 1000)

    # Update task state
    task = dict(task)
    task["step_results"] = list(task.get("step_results", []))
    task["step_results"].append(step_result)

    execution = dict(task.get("execution", {}))
    execution["current_step_index"] = step_index + 1
    execution["completed_steps"] = len([r for r in task["step_results"] if r.get("status") == "ok"])
    task["execution"] = execution

    return task


def run_pipeline_executor(
    task_id: str,
    query: str,
    skill_chain: List[str],
    step_fns: List,  # List of callables, one per skill
    tasks_dir: Path,
    source: str = "cli",
    continue_on_error_chain: List[bool] | None = None,
) -> Dict[str, Any]:
    """Execute a pipeline of skills with proper state management.

    Args:
        task_id: Unique task identifier
        query: User query text
        skill_chain: List of skill names to execute
        step_fns: List of step functions (one per skill)
        tasks_dir: Directory to store task state
        source: Request source (cli, telegram, etc.)
        continue_on_error_chain: Per-step continue_on_error flags

    Returns:
        Final task state
    """
    if not skill_chain:
        skill_chain = ["research"]
    if not step_fns:
        step_fns = [None] * len(skill_chain)
    if continue_on_error_chain is None:
        continue_on_error_chain = [False] * len(skill_chain)

    # Initialize task
    selected_skill = skill_chain[0] if skill_chain else "research"
    task = _init_task_state(task_id, query, selected_skill, skill_chain, source)

    task_path = tasks_dir / f"{task_id}.json"

    # Mark as running
    task["status"] = "running"
    task["started_at"] = _now_iso()
    _atomic_write_json(task_path, task)

    # Execute steps
    stopped_early = False
    for i, (skill, step_fn, continue_on_error) in enumerate(
        zip(skill_chain, step_fns, continue_on_error_chain)
    ):
        task = _execute_single_step(task, i, skill, step_fn, continue_on_error)
        _atomic_write_json(task_path, task)

        # Check for errors
        last_result = task["step_results"][-1] if task["step_results"] else None
        if last_result and last_result.get("status") == "error":
            if not continue_on_error:
                stopped_early = True
                break

    # Finalize task
    task["finished_at"] = _now_iso()

    if stopped_early:
        task["status"] = "failed"
    elif any(r.get("status") == "error" for r in task["step_results"]):
        # Has errors but continued - mark as "partial"
        task["status"] = "partial"
    else:
        task["status"] = "completed"

    _atomic_write_json(task_path, task)

    return task


def choose_skill(query: str):
    if "比較" in query or "決め" in query:
        return "decision", "decision_keyword_match"
    return "research", "fallback_research"
