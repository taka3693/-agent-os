from __future__ import annotations

from typing import Any, Dict, List

from .constants import ROUTER_MAX_CHAIN, ROUTE_REASON_LITERALS


def normalize_selected_skills(value, primary=None, max_chain=None) -> List[str]:
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


def build_pipeline(route_result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(route_result, dict):
        route_result = {}

    primary = route_result.get("selected_skill") or "research"
    selected_skills = normalize_selected_skills(
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
