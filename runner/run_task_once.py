#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Callable

from skills.critique import critique_impl
from skills.experiment import experiment_impl
from skills.execution import execution_impl
from skills.retrospective import retrospective_impl

BASE_DIR = Path(__file__).resolve().parents[1]
TASKS_DIR = BASE_DIR / "state" / "tasks"

SKILL_MODULES = {
    "critique": critique_impl,
    "experiment": experiment_impl,
    "execution": execution_impl,
    "retrospective": retrospective_impl,
    "research": BASE_DIR / "skills" / "research" / "research_impl.py",
    "decision": BASE_DIR / "skills" / "decision" / "decision_impl.py",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_task_path(arg: str | None) -> Path:
    if arg:
        p = Path(arg)
        if not p.is_absolute():
            p = (BASE_DIR / p).resolve()
        if not p.exists():
            raise FileNotFoundError(f"task not found: {p}")
        return p

    candidates = []
    for q in sorted(TASKS_DIR.glob("task-*.json")):
        try:
            obj = read_json(q)
        except Exception:
            continue
        if obj.get("status") == "queued":
            candidates.append(q)

    if not candidates:
        raise FileNotFoundError("queued task not found")

    return candidates[0]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _step80_run_skill_module(skill_module, query, **kwargs):
    for fn_name in ("run", "execute", "critique", "experiment", "execution", "retrospective", "decide", "research"):
        fn = getattr(skill_module, fn_name, None)
        if callable(fn):
            return fn(query, **kwargs)
    raise RuntimeError(f"skill module has no supported entrypoint: {skill_module!r}")


def pick_callable(mod: Any, skill: str) -> Callable[[str], Any]:
    preferred = {
        "research": ("run_research", "execute", "research_impl", "main"),
        "decision": ("run_decision", "execute", "decision_impl", "main"),
    }.get(skill, ("execute", "run", "main"))

    for fn_name in preferred:
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            return fn

    for fn_name in ("execute", "run", "main"):
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            return fn

    raise RuntimeError(f"callable not found for skill: {skill}")


def normalize_query(task: Dict[str, Any]) -> str:
    dict_candidates = [
        task,
        task.get("input") if isinstance(task.get("input"), dict) else None,
        task.get("payload") if isinstance(task.get("payload"), dict) else None,
        task.get("router_result") if isinstance(task.get("router_result"), dict) else None,
        task.get("request") if isinstance(task.get("request"), dict) else None,
        task.get("params") if isinstance(task.get("params"), dict) else None,
    ]

    scalar_candidates = [
        task.get("query"),
        task.get("text"),
        task.get("message"),
        task.get("prompt"),
        task.get("request_text"),
        task.get("original_text"),
    ]

    for d in dict_candidates:
        if not isinstance(d, dict):
            continue
        for key in ("query", "text", "message", "prompt", "request_text", "original_text"):
            v = d.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()

    for v in scalar_candidates:
        if isinstance(v, str) and v.strip():
            return v.strip()

    raise RuntimeError("query not found in task")


def _step85_pick_selected_skill(task_obj, fallback=None):
    fallback = str(fallback).strip() if fallback else None

    selected_skill = None
    if isinstance(task_obj, dict):
        raw = task_obj.get("selected_skill")
        if isinstance(raw, str) and raw.strip():
            selected_skill = raw.strip()
        else:
            selected_skills = task_obj.get("selected_skills")
            if isinstance(selected_skills, list) and selected_skills:
                first = selected_skills[0]
                if isinstance(first, str) and first.strip():
                    selected_skill = first.strip()

        if not selected_skill:
            router_result = task_obj.get("router_result")
            if isinstance(router_result, dict):
                raw = router_result.get("selected_skill")
                if isinstance(raw, str) and raw.strip():
                    selected_skill = raw.strip()
                else:
                    selected_skills = router_result.get("selected_skills")
                    if isinstance(selected_skills, list) and selected_skills:
                        first = selected_skills[0]
                        if isinstance(first, str) and first.strip():
                            selected_skill = first.strip()

        if not selected_skill:
            raw = task_obj.get("skill")
            if isinstance(raw, str) and raw.strip():
                selected_skill = raw.strip()

    return selected_skill or fallback or "research"


def normalize_skill(task: Dict[str, Any]) -> str:
    return _step85_pick_selected_skill(task)


def _step85_pipeline_meta(task_obj, selected_skill):
    selected_skills = []

    if isinstance(task_obj, dict):
        for container in (
            task_obj,
            task_obj.get("router_result") if isinstance(task_obj.get("router_result"), dict) else None,
        ):
            if not isinstance(container, dict):
                continue
            raw = container.get("selected_skills")
            if isinstance(raw, list):
                for x in raw:
                    if isinstance(x, str) and x.strip() and x.strip() not in selected_skills:
                        selected_skills.append(x.strip())

    if not selected_skills:
        selected_skills = [selected_skill]

    return {
        "primary_skill": selected_skill,
        "skill_chain": selected_skills,
        "chain_length": len(selected_skills),
    }


def _step86_extract_plan(task_obj):
    if not isinstance(task_obj, dict):
        return {
            "goal": "",
            "steps": [],
            "step_count": 0,
            "mode": "autonomous_planning",
        }

    plan = task_obj.get("plan")
    if isinstance(plan, dict):
        return plan

    selected_skill = _step85_pick_selected_skill(task_obj)
    return {
        "goal": str(task_obj.get("query") or ""),
        "steps": [
            {
                "skill": selected_skill,
                "purpose": "single skill execution",
                "done_when": "result returned",
            }
        ],
        "step_count": 1,
        "mode": "autonomous_planning",
    }


def normalize_skill_output(skill: str, out: Any) -> Dict[str, Any]:
    if isinstance(out, dict):
        normalized = dict(out)
        normalized.setdefault("summary", str(out.get("summary", "")).strip())
        normalized.setdefault("skill", skill)
        return normalized
    return {"summary": str(out).strip(), "findings": [], "skill": skill}


def dispatch_skill(skill: str, query: str) -> Dict[str, Any]:
    skill_ref = SKILL_MODULES.get(skill)
    if skill_ref is None:
        raise RuntimeError(f"unsupported skill: {skill}")

    if isinstance(skill_ref, Path):
        if not skill_ref.exists():
            raise RuntimeError(f"skill module not found: {skill_ref}")
        mod = load_module(skill_ref, f"agent_os_skill_{skill}")
        fn = pick_callable(mod, skill)
        out = fn(query)
    else:
        out = _step80_run_skill_module(skill_ref, query)

    return normalize_skill_output(skill, out)


def run_research(query: str) -> Dict[str, Any]:
    return dispatch_skill("research", query)


def execute_task(task: Dict[str, Any]) -> Dict[str, Any]:
    selected_skill = normalize_skill(task)
    query = normalize_query(task)
    result = dispatch_skill(selected_skill, query)
    pipeline = _step85_pipeline_meta(task, selected_skill)
    plan = _step86_extract_plan(task)

    return {
        "selected_skill": selected_skill,
        "selected_skills": pipeline["skill_chain"],
        "pipeline": pipeline,
        "plan": plan,
        "planning_mode": "autonomous",
        "query": query,
        "result": result,
    }


def process_one(task_path: Path) -> Dict[str, Any]:
    task = read_json(task_path)
    task_id = task.get("task_id") or task_path.stem

    if task.get("status") not in (None, "queued", "failed"):
        return {
            "ok": False,
            "status": "skipped",
            "task_id": task_id,
            "task_path": str(task_path),
            "reason": f"task status is {task.get('status')}",
        }

    task["status"] = "running"
    task["started_at"] = now_iso()
    write_json(task_path, task)

    try:
        payload = execute_task(task)
        task["status"] = "completed"
        task["completed_at"] = now_iso()
        task["selected_skill"] = payload["selected_skill"]
        task["selected_skills"] = payload["selected_skills"]
        task["pipeline"] = payload["pipeline"]
        task["plan"] = payload["plan"]
        task["planning_mode"] = payload["planning_mode"]
        task["query"] = payload["query"]
        task["result"] = payload["result"]
        write_json(task_path, task)
        return {
            "ok": True,
            "status": "completed",
            "task_id": task_id,
            "task_path": str(task_path),
            "selected_skill": payload["selected_skill"],
            "selected_skills": payload["selected_skills"],
            "planning_mode": payload["planning_mode"],
        }
    except Exception as e:
        task["status"] = "failed"
        task["failed_at"] = now_iso()
        task["error"] = f"{type(e).__name__}: {e}"
        task["traceback"] = traceback.format_exc()
        write_json(task_path, task)
        return {
            "ok": False,
            "status": "failed",
            "task_id": task_id,
            "task_path": str(task_path),
            "error": task["error"],
        }


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) >= 2 else None
    try:
        task_path = find_task_path(arg)
        out = process_one(task_path)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("ok") else 1
    except Exception as e:
        out = {
            "ok": False,
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
