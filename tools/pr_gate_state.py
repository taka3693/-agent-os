import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _iter_json_files(path: Path) -> Iterable[Path]:
    if not path.exists() or not path.is_dir():
        return []
    return sorted(path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def _latest_task(change_context: str = "") -> Optional[Dict[str, Any]]:
    dirs = [
        STATE_DIR / "tasks",
        STATE_DIR / "router_tasks",
    ]
    files = []
    for d in dirs:
        files.extend(list(_iter_json_files(d)))
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    # 1. query match 優先
    ctx = (change_context or "").lower().strip()
    tokens = [t for t in re.split(r"[^a-zA-Z0-9_\-]+", ctx) if len(t) >= 3]

    best_obj = None
    best_score = 0

    if ctx:
        for p in files:
            obj = _load_json(p)
            if not obj:
                continue

            query = str(obj.get("query", "")).lower()
            change_context = str(obj.get("change_context", "")).lower()
            work_summary = str(obj.get("work_summary", "")).lower()
            branch = str(obj.get("branch", "")).lower()
            files_touched = " ".join(str(x).lower() for x in (obj.get("files_touched") or []))

            haystack = " ".join([
                query,
                change_context,
                work_summary,
                branch,
                files_touched,
                str(obj.get("task_id", "")).lower(),
                str(obj.get("selected_skill", "")).lower(),
                " ".join(str(x).lower() for x in (obj.get("selected_skills") or [])),
                str(obj.get("planning_mode", "")).lower(),
            ]).strip()

            if not haystack:
                continue

            score = 0
            if query and ctx in query:
                score = 100
            elif tokens:
                score = sum(1 for t in tokens if t in haystack)

            if score > best_score:
                best_score = score
                best_obj = obj.copy()
                best_obj["_source_file"] = str(p.relative_to(ROOT))

        if best_obj and best_score > 0:
            best_obj["_match_mode"] = "query_match"
            best_obj["_match_confidence"] = "high" if best_score >= 2 or best_score == 100 else "medium"
            return _normalize_task(best_obj)

    # 2. fallback: 最新
    for p in files:
        obj = _load_json(p)
        if not obj:
            continue
        if any(k in obj for k in ("task_id", "status", "selected_skill")):
            obj["_source_file"] = str(p.relative_to(ROOT))
            obj["_match_mode"] = "latest_fallback"
            obj["_match_confidence"] = "medium" if ctx else "low"
            return _normalize_task(obj)

    return None


def _normalize_task(task: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(task, dict):
        return task

    source = str(task.get("_source_file") or "")

    # router_tasks are lightweight; normalize them to state-summary shape
    if "state/router_tasks/" in source:
        if task.get("status") is None:
            task["status"] = "completed"
        if task.get("selected_skills") is None and task.get("selected_skill") is not None:
            task["selected_skills"] = [task.get("selected_skill")]
        if task.get("planning_mode") is None:
            task["planning_mode"] = "autonomous"
        pipeline = task.get("pipeline")
        if not isinstance(pipeline, dict):
            pipeline = {}
            task["pipeline"] = pipeline
        if pipeline.get("chain_length") is None:
            skills = task.get("selected_skills") or []
            pipeline["chain_length"] = len(skills) if isinstance(skills, list) and skills else 1

    return task


def _pick_task_id(task: Dict[str, Any]) -> Any:
    return (
        task.get("task_id")
        or task.get("id")
        or task.get("router_result", {}).get("task_id")
        or task.get("result", {}).get("task_id")
    )


def _pick_selected_skill(task: Dict[str, Any]) -> Any:
    return (
        task.get("selected_skill")
        or task.get("router_result", {}).get("selected_skill")
        or task.get("result", {}).get("selected_skill")
    )


def _pick_selected_skills(task: Dict[str, Any]) -> Any:
    return (
        task.get("selected_skills")
        or task.get("router_result", {}).get("selected_skills")
        or task.get("pipeline", {}).get("skill_chain")
    )


def load_state_summary(change_context: str = "") -> Dict[str, Any]:
    task = _latest_task(change_context)

    task_id = _pick_task_id(task) if task else None
    task_status = task.get("status") if task else None
    selected_skill = _pick_selected_skill(task) if task else None
    selected_skills = _pick_selected_skills(task) if task else None
    planning_mode = task.get("planning_mode") if task else None
    chain_length = task.get("pipeline", {}).get("chain_length") if task else None

    reasons = []
    if not task_id:
        reasons.append("missing_task_id")
    if task_status is None:
        reasons.append("missing_task_status")
    if selected_skill is None:
        reasons.append("missing_selected_skill")

    if selected_skills is not None and isinstance(selected_skills, list) and selected_skill:
        if selected_skill not in selected_skills:
            reasons.append("selected_skill_not_in_selected_skills")

    state_match = len(reasons) == 0

    return {
        "task_id": task_id,
        "task_status": task_status,
        "selected_skill": selected_skill,
        "selected_skills": selected_skills,
        "planning_mode": planning_mode,
        "chain_length": chain_length,
        "state_match": state_match,
        "reasons": reasons,
        "match_mode": task.get("_match_mode") if task else None,
        "match_confidence": task.get("_match_confidence") if task else None,
        "sources": {
            "task": task.get("_source_file") if task else None,
        },
    }


if __name__ == "__main__":
    print(json.dumps(load_state_summary(), ensure_ascii=False, indent=2))
