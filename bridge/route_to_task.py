from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

try:
    from router.result import build_route_result as SHARED_build_route_result
except Exception:
    SHARED_build_route_result = None

try:
    from router.planning import (
        make_plan_outline as SHARED_make_plan_outline,
        attach_autonomous_plan as SHARED_attach_autonomous_plan,
    )
except Exception:
    SHARED_make_plan_outline = None
    SHARED_attach_autonomous_plan = None

try:
    from router.pipeline import (
        normalize_selected_skills as SHARED_normalize_selected_skills,
        build_pipeline as SHARED_build_pipeline,
    )
except Exception:
    SHARED_normalize_selected_skills = None
    SHARED_build_pipeline = None

try:
    from router.classify import (
        safe_text as SHARED_safe_text,
        contains_any as SHARED_contains_any,
        is_decision_text as SHARED_is_decision_text,
        is_critique_text as SHARED_is_critique_text,
        is_experiment_text as SHARED_is_experiment_text,
        is_execution_text as SHARED_is_execution_text,
        is_retrospective_text as SHARED_is_retrospective_text,
        detect_route_candidates as SHARED_detect_route_candidates,
    )
except Exception:
    SHARED_safe_text = None
    SHARED_contains_any = None
    SHARED_is_decision_text = None
    SHARED_is_critique_text = None
    SHARED_is_experiment_text = None
    SHARED_is_execution_text = None
    SHARED_is_retrospective_text = None
    SHARED_detect_route_candidates = None

try:
    from router.constants import (
        ROUTER_CATEGORY_ORDER as SHARED_ROUTER_CATEGORY_ORDER,
        ROUTER_FALLBACK_ORDER as SHARED_ROUTER_FALLBACK_ORDER,
        ROUTER_MAX_CHAIN as SHARED_ROUTER_MAX_CHAIN,
        ROUTE_REASON_LITERALS as SHARED_ROUTE_REASON_LITERALS,
    )
except Exception:
    SHARED_ROUTER_CATEGORY_ORDER = None
    SHARED_ROUTER_FALLBACK_ORDER = None
    SHARED_ROUTER_MAX_CHAIN = None
    SHARED_ROUTE_REASON_LITERALS = None


# Keywords imported from single source of truth
from router.classify import (
    DECISION_KEYWORDS,
    CRITIQUE_KEYWORDS,
    EXPERIMENT_KEYWORDS,
    EXECUTION_KEYWORDS,
    RETROSPECTIVE_KEYWORDS,
)

ROUTER_CATEGORY_ORDER = [
    "critique",
    "decision",
    "experiment",
    "execution",
    "research",
    "retrospective",
]

ROUTER_FALLBACK_ORDER = [
    "decision",
    "critique",
    "research",
    "execution",
]

ROUTER_MAX_CHAIN = 3

ROUTE_REASON_LITERALS = {
    "critique": "critique_keyword_match",
    "decision": "decision_keyword_match",
    "experiment": "experiment_keyword_match",
    "execution": "execution_keyword_match",
    "retrospective": "retrospective_keyword_match",
    "research": "fallback_research",
}

if isinstance(SHARED_ROUTER_CATEGORY_ORDER, (list, tuple)) and SHARED_ROUTER_CATEGORY_ORDER:
    ROUTER_CATEGORY_ORDER = list(SHARED_ROUTER_CATEGORY_ORDER)

if isinstance(SHARED_ROUTER_FALLBACK_ORDER, (list, tuple)) and SHARED_ROUTER_FALLBACK_ORDER:
    ROUTER_FALLBACK_ORDER = list(SHARED_ROUTER_FALLBACK_ORDER)

if isinstance(SHARED_ROUTER_MAX_CHAIN, int) and SHARED_ROUTER_MAX_CHAIN > 0:
    ROUTER_MAX_CHAIN = SHARED_ROUTER_MAX_CHAIN

if isinstance(SHARED_ROUTE_REASON_LITERALS, dict) and SHARED_ROUTE_REASON_LITERALS:
    ROUTE_REASON_LITERALS = dict(SHARED_ROUTE_REASON_LITERALS)


