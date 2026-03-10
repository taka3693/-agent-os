from __future__ import annotations

from typing import Any, Dict

from .classify import detect_route_candidates
from .constants import (
    ROUTER_CATEGORY_ORDER,
    ROUTER_FALLBACK_ORDER,
    ROUTER_MAX_CHAIN,
    ROUTE_REASON_LITERALS,
)
from .pipeline import build_pipeline
from .planning import attach_autonomous_plan


def build_route_result(text: str) -> Dict[str, Any]:
    selected = detect_route_candidates(text)
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

    routed = build_pipeline(base)
    planned = attach_autonomous_plan(routed, text)
    return planned
