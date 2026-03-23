import json
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


def _latest_task() -> Optional[Dict[str, Any]]:
    d = STATE_DIR / "tasks"
    for p in _iter_json_files(d):
        obj = _load_json(p)
        if not obj:
            continue
        if any(k in obj for k in ("task_id", "status", "selected_skill")):
            obj["_source_file"] = str(p.relative_to(ROOT))
            return obj
    return None


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


def load_state_summary() -> Dict[str, Any]:
    task = _latest_task()

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
        "sources": {
            "task": task.get("_source_file") if task else None,
        },
    }


if __name__ == "__main__":
    print(json.dumps(load_state_summary(), ensure_ascii=False, indent=2))