def _safe_text(text: Any) -> str:
    return "" if text is None else str(text)


def _contains_any(text_lower: str, keywords: List[str]) -> bool:
    return any(str(k).lower() in text_lower for k in keywords)


def _step79_is_decision_text(text: str) -> bool:
    return _contains_any(_safe_text(text).lower(), DECISION_KEYWORDS)


def _step80_is_critique_text(text: str) -> bool:
    return _contains_any(_safe_text(text).lower(), CRITIQUE_KEYWORDS)


def _step81_is_experiment_text(text: str) -> bool:
    return _contains_any(_safe_text(text).lower(), EXPERIMENT_KEYWORDS)


def _step82_is_execution_text(text: str) -> bool:
    return _contains_any(_safe_text(text).lower(), EXECUTION_KEYWORDS)


def _step83_is_retrospective_text(text: str) -> bool:
    return _contains_any(_safe_text(text).lower(), RETROSPECTIVE_KEYWORDS)


def _step84_detect_route_candidates(text: str) -> List[str]:
    if callable(SHARED_detect_route_candidates):
        return SHARED_detect_route_candidates(text)

    text_lower = _safe_text(text).lower()
    candidates: List[str] = []

    checks = [
        ("critique", _step80_is_critique_text),
        ("decision", _step79_is_decision_text),
        ("experiment", _step81_is_experiment_text),
        ("execution", _step82_is_execution_text),
        ("retrospective", _step83_is_retrospective_text),
    ]

    for skill, fn in checks:
        if fn(text_lower):
            candidates.append(skill)

    if not candidates:
        candidates.append("research")

    ordered: List[str] = []
    for skill in ROUTER_CATEGORY_ORDER:
        if skill in candidates and skill not in ordered:
            ordered.append(skill)

    for skill in candidates:
        if skill not in ordered:
            ordered.append(skill)

    return ordered[:ROUTER_MAX_CHAIN]


def _step85_normalize_selected_skills(value, primary=None, max_chain=None):
    if callable(SHARED_normalize_selected_skills):
        return SHARED_normalize_selected_skills(value, primary=primary, max_chain=max_chain)

    if max_chain is None:
        max_chain = ROUTER_MAX_CHAIN

    items = value if isinstance(value, list) else ([value] if value else [])
    if primary and primary not in items:
        items = [primary] + items

    ordered: List[str] = []
    for skill in items:
        if not skill:
            continue
        skill = str(skill).strip()
        if skill and skill not in ordered:
            ordered.append(skill)

    if not ordered:
        ordered = [primary or "research"]

    return ordered[:max_chain]


def _step85_build_pipeline(route_result: Dict[str, Any]) -> Dict[str, Any]:
    if callable(SHARED_build_pipeline):
        return SHARED_build_pipeline(route_result)

    if not isinstance(route_result, dict):
        route_result = {}

    primary = route_result.get("selected_skill") or "research"
    selected_skills = _step85_normalize_selected_skills(
        route_result.get("selected_skills"),
        primary=primary,
        max_chain=ROUTER_MAX_CHAIN,
    )

    primary = selected_skills[0] if selected_skills else "research"
    route_reason = route_result.get("route_reason") or ROUTE_REASON_LITERALS.get(
        primary, f"{primary}_keyword_match"
    )

    out = dict(route_result)
    out["selected_skill"] = primary
    out["selected_skills"] = selected_skills
    out["route_reason"] = route_reason
    out["pipeline"] = {
        "primary_skill": primary,
        "skill_chain": selected_skills,
        "chain_length": len(selected_skills),
        "max_chain": ROUTER_MAX_CHAIN,
    }
    return out


