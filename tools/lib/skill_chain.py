from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Tuple


SkillRunner = Callable[[str, Any], Dict[str, Any]]


def default_chain_for_skill(selected_skill: str) -> List[str]:
    skill = str(selected_skill or "").strip().lower()
    if skill in {"decision", "execution"}:
        return ["execution", "critique"]
    if skill == "research":
        return ["research", "decision", "execution", "critique"]
    if skill == "improve":
        return ["improve", "critique"]
    return ["decision"]


def _next_skill_from_critique(result: Dict[str, Any]) -> str | None:
    payload = result.get("result") if isinstance(result, dict) else None
    if not isinstance(payload, dict):
        return None
    nxt = payload.get("next_action")
    if nxt in {"improve", "deploy", "monitor", "stop"}:
        return str(nxt)
    return None


def run_chain(
    selected_skills: Iterable[str],
    *,
    query: str,
    run_skill: SkillRunner,
    max_dynamic_steps: int = 2,
) -> List[Dict[str, Any]]:
    chain_results: List[Dict[str, Any]] = []
    current_input: Any = query
    queue: List[str] = [str(x) for x in selected_skills if str(x).strip()]
    dynamic_steps = 0

    while queue:
        skill = queue.pop(0)
        out = run_skill(skill, current_input)
        if not isinstance(out, dict):
            out = {"ok": False, "skill": str(skill), "error": "skill output must be dict", "result": out}
        out.setdefault("skill", str(skill))
        chain_results.append(out)
        current_input = out

        if str(skill) == "critique":
            nxt = _next_skill_from_critique(out)
            if nxt == "improve" and dynamic_steps < max_dynamic_steps:
                queue = ["improve", "critique"] + queue
                dynamic_steps += 1
            elif nxt in {"deploy", "monitor", "stop"}:
                break

    return chain_results


def summarize_chain_results(chain_results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items = list(chain_results)
    if not items:
        return {"ok": False, "final_skill": None, "count": 0, "next_action": None}

    final_item = items[-1]
    ok = all(bool(x.get("ok", True)) for x in items if isinstance(x, dict))
    final_result = final_item.get("result") if isinstance(final_item, dict) else None
    next_action = final_result.get("next_action") if isinstance(final_result, dict) else None

    return {
        "ok": ok,
        "count": len(items),
        "final_skill": final_item.get("skill"),
        "final_result": final_item,
        "next_action": next_action,
    }
