#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Callable, List

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from policy.light_check_policy import evaluate_light_check, record_light_check
from skills.critique import critique_impl
from skills.experiment import experiment_impl
from skills.execution import execution_impl
from skills.retrospective import retrospective_impl

TASKS_DIR = BASE_DIR / "state" / "tasks"
ROUTE_RUNNER = BASE_DIR / "runner" / "run_route_task.py"

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


def resolve_light_check_route(task: Dict[str, Any]) -> str | None:
    answer = task.get("light_check_answer")
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    return None


def infer_route_target(query: str) -> str | None:
    q = (query or "").strip().lower()
    if "scrapling-official" in q:
        return "scrapling"
    if "scrapling" in q:
        return "scrapling"
    return None


def build_route_context(query: str, chosen_route: str | None = None) -> Dict[str, Any]:
    target = infer_route_target(query)
    return {
        "target": target,
        "chosen_route": chosen_route,
        "route_family": "install_path" if chosen_route else None,
    }


def _extract_recent_actions(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    recent_actions: List[Dict[str, Any]] = []
    raw = task.get("recent_actions")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                recent_actions.append(item)
    return recent_actions


def _extract_completed_topic_keys(task: Dict[str, Any]) -> List[str]:
    topic_keys: List[str] = []
    raw = task.get("completed_light_checks")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip() and item.strip() not in topic_keys:
                topic_keys.append(item.strip())
    return topic_keys


def _apply_light_check(task: Dict[str, Any], query: str) -> Dict[str, Any]:
    return evaluate_light_check(
        text=query,
        recent_actions=_extract_recent_actions(task),
        task_id=str(task.get("task_id") or ""),
        completed_topic_keys=_extract_completed_topic_keys(task),
    )


def mark_light_check_completed(task: Dict[str, Any], topic_key: str) -> Dict[str, Any]:
    task = dict(task)
    completed = _extract_completed_topic_keys(task)
    normalized = (topic_key or "").strip()
    if normalized and normalized not in completed:
        completed.append(normalized)
    task["completed_light_checks"] = completed
    return task


def apply_light_check_answer(task: Dict[str, Any], answer: str) -> Dict[str, Any]:
    task = dict(task)
    light_check = task.get("light_check") if isinstance(task.get("light_check"), dict) else {}
    topic_key = str(light_check.get("topic_key") or "").strip()
    if not topic_key:
        return task

    task = mark_light_check_completed(task, topic_key)
    task["light_check_answer"] = (answer or "").strip() or None
    task["light_check_resolved_at"] = now_iso()
    if task.get("status") == "awaiting_check":
        task["status"] = "queued"
    return task


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


def _apply_route_metadata(
    result: Dict[str, Any],
    route_context: Dict[str, Any],
    chosen_route: str | None = None,
    dispatch_mode: str = "route-aware",
) -> Dict[str, Any]:
    enriched = dict(result)

    if chosen_route:
        enriched.setdefault("execution_route", chosen_route)

    if route_context.get("target"):
        enriched.setdefault("route_target", route_context["target"])

    if chosen_route and route_context.get("target") == "scrapling":
        enriched.setdefault(
            "route_decision",
            {
                "target": "scrapling",
                "chosen_route": chosen_route,
                "dispatch_mode": dispatch_mode,
            },
        )

    return enriched


def _handle_direct_install(result: Dict[str, Any], route_context: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(result)
    target = route_context.get("target") or "target"
    enriched["summary"] = f"{target} を直接導入する方針"
    enriched.setdefault("next_inputs", [])
    enriched.setdefault("route_next_action", f"direct install path for {target}")
    return enriched


def _handle_clawhub_skill(result: Dict[str, Any], route_context: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(result)
    target = route_context.get("target") or "target"
    enriched["summary"] = f"{target} を ClawHub 経由で導入する方針"
    enriched.setdefault("next_inputs", [])
    enriched.setdefault("route_next_action", f"clawhub install path for {target}")
    return enriched


def dispatch_route_handler(skill: str, query: str, chosen_route: str, route_context: Dict[str, Any]) -> Dict[str, Any]:
    result = dispatch_skill(skill, query)
    result = dict(result)

    handler_name = None
    if route_context.get("target") == "scrapling":
        if chosen_route == "direct_install":
            handler_name = "handle_direct_install"
            result = _handle_direct_install(result, route_context)
        elif chosen_route == "clawhub_skill":
            handler_name = "handle_clawhub_skill"
            result = _handle_clawhub_skill(result, route_context)

    if handler_name:
        result.setdefault("route_handler", handler_name)
        result.setdefault("route_family", "install_path")
        return _apply_route_metadata(
            result,
            route_context=route_context,
            chosen_route=chosen_route,
            dispatch_mode="route-specific",
        )

    return _apply_route_metadata(
        result,
        route_context=route_context,
        chosen_route=chosen_route,
        dispatch_mode="route-aware",
    )


def dispatch_with_route(skill: str, query: str, chosen_route: str | None = None) -> Dict[str, Any]:
    route_context = build_route_context(query, chosen_route)
    if chosen_route:
        return dispatch_route_handler(skill, query, chosen_route, route_context)

    result = dispatch_skill(skill, query)
    return _apply_route_metadata(result, route_context=route_context, chosen_route=chosen_route)


def run_research(query: str) -> Dict[str, Any]:
    return dispatch_skill("research", query)


def execute_route_next_action(task: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    action = result.get("route_next_action") if isinstance(result, dict) else None
    if not isinstance(action, str) or not action.strip():
        return {}

    chosen_route = task.get("chosen_route") or result.get("execution_route")
    route_target = result.get("route_target")
    handler = result.get("route_handler")

    return {
        "status": "planned",
        "action": action,
        "handler": handler,
        "chosen_route": chosen_route,
        "target": route_target,
    }


def execute_task(task: Dict[str, Any]) -> Dict[str, Any]:
    selected_skill = normalize_skill(task)
    query = normalize_query(task)
    chosen_route = resolve_light_check_route(task)
    light_check = _apply_light_check(task, query)
    pipeline = _step85_pipeline_meta(task, selected_skill)
    plan = _step86_extract_plan(task)
    route_context = build_route_context(query, chosen_route)

    if light_check.get("check_required"):
        return {
            "selected_skill": selected_skill,
            "selected_skills": pipeline["skill_chain"],
            "pipeline": pipeline,
            "plan": plan,
            "route_context": route_context,
            "planning_mode": "autonomous",
            "query": query,
            "chosen_route": chosen_route,
            "light_check": light_check,
            "result": {
                "summary": "light check required before execution",
                "skill": "light_check",
                "findings": [],
            },
        }

    result = dispatch_with_route(selected_skill, query, chosen_route)

    return {
        "selected_skill": selected_skill,
        "selected_skills": pipeline["skill_chain"],
        "pipeline": pipeline,
        "plan": plan,
        "route_context": route_context,
        "planning_mode": "autonomous",
        "query": query,
        "chosen_route": chosen_route,
        "light_check": light_check,
        "result": result,
    }


def is_safe_route_autorun(task: Dict[str, Any]) -> bool:
    route_execution = task.get("route_execution")
    if not isinstance(route_execution, dict):
        return False
    if route_execution.get("status") != "planned":
        return False
    if task.get("route_family") != "install_path":
        return False
    if task.get("route_context", {}).get("target") != "scrapling":
        return False
    if task.get("route_handler") not in {"handle_direct_install", "handle_clawhub_skill"}:
        return False
    return True


def maybe_autorun_route_task(task_path: Path, task: Dict[str, Any]) -> Dict[str, Any] | None:
    forced = os.environ.get("AGENTOS_AUTORUN_ROUTE_TASK") == "1"
    allowed_by_default = is_safe_route_autorun(task)
    if not forced and not allowed_by_default:
        return None

    route_execution = task.get("route_execution")
    if not isinstance(route_execution, dict):
        return None
    if route_execution.get("status") != "planned":
        return None
    if not ROUTE_RUNNER.exists():
        return None

    cp = subprocess.run(
        [sys.executable, str(ROUTE_RUNNER), str(task_path)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"route runner failed: {cp.stderr or cp.stdout}")
    result = json.loads(cp.stdout)
    if isinstance(result, dict):
        result.setdefault("route_autorun_policy", "forced_env" if forced else "allowed_safe_default")
    return result


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
        task["route_context"] = payload.get("route_context")
        task["planning_mode"] = payload["planning_mode"]
        task["query"] = payload["query"]
        task["chosen_route"] = payload.get("chosen_route")
        task["light_check"] = payload.get("light_check")
        task["result"] = payload["result"]
        if isinstance(payload.get("result"), dict):
            task["route_handler"] = payload["result"].get("route_handler")
            task["route_family"] = payload["result"].get("route_family")
            task["route_next_action"] = payload["result"].get("route_next_action")
            route_execution = execute_route_next_action(task, payload["result"])
            if route_execution:
                task["route_execution"] = route_execution

        light_check = payload.get("light_check") or {}
        if light_check.get("suppressed"):
            record_light_check(light_check, suppressed=True)

        if light_check.get("check_required"):
            record_light_check(light_check, suppressed=False)
            task["status"] = "awaiting_check"
            write_json(task_path, task)
            return {
                "ok": False,
                "status": "awaiting_check",
                "task_id": task_id,
                "task_path": str(task_path),
                "selected_skill": payload["selected_skill"],
                "light_check": light_check,
            }

        write_json(task_path, task)
        route_autorun = maybe_autorun_route_task(task_path, task)
        if route_autorun is not None:
            task = read_json(task_path)

        return {
            "ok": True,
            "status": "completed",
            "task_id": task_id,
            "task_path": str(task_path),
            "selected_skill": payload["selected_skill"],
            "selected_skills": payload["selected_skills"],
            "planning_mode": payload["planning_mode"],
            "route_autorun": route_autorun,
            "route_execution": task.get("route_execution"),
            "route_result": task.get("route_result"),
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