def _step86_make_plan_outline(text: str, selected_skills):
    if callable(SHARED_make_plan_outline):
        return SHARED_make_plan_outline(text, selected_skills)

    text = _safe_text(text).strip()
    skills = selected_skills if isinstance(selected_skills, list) and selected_skills else ["research"]

    steps = []
    for skill in skills:
        if skill == "research":
            steps.append({
                "skill": "research",
                "purpose": "入力内容の整理と情報抽出",
                "done_when": "要点・論点・不足情報が見える",
            })
        elif skill == "decision":
            steps.append({
                "skill": "decision",
                "purpose": "比較と優先順位づけ",
                "done_when": "採用候補と判断理由が明文化される",
            })
        elif skill == "critique":
            steps.append({
                "skill": "critique",
                "purpose": "弱点・前提漏れ・リスクの洗い出し",
                "done_when": "問題点と改善観点が列挙される",
            })
        elif skill == "experiment":
            steps.append({
                "skill": "experiment",
                "purpose": "仮説検証の最小実験化",
                "done_when": "仮説と検証手順が定義される",
            })
        elif skill == "execution":
            steps.append({
                "skill": "execution",
                "purpose": "実行手順への分解",
                "done_when": "着手可能な手順列になる",
            })
        elif skill == "retrospective":
            steps.append({
                "skill": "retrospective",
                "purpose": "結果の振り返りと改善抽出",
                "done_when": "次回アクションが明確になる",
            })
        else:
            steps.append({
                "skill": str(skill),
                "purpose": "未定義スキル",
                "done_when": "処理結果が返る",
            })

    goal = text if text else "入力要求を処理する"
    return {
        "goal": goal,
        "steps": steps,
        "step_count": len(steps),
        "mode": "autonomous_planning",
    }


def _step86_attach_autonomous_plan(route_result: Dict[str, Any], text: str) -> Dict[str, Any]:
    if callable(SHARED_attach_autonomous_plan):
        return SHARED_attach_autonomous_plan(route_result, text)

    if not isinstance(route_result, dict):
        route_result = {}

    selected_skills = route_result.get("selected_skills")
    if not isinstance(selected_skills, list) or not selected_skills:
        selected_skills = [route_result.get("selected_skill") or "research"]

    out = dict(route_result)
    out["plan"] = _step86_make_plan_outline(text, selected_skills)
    out["planning_mode"] = "autonomous"
    return out


def _step84_build_route_result(text: str) -> Dict[str, Any]:
    if callable(SHARED_build_route_result):
        return SHARED_build_route_result(text)

    selected = _step84_detect_route_candidates(text)
    primary = selected[0] if selected else "research"
    route_reason = ROUTE_REASON_LITERALS.get(primary, f"{primary}_keyword_match")

    base = {
        "selected_skill": primary,
        "selected_skills": selected,
        "route_reason": route_reason,
        "router_policy": {
            "category_order": list(ROUTER_CATEGORY_ORDER),
            "fallback_order": list(ROUTER_FALLBACK_ORDER),
            "max_chain": ROUTER_MAX_CHAIN,
        },
    }

    routed = _step85_build_pipeline(base)
    planned = _step86_attach_autonomous_plan(routed, text)
    return planned


def route_to_task(text: str, allowed_skills=None, **kwargs) -> Dict[str, Any]:
    route_obj = _step84_build_route_result(text)

    if not isinstance(allowed_skills, list) or not allowed_skills:
        return route_obj

    allowed = [str(x).strip() for x in allowed_skills if str(x).strip()]
    if not allowed:
        return route_obj

    selected = [x for x in route_obj.get("selected_skills", []) if x in allowed]
    if not selected:
        fallback = "research" if "research" in allowed else allowed[0]
        selected = [fallback]

    route_obj["selected_skill"] = selected[0]
    route_obj["selected_skills"] = selected[:ROUTER_MAX_CHAIN]
    route_obj["route_reason"] = ROUTE_REASON_LITERALS.get(
        route_obj["selected_skill"],
        f"{route_obj['selected_skill']}_keyword_match",
    )
    route_obj = _step85_build_pipeline(route_obj)
    route_obj = _step86_attach_autonomous_plan(route_obj, text)
    return route_obj


def route(text: str, allowed_skills=None, **kwargs) -> Dict[str, Any]:
    return route_to_task(text, allowed_skills=allowed_skills, **kwargs)


