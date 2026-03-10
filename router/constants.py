from __future__ import annotations

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