def _extract_text_from_argv(argv) -> str:
    if not argv:
        return ""

    args = list(argv[1:]) if len(argv) >= 1 else []

    while args and args[0] in {"router", "route"}:
        args = args[1:]

    for flag in ("--text", "--query", "-t", "-q"):
        if flag in args:
            i = args.index(flag)
            if i + 1 < len(args):
                return str(args[i + 1]).strip()

    if len(args) == 1:
        raw = str(args[0]).strip()
        if raw:
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    for key in ("text", "query", "message", "prompt", "request_text", "original_text"):
                        v = obj.get(key)
                        if isinstance(v, str) and v.strip():
                            return v.strip()
            except Exception:
                pass

    text = " ".join(str(x) for x in args).strip()
    if text:
        return text

    try:
        stdin_text = sys.stdin.read().strip()
        if stdin_text:
            try:
                obj = json.loads(stdin_text)
                if isinstance(obj, dict):
                    for key in ("text", "query", "message", "prompt", "request_text", "original_text"):
                        v = obj.get(key)
                        if isinstance(v, str) and v.strip():
                            return v.strip()
            except Exception:
                pass
            return stdin_text
    except Exception:
        pass

    return ""



def map_skill_to_action_type(selected_skill: str) -> str:
    mapping = {
        "execution": "plan",
        "experiment": "plan",
        "decision": "plan",
        "critique": "plan",
        "retrospective": "plan",
        "research": "plan",
    }
    return mapping.get(str(selected_skill or "").strip(), "plan")


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    text = _extract_text_from_argv(argv)

    try:
        result = route_to_task(text)
        # === CREATE TASK + ENQUEUE ===
        from pathlib import Path
        import json, time

        tasks_dir = Path.home() / 'agent-os' / 'state' / 'tasks'
        tasks_dir.mkdir(parents=True, exist_ok=True)

        task_id = f"task-{int(time.time()*1000)}"
        task_path = tasks_dir / f"{task_id}.json"

        task_data = {
            'id': task_id,
            'text': text,
            'route': result,
        }

        task_path.write_text(json.dumps(task_data, ensure_ascii=False, indent=2), encoding='utf-8')

        queue_path = tasks_dir.parent / 'execution_queue.jsonl'
        queue_entry = {
            'execution_id': task_id,
            'idempotency_key': task_id,
            'fingerprint': task_id,
            'action_type': map_skill_to_action_type(result.get('selected_skill', 'research')),
            'payload': {
                'task': text,
                'task_path': str(task_path),
            },
            'status': 'queued',
            'created_at': time.time(),
            'attempt': 0,
        }

        queue_entry.setdefault("execution_id", task_id)
        queue_entry.setdefault("idempotency_key", task_id)
        queue_entry.setdefault("fingerprint", task_id)
        queue_entry.setdefault("action_type", map_skill_to_action_type(result.get('selected_skill', 'research')))
        queue_entry.setdefault("payload", {})
        queue_entry["payload"].setdefault("task", text)
        queue_entry["payload"].setdefault("task_path", str(task_path))
        queue_entry.setdefault("status", "queued")
        queue_entry.setdefault("created_at", time.time())
        queue_entry.setdefault("attempt", 0)

        with open(queue_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(queue_entry, ensure_ascii=False) + '\n')

        result['task_id'] = task_id
        result['task_path'] = str(task_path)

        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


def choose_skill(text: str):
    """Return (skill, reason) tuple for the given text."""
    text_lower = _safe_text(text).lower()
    
    if _step79_is_decision_text(text):
        return ("decision", "decision_keyword_match")
    if _step80_is_critique_text(text):
        return ("critique", "critique_keyword_match")
    if _step81_is_experiment_text(text):
        return ("experiment", "experiment_keyword_match")
    if _step82_is_execution_text(text):
        return ("execution", "execution_keyword_match")
    if _step83_is_retrospective_text(text):
        return ("retrospective", "retrospective_keyword_match")
    
    # Default fallback
    return ("research", "keyword match")
